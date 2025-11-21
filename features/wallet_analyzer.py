"""
Wallet intelligence and profitability tracking
"""
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict
from loguru import logger

from database.db_manager import DatabaseManager


class WalletAnalyzer:
    """Analyzes wallet behavior and profitability"""

    def __init__(self, db_manager: DatabaseManager, config: Dict[str, Any]):
        """
        Initialize wallet analyzer

        Args:
            db_manager: Database manager instance
            config: Configuration dict with thresholds
        """
        self.db = db_manager
        self.config = config
        self.wallet_positions = defaultdict(dict)  # Track open positions

    def analyze_wallet_performance(self, wallet_address: str) -> Dict[str, Any]:
        """
        Analyze historical performance of a wallet

        Args:
            wallet_address: Wallet address to analyze

        Returns:
            Dict with performance metrics
        """
        # Get all transactions for this wallet
        with self.db.get_session() as session:
            from database.models import Transaction
            transactions = session.query(Transaction).filter_by(
                wallet_address=wallet_address
            ).order_by(Transaction.timestamp).all()

        if not transactions:
            return self._empty_wallet_stats()

        # Group by token
        token_trades = defaultdict(list)
        for txn in transactions:
            token_trades[txn.mint_address].append({
                'timestamp': txn.timestamp,
                'is_buy': txn.is_buy,
                'sol_amount': txn.sol_amount,
                'token_amount': txn.token_amount,
                'price': txn.sol_amount / txn.token_amount if txn.token_amount > 0 else 0
            })

        # Calculate P&L for each token
        total_pnl = 0
        wins = 0
        losses = 0
        total_trades = 0

        for mint_address, trades in token_trades.items():
            pnl = self._calculate_token_pnl(trades)
            total_pnl += pnl
            total_trades += 1

            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1

        # Calculate metrics
        win_rate = wins / total_trades if total_trades > 0 else 0

        return {
            'wallet_address': wallet_address,
            'total_trades': total_trades,
            'win_count': wins,
            'loss_count': losses,
            'win_rate': win_rate,
            'total_pnl_sol': total_pnl,
            'avg_pnl_per_trade': total_pnl / total_trades if total_trades > 0 else 0,
            'is_known_profitable': self._is_profitable(win_rate, total_pnl, total_trades)
        }

    def _calculate_token_pnl(self, trades: List[Dict]) -> float:
        """
        Calculate P&L for a single token using FIFO

        Args:
            trades: List of trades for one token

        Returns:
            P&L in SOL
        """
        position = 0  # Current token position
        cost_basis = 0  # Total SOL spent
        realized_pnl = 0

        for trade in trades:
            if trade['is_buy']:
                # Buy: add to position and cost
                position += trade['token_amount']
                cost_basis += trade['sol_amount']
            else:
                # Sell: realize P&L
                if position > 0:
                    sell_ratio = min(trade['token_amount'] / position, 1.0)
                    cost_of_sold = cost_basis * sell_ratio
                    realized_pnl += trade['sol_amount'] - cost_of_sold

                    position -= trade['token_amount']
                    cost_basis -= cost_of_sold

        # For simplicity, we ignore unrealized P&L on remaining position
        return realized_pnl

    def _is_profitable(self, win_rate: float, total_pnl: float, total_trades: int) -> bool:
        """
        Determine if wallet meets 'known profitable' criteria

        Args:
            win_rate: Win percentage
            total_pnl: Total P&L in SOL
            total_trades: Number of trades

        Returns:
            True if wallet is profitable
        """
        config = self.config.get('wallet_intelligence', {})

        return (
            total_trades >= config.get('min_trades', 5) and
            win_rate >= config.get('min_win_rate', 0.40) and
            total_pnl >= config.get('min_total_pnl_sol', 5.0)
        )

    def _empty_wallet_stats(self) -> Dict[str, Any]:
        """Return empty wallet statistics"""
        return {
            'total_trades': 0,
            'win_count': 0,
            'loss_count': 0,
            'win_rate': 0,
            'total_pnl_sol': 0,
            'avg_pnl_per_trade': 0,
            'is_known_profitable': False
        }

    def update_wallet_intelligence(self, wallet_address: str):
        """
        Update wallet intelligence in database

        Args:
            wallet_address: Wallet to update
        """
        stats = self.analyze_wallet_performance(wallet_address)
        stats['last_updated'] = datetime.utcnow()

        self.db.update_wallet_intelligence(stats)
        logger.debug(f"Updated intelligence for wallet {wallet_address[:8]}...")

    def get_known_profitable_wallets(self) -> List[str]:
        """
        Get list of known profitable wallet addresses

        Returns:
            List of wallet addresses
        """
        return self.db.get_known_profitable_wallets()

    def batch_update_wallets(self, lookback_days: int = 7):
        """
        Update intelligence for all active wallets

        Args:
            lookback_days: Days to look back for active wallets
        """
        cutoff = datetime.utcnow() - timedelta(days=lookback_days)

        with self.db.get_session() as session:
            from database.models import Transaction
            from sqlalchemy import distinct

            # Get unique wallets from recent transactions
            wallet_addresses = session.query(
                distinct(Transaction.wallet_address)
            ).filter(
                Transaction.timestamp >= cutoff
            ).all()

            wallet_addresses = [w[0] for w in wallet_addresses]

        logger.info(f"Updating intelligence for {len(wallet_addresses)} wallets...")

        for i, wallet in enumerate(wallet_addresses):
            try:
                self.update_wallet_intelligence(wallet)

                if (i + 1) % 100 == 0:
                    logger.info(f"Processed {i + 1}/{len(wallet_addresses)} wallets")

            except Exception as e:
                logger.error(f"Failed to update wallet {wallet}: {e}")

        logger.info(f"Wallet intelligence update complete")

    def get_wallet_token_count(self, wallet_address: str, window_minutes: int = 60) -> int:
        """
        Get number of different tokens wallet has traded recently

        Args:
            wallet_address: Wallet address
            window_minutes: Time window

        Returns:
            Number of unique tokens
        """
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)

        with self.db.get_session() as session:
            from database.models import Transaction
            from sqlalchemy import distinct

            token_count = session.query(
                distinct(Transaction.mint_address)
            ).filter(
                Transaction.wallet_address == wallet_address,
                Transaction.timestamp >= cutoff
            ).count()

        return token_count

    def is_likely_bot(self, wallet_address: str) -> bool:
        """
        Simple heuristic to detect bot wallets

        Args:
            wallet_address: Wallet to check

        Returns:
            True if likely a bot
        """
        # Get recent activity
        recent_token_count = self.get_wallet_token_count(wallet_address, window_minutes=10)

        # Simple heuristic: trading >20 different tokens in 10 minutes
        return recent_token_count > 20

    def track_position(self, wallet_address: str, mint_address: str, transaction: Dict):
        """
        Track wallet position for real-time monitoring

        Args:
            wallet_address: Wallet address
            mint_address: Token address
            transaction: Transaction data
        """
        key = f"{wallet_address}_{mint_address}"

        if key not in self.wallet_positions:
            self.wallet_positions[key] = {
                'wallet': wallet_address,
                'token': mint_address,
                'position': 0,
                'cost_basis': 0,
                'entry_time': None,
                'last_update': datetime.utcnow()
            }

        pos = self.wallet_positions[key]

        if transaction['is_buy']:
            if pos['position'] == 0:
                pos['entry_time'] = transaction['timestamp']

            pos['position'] += transaction['token_amount']
            pos['cost_basis'] += transaction['sol_amount']
        else:
            pos['position'] -= transaction['token_amount']
            if pos['position'] <= 0:
                # Position closed
                pos['position'] = 0
                pos['cost_basis'] = 0
                pos['entry_time'] = None

        pos['last_update'] = datetime.utcnow()
