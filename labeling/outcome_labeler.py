"""
Outcome labeler for creating ML training data
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List
from loguru import logger

from database.db_manager import DatabaseManager
from data_pipeline.pumpfun_api import PumpFunAPI


class OutcomeLabeler:
    """Labels alerts with future outcomes for ML training"""

    def __init__(self, db_manager: DatabaseManager, api_client: PumpFunAPI, config: Dict[str, Any]):
        """
        Initialize outcome labeler

        Args:
            db_manager: Database manager
            api_client: Pump.fun API client
            config: Configuration dict
        """
        self.db = db_manager
        self.api = api_client
        self.config = config.get('labeling', {})

    def label_unlabeled_alerts(self, min_age_minutes: int = 60):
        """
        Label all unlabeled alerts that are old enough

        Args:
            min_age_minutes: Minimum age before labeling (default 60 min)
        """
        alerts = self.db.get_unlabeled_alerts(limit=1000)
        cutoff_time = datetime.utcnow() - timedelta(minutes=min_age_minutes)

        eligible_alerts = [a for a in alerts if a.alert_timestamp <= cutoff_time]

        if not eligible_alerts:
            logger.info("No alerts ready for labeling")
            return

        logger.info(f"Labeling {len(eligible_alerts)} alerts...")

        for i, alert in enumerate(eligible_alerts):
            try:
                self.label_alert(alert.alert_id)

                if (i + 1) % 10 == 0:
                    logger.info(f"Labeled {i + 1}/{len(eligible_alerts)} alerts")

            except Exception as e:
                logger.error(f"Failed to label alert {alert.alert_id}: {e}")

        logger.info(f"Labeling complete!")

    def label_alert(self, alert_id: int) -> bool:
        """
        Label a single alert with future outcomes

        Args:
            alert_id: Alert ID to label

        Returns:
            True if successful
        """
        # Get alert from database
        with self.db.get_session() as session:
            from database.models import MotionAlert
            alert = session.query(MotionAlert).filter_by(alert_id=alert_id).first()

            if not alert or alert.labeled:
                return False

            mint_address = alert.mint_address
            alert_time = alert.alert_timestamp
            price_at_alert = alert.price_at_alert

        # Get future intervals from config
        intervals = self.config.get('future_intervals', [1, 5, 15, 30, 60])

        # Collect future prices
        future_prices = {}
        max_price = price_at_alert

        for interval in intervals:
            future_time = alert_time + timedelta(minutes=interval)
            price = self._get_price_at_time(mint_address, future_time)

            if price is not None:
                future_prices[f'price_{interval}m_later'] = price
                max_price = max(max_price, price)

        # Calculate labels based on thresholds
        thresholds = self.config.get('pump_thresholds', {
            'small': 0.10,
            'medium': 0.25,
            'large': 0.50
        })

        outcomes = {
            **future_prices,
            'max_price_1h': max_price,
        }

        # Boolean labels
        if 'price_5m_later' in future_prices and price_at_alert > 0:
            gain_5m = (future_prices['price_5m_later'] - price_at_alert) / price_at_alert
            outcomes['pumped_10pct_5m'] = gain_5m >= thresholds['small']

        if 'price_15m_later' in future_prices and price_at_alert > 0:
            gain_15m = (future_prices['price_15m_later'] - price_at_alert) / price_at_alert
            outcomes['pumped_25pct_15m'] = gain_15m >= thresholds['medium']

        if 'price_30m_later' in future_prices and price_at_alert > 0:
            gain_30m = (future_prices['price_30m_later'] - price_at_alert) / price_at_alert
            outcomes['pumped_50pct_30m'] = gain_30m >= thresholds['large']

        # Time to peak
        if max_price > price_at_alert:
            time_to_peak = self._find_time_to_peak(mint_address, alert_time, max_price)
            if time_to_peak:
                outcomes['time_to_peak_minutes'] = int(time_to_peak.total_seconds() / 60)

        # Check if graduated
        token = self.db.get_token(mint_address)
        if token:
            latest_snapshot = self.db.get_latest_snapshot(mint_address)
            if latest_snapshot:
                outcomes['graduated'] = latest_snapshot.graduated

        # Update database
        success = self.db.update_alert_outcomes(alert_id, outcomes)

        if success:
            logger.debug(f"Labeled alert {alert_id} - Max gain: {(max_price/price_at_alert - 1)*100:.1f}%")

        return success

    def _get_price_at_time(self, mint_address: str, target_time: datetime) -> float:
        """
        Get price at or near a specific time

        Args:
            mint_address: Token address
            target_time: Target timestamp

        Returns:
            Price in SOL, or None if not found
        """
        # Try to get snapshot from database first
        snapshot = self.db.get_snapshot_at_time(mint_address, target_time)

        if snapshot and snapshot.price_sol:
            return snapshot.price_sol

        # Fallback: Get current price from API if target time is recent
        time_diff = datetime.utcnow() - target_time
        if time_diff.total_seconds() < 300:  # Within 5 minutes
            coin_data = self.api.get_coin_data(mint_address)
            if coin_data:
                # Calculate price from market cap and supply
                market_cap = coin_data.get('usd_market_cap', 0)
                supply = coin_data.get('total_supply', 1)
                if supply > 0:
                    # Approximate SOL price (would need SOL/USD rate)
                    return market_cap / supply / 100  # Rough approximation

        return None

    def _find_time_to_peak(self, mint_address: str, start_time: datetime, peak_price: float) -> timedelta:
        """
        Find how long it took to reach peak price

        Args:
            mint_address: Token address
            start_time: Alert timestamp
            peak_price: Peak price reached

        Returns:
            Time delta to peak, or None
        """
        # Query snapshots between start and peak
        end_time = start_time + timedelta(hours=1)

        with self.db.get_session() as session:
            from database.models import TokenSnapshot

            snapshots = session.query(TokenSnapshot).filter(
                TokenSnapshot.mint_address == mint_address,
                TokenSnapshot.timestamp >= start_time,
                TokenSnapshot.timestamp <= end_time,
                TokenSnapshot.price_sol >= peak_price * 0.99  # Within 1% of peak
            ).order_by(TokenSnapshot.timestamp).first()

            if snapshots:
                return snapshots.timestamp - start_time

        return None

    def get_labeling_stats(self) -> Dict[str, Any]:
        """
        Get statistics about labeled data

        Returns:
            Dict with labeling statistics
        """
        alerts = self.db.get_alerts_for_analysis(labeled_only=True)

        if not alerts:
            return {
                'total_labeled': 0,
                'pump_10pct_5m': 0,
                'pump_25pct_15m': 0,
                'pump_50pct_30m': 0,
                'avg_max_return': 0,
                'graduation_rate': 0
            }

        total = len(alerts)
        pump_10_5m = sum(1 for a in alerts if a.pumped_10pct_5m)
        pump_25_15m = sum(1 for a in alerts if a.pumped_25pct_15m)
        pump_50_30m = sum(1 for a in alerts if a.pumped_50pct_30m)

        # Calculate average max return
        valid_returns = [
            (a.max_price_1h / a.price_at_alert - 1) * 100
            for a in alerts
            if a.max_price_1h and a.price_at_alert > 0
        ]
        avg_max_return = sum(valid_returns) / len(valid_returns) if valid_returns else 0

        graduated = sum(1 for a in alerts if a.graduated)

        return {
            'total_labeled': total,
            'pump_10pct_5m': pump_10_5m,
            'pump_10pct_5m_rate': pump_10_5m / total * 100,
            'pump_25pct_15m': pump_25_15m,
            'pump_25pct_15m_rate': pump_25_15m / total * 100,
            'pump_50pct_30m': pump_50_30m,
            'pump_50pct_30m_rate': pump_50_30m / total * 100,
            'avg_max_return_pct': avg_max_return,
            'graduated': graduated,
            'graduation_rate': graduated / total * 100
        }
