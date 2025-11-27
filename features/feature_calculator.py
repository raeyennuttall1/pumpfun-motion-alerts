"""
Real-time feature calculation for motion detection
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict
import numpy as np
from loguru import logger

from database.db_manager import DatabaseManager


class FeatureCalculator:
    """Calculates real-time features for tokens"""

    def __init__(self, db_manager: DatabaseManager):
        """
        Initialize feature calculator

        Args:
            db_manager: Database manager instance
        """
        self.db = db_manager
        self.token_cache = defaultdict(list)  # In-memory transaction cache
        self.cache_limit = 1000  # Max transactions per token in cache

    def update_cache(self, mint_address: str, transaction: Dict[str, Any]):
        """
        Add transaction to in-memory cache

        Args:
            mint_address: Token mint address
            transaction: Transaction data
        """
        cache = self.token_cache[mint_address]
        cache.append(transaction)

        # Limit cache size
        if len(cache) > self.cache_limit:
            cache.pop(0)

    def get_cached_transactions(
        self,
        mint_address: str,
        lookback_minutes: int
    ) -> List[Dict[str, Any]]:
        """
        Get transactions from cache within time window

        Args:
            mint_address: Token mint address
            lookback_minutes: Minutes to look back

        Returns:
            List of transactions within window
        """
        cutoff = datetime.utcnow() - timedelta(minutes=lookback_minutes)
        cache = self.token_cache[mint_address]

        return [
            txn for txn in cache
            if txn.get('timestamp', datetime.utcnow()) >= cutoff
        ]

    def calculate_features(
        self,
        mint_address: str,
        time_windows: List[int] = [1, 3, 5, 10]
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive features for a token

        Args:
            mint_address: Token mint address
            time_windows: Time windows in minutes to calculate features for

        Returns:
            Dict of calculated features
        """
        features = {
            'mint_address': mint_address,
            'timestamp': datetime.utcnow(),
        }

        # Get latest snapshot for current state
        snapshot = self.db.get_latest_snapshot(mint_address)
        if snapshot:
            features.update({
                'current_market_cap': snapshot['market_cap'],
                'current_price_sol': snapshot['price_sol'],
                'bonding_curve_pct': snapshot['bonding_curve_pct'],
                'graduated': snapshot['graduated'],
            })
        else:
            features.update({
                'current_market_cap': 0,
                'current_price_sol': 0,
                'bonding_curve_pct': 0,
                'graduated': False,
            })

        # If price is 0, try to calculate from recent transactions
        if features['current_price_sol'] == 0:
            recent_txns = self.get_cached_transactions(mint_address, 1)  # Last 1 minute
            if recent_txns:
                # Get most recent buy transaction
                buys = [t for t in recent_txns if t.get('is_buy')]
                if buys:
                    latest_buy = buys[-1]
                    sol_amt = latest_buy.get('sol_amount', 0)
                    token_amt = latest_buy.get('token_amount', 0)
                    if token_amt > 0:
                        features['current_price_sol'] = sol_amt / token_amt

        # Calculate features for each time window
        for window in time_windows:
            window_features = self._calculate_window_features(mint_address, window)
            # Prefix with window duration
            for key, value in window_features.items():
                features[f"{key}_{window}m"] = value

        # Calculate derived features
        features.update(self._calculate_derived_features(features, time_windows))

        return features

    def _calculate_window_features(
        self,
        mint_address: str,
        window_minutes: int
    ) -> Dict[str, float]:
        """
        Calculate features for a specific time window

        Args:
            mint_address: Token mint address
            window_minutes: Time window in minutes

        Returns:
            Dict of window-specific features
        """
        # Try cache first, fall back to database
        transactions = self.get_cached_transactions(mint_address, window_minutes)

        if not transactions:
            # Fallback to database
            cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
            db_txns = self.db.get_transactions(mint_address, since=cutoff)
            transactions = [
                {
                    'is_buy': t.is_buy,
                    'sol_amount': t.sol_amount,
                    'wallet_address': t.wallet_address,
                    'timestamp': t.timestamp
                }
                for t in db_txns
            ]

        if not transactions:
            return self._empty_window_features()

        # Separate buys and sells
        buys = [t for t in transactions if t['is_buy']]
        sells = [t for t in transactions if not t['is_buy']]

        # Calculate features
        unique_buyers = len(set(t['wallet_address'] for t in buys))
        unique_sellers = len(set(t['wallet_address'] for t in sells))
        buy_volume_sol = sum(t['sol_amount'] for t in buys)
        sell_volume_sol = sum(t['sol_amount'] for t in sells)

        return {
            'txn_count': len(transactions),
            'buy_count': len(buys),
            'sell_count': len(sells),
            'unique_buyers': unique_buyers,
            'unique_sellers': unique_sellers,
            'buy_volume_sol': buy_volume_sol,
            'sell_volume_sol': sell_volume_sol,
            'net_volume_sol': buy_volume_sol - sell_volume_sol,
            'buy_sell_ratio': len(buys) / max(len(sells), 1),
            'avg_buy_size': np.mean([t['sol_amount'] for t in buys]) if buys else 0,
            'avg_sell_size': np.mean([t['sol_amount'] for t in sells]) if sells else 0,
            'max_buy_size': max([t['sol_amount'] for t in buys], default=0),
            'buyer_seller_ratio': unique_buyers / max(unique_sellers, 1),
        }

    def _empty_window_features(self) -> Dict[str, float]:
        """Return empty features when no data available"""
        return {
            'txn_count': 0,
            'buy_count': 0,
            'sell_count': 0,
            'unique_buyers': 0,
            'unique_sellers': 0,
            'buy_volume_sol': 0,
            'sell_volume_sol': 0,
            'net_volume_sol': 0,
            'buy_sell_ratio': 0,
            'avg_buy_size': 0,
            'avg_sell_size': 0,
            'max_buy_size': 0,
            'buyer_seller_ratio': 0,
        }

    def _calculate_derived_features(
        self,
        features: Dict[str, Any],
        windows: List[int]
    ) -> Dict[str, float]:
        """
        Calculate derived/cross-window features

        Args:
            features: Already calculated features
            windows: Time windows used

        Returns:
            Dict of derived features
        """
        derived = {}

        # Transaction velocity (txns per minute)
        if windows:
            shortest_window = min(windows)
            txn_count = features.get(f'txn_count_{shortest_window}m', 0)
            derived['txn_velocity'] = txn_count / shortest_window if shortest_window > 0 else 0

        # Volume momentum (comparing windows)
        if len(windows) >= 2:
            short_window = min(windows)
            long_window = max(windows)

            short_vol = features.get(f'buy_volume_sol_{short_window}m', 0)
            long_vol = features.get(f'buy_volume_sol_{long_window}m', 0)

            # Annualized momentum
            if long_vol > 0:
                derived['volume_momentum'] = (short_vol / short_window) / (long_vol / long_window)
            else:
                derived['volume_momentum'] = 0

        # Volume/Market Cap ratio (Tier 1 requirement)
        # Calculate for 1 hour window
        market_cap = features.get('current_market_cap', 0)

        # Use longest window available or 60 minutes
        volume_window = max(windows) if windows else 60
        buy_volume_sol = features.get(f'buy_volume_sol_{volume_window}m', 0)

        # Convert SOL volume to USD (approximate: 1 SOL = $100 for ratio calculation)
        # For more accuracy, you'd fetch real-time SOL/USD price
        SOL_PRICE_USD = 100  # Approximate - update with real price if needed
        volume_usd = buy_volume_sol * SOL_PRICE_USD

        # Scale to 1 hour if needed
        if volume_window < 60:
            volume_1h_usd = volume_usd * (60 / volume_window)
        else:
            volume_1h_usd = volume_usd

        # Calculate ratio
        if market_cap > 0:
            derived['volume_mc_ratio_1h'] = volume_1h_usd / market_cap
        else:
            derived['volume_mc_ratio_1h'] = 0

        return derived

    def calculate_wallet_features(
        self,
        mint_address: str,
        known_wallets: List[str],
        window_minutes: int = 3
    ) -> Dict[str, Any]:
        """
        Calculate wallet-related features

        Args:
            mint_address: Token mint address
            known_wallets: List of known profitable wallet addresses
            window_minutes: Time window

        Returns:
            Dict of wallet features
        """
        transactions = self.get_cached_transactions(mint_address, window_minutes)

        if not transactions:
            cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
            db_txns = self.db.get_transactions(mint_address, since=cutoff)
            transactions = [{'wallet_address': t.wallet_address, 'is_buy': t.is_buy} for t in db_txns]

        buys = [t for t in transactions if t['is_buy']]
        buyer_wallets = set(t['wallet_address'] for t in buys)

        # Count known wallets
        known_wallet_count = len(buyer_wallets.intersection(set(known_wallets)))

        # Calculate wallet age (would need historical data)
        # For now, return basic metrics
        return {
            'known_wallet_count': known_wallet_count,
            'total_unique_buyers': len(buyer_wallets),
            'known_wallet_percentage': known_wallet_count / max(len(buyer_wallets), 1) * 100
        }

    def get_token_age_seconds(self, mint_address: str) -> float:
        """
        Get token age in seconds

        Args:
            mint_address: Token mint address

        Returns:
            Age in seconds
        """
        token = self.db.get_token(mint_address)
        if not token:
            return 0

        age = datetime.utcnow() - token['created_timestamp']
        return age.total_seconds()

    def clear_cache(self, mint_address: Optional[str] = None):
        """
        Clear transaction cache

        Args:
            mint_address: Specific token to clear, or None for all
        """
        if mint_address:
            self.token_cache.pop(mint_address, None)
            logger.debug(f"Cleared cache for {mint_address}")
        else:
            self.token_cache.clear()
            logger.debug("Cleared all transaction cache")
