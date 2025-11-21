"""
Script to train the ML model
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager
from ml.train import ModelTrainer


def main():
    """Train the motion prediction model"""
    print("\n" + "="*60)
    print("MOTION PREDICTION MODEL TRAINING")
    print("="*60 + "\n")

    db = DatabaseManager()

    # Check data availability
    stats = db.get_stats()
    print(f"Database statistics:")
    print(f"  Total alerts: {stats['total_alerts']}")
    print(f"  Labeled alerts: {stats['labeled_alerts']}")
    print()

    if stats['labeled_alerts'] < 50:
        print("⚠️  WARNING: Less than 50 labeled alerts available.")
        print("   Collect more data before training for better results.")
        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            print("Exiting...")
            return

    # Initialize trainer
    trainer = ModelTrainer(db)

    # Train model
    print("\nStarting training...")
    print("This may take several minutes...\n")

    history = trainer.train(
        epochs=50,
        batch_size=32,
        learning_rate=0.001,
        val_split=0.2
    )

    # Print final results
    print("\n" + "="*60)
    print("TRAINING COMPLETE")
    print("="*60)
    print(f"\nFinal validation accuracy: {history['val_accuracy'][-1]:.2f}%")
    print(f"Best validation loss: {min(history['val_loss']):.4f}")
    print(f"\nModel saved to: models/best_model.pt")


if __name__ == "__main__":
    main()
