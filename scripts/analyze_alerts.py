"""
Script to analyze alert performance
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager
from analysis.hit_rate_analyzer import HitRateAnalyzer


def main():
    """Analyze and print hit rate statistics"""
    db = DatabaseManager()
    analyzer = HitRateAnalyzer(db)

    print("\n" + "="*60)
    print("MOTION ALERT HIT RATE ANALYSIS")
    print("="*60 + "\n")

    # Print detailed report
    report = analyzer.get_detailed_report()
    print(report)

    # Get top performers
    print("\n" + "="*60)
    print("TOP 10 PERFORMING ALERTS")
    print("="*60 + "\n")

    top_alerts = analyzer.get_top_performers(n=10)

    for i, alert in enumerate(top_alerts, 1):
        print(f"{i}. Alert #{alert['alert_id']}")
        print(f"   Token: {alert['mint_address'][:8]}...")
        print(f"   Entry: {alert['entry_price']:.8f} SOL")
        print(f"   Peak:  {alert['max_price']:.8f} SOL")
        print(f"   Return: +{alert['max_return_pct']:.1f}%")
        print(f"   Time to peak: {alert['time_to_peak_min']} min\n")

    # Export to CSV
    print("\nExporting data to CSV...")
    analyzer.export_to_csv()
    print("Done! Check data/alert_analysis.csv")


if __name__ == "__main__":
    main()
