"""
Training script for motion prediction model
"""
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split
import numpy as np
from typing import Dict, Any, List, Tuple
from loguru import logger
import json

from database.db_manager import DatabaseManager
from ml.model import MotionPredictorDNN


class AlertDataset(Dataset):
    """PyTorch dataset for motion alerts"""

    def __init__(self, alerts: List[Dict], feature_keys: List[str]):
        """
        Initialize dataset

        Args:
            alerts: List of alert dicts with features and labels
            feature_keys: List of feature names to use
        """
        self.alerts = alerts
        self.feature_keys = feature_keys

        # Extract features and labels
        self.features = []
        self.pump_labels = []
        self.return_labels = []

        for alert in alerts:
            # Extract features from trigger_features JSON
            features = alert.get('trigger_features', {})
            feature_vector = [features.get(key, 0) for key in feature_keys]

            self.features.append(feature_vector)
            self.pump_labels.append(1 if alert.get('pumped_25pct_15m', False) else 0)

            # Return label (normalized)
            max_return = 0
            if alert.get('max_price_1h') and alert.get('price_at_alert', 0) > 0:
                max_return = (alert['max_price_1h'] / alert['price_at_alert'] - 1) * 100

            self.return_labels.append(max_return)

        self.features = torch.FloatTensor(self.features)
        self.pump_labels = torch.FloatTensor(self.pump_labels)
        self.return_labels = torch.FloatTensor(self.return_labels)

    def __len__(self):
        return len(self.alerts)

    def __getitem__(self, idx):
        return self.features[idx], self.pump_labels[idx], self.return_labels[idx]


class ModelTrainer:
    """Handles model training and evaluation"""

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize trainer

        Args:
            db_manager: Database manager
        """
        self.db = db_manager
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"Using device: {self.device}")

    def prepare_dataset(self) -> Tuple[AlertDataset, List[str]]:
        """
        Prepare dataset from database

        Returns:
            Tuple of (dataset, feature_keys)
        """
        # Get labeled alerts
        alerts = self.db.get_alerts_for_analysis(labeled_only=True)

        if len(alerts) < 50:
            raise ValueError(f"Insufficient data for training: {len(alerts)} alerts")

        logger.info(f"Loaded {len(alerts)} labeled alerts")

        # Convert to dicts
        alert_dicts = []
        for alert in alerts:
            alert_dicts.append({
                'alert_id': alert.alert_id,
                'trigger_features': alert.trigger_features,
                'price_at_alert': alert.price_at_alert,
                'max_price_1h': alert.max_price_1h,
                'pumped_25pct_15m': alert.pumped_25pct_15m,
            })

        # Define feature keys to use
        # These should match what's in trigger_features
        feature_keys = [
            # Current state
            'current_market_cap',
            'current_price_sol',
            'bonding_curve_pct',

            # 3-minute window (primary)
            'txn_count_3m',
            'buy_count_3m',
            'sell_count_3m',
            'unique_buyers_3m',
            'unique_sellers_3m',
            'buy_volume_sol_3m',
            'sell_volume_sol_3m',
            'net_volume_sol_3m',
            'buy_sell_ratio_3m',
            'avg_buy_size_3m',
            'avg_sell_size_3m',
            'max_buy_size_3m',
            'buyer_seller_ratio_3m',

            # 5-minute window
            'buy_volume_sol_5m',
            'unique_buyers_5m',
            'buy_sell_ratio_5m',

            # Derived features
            'txn_velocity',
            'volume_momentum',

            # Wallet features
            'known_wallet_count',
            'total_unique_buyers',
            'known_wallet_percentage',

            # Time
            'time_since_launch_seconds',
        ]

        dataset = AlertDataset(alert_dicts, feature_keys)

        return dataset, feature_keys

    def train(
        self,
        epochs: int = 50,
        batch_size: int = 32,
        learning_rate: float = 0.001,
        val_split: float = 0.2
    ) -> Dict[str, Any]:
        """
        Train the model

        Args:
            epochs: Number of training epochs
            batch_size: Batch size
            learning_rate: Learning rate
            val_split: Validation split ratio

        Returns:
            Training history dict
        """
        # Prepare dataset
        dataset, feature_keys = self.prepare_dataset()

        # Split into train/val
        val_size = int(len(dataset) * val_split)
        train_size = len(dataset) - val_size

        train_dataset, val_dataset = random_split(
            dataset,
            [train_size, val_size],
            generator=torch.Generator().manual_seed(42)
        )

        train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=batch_size)

        logger.info(f"Training set: {train_size}, Validation set: {val_size}")

        # Initialize model
        model = MotionPredictorDNN(input_dim=len(feature_keys))
        model = model.to(self.device)

        # Loss functions
        classification_loss_fn = nn.BCELoss()
        regression_loss_fn = nn.MSELoss()

        # Optimizer
        optimizer = optim.Adam(model.parameters(), lr=learning_rate)
        scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)

        # Training history
        history = {
            'train_loss': [],
            'val_loss': [],
            'val_accuracy': [],
            'feature_keys': feature_keys
        }

        best_val_loss = float('inf')

        # Training loop
        for epoch in range(epochs):
            model.train()
            train_loss = 0.0

            for features, pump_labels, return_labels in train_loader:
                features = features.to(self.device)
                pump_labels = pump_labels.to(self.device)
                return_labels = return_labels.to(self.device)

                # Forward pass
                pump_pred, return_pred, confidence = model(features)

                # Calculate losses
                cls_loss = classification_loss_fn(pump_pred, pump_labels)
                reg_loss = regression_loss_fn(return_pred, return_labels)

                # Combined loss
                loss = cls_loss + 0.1 * reg_loss  # Weight regression less

                # Backward pass
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                train_loss += loss.item()

            # Validation
            model.eval()
            val_loss = 0.0
            correct = 0
            total = 0

            with torch.no_grad():
                for features, pump_labels, return_labels in val_loader:
                    features = features.to(self.device)
                    pump_labels = pump_labels.to(self.device)
                    return_labels = return_labels.to(self.device)

                    pump_pred, return_pred, confidence = model(features)

                    cls_loss = classification_loss_fn(pump_pred, pump_labels)
                    reg_loss = regression_loss_fn(return_pred, return_labels)
                    loss = cls_loss + 0.1 * reg_loss

                    val_loss += loss.item()

                    # Calculate accuracy
                    predicted = (pump_pred > 0.5).float()
                    correct += (predicted == pump_labels).sum().item()
                    total += pump_labels.size(0)

            # Average losses
            train_loss /= len(train_loader)
            val_loss /= len(val_loader)
            val_accuracy = correct / total * 100

            history['train_loss'].append(train_loss)
            history['val_loss'].append(val_loss)
            history['val_accuracy'].append(val_accuracy)

            # Learning rate scheduling
            scheduler.step(val_loss)

            # Log progress
            if (epoch + 1) % 5 == 0:
                logger.info(
                    f"Epoch {epoch+1}/{epochs} - "
                    f"Train Loss: {train_loss:.4f}, "
                    f"Val Loss: {val_loss:.4f}, "
                    f"Val Accuracy: {val_accuracy:.1f}%"
                )

            # Save best model
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                self.save_model(model, feature_keys, 'models/best_model.pt')

        logger.info(f"Training complete! Best val loss: {best_val_loss:.4f}")

        return history

    def save_model(self, model: nn.Module, feature_keys: List[str], path: str):
        """
        Save model and metadata

        Args:
            model: Trained model
            feature_keys: Feature names
            path: Save path
        """
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)

        torch.save({
            'model_state_dict': model.state_dict(),
            'feature_keys': feature_keys,
            'input_dim': model.input_dim,
        }, path)

        logger.info(f"Model saved to {path}")

    def load_model(self, path: str) -> Tuple[nn.Module, List[str]]:
        """
        Load saved model

        Args:
            path: Model path

        Returns:
            Tuple of (model, feature_keys)
        """
        checkpoint = torch.load(path, map_location=self.device)

        model = MotionPredictorDNN(input_dim=checkpoint['input_dim'])
        model.load_state_dict(checkpoint['model_state_dict'])
        model = model.to(self.device)
        model.eval()

        logger.info(f"Model loaded from {path}")

        return model, checkpoint['feature_keys']
