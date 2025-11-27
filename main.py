"""
Main orchestrator for Pump.fun motion alert system
"""
import asyncio
import yaml
from loguru import logger
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db_manager import DatabaseManager
from data_pipeline.pumpfun_api import PumpFunAPI
from data_pipeline.websocket_monitor import PumpFunWebSocket
from data_pipeline.gmgn_api import GMGNAPI
from data_pipeline.solana_rpc import SolanaRPC
from features.feature_calculator import FeatureCalculator
from features.wallet_analyzer import WalletAnalyzer
from alerts.motion_detector import MotionDetector
from alerts.tier1_screener import Tier1Screener
from labeling.outcome_labeler import OutcomeLabeler
from analysis.hit_rate_analyzer import HitRateAnalyzer
from trading.paper_trader import PaperTrader


class MotionAlertSystem:
    """Main system orchestrator"""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize the system

        Args:
            config_path: Path to configuration file
        """
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)

        # Setup logging
        self._setup_logging()

        logger.info("Initializing Hybrid Motion Alert System (pump.fun + GMGN)...")

        # Initialize components
        self.db = DatabaseManager(
            db_path=self.config['database']['sqlite_path'],
            echo=self.config['database'].get('echo_sql', False)
        )

        # pump.fun API for real-time monitoring
        self.pumpfun_api = PumpFunAPI(base_url=self.config['api']['pumpfun_base_url'])

        # GMGN & Solana for Tier 1 enrichment
        self.gmgn_api = GMGNAPI()
        self.solana_rpc = SolanaRPC(rpc_url=self.config['api']['solana_rpc'])

        self.feature_calc = FeatureCalculator(self.db)

        self.wallet_analyzer = WalletAnalyzer(self.db, self.config)

        self.motion_detector = MotionDetector(
            self.db,
            self.feature_calc,
            self.config,
            on_alert=self.handle_alert
        )

        # Tier 1 screener for advanced filtering
        self.tier1_screener = Tier1Screener(
            self.db,
            self.feature_calc,
            self.config,
            gmgn_api=self.gmgn_api,
            solana_rpc=self.solana_rpc,
            on_tier1_alert=self.handle_tier1_alert
        )

        self.outcome_labeler = OutcomeLabeler(self.db, self.pumpfun_api, self.config)

        self.hit_rate_analyzer = HitRateAnalyzer(self.db)

        self.paper_trader = PaperTrader(self.db, self.pumpfun_api, self.config)

        # WebSocket (initialized in start)
        self.websocket = None

        # State
        self.active_tokens = set()
        self.known_wallets = []

        logger.info("System initialized successfully")

    def _setup_logging(self):
        """Configure logging"""
        log_config = self.config.get('logging', {})

        logger.remove()  # Remove default handler

        # Console handler
        logger.add(
            sys.stdout,
            level=log_config.get('level', 'INFO'),
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
        )

        # File handler
        log_file = log_config.get('file', 'logs/pumpfun_alerts.log')
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        logger.add(
            log_file,
            level=log_config.get('level', 'INFO'),
            rotation=log_config.get('rotation', '100 MB'),
            retention=log_config.get('retention', '30 days'),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
        )

    async def handle_new_token(self, token_data: dict):
        """
        Handle new token launch event

        Args:
            token_data: Token metadata
        """
        try:
            # Add to database
            self.db.add_token_launch(token_data)

            # Add to active monitoring
            self.active_tokens.add(token_data['mint_address'])

            logger.info(f"New token detected: {token_data['symbol']} ({token_data['mint_address']})")

            # Subscribe to trades for this specific token
            if self.websocket and self.websocket.websocket:
                await self.websocket.subscribe_token_trades(token_data['mint_address'])

            # Create initial snapshot
            snapshot_data = {
                'mint_address': token_data['mint_address'],
                'timestamp': datetime.utcnow(),
                'market_cap': token_data.get('initial_market_cap', 0),
                'price_sol': 0,
                'bonding_curve_pct': 0,
                'graduated': False,
            }
            self.db.add_snapshot(snapshot_data)

            # Clean up old tokens if too many active
            max_active = self.config.get('data_collection', {}).get('max_active_tokens', 100)
            if len(self.active_tokens) > max_active:
                # Remove oldest
                self.active_tokens.pop()

        except Exception as e:
            logger.error(f"Error handling new token: {e}")

    async def handle_trade(self, trade_data: dict):
        """
        Handle trade event

        Args:
            trade_data: Transaction data
        """
        try:
            mint_address = trade_data['mint_address']

            # Only process if we're tracking this token
            if mint_address not in self.active_tokens:
                return

            # Add transaction to database
            self.db.add_transaction(trade_data)

            # Update feature calculator cache
            self.feature_calc.update_cache(mint_address, trade_data)

            # Check for motion alert
            if trade_data['is_buy']:  # Only check on buys
                self.motion_detector.check_motion(mint_address, self.known_wallets)

            # Track wallet position
            if trade_data['wallet_address']:
                self.wallet_analyzer.track_position(
                    trade_data['wallet_address'],
                    mint_address,
                    trade_data
                )

            # Check paper trading exits based on latest price
            try:
                latest_snapshot = self.db.get_latest_snapshot(mint_address)
                if latest_snapshot and hasattr(latest_snapshot, 'price_sol') and latest_snapshot.price_sol:
                    self.paper_trader.check_exits(mint_address, latest_snapshot.price_sol)
            except Exception:
                pass  # Snapshot may not exist yet for new tokens

        except Exception as e:
            logger.error(f"Error handling trade: {e}")

    def handle_alert(self, alert_data: dict):
        """
        Handle motion alert trigger

        Args:
            alert_data: Alert data
        """
        # Print alert summary
        summary = self.motion_detector.get_alert_summary(alert_data)
        logger.info(f"\n{summary}\n")

        # Enter paper trading position
        self.paper_trader.enter_position(alert_data)

        # You can add custom actions here:
        # - Send notification (Discord, Telegram, etc.)
        # - Execute trade
        # - etc.

    def handle_tier1_alert(self, alert_data: dict):
        """
        Handle Tier 1 alert trigger

        Args:
            alert_data: Tier 1 alert data
        """
        # Print formatted alert
        self.tier1_screener.print_alert_summary(alert_data)

        # Enter paper trading position (higher confidence)
        self.paper_trader.enter_position(alert_data)

        # You can add priority actions here:
        # - Send high-priority notification
        # - Execute immediate trade
        # - etc.

    async def start_monitoring(self):
        """Start real-time monitoring via pump.fun WebSocket"""
        logger.info("Starting pump.fun real-time monitoring...")

        # Load known profitable wallets
        self.known_wallets = self.wallet_analyzer.get_known_profitable_wallets()
        logger.info(f"Loaded {len(self.known_wallets)} known profitable wallets")

        # Initialize pump.fun WebSocket
        self.websocket = PumpFunWebSocket(
            websocket_url=self.config['api']['pumpfun_websocket'],
            on_new_token=self.handle_new_token,
            on_trade=self.handle_trade
        )

        # Start listening
        await self.websocket.listen()

    async def run_labeling_loop(self):
        """Background task to label alerts periodically"""
        while True:
            try:
                logger.info("Running outcome labeler...")
                self.outcome_labeler.label_unlabeled_alerts(min_age_minutes=60)

                # Wait 10 minutes
                await asyncio.sleep(600)

            except Exception as e:
                logger.error(f"Labeling loop error: {e}")
                await asyncio.sleep(60)

    async def run_wallet_update_loop(self):
        """Background task to update wallet intelligence"""
        while True:
            try:
                logger.info("Updating wallet intelligence...")
                self.wallet_analyzer.batch_update_wallets(lookback_days=7)

                # Refresh known wallets
                self.known_wallets = self.wallet_analyzer.get_known_profitable_wallets()
                logger.info(f"Updated: {len(self.known_wallets)} known profitable wallets")

                # Wait 1 hour
                await asyncio.sleep(3600)

            except Exception as e:
                logger.error(f"Wallet update loop error: {e}")
                await asyncio.sleep(300)

    async def run_paper_trading_loop(self):
        """Background task to manage paper trading positions"""
        while True:
            try:
                # Check for stale positions (held too long)
                self.paper_trader.check_stale_positions()

                # Show performance summary every 5 minutes
                if self.paper_trader.total_trades > 0 or len(self.paper_trader.open_positions) > 0:
                    summary = self.paper_trader.get_performance_summary()
                    logger.info(summary)

                # Wait 5 minutes
                await asyncio.sleep(300)

            except Exception as e:
                logger.error(f"Paper trading loop error: {e}")
                await asyncio.sleep(60)

    async def run_tier1_screening_loop(self):
        """Background task to run Tier 1 screening on active tokens"""
        logger.info("Tier 1 screener starting immediately (concurrent with motion detection)")
        logger.info("Will only screen tokens that are 1+ hour old")

        check_interval = self.config.get('tier1_screening', {}).get('check_interval_minutes', 5) * 60

        while True:
            try:
                logger.info("Running Tier 1 screening on active tokens...")

                # Get tokens that are old enough (1+ hour)
                min_age = timedelta(hours=1)
                recent_tokens = self.db.get_recent_launches(hours=24, limit=100)

                screened_count = 0
                passed_count = 0

                for token in recent_tokens:
                    token_age = datetime.utcnow() - token.created_timestamp

                    if token_age >= min_age:
                        screened_count += 1
                        result = self.tier1_screener.check_tier1_criteria(token.mint_address)

                        if result:
                            passed_count += 1

                logger.info(f"Tier 1 screening complete: {screened_count} tokens checked, {passed_count} passed")

                # Wait for next check
                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.error(f"Tier 1 screening loop error: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error

    async def start(self):
        """Start the entire system"""
        logger.info("="*60)
        logger.info("Starting Hybrid Motion Alert System")
        logger.info("pump.fun (Real-time) + GMGN (Enrichment)")
        logger.info("="*60)

        # Print stats
        stats = self.db.get_stats()
        logger.info(f"Database stats: {stats}")

        # Start background tasks
        tasks = [
            asyncio.create_task(self.start_monitoring()),
            asyncio.create_task(self.run_labeling_loop()),
            asyncio.create_task(self.run_wallet_update_loop()),
            asyncio.create_task(self.run_paper_trading_loop()),
            asyncio.create_task(self.run_tier1_screening_loop()),
        ]

        # Run all tasks
        await asyncio.gather(*tasks)

    def stop(self):
        """Stop the system"""
        logger.info("Stopping system...")
        if self.websocket:
            asyncio.create_task(self.websocket.stop())

    def print_hit_rates(self):
        """Print current hit rate analysis"""
        report = self.hit_rate_analyzer.get_detailed_report()
        print(report)

    def export_data(self):
        """Export alert data for analysis"""
        self.hit_rate_analyzer.export_to_csv()
        logger.info("Data exported successfully")


async def main():
    """Main entry point"""
    system = MotionAlertSystem()

    try:
        await system.start()
    except KeyboardInterrupt:
        logger.info("\nShutdown requested by user")
        system.stop()
    except Exception as e:
        logger.error(f"System error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
