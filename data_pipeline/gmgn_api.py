"""
GMGN.ai API client for token holder data and market intelligence
"""
import requests
from typing import Optional, Dict, Any, List
from loguru import logger
import time


class GMGNAPI:
    """Client for GMGN.ai public API endpoints"""

    def __init__(self, base_url: str = "https://gmgn.ai"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Referer': 'https://gmgn.ai/',
            'Origin': 'https://gmgn.ai'
        })
        self.last_request_time = 0
        self.min_request_interval = 2.0  # 2 seconds between requests to be respectful

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Make API request with rate limiting and error handling

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Response JSON or None on error
        """
        # Rate limiting - be respectful to avoid getting blocked
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)

        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=15)
            self.last_request_time = time.time()

            response.raise_for_status()
            data = response.json()

            # GMGN API typically returns {code: 0, data: {...}}
            if isinstance(data, dict) and data.get('code') == 0:
                return data.get('data')

            return data

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.warning(f"GMGN API rate limit hit, backing off...")
                time.sleep(5)
            else:
                logger.error(f"GMGN API HTTP error: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"GMGN API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"GMGN API unexpected error: {e}")
            return None

    def get_token_info(self, mint_address: str, chain: str = "sol") -> Optional[Dict[str, Any]]:
        """
        Get detailed token information including holder count

        Args:
            mint_address: Token mint address
            chain: Blockchain (sol, eth, base, bsc)

        Returns:
            Dict with token info or None
        """
        # Try to find token in trending lists first (more reliable)
        for time_period in ['1h', '6h', '24h']:
            trending = self.get_trending_tokens(
                chain=chain,
                time_period=time_period,
                limit=200
            )

            if trending:
                for token in trending:
                    if token.get('address', '').lower() == mint_address.lower():
                        logger.info(f"Found {mint_address} in trending {time_period} list")
                        return self._parse_token_data(token)

        logger.debug(f"Token {mint_address} not found in GMGN trending lists")
        return None

    def get_trending_tokens(
        self,
        chain: str = "sol",
        time_period: str = "1h",
        orderby: str = "swaps",
        limit: int = 50
    ) -> Optional[List[Dict]]:
        """
        Get trending tokens list

        Args:
            chain: Blockchain (sol, eth, base, bsc, tron)
            time_period: Time window (1m, 5m, 1h, 6h, 24h)
            orderby: Sort criteria (volume, marketcap, swaps, holder_count, liquidity)
            limit: Number of results (max ~200)

        Returns:
            List of token dicts or None
        """
        endpoint = f"/defi/quotation/v1/rank/{chain}/swaps/{time_period}"
        params = {
            'orderby': orderby,
            'direction': 'desc',
            'limit': limit
        }

        data = self._make_request(endpoint, params=params)

        if data and isinstance(data, dict):
            # Response format: {rank: [...], update_time: ...}
            tokens = data.get('rank', [])
            logger.info(f"Retrieved {len(tokens)} trending tokens from GMGN")
            return tokens

        return None

    def search_token_by_filters(
        self,
        chain: str = "sol",
        min_holder_count: int = 100,
        min_market_cap: float = 25000,
        max_market_cap: float = 500000,
        time_period: str = "1h"
    ) -> List[Dict[str, Any]]:
        """
        Search for tokens matching specific criteria

        Args:
            chain: Blockchain
            min_holder_count: Minimum unique holders
            min_market_cap: Minimum market cap in USD
            max_market_cap: Maximum market cap in USD
            time_period: Activity time window

        Returns:
            List of matching tokens
        """
        trending = self.get_trending_tokens(
            chain=chain,
            time_period=time_period,
            orderby='holder_count',
            limit=200
        )

        if not trending:
            return []

        matching = []
        for token in trending:
            parsed = self._parse_token_data(token)

            holder_count = parsed.get('holder_count', 0)
            market_cap = parsed.get('market_cap', 0)

            if (holder_count >= min_holder_count and
                min_market_cap <= market_cap <= max_market_cap):
                matching.append(parsed)

        logger.info(f"Found {len(matching)} tokens matching filters")
        return matching

    def _parse_token_data(self, token: Dict) -> Dict[str, Any]:
        """
        Parse GMGN token data into standardized format

        Args:
            token: Raw token data from GMGN

        Returns:
            Standardized token dict
        """
        return {
            'mint_address': token.get('address', ''),
            'symbol': token.get('symbol', 'UNKNOWN'),
            'name': token.get('name', ''),
            'chain': token.get('chain', 'sol'),

            # Market data
            'market_cap': float(token.get('market_cap', 0) or 0),
            'price': float(token.get('price', 0) or 0),
            'liquidity': float(token.get('liquidity', 0) or 0),

            # Holder data
            'holder_count': int(token.get('holder_count', 0) or 0),

            # Volume data
            'volume_24h': float(token.get('volume_24h', 0) or 0),
            'volume_change_24h': float(token.get('volume_change_24h', 0) or 0),

            # Activity metrics
            'swaps_5m': int(token.get('swaps_5m', 0) or 0),
            'swaps_1h': int(token.get('swaps_1h', 0) or 0),
            'swaps_24h': int(token.get('swaps_24h', 0) or 0),

            # Smart money
            'smart_buy_24h': int(token.get('smart_buy_24h', 0) or 0),
            'smart_sell_24h': int(token.get('smart_sell_24h', 0) or 0),

            # Timing
            'open_timestamp': token.get('open_timestamp', 0),
            'creation_timestamp': token.get('creation_timestamp', 0),

            # Raw data
            'raw_data': token
        }

    def get_holder_count(self, mint_address: str) -> Optional[int]:
        """
        Get holder count for a specific token

        Args:
            mint_address: Token mint address

        Returns:
            Holder count or None if not found
        """
        token_info = self.get_token_info(mint_address)
        if token_info:
            return token_info.get('holder_count')
        return None

    def get_smart_money_activity(self, mint_address: str) -> Optional[Dict[str, int]]:
        """
        Get smart money buy/sell activity

        Args:
            mint_address: Token mint address

        Returns:
            Dict with smart_buy_24h and smart_sell_24h counts
        """
        token_info = self.get_token_info(mint_address)
        if token_info:
            return {
                'smart_buy_24h': token_info.get('smart_buy_24h', 0),
                'smart_sell_24h': token_info.get('smart_sell_24h', 0),
                'smart_net': token_info.get('smart_buy_24h', 0) - token_info.get('smart_sell_24h', 0)
            }
        return None


# Test function
def test_gmgn_api():
    """Test GMGN API functionality"""
    api = GMGNAPI()

    print("\n=== Testing GMGN API ===\n")

    # Test 1: Get trending tokens
    print("1. Fetching trending SOL tokens (1h)...")
    trending = api.get_trending_tokens(chain='sol', time_period='1h', limit=10)

    if trending:
        print(f"   Found {len(trending)} trending tokens")
        for i, token in enumerate(trending[:3], 1):
            parsed = api._parse_token_data(token)
            print(f"   {i}. {parsed['symbol']} - Holders: {parsed['holder_count']}, MC: ${parsed['market_cap']:,.0f}")

    # Test 2: Search with filters
    print("\n2. Searching tokens with filters...")
    matches = api.search_token_by_filters(
        min_holder_count=100,
        min_market_cap=25000,
        max_market_cap=500000
    )
    print(f"   Found {len(matches)} tokens matching Tier 1 criteria")

    if matches:
        for token in matches[:5]:
            print(f"   - {token['symbol']}: {token['holder_count']} holders, ${token['market_cap']:,.0f} MC")

    print("\n=== Test Complete ===\n")


if __name__ == "__main__":
    test_gmgn_api()
