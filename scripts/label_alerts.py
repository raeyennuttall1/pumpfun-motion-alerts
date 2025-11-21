"""
Script to manually label unlabeled alerts
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from database.db_manager import DatabaseManager
from data_pipeline.pumpfun_api import PumpFunAPI
from labeling.outcome_labeler import OutcomeLabeler


def main():
    """Label unlabeled alerts"""
    print("\n" + "="*60)
    print("OUTCOME LABELING")
    print("="*60 + "\n")

    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Initialize components
    db = DatabaseManager()
    api = PumpFunAPI()
    labeler = OutcomeLabeler(db, api, config)

    # Get unlabeled count
    unlabeled = db.get_unlabeled_alerts(limit=1000)
    print(f"Found {len(unlabeled)} unlabeled alerts\n")

    if len(unlabeled) == 0:
        print("No alerts to label!")
        return

    # Label alerts
    print("Starting labeling process...")
    print("(Only labeling alerts older than 60 minutes)\n")

    labeler.label_unlabeled_alerts(min_age_minutes=60)

    # Print stats
    print("\n" + "="*60)
    print("LABELING STATISTICS")
    print("="*60 + "\n")

    stats = labeler.get_labeling_stats()

    print(f"Total labeled: {stats['total_labeled']}")
    print(f"\nHit rates:")
    print(f"  10% in 5m:  {stats['pump_10pct_5m_rate']:.1f}%")
    print(f"  25% in 15m: {stats['pump_25pct_15m_rate']:.1f}%")
    print(f"  50% in 30m: {stats['pump_50pct_30m_rate']:.1f}%")
    print(f"\nAvg max return: {stats['avg_max_return_pct']:.1f}%")
    print(f"Graduation rate: {stats['graduation_rate']:.1f}%")


if __name__ == "__main__":
    main()
