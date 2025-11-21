"""
Hit rate analysis for alert performance evaluation
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from loguru import logger

from database.db_manager import DatabaseManager


class HitRateAnalyzer:
    """Analyzes motion alert hit rates and performance"""

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize hit rate analyzer

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager

    def calculate_hit_rates(self, labeled_only: bool = True) -> Dict[str, Any]:
        """
        Calculate comprehensive hit rate statistics

        Args:
            labeled_only: Only analyze labeled alerts

        Returns:
            Dict with hit rate metrics
        """
        alerts = self.db.get_alerts_for_analysis(labeled_only=labeled_only)

        if not alerts:
            logger.warning("No alerts available for analysis")
            return self._empty_stats()

        # Convert to list of dicts for easier processing
        alert_data = []
        for alert in alerts:
            if alert.price_at_alert > 0:  # Valid price
                alert_data.append({
                    'alert_id': alert.alert_id,
                    'mint_address': alert.mint_address,
                    'alert_timestamp': alert.alert_timestamp,
                    'price_at_alert': alert.price_at_alert,
                    'market_cap_at_alert': alert.market_cap_at_alert,
                    'price_1m_later': alert.price_1m_later,
                    'price_5m_later': alert.price_5m_later,
                    'price_15m_later': alert.price_15m_later,
                    'price_30m_later': alert.price_30m_later,
                    'price_60m_later': alert.price_60m_later,
                    'max_price_1h': alert.max_price_1h,
                    'pumped_10pct_5m': alert.pumped_10pct_5m,
                    'pumped_25pct_15m': alert.pumped_25pct_15m,
                    'pumped_50pct_30m': alert.pumped_50pct_30m,
                    'graduated': alert.graduated,
                    'time_to_peak_minutes': alert.time_to_peak_minutes,
                })

        df = pd.DataFrame(alert_data)

        # Calculate returns
        df['return_1m'] = (df['price_1m_later'] / df['price_at_alert'] - 1) * 100
        df['return_5m'] = (df['price_5m_later'] / df['price_at_alert'] - 1) * 100
        df['return_15m'] = (df['price_15m_later'] / df['price_at_alert'] - 1) * 100
        df['return_30m'] = (df['price_30m_later'] / df['price_at_alert'] - 1) * 100
        df['return_60m'] = (df['price_60m_later'] / df['price_at_alert'] - 1) * 100
        df['max_return_1h'] = (df['max_price_1h'] / df['price_at_alert'] - 1) * 100

        # Calculate statistics
        stats = {
            'total_alerts': len(df),

            # Hit rates
            'hit_rate_10pct_5m': df['pumped_10pct_5m'].mean() * 100 if 'pumped_10pct_5m' in df else 0,
            'hit_rate_25pct_15m': df['pumped_25pct_15m'].mean() * 100 if 'pumped_25pct_15m' in df else 0,
            'hit_rate_50pct_30m': df['pumped_50pct_30m'].mean() * 100 if 'pumped_50pct_30m' in df else 0,

            # Average returns
            'avg_return_1m': df['return_1m'].mean(),
            'avg_return_5m': df['return_5m'].mean(),
            'avg_return_15m': df['return_15m'].mean(),
            'avg_return_30m': df['return_30m'].mean(),
            'avg_return_60m': df['return_60m'].mean(),
            'avg_max_return_1h': df['max_return_1h'].mean(),

            # Median returns
            'median_return_5m': df['return_5m'].median(),
            'median_return_15m': df['return_15m'].median(),
            'median_max_return_1h': df['max_return_1h'].median(),

            # Best/worst
            'best_return_1h': df['max_return_1h'].max(),
            'worst_return_15m': df['return_15m'].min(),

            # Risk metrics
            'positive_return_5m_pct': (df['return_5m'] > 0).mean() * 100,
            'positive_return_15m_pct': (df['return_15m'] > 0).mean() * 100,

            # Graduation
            'graduation_rate': df['graduated'].mean() * 100 if 'graduated' in df else 0,

            # Time to peak
            'avg_time_to_peak_min': df['time_to_peak_minutes'].mean() if 'time_to_peak_minutes' in df else 0,
        }

        return stats

    def _empty_stats(self) -> Dict[str, Any]:
        """Return empty statistics"""
        return {
            'total_alerts': 0,
            'hit_rate_10pct_5m': 0,
            'hit_rate_25pct_15m': 0,
            'hit_rate_50pct_30m': 0,
            'avg_max_return_1h': 0,
        }

    def get_detailed_report(self) -> str:
        """
        Generate detailed text report

        Returns:
            Formatted report string
        """
        stats = self.calculate_hit_rates()

        if stats['total_alerts'] == 0:
            return "No labeled alerts available for analysis."

        report = f"""
╔════════════════════════════════════════════════════╗
║         MOTION ALERT HIT RATE ANALYSIS             ║
╚════════════════════════════════════════════════════╝

📊 Dataset:
   Total Alerts Analyzed: {stats['total_alerts']}

🎯 Hit Rates (Success Criteria):
   10% gain in 5m:  {stats['hit_rate_10pct_5m']:.1f}%
   25% gain in 15m: {stats['hit_rate_25pct_15m']:.1f}%
   50% gain in 30m: {stats['hit_rate_50pct_30m']:.1f}%

📈 Average Returns:
   1 minute:  {stats['avg_return_1m']:+.1f}%
   5 minutes: {stats['avg_return_5m']:+.1f}%
   15 minutes: {stats['avg_return_15m']:+.1f}%
   30 minutes: {stats['avg_return_30m']:+.1f}%
   60 minutes: {stats['avg_return_60m']:+.1f}%

   Average Max (1h): {stats['avg_max_return_1h']:+.1f}%
   Median Max (1h):  {stats['median_max_return_1h']:+.1f}%

🏆 Best & Worst:
   Best 1h Return:  +{stats['best_return_1h']:.1f}%
   Worst 15m Return: {stats['worst_return_15m']:+.1f}%

✅ Positive Return Rate:
   After 5m:  {stats['positive_return_5m_pct']:.1f}%
   After 15m: {stats['positive_return_15m_pct']:.1f}%

🚀 Graduation Rate: {stats['graduation_rate']:.1f}%

⏱️  Avg Time to Peak: {stats['avg_time_to_peak_min']:.1f} minutes

        """

        return report.strip()

    def analyze_by_market_cap(self, bins: List[float] = [0, 10000, 50000, 100000]) -> pd.DataFrame:
        """
        Analyze hit rates by market cap ranges

        Args:
            bins: Market cap bin edges

        Returns:
            DataFrame with stats by MC range
        """
        alerts = self.db.get_alerts_for_analysis(labeled_only=True)

        if not alerts:
            return pd.DataFrame()

        data = []
        for alert in alerts:
            if alert.price_at_alert > 0:
                data.append({
                    'market_cap': alert.market_cap_at_alert,
                    'pumped_25pct_15m': alert.pumped_25pct_15m,
                    'max_return': (alert.max_price_1h / alert.price_at_alert - 1) * 100 if alert.max_price_1h else 0
                })

        df = pd.DataFrame(data)
        df['mc_range'] = pd.cut(df['market_cap'], bins=bins)

        grouped = df.groupby('mc_range').agg({
            'pumped_25pct_15m': 'mean',
            'max_return': 'mean',
            'market_cap': 'count'
        }).rename(columns={'market_cap': 'count'})

        return grouped

    def get_top_performers(self, n: int = 10) -> List[Dict[str, Any]]:
        """
        Get top N performing alerts

        Args:
            n: Number of top alerts to return

        Returns:
            List of top alert dicts
        """
        alerts = self.db.get_alerts_for_analysis(labeled_only=True)

        if not alerts:
            return []

        # Calculate returns and sort
        alert_returns = []
        for alert in alerts:
            if alert.price_at_alert > 0 and alert.max_price_1h:
                max_return = (alert.max_price_1h / alert.price_at_alert - 1) * 100
                alert_returns.append({
                    'alert_id': alert.alert_id,
                    'mint_address': alert.mint_address,
                    'alert_time': alert.alert_timestamp,
                    'entry_price': alert.price_at_alert,
                    'max_price': alert.max_price_1h,
                    'max_return_pct': max_return,
                    'time_to_peak_min': alert.time_to_peak_minutes,
                })

        # Sort by return
        alert_returns.sort(key=lambda x: x['max_return_pct'], reverse=True)

        return alert_returns[:n]

    def export_to_csv(self, filepath: str = "data/alert_analysis.csv"):
        """
        Export alert data to CSV for external analysis

        Args:
            filepath: Output file path
        """
        alerts = self.db.get_alerts_for_analysis(labeled_only=True)

        if not alerts:
            logger.warning("No alerts to export")
            return

        data = []
        for alert in alerts:
            data.append({
                'alert_id': alert.alert_id,
                'mint_address': alert.mint_address,
                'alert_timestamp': alert.alert_timestamp,
                'market_cap_at_alert': alert.market_cap_at_alert,
                'price_at_alert': alert.price_at_alert,
                'price_5m_later': alert.price_5m_later,
                'price_15m_later': alert.price_15m_later,
                'price_30m_later': alert.price_30m_later,
                'max_price_1h': alert.max_price_1h,
                'pumped_10pct_5m': alert.pumped_10pct_5m,
                'pumped_25pct_15m': alert.pumped_25pct_15m,
                'pumped_50pct_30m': alert.pumped_50pct_30m,
                'graduated': alert.graduated,
                'time_to_peak_minutes': alert.time_to_peak_minutes,
            })

        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)
        logger.info(f"Exported {len(df)} alerts to {filepath}")
