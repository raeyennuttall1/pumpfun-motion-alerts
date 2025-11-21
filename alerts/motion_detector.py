"""
Motion detection system for identifying trending tokens
"""
from typing import Dict, Any, Optional, Callable
from datetime import datetime
from loguru import logger

from database.db_manager import DatabaseManager
from features.feature_calculator import FeatureCalculator


class MotionDetector:
    """Detects motion/traction for tokens based on configurable thresholds"""

    def __init__(
        self,
        db_manager: DatabaseManager,
        feature_calculator: FeatureCalculator,
        config: Dict[str, Any],
        on_alert: Optional[Callable] = None
    ):
        """
        Initialize motion detector

        Args:
            db_manager: Database manager
            feature_calculator: Feature calculator instance
            config: Configuration dict with thresholds
            on_alert: Callback function when alert triggers
        """
        self.db = db_manager
        self.feature_calc = feature_calculator
        self.config = config.get('motion_alert', {})
        self.on_alert = on_alert
        self.alerted_tokens = set()  # Track tokens we've alerted on

    def check_motion(
        self,
        mint_address: str,
        known_wallets: list
    ) -> Optional[Dict[str, Any]]:
        """
        Check if token meets motion alert criteria

        Args:
            mint_address: Token to check
            known_wallets: List of known profitable wallet addresses

        Returns:
            Alert data if triggered, None otherwise
        """
        logger.debug(f"check_motion called for {mint_address[:8]}...")

        # Skip if already alerted
        if mint_address in self.alerted_tokens:
            logger.debug(f"Skipping {mint_address[:8]}... - already alerted")
            return None

        # Get token age
        token_age = self.feature_calc.get_token_age_seconds(mint_address)
        logger.debug(f"Token age: {token_age}s, min required: {self.config.get('min_time_since_launch', 60)}s")

        # Skip if too young (avoid initial bot spam)
        min_age = self.config.get('min_time_since_launch', 60)
        if token_age < min_age:
            logger.debug(f"Skipping {mint_address[:8]}... - too young ({token_age}s < {min_age}s)")
            return None

        # Calculate features
        time_windows = self.config.get('feature_windows', [1, 3, 5, 10])
        logger.debug(f"Calculating features for {mint_address[:8]}...")
        features = self.feature_calc.calculate_features(mint_address, time_windows)
        logger.debug(f"Features calculated: {list(features.keys())[:10]}...")

        # Calculate wallet features
        wallet_features = self.feature_calc.calculate_wallet_features(
            mint_address,
            known_wallets,
            window_minutes=3
        )
        features.update(wallet_features)

        # Add token age
        features['time_since_launch_seconds'] = token_age

        # Check thresholds
        if self._meets_criteria(features):
            alert_data = self._create_alert(mint_address, features)
            logger.info(f"🚨 MOTION ALERT: {mint_address[:8]}... - MC: ${features.get('current_market_cap', 0):.0f}")

            # Mark as alerted
            self.alerted_tokens.add(mint_address)

            # Trigger callback
            if self.on_alert:
                self.on_alert(alert_data)

            return alert_data

        return None

    def _meets_criteria(self, features: Dict[str, Any]) -> bool:
        """
        Check if features meet alert criteria

        Args:
            features: Calculated features

        Returns:
            True if criteria met
        """
        # Use 3-minute window as primary (can be configured)
        primary_window = '3m'

        # Extract thresholds from config
        min_buy_volume = self.config.get('min_buy_volume_sol', 10.0)
        min_unique_buyers = self.config.get('min_unique_buyers', 30)
        min_buy_sell_ratio = self.config.get('min_buy_sell_ratio', 2.5)
        min_txn_velocity = self.config.get('min_txn_velocity', 15)
        min_known_wallets = self.config.get('min_known_wallets', 3)
        max_market_cap = self.config.get('max_market_cap', 100000)
        max_bonding_curve = self.config.get('max_bonding_curve_pct', 60)

        # Check each criterion
        buy_volume_ok = features.get(f'buy_volume_sol_{primary_window}', 0) >= min_buy_volume
        unique_buyers_ok = features.get(f'unique_buyers_{primary_window}', 0) >= min_unique_buyers
        buy_sell_ratio_ok = features.get(f'buy_sell_ratio_{primary_window}', 0) >= min_buy_sell_ratio
        txn_velocity_ok = features.get('txn_velocity', 0) >= min_txn_velocity
        known_wallets_ok = features.get('known_wallet_count', 0) >= min_known_wallets
        market_cap_ok = features.get('current_market_cap', 0) < max_market_cap
        bonding_curve_ok = features.get('bonding_curve_pct', 100) < max_bonding_curve
        not_graduated = not features.get('graduated', False)

        # Log criteria for debugging
        if buy_volume_ok and unique_buyers_ok:  # At least some interest
            logger.debug(f"Motion check for {features.get('mint_address', 'unknown')[:8]}... - "
                        f"Vol: {buy_volume_ok}, Buyers: {unique_buyers_ok}, "
                        f"Ratio: {buy_sell_ratio_ok}, Velocity: {txn_velocity_ok}, "
                        f"Wallets: {known_wallets_ok}, MC: {market_cap_ok}, "
                        f"Curve: {bonding_curve_ok}")

        # All criteria must be met
        return all([
            buy_volume_ok,
            unique_buyers_ok,
            buy_sell_ratio_ok,
            txn_velocity_ok,
            known_wallets_ok,
            market_cap_ok,
            bonding_curve_ok,
            not_graduated
        ])

    def _create_alert(self, mint_address: str, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create alert record

        Args:
            mint_address: Token address
            features: Calculated features

        Returns:
            Alert data dict
        """
        # Get token info
        token = self.db.get_token(mint_address)

        # Convert datetime objects to strings for JSON serialization
        features_json = {}
        for key, value in features.items():
            if isinstance(value, datetime):
                features_json[key] = value.isoformat()
            else:
                features_json[key] = value

        alert_data = {
            'mint_address': mint_address,
            'alert_timestamp': datetime.utcnow(),
            'trigger_features': features_json,
            'market_cap_at_alert': features.get('current_market_cap', 0),
            'price_at_alert': features.get('current_price_sol', 0),
            'bonding_curve_pct': features.get('bonding_curve_pct', 0),
        }

        # Save to database
        self.db.add_alert(alert_data)

        return alert_data

    def reset_alert(self, mint_address: str):
        """
        Reset alert status for a token (allow re-alerting)

        Args:
            mint_address: Token to reset
        """
        self.alerted_tokens.discard(mint_address)

    def get_alert_summary(self, alert_data: Dict[str, Any]) -> str:
        """
        Generate human-readable alert summary

        Args:
            alert_data: Alert data

        Returns:
            Formatted string summary
        """
        features = alert_data.get('trigger_features', {})

        # Get token info from database
        token = self.db.get_token(alert_data['mint_address'])
        token_symbol = token['symbol'] if token else 'UNKNOWN'
        token_name = token['name'] if token else 'Unknown'

        summary = f"""
╔══════════════════════════════════════╗
║       MOTION ALERT TRIGGERED         ║
╚══════════════════════════════════════╝

Token: {token_symbol} ({token_name})
Mint: {alert_data['mint_address']}

📊 Entry Metrics:
   Market Cap: ${alert_data.get('market_cap_at_alert', 0):,.0f}
   Price: {alert_data.get('price_at_alert', 0):.8f} SOL
   Bonding Curve: {alert_data.get('bonding_curve_pct', 0):.1f}%

📈 3-Minute Activity:
   Buy Volume: {features.get('buy_volume_sol_3m', 0):.2f} SOL
   Unique Buyers: {features.get('unique_buyers_3m', 0)}
   Buy/Sell Ratio: {features.get('buy_sell_ratio_3m', 0):.2f}
   Txn Velocity: {features.get('txn_velocity', 0):.1f}/min

👛 Smart Money:
   Known Wallets: {features.get('known_wallet_count', 0)}
   Known %: {features.get('known_wallet_percentage', 0):.1f}%

⏰ Time Since Launch: {features.get('time_since_launch_seconds', 0):.0f}s
        """

        return summary.strip()

    def update_config(self, new_config: Dict[str, Any]):
        """
        Update detection thresholds

        Args:
            new_config: New configuration dict
        """
        self.config.update(new_config)
        logger.info("Motion detector config updated")

    def get_active_alerts_count(self) -> int:
        """Get count of tokens currently alerted"""
        return len(self.alerted_tokens)
