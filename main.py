"""
Main orchestrator for Pump.fun motion alert system
"""
import asyncio
import yaml
from loguru import logger
from datetime import datetime
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db_manager import DatabaseManager
from data_pipeline.pumpfun_api import PumpFunAPI
from data_pipeline.websocket_monitor import PumpFunWebSocket
from features.feature_calculator import FeatureCalculator
from features.wallet_analyzer import WalletAnalyzer
from alerts.motion_detector import MotionDetector
from labeling.outcome_labeler import OutcomeLabeler
from analysis.hit_rate_analyzer import HitRateAnalyzer


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

        logger.info("Initializing Pump.fun Motion Alert System...")

        # Initialize components
        self.db = DatabaseManager(
            db_path=self.config['database']['sqlite_path'],
            echo=self.config['database'].get('echo_sql', False)
        )

        self.api = PumpFunAPI(base_url=self.config['api']['pumpfun_base_url'])

        self.feature_calc = FeatureCalculator(self.db)

        self.wallet_analyzer = WalletAnalyzer(self.db, self.config)

        self.motion_detector = MotionDetector(
            self.db,
            self.feature_calc,
            self.config,
            on_alert=self.handle_alert
        )

        self.outcome_labeler = OutcomeLabeler(self.db, self.api, self.config)

        self.hit_rate_analyzer = HitRateAnalyzer(self.db)

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

        # You can add custom actions here:
        # - Send notification (Discord, Telegram, etc.)
        # - Execute trade
        # - etc.

    async def start_monitoring(self):
        """Start real-time monitoring via WebSocket"""
        logger.info("Starting real-time monitoring...")

        # Load known profitable wallets
        self.known_wallets = self.wallet_analyzer.get_known_profitable_wallets()
        logger.info(f"Loaded {len(self.known_wallets)} known profitable wallets")

        # Initialize WebSocket
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

    async def start(self):
        """Start the entire system"""
        logger.info("="*60)
        logger.info("Starting Pump.fun Motion Alert System")
        logger.info("="*60)

        # Print stats
        stats = self.db.get_stats()
        logger.info(f"Database stats: {stats}")

        # Start background tasks
        tasks = [
            asyncio.create_task(self.start_monitoring()),
            asyncio.create_task(self.run_labeling_loop()),
            asyncio.create_task(self.run_wallet_update_loop()),
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
