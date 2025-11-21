"""
Quick status viewer for tokens and motion alerts
"""
import sys
import os

# Fix Windows encoding for emoji display
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db_manager import DatabaseManager
from datetime import datetime, timedelta

def main():
    db = DatabaseManager()

    print("=" * 80)
    print("PUMP.FUN MOTION ALERT SYSTEM - STATUS")
    print("=" * 80)

    # Get overall stats
    stats = db.get_stats()
    print(f"\nSYSTEM STATS:")
    print(f"  Total Tokens Monitored: {stats['total_tokens']}")
    print(f"  Total Transactions: {stats['total_transactions']}")
    print(f"  Total Motion Alerts: {stats['total_alerts']}")
    print(f"  Labeled Alerts: {stats['labeled_alerts']}")
    print(f"  Known Profitable Wallets: {stats['known_wallets']}")

    # Get recent tokens (last 50)
    print(f"\nRECENT TOKENS (Last 50):")
    print("-" * 80)
    with db.get_session() as session:
        from database.models import TokenLaunch
        tokens = session.query(TokenLaunch).order_by(
            TokenLaunch.created_timestamp.desc()
        ).limit(50).all()

        if tokens:
            for i, token in enumerate(tokens, 1):
                time_str = token.created_timestamp.strftime("%H:%M:%S")
                print(f"{i:2}. {time_str} | {token.symbol:12} | {token.mint_address}")
        else:
            print("  No tokens yet")

    # Get motion alerts
    print(f"\nMOTION ALERTS:")
    print("-" * 80)
    with db.get_session() as session:
        from database.models import MotionAlert
        alerts = session.query(MotionAlert).order_by(
            MotionAlert.alert_timestamp.desc()
        ).limit(20).all()

        if alerts:
            for i, alert in enumerate(alerts, 1):
                time_str = alert.alert_timestamp.strftime("%H:%M:%S")
                token = alert.token
                mc = alert.market_cap_at_alert
                labeled = "[LABELED]" if alert.labeled else "[PENDING]"
                print(f"{i:2}. {time_str} | {token.symbol:12} | MC: ${mc:,.0f} | {labeled} | {token.mint_address}")
        else:
            print("  No motion alerts triggered yet")
            print("  NOTE: Alerts trigger when tokens meet criteria in config.yaml:")
            print("     - Minimum buy volume")
            print("     - Minimum unique buyers")
            print("     - Maximum market cap")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
