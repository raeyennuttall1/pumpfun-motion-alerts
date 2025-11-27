"""
Tier 1 screening logic for advanced token filtering
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
from loguru import logger

from database.db_manager import DatabaseManager
from features.feature_calculator import FeatureCalculator
from data_pipeline.gmgn_api import GMGNAPI
from data_pipeline.solana_rpc import SolanaRPC


class Tier1Screener:
    """
    Advanced token screening with Tier 1 criteria:
    ✓ Market cap $25-$500K
    ✓ 3+ smart wallets entered (>60% win rate)
    ✓ Top 10 holders <40%
    ✓ Volume/MC ratio 0.5-1.2x
    ✓ Active for 1 hour
    ✓ 100+ unique holders
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        feature_calc: FeatureCalculator,
        config: Dict[str, Any],
        gmgn_api: Optional[GMGNAPI] = None,
        solana_rpc: Optional[SolanaRPC] = None,
        on_tier1_alert: Optional[Callable] = None
    ):
        """
        Initialize Tier 1 screener

        Args:
            db_manager: Database manager
            feature_calc: Feature calculator
            config: Configuration dict
            gmgn_api: GMGN API client (optional, will create if None)
            solana_rpc: Solana RPC client (optional, will create if None)
            on_tier1_alert: Callback when Tier 1 alert triggers
        """
        self.db = db_manager
        self.feature_calc = feature_calc
        self.config = config
        self.on_tier1_alert = on_tier1_alert

        # Initialize API clients
        self.gmgn = gmgn_api or GMGNAPI()
        self.solana = solana_rpc or SolanaRPC(
            rpc_url=config.get('api', {}).get('solana_rpc', 'https://api.mainnet-beta.solana.com')
        )

        # Load thresholds from config
        tier1_config = config.get('tier1_screening', {})
        self.thresholds = {
            'min_market_cap': tier1_config.get('min_market_cap', 25000),
            'max_market_cap': tier1_config.get('max_market_cap', 500000),
            'min_smart_wallets': tier1_config.get('min_smart_wallets', 3),
            'max_top10_holders_pct': tier1_config.get('max_top10_holders_pct', 40.0),
            'min_volume_mc_ratio': tier1_config.get('min_volume_mc_ratio', 0.5),
            'max_volume_mc_ratio': tier1_config.get('max_volume_mc_ratio', 1.2),
            'min_active_minutes': tier1_config.get('min_active_minutes', 60),
            'min_holder_count': tier1_config.get('min_holder_count', 100),
        }

        # Track tokens already alerted
        self.alerted_tokens = set()

        logger.info("Tier 1 Screener initialized with thresholds:")
        for key, value in self.thresholds.items():
            logger.info(f"  {key}: {value}")

    def check_tier1_criteria(self, mint_address: str) -> Optional[Dict[str, Any]]:
        """
        Check if token meets all Tier 1 criteria

        Args:
            mint_address: Token mint address

        Returns:
            Alert data dict if all criteria met, None otherwise
        """
        # Prevent duplicate alerts
        if mint_address in self.alerted_tokens:
            return None

        logger.info(f"Checking Tier 1 criteria for {mint_address[:8]}...")

        # Calculate all features
        features = self.feature_calc.calculate_features(mint_address)

        # Get known profitable wallets
        known_wallets = self._get_known_wallets()
        wallet_features = self.feature_calc.calculate_wallet_features(
            mint_address,
            known_wallets,
            window_minutes=60  # Check last hour
        )
        features.update(wallet_features)

        # Run all criteria checks
        criteria_results = {
            'mint_address': mint_address,
            'timestamp': datetime.utcnow(),
        }

        # 1. Market cap check
        market_cap = features.get('current_market_cap', 0)
        mc_check = self.thresholds['min_market_cap'] <= market_cap <= self.thresholds['max_market_cap']
        criteria_results['market_cap'] = market_cap
        criteria_results['market_cap_check'] = mc_check

        if not mc_check:
            logger.debug(f"  ❌ Market cap ${market_cap:,.0f} outside range")
            return None

        # 2. Token age check
        token_age_seconds = self.feature_calc.get_token_age_seconds(mint_address)
        token_age_minutes = token_age_seconds / 60
        age_check = token_age_minutes >= self.thresholds['min_active_minutes']
        criteria_results['age_minutes'] = token_age_minutes
        criteria_results['age_check'] = age_check

        if not age_check:
            logger.debug(f"  ❌ Token age {token_age_minutes:.1f}m < {self.thresholds['min_active_minutes']}m")
            return None

        # 3. Smart wallets check
        smart_wallet_count = wallet_features.get('known_wallet_count', 0)
        smart_check = smart_wallet_count >= self.thresholds['min_smart_wallets']
        criteria_results['smart_wallet_count'] = smart_wallet_count
        criteria_results['smart_wallet_check'] = smart_check

        if not smart_check:
            logger.debug(f"  ❌ Smart wallets {smart_wallet_count} < {self.thresholds['min_smart_wallets']}")
            return None

        # 4. Volume/MC ratio check
        volume_mc_ratio = features.get('volume_mc_ratio_1h', 0)
        ratio_check = (self.thresholds['min_volume_mc_ratio'] <= volume_mc_ratio <=
                      self.thresholds['max_volume_mc_ratio'])
        criteria_results['volume_mc_ratio'] = volume_mc_ratio
        criteria_results['volume_mc_ratio_check'] = ratio_check

        if not ratio_check:
            logger.debug(f"  ❌ Volume/MC ratio {volume_mc_ratio:.2f} outside range")
            return None

        # 5. Holder count check (from GMGN)
        holder_count = self._get_holder_count(mint_address)
        holder_check = holder_count >= self.thresholds['min_holder_count'] if holder_count else False
        criteria_results['holder_count'] = holder_count
        criteria_results['holder_count_check'] = holder_check

        if not holder_check:
            logger.debug(f"  ❌ Holder count {holder_count} < {self.thresholds['min_holder_count']}")
            return None

        # 6. Top 10 holders concentration check (from Solana RPC)
        concentration = self._get_holder_concentration(mint_address)
        concentration_pct = concentration.get('concentration_pct', 100) if concentration else 100
        concentration_check = concentration_pct < self.thresholds['max_top10_holders_pct']
        criteria_results['top10_holders_pct'] = concentration_pct
        criteria_results['concentration_check'] = concentration_check

        if not concentration_check:
            logger.debug(f"  ❌ Top 10 holders own {concentration_pct:.1f}% (max {self.thresholds['max_top10_holders_pct']}%)")
            return None

        # ALL CRITERIA MET!
        logger.success(f"✅ TIER 1 ALERT: {mint_address[:8]}... passed all criteria!")

        # Mark as alerted
        self.alerted_tokens.add(mint_address)

        # Prepare alert data
        alert_data = {
            **criteria_results,
            'all_features': features,
            'concentration_details': concentration,
            'alert_type': 'tier1'
        }

        # Save to database
        self._save_tier1_alert(alert_data)

        # Trigger callback
        if self.on_tier1_alert:
            self.on_tier1_alert(alert_data)

        return alert_data

    def _get_known_wallets(self) -> list:
        """Get list of known profitable wallet addresses"""
        wallets = self.db.get_known_profitable_wallets()
        return [w['wallet_address'] for w in wallets]

    def _get_holder_count(self, mint_address: str) -> Optional[int]:
        """
        Get holder count from GMGN API

        Args:
            mint_address: Token mint address

        Returns:
            Holder count or None
        """
        try:
            holder_count = self.gmgn.get_holder_count(mint_address)
            if holder_count:
                logger.debug(f"  GMGN holder count: {holder_count}")
                return holder_count
        except Exception as e:
            logger.warning(f"Failed to get holder count from GMGN: {e}")

        return None

    def _get_holder_concentration(self, mint_address: str) -> Optional[Dict[str, Any]]:
        """
        Get top holder concentration from Solana RPC

        Args:
            mint_address: Token mint address

        Returns:
            Concentration dict or None
        """
        try:
            concentration = self.solana.get_top_holder_concentration(mint_address, top_n=10)
            if concentration:
                logger.debug(f"  Top 10 holders: {concentration['concentration_pct']:.1f}%")
                return concentration
        except Exception as e:
            logger.warning(f"Failed to get holder concentration: {e}")

        return None

    def _save_tier1_alert(self, alert_data: Dict[str, Any]):
        """
        Save Tier 1 alert to database

        Args:
            alert_data: Alert data to save
        """
        try:
            # Create alert record
            alert_record = {
                'mint_address': alert_data['mint_address'],
                'alert_timestamp': alert_data['timestamp'],
                'trigger_features': alert_data['all_features'],
                'market_cap_at_alert': alert_data['market_cap'],
                'price_at_alert': alert_data['all_features'].get('current_price_sol', 0),
                'bonding_curve_pct': alert_data['all_features'].get('bonding_curve_pct', 0),
            }

            self.db.add_alert(alert_record)
            logger.info(f"Saved Tier 1 alert to database")

        except Exception as e:
            logger.error(f"Failed to save Tier 1 alert: {e}")

    def print_alert_summary(self, alert_data: Dict[str, Any]):
        """
        Print formatted alert summary

        Args:
            alert_data: Alert data
        """
        token = self.db.get_token(alert_data['mint_address'])
        symbol = token['symbol'] if token else 'UNKNOWN'
        name = token['name'] if token else 'Unknown Token'

        print("\n" + "="*60)
        print("          🎯 TIER 1 ALERT TRIGGERED 🎯")
        print("="*60)
        print(f"\nToken: {symbol} ({name})")
        print(f"Mint: {alert_data['mint_address']}")
        print(f"\n📊 Tier 1 Criteria (ALL MET):")
        print(f"   ✅ Market Cap: ${alert_data['market_cap']:,.0f}")
        print(f"   ✅ Active For: {alert_data['age_minutes']:.1f} minutes")
        print(f"   ✅ Smart Wallets: {alert_data['smart_wallet_count']}")
        print(f"   ✅ Volume/MC Ratio: {alert_data['volume_mc_ratio']:.2f}x")
        print(f"   ✅ Holder Count: {alert_data['holder_count']}")
        print(f"   ✅ Top 10 Holders: {alert_data['top10_holders_pct']:.1f}%")
        print(f"\n⏰ Time: {alert_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("="*60 + "\n")


# Test function
def test_tier1_screener():
    """Test Tier 1 screener (requires database and config)"""
    import yaml
    from database.db_manager import DatabaseManager

    print("\n=== Testing Tier 1 Screener ===\n")

    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Initialize components
    db = DatabaseManager(config['database']['sqlite_path'])
    feature_calc = FeatureCalculator(db)
    screener = Tier1Screener(db, feature_calc, config)

    # Get a recent token to test
    recent_tokens = db.get_recent_launches(hours=24, limit=5)

    if recent_tokens:
        print(f"Testing with {len(recent_tokens)} recent tokens...\n")
        for token in recent_tokens:
            mint = token.mint_address
            result = screener.check_tier1_criteria(mint)

            if result:
                screener.print_alert_summary(result)
            else:
                print(f"Token {token.symbol} did not pass Tier 1 screening")
    else:
        print("No recent tokens found in database")

    print("\n=== Test Complete ===\n")


if __name__ == "__main__":
    test_tier1_screener()
