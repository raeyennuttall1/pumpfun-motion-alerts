"""
Paper trading simulation for motion alerts
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from loguru import logger
from dataclasses import dataclass, field

from database.db_manager import DatabaseManager
from data_pipeline.pumpfun_api import PumpFunAPI


@dataclass
class Position:
    """Represents an open paper trading position"""
    mint_address: str
    entry_time: datetime
    entry_price: float
    entry_market_cap: float
    position_size_sol: float = 1.0  # Default 1 SOL per trade
    take_profit_pct: float = 0.25  # 25% profit target
    stop_loss_pct: float = 0.10    # 10% stop loss
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    pnl_pct: Optional[float] = None
    pnl_sol: Optional[float] = None
    exit_reason: Optional[str] = None  # "take_profit", "stop_loss", "manual"

    @property
    def is_open(self) -> bool:
        """Check if position is still open"""
        return self.exit_time is None

    @property
    def take_profit_target(self) -> float:
        """Calculate take profit price"""
        return self.entry_price * (1 + self.take_profit_pct)

    @property
    def stop_loss_target(self) -> float:
        """Calculate stop loss price"""
        return self.entry_price * (1 - self.stop_loss_pct)

    def check_exit(self, current_price: float) -> bool:
        """
        Check if position should be exited

        Args:
            current_price: Current token price

        Returns:
            True if exit conditions met
        """
        if not self.is_open:
            return False

        # Take profit hit
        if current_price >= self.take_profit_target:
            self.close_position(current_price, "take_profit")
            return True

        # Stop loss hit
        if current_price <= self.stop_loss_target:
            self.close_position(current_price, "stop_loss")
            return True

        return False

    def close_position(self, exit_price: float, reason: str = "manual"):
        """
        Close the position

        Args:
            exit_price: Exit price
            reason: Reason for exit
        """
        self.exit_time = datetime.utcnow()
        self.exit_price = exit_price
        self.exit_reason = reason

        # Calculate P&L
        self.pnl_pct = (exit_price - self.entry_price) / self.entry_price
        self.pnl_sol = self.position_size_sol * self.pnl_pct

    def get_unrealized_pnl(self, current_price: float) -> Dict[str, float]:
        """
        Get unrealized P&L for open position

        Args:
            current_price: Current price

        Returns:
            Dict with pnl_pct and pnl_sol
        """
        if not self.is_open:
            return {"pnl_pct": self.pnl_pct, "pnl_sol": self.pnl_sol}

        pnl_pct = (current_price - self.entry_price) / self.entry_price
        pnl_sol = self.position_size_sol * pnl_pct

        return {"pnl_pct": pnl_pct, "pnl_sol": pnl_sol}


class PaperTrader:
    """Manages paper trading positions and P&L tracking"""

    def __init__(self, db_manager: DatabaseManager, api_client: PumpFunAPI, config: Dict[str, Any]):
        """
        Initialize paper trader

        Args:
            db_manager: Database manager
            api_client: Pump.fun API client
            config: Configuration dict
        """
        self.db = db_manager
        self.api = api_client
        self.config = config.get('paper_trading', {
            'position_size_sol': 1.0,
            'take_profit_pct': 0.25,  # 25%
            'stop_loss_pct': 0.10,    # 10%
            'max_open_positions': 20,
            'max_position_duration_minutes': 60
        })

        # Track open positions
        self.open_positions: Dict[str, Position] = {}

        # Track closed positions
        self.closed_positions: List[Position] = []

        # Performance tracking
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl_sol = 0.0

        logger.info("Paper trader initialized")

    def enter_position(self, alert_data: Dict[str, Any]) -> Optional[Position]:
        """
        Enter a paper trading position based on alert

        Args:
            alert_data: Alert data from motion detector

        Returns:
            Position object if entered, None if skipped
        """
        mint_address = alert_data['mint_address']

        # Skip if already have position in this token
        if mint_address in self.open_positions:
            logger.debug(f"Already have position in {mint_address}, skipping")
            return None

        # Skip if max positions reached
        if len(self.open_positions) >= self.config['max_open_positions']:
            logger.debug(f"Max positions ({self.config['max_open_positions']}) reached, skipping")
            return None

        # Create position
        position = Position(
            mint_address=mint_address,
            entry_time=datetime.utcnow(),
            entry_price=alert_data.get('price_at_alert', 0),
            entry_market_cap=alert_data.get('market_cap_at_alert', 0),
            position_size_sol=self.config['position_size_sol'],
            take_profit_pct=self.config['take_profit_pct'],
            stop_loss_pct=self.config['stop_loss_pct']
        )

        # Add to open positions
        self.open_positions[mint_address] = position

        logger.info(
            f"📈 PAPER ENTRY: {mint_address} at {position.entry_price:.8f} SOL | "
            f"TP: {position.take_profit_target:.8f} (+{position.take_profit_pct*100:.0f}%) | "
            f"SL: {position.stop_loss_target:.8f} (-{position.stop_loss_pct*100:.0f}%)"
        )

        return position

    def check_exits(self, mint_address: str, current_price: float) -> Optional[Position]:
        """
        Check if any position should be exited

        Args:
            mint_address: Token address
            current_price: Current price

        Returns:
            Position if exited, None otherwise
        """
        position = self.open_positions.get(mint_address)

        if not position or not position.is_open:
            return None

        # Check exit conditions
        if position.check_exit(current_price):
            # Remove from open positions
            self.open_positions.pop(mint_address)

            # Add to closed positions
            self.closed_positions.append(position)

            # Update stats
            self.total_trades += 1
            self.total_pnl_sol += position.pnl_sol

            if position.pnl_sol > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1

            # Log exit
            emoji = "🎯" if position.exit_reason == "take_profit" else "🛑"
            pnl_emoji = "✅" if position.pnl_sol > 0 else "❌"

            logger.info(
                f"{emoji} PAPER EXIT ({position.exit_reason.upper()}): {mint_address} | "
                f"Entry: {position.entry_price:.8f} → Exit: {position.exit_price:.8f} | "
                f"{pnl_emoji} P&L: {position.pnl_pct*100:+.2f}% ({position.pnl_sol:+.4f} SOL) | "
                f"Duration: {(position.exit_time - position.entry_time).seconds}s"
            )

            return position

        return None

    def check_stale_positions(self):
        """Close positions that have been open too long"""
        max_duration = timedelta(minutes=self.config['max_position_duration_minutes'])
        current_time = datetime.utcnow()

        stale_positions = []

        for mint_address, position in self.open_positions.items():
            if current_time - position.entry_time > max_duration:
                stale_positions.append(mint_address)

        for mint_address in stale_positions:
            position = self.open_positions.get(mint_address)
            if position:
                # Get current price from database
                latest_snapshot = self.db.get_latest_snapshot(mint_address)
                current_price = latest_snapshot.price_sol if latest_snapshot else position.entry_price

                # Close at current price
                position.close_position(current_price, "timeout")

                # Move to closed
                self.open_positions.pop(mint_address)
                self.closed_positions.append(position)

                # Update stats
                self.total_trades += 1
                self.total_pnl_sol += position.pnl_sol

                if position.pnl_sol > 0:
                    self.winning_trades += 1
                else:
                    self.losing_trades += 1

                logger.info(
                    f"⏰ PAPER TIMEOUT: {mint_address} | "
                    f"P&L: {position.pnl_pct*100:+.2f}% ({position.pnl_sol:+.4f} SOL)"
                )

    def get_performance_summary(self) -> str:
        """
        Get formatted performance summary

        Returns:
            Formatted string with performance stats
        """
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        avg_pnl = (self.total_pnl_sol / self.total_trades) if self.total_trades > 0 else 0

        # Calculate unrealized P&L from open positions
        unrealized_pnl = 0.0
        for position in self.open_positions.values():
            latest_snapshot = self.db.get_latest_snapshot(position.mint_address)
            if latest_snapshot and latest_snapshot.price_sol:
                pnl_data = position.get_unrealized_pnl(latest_snapshot.price_sol)
                unrealized_pnl += pnl_data['pnl_sol']

        summary = f"""
╔════════════════════════════════════════════════╗
║         PAPER TRADING PERFORMANCE              ║
╚════════════════════════════════════════════════╝

📊 Overall Stats:
   Total Trades: {self.total_trades}
   Win Rate: {win_rate:.1f}% ({self.winning_trades}W / {self.losing_trades}L)
   Total P&L: {self.total_pnl_sol:+.4f} SOL
   Avg P&L/Trade: {avg_pnl:+.4f} SOL

💼 Open Positions: {len(self.open_positions)}
   Unrealized P&L: {unrealized_pnl:+.4f} SOL

🎯 Best Trade: {max([p.pnl_sol for p in self.closed_positions], default=0):+.4f} SOL
📉 Worst Trade: {min([p.pnl_sol for p in self.closed_positions], default=0):+.4f} SOL
"""
        return summary

    def get_open_positions_summary(self) -> str:
        """
        Get formatted summary of open positions

        Returns:
            Formatted string with open positions
        """
        if not self.open_positions:
            return "No open positions"

        lines = ["=" * 60, "OPEN PAPER POSITIONS", "=" * 60]

        for mint_address, position in self.open_positions.items():
            # Get current price
            latest_snapshot = self.db.get_latest_snapshot(mint_address)
            current_price = latest_snapshot.price_sol if latest_snapshot else position.entry_price

            # Calculate unrealized P&L
            pnl_data = position.get_unrealized_pnl(current_price)

            # Duration
            duration = (datetime.utcnow() - position.entry_time).seconds

            lines.append(
                f"\n{mint_address[:8]}... | "
                f"Entry: {position.entry_price:.8f} | "
                f"Current: {current_price:.8f} | "
                f"P&L: {pnl_data['pnl_pct']*100:+.2f}% ({pnl_data['pnl_sol']:+.4f} SOL) | "
                f"{duration}s"
            )

        lines.append("=" * 60)

        return "\n".join(lines)
