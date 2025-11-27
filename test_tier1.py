"""
Test script for Tier 1 screening components
"""
import asyncio
import yaml
from loguru import logger

from database.db_manager import DatabaseManager
from data_pipeline.gmgn_api import GMGNAPI
from data_pipeline.solana_rpc import SolanaRPC
from features.feature_calculator import FeatureCalculator
from alerts.tier1_screener import Tier1Screener


async def test_gmgn_api():
    """Test GMGN API functionality"""
    print("\n" + "="*60)
    print("TEST 1: GMGN API - Holder Count & Token Info")
    print("="*60 + "\n")

    api = GMGNAPI()

    # Get trending tokens
    print("Fetching trending SOL tokens (1h)...")
    trending = api.get_trending_tokens(chain='sol', time_period='1h', limit=5)

    if trending and len(trending) > 0:
        print(f"✅ Found {len(trending)} trending tokens\n")

        for i, token in enumerate(trending[:3], 1):
            parsed = api._parse_token_data(token)
            print(f"{i}. {parsed['symbol']}")
            print(f"   Holders: {parsed['holder_count']:,}")
            print(f"   Market Cap: ${parsed['market_cap']:,.0f}")
            print(f"   Smart Money: {parsed['smart_buy_24h']} buys / {parsed['smart_sell_24h']} sells")
            print()

        # Test filtering
        print("\nSearching tokens matching Tier 1 holder criteria (100+ holders)...")
        matches = api.search_token_by_filters(
            min_holder_count=100,
            min_market_cap=25000,
            max_market_cap=500000
        )
        print(f"✅ Found {len(matches)} tokens with 100+ holders in MC range\n")

        return True
    else:
        print("❌ Failed to fetch trending tokens")
        return False


async def test_solana_rpc():
    """Test Solana RPC functionality"""
    print("\n" + "="*60)
    print("TEST 2: Solana RPC - Holder Distribution")
    print("="*60 + "\n")

    rpc = SolanaRPC()

    # Test with USDC (known token)
    test_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    print(f"Testing with USDC: {test_mint}\n")

    # Get supply
    print("1. Getting token supply...")
    supply = rpc.get_token_supply(test_mint)
    if supply:
        print(f"   ✅ Total supply: {supply:,.0f}\n")
    else:
        print("   ❌ Failed to get supply\n")
        return False

    # Get top holders
    print("2. Getting top 10 holders...")
    concentration = rpc.get_top_holder_concentration(test_mint, top_n=10)

    if concentration:
        print(f"   ✅ Top 10 holders own: {concentration['concentration_pct']:.2f}% of supply")
        print(f"   ✅ Passes <40% check: {concentration['passes_40pct_check']}\n")

        print("   Top 5 holders:")
        for i, holder in enumerate(concentration['holders'][:5], 1):
            print(f"     {i}. {holder['address'][:8]}... : {holder['percentage']:.2f}%")

        print()
        return True
    else:
        print("   ❌ Failed to get holder concentration\n")
        return False


async def test_tier1_screener():
    """Test Tier 1 screener with database"""
    print("\n" + "="*60)
    print("TEST 3: Tier 1 Screener Integration")
    print("="*60 + "\n")

    # Load config
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)

    # Initialize components
    print("Initializing components...")
    db = DatabaseManager(config['database']['sqlite_path'])
    feature_calc = FeatureCalculator(db)
    screener = Tier1Screener(db, feature_calc, config)

    print("✅ Tier 1 screener initialized\n")

    # Print thresholds
    print("Tier 1 Thresholds:")
    for key, value in screener.thresholds.items():
        print(f"  {key}: {value}")

    print("\n" + "-"*60)

    # Get recent tokens
    recent_tokens = db.get_recent_launches(hours=24, limit=10)

    if recent_tokens and len(recent_tokens) > 0:
        print(f"\nTesting with {len(recent_tokens)} recent tokens from database...\n")

        passed_count = 0
        for token in recent_tokens[:5]:  # Test first 5
            print(f"Checking {token.symbol} ({token.mint_address[:8]}...)...")

            result = screener.check_tier1_criteria(token.mint_address)

            if result:
                passed_count += 1
                screener.print_alert_summary(result)
            else:
                print(f"  Did not pass all criteria\n")

        print("="*60)
        print(f"Screening Results: {passed_count}/{min(5, len(recent_tokens))} tokens passed Tier 1")
        print("="*60 + "\n")

        return True
    else:
        print("⚠️  No recent tokens in database to test")
        print("   Run the main system first to collect data\n")
        return False


async def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("                  TIER 1 SCREENING SYSTEM TEST SUITE")
    print("="*70)

    results = []

    # Test 1: GMGN API
    try:
        result = await test_gmgn_api()
        results.append(("GMGN API", result))
    except Exception as e:
        logger.error(f"GMGN API test failed: {e}")
        results.append(("GMGN API", False))

    # Test 2: Solana RPC
    try:
        result = await test_solana_rpc()
        results.append(("Solana RPC", result))
    except Exception as e:
        logger.error(f"Solana RPC test failed: {e}")
        results.append(("Solana RPC", False))

    # Test 3: Tier 1 Screener
    try:
        result = await test_tier1_screener()
        results.append(("Tier 1 Screener", result))
    except Exception as e:
        logger.error(f"Tier 1 Screener test failed: {e}")
        results.append(("Tier 1 Screener", False))

    # Summary
    print("\n" + "="*70)
    print("                         TEST SUMMARY")
    print("="*70)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} | {test_name}")

    total_passed = sum(1 for _, passed in results if passed)
    print(f"\nTotal: {total_passed}/{len(results)} tests passed")
    print("="*70 + "\n")

    if total_passed == len(results):
        print("🎉 All systems operational! Ready to run main.py\n")
    else:
        print("⚠️  Some tests failed. Check errors above.\n")


if __name__ == "__main__":
    asyncio.run(main())
