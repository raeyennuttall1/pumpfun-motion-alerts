"""
Deep Neural Network model for motion alert prediction
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple


class MotionPredictorDNN(nn.Module):
    """
    Deep neural network for predicting token pump probability and expected returns
    """

    def __init__(
        self,
        input_dim: int = 50,
        hidden_dims: Tuple[int, ...] = (128, 64, 32),
        dropout: float = 0.3
    ):
        """
        Initialize the model

        Args:
            input_dim: Number of input features
            hidden_dims: Tuple of hidden layer dimensions
            dropout: Dropout rate
        """
        super(MotionPredictorDNN, self).__init__()

        self.input_dim = input_dim

        # Feature extraction layers
        layers = []
        prev_dim = input_dim

        for i, hidden_dim in enumerate(hidden_dims):
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.ReLU(),
                nn.BatchNorm1d(hidden_dim),
                nn.Dropout(dropout if i < len(hidden_dims) - 1 else dropout * 0.5)
            ])
            prev_dim = hidden_dim

        self.feature_net = nn.Sequential(*layers)

        # Output heads
        final_dim = hidden_dims[-1]

        # Classification head: Will it pump 25%+ in 15m?
        self.pump_classifier = nn.Sequential(
            nn.Linear(final_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1)
        )

        # Regression head: Expected max return in 30m
        self.return_regressor = nn.Sequential(
            nn.Linear(final_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1)
        )

        # Confidence head: Model confidence in prediction
        self.confidence_head = nn.Sequential(
            nn.Linear(final_dim, 16),
            nn.ReLU(),
            nn.Linear(16, 1)
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Forward pass

        Args:
            x: Input tensor of shape (batch_size, input_dim)

        Returns:
            Tuple of (pump_probability, expected_return, confidence)
        """
        # Extract features
        features = self.feature_net(x)

        # Output predictions
        pump_logits = self.pump_classifier(features)
        pump_prob = torch.sigmoid(pump_logits)

        expected_return = self.return_regressor(features)

        confidence_logits = self.confidence_head(features)
        confidence = torch.sigmoid(confidence_logits)

        return pump_prob.squeeze(-1), expected_return.squeeze(-1), confidence.squeeze(-1)

    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        """
        Get pump probability only

        Args:
            x: Input tensor

        Returns:
            Pump probability tensor
        """
        with torch.no_grad():
            pump_prob, _, _ = self.forward(x)
            return pump_prob

    def predict_return(self, x: torch.Tensor) -> torch.Tensor:
        """
        Get expected return only

        Args:
            x: Input tensor

        Returns:
            Expected return tensor
        """
        with torch.no_grad():
            _, expected_return, _ = self.forward(x)
            return expected_return


class MotionPredictorCNN(nn.Module):
    """
    Convolutional model for time-series transaction patterns
    More advanced - can process transaction sequences
    """

    def __init__(
        self,
        sequence_length: int = 100,
        feature_dim: int = 10,
        static_features: int = 20
    ):
        """
        Initialize CNN model

        Args:
            sequence_length: Length of transaction sequence
            feature_dim: Features per transaction
            static_features: Number of aggregated features
        """
        super(MotionPredictorCNN, self).__init__()

        # 1D CNN for transaction sequences
        self.conv1 = nn.Conv1d(feature_dim, 32, kernel_size=5, padding=2)
        self.conv2 = nn.Conv1d(32, 64, kernel_size=5, padding=2)
        self.conv3 = nn.Conv1d(64, 32, kernel_size=3, padding=1)

        self.pool = nn.MaxPool1d(2)
        self.dropout = nn.Dropout(0.3)

        # Calculate flattened size after convolutions
        # After 3 pools: sequence_length / 8
        conv_output_size = (sequence_length // 8) * 32

        # Static feature processing
        self.static_fc = nn.Sequential(
            nn.Linear(static_features, 32),
            nn.ReLU(),
            nn.Dropout(0.2)
        )

        # Combined processing
        combined_size = conv_output_size + 32

        self.fc = nn.Sequential(
            nn.Linear(combined_size, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 32),
            nn.ReLU()
        )

        # Output heads
        self.pump_classifier = nn.Linear(32, 1)
        self.return_regressor = nn.Linear(32, 1)

    def forward(
        self,
        sequence: torch.Tensor,
        static: torch.Tensor
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass

        Args:
            sequence: Transaction sequence (batch, feature_dim, sequence_length)
            static: Static features (batch, static_features)

        Returns:
            Tuple of (pump_probability, expected_return)
        """
        # Process sequence with CNN
        x = F.relu(self.conv1(sequence))
        x = self.pool(x)
        x = F.relu(self.conv2(x))
        x = self.pool(x)
        x = F.relu(self.conv3(x))
        x = self.pool(x)

        # Flatten
        x = x.view(x.size(0), -1)
        x = self.dropout(x)

        # Process static features
        static_features = self.static_fc(static)

        # Combine
        combined = torch.cat([x, static_features], dim=1)

        # Final layers
        features = self.fc(combined)

        pump_prob = torch.sigmoid(self.pump_classifier(features))
        expected_return = self.return_regressor(features)

        return pump_prob.squeeze(-1), expected_return.squeeze(-1)


def get_model(model_type: str = 'dnn', **kwargs) -> nn.Module:
    """
    Factory function to get model by type

    Args:
        model_type: 'dnn' or 'cnn'
        **kwargs: Model-specific parameters

    Returns:
        Model instance
    """
    if model_type == 'dnn':
        return MotionPredictorDNN(**kwargs)
    elif model_type == 'cnn':
        return MotionPredictorCNN(**kwargs)
    else:
        raise ValueError(f"Unknown model type: {model_type}")
