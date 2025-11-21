"""
Pump.fun API client for fetching token and trade data
"""
import requests
from typing import Optional, Dict, Any, List
from loguru import logger
import time


class PumpFunAPI:
    """Client for Pump.fun REST API"""

    def __init__(self, base_url: str = "https://client-api-2-74b1891ee9f9.herokuapp.com"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make API request with error handling"""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return None

    def get_coin_data(self, mint_address: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed data for a specific coin

        Args:
            mint_address: The token mint address

        Returns:
            Dict with token data or None
        """
        data = self._make_request(f"/coins/{mint_address}")
        if data:
            logger.debug(f"Fetched data for {mint_address}")
        return data

    def get_latest_trades(self, mint_address: str, limit: int = 100) -> Optional[List[Dict]]:
        """
        Get latest trades for a token

        Args:
            mint_address: The token mint address
            limit: Number of trades to fetch

        Returns:
            List of trade dicts or None
        """
        data = self._make_request(f"/trades/latest/{mint_address}", params={'limit': limit})
        return data if data else None

    def get_all_coins(
        self,
        limit: int = 50,
        offset: int = 0,
        sort: str = "created_timestamp",
        order: str = "DESC",
        include_nsfw: bool = False
    ) -> Optional[List[Dict]]:
        """
        Get list of all coins with pagination

        Args:
            limit: Number of results
            offset: Pagination offset
            sort: Sort field (created_timestamp, market_cap, etc.)
            order: ASC or DESC
            include_nsfw: Include NSFW tokens

        Returns:
            List of coin dicts or None
        """
        params = {
            'limit': limit,
            'offset': offset,
            'sort': sort,
            'order': order,
            'includeNsfw': include_nsfw
        }
        data = self._make_request("/coins", params=params)
        return data if data else None

    def get_king_of_hill(self) -> Optional[Dict]:
        """Get current King of the Hill token"""
        return self._make_request("/king-of-the-hill")

    def search_coins(self, query: str) -> Optional[List[Dict]]:
        """
        Search for coins by name or symbol

        Args:
            query: Search term

        Returns:
            List of matching coins or None
        """
        return self._make_request("/search", params={'q': query})

    def get_token_metadata(self, mint_address: str) -> Dict[str, Any]:
        """
        Parse token data into standardized format for database

        Args:
            mint_address: Token mint address

        Returns:
            Standardized token metadata dict
        """
        data = self.get_coin_data(mint_address)
        if not data:
            return {}

        return {
            'mint_address': mint_address,
            'name': data.get('name', 'Unknown'),
            'symbol': data.get('symbol', 'UNKNOWN'),
            'description': data.get('description', ''),
            'creator_address': data.get('creator', ''),
            'bonding_curve': data.get('bonding_curve', ''),
            'initial_market_cap': data.get('usd_market_cap', 0),
            'metadata': {
                'twitter': data.get('twitter'),
                'telegram': data.get('telegram'),
                'website': data.get('website'),
                'image_uri': data.get('image_uri'),
                'show_name': data.get('show_name', True),
                'king_of_the_hill_timestamp': data.get('king_of_the_hill_timestamp'),
                'nsfw': data.get('nsfw', False),
            }
        }

    def parse_trade_data(self, trade: Dict) -> Dict[str, Any]:
        """
        Parse trade data into standardized format

        Args:
            trade: Raw trade data from API

        Returns:
            Standardized transaction dict
        """
        return {
            'signature': trade.get('signature', ''),
            'mint_address': trade.get('mint', ''),
            'wallet_address': trade.get('user', ''),
            'is_buy': trade.get('is_buy', True),
            'sol_amount': trade.get('sol_amount', 0) / 1e9,  # Convert lamports to SOL
            'token_amount': trade.get('token_amount', 0),
            'market_cap_at_time': trade.get('market_cap_sol', 0),
        }

    def get_recent_launches(self, hours: int = 1, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recently launched tokens

        Args:
            hours: Number of hours to look back
            limit: Maximum number of tokens

        Returns:
            List of token metadata dicts
        """
        all_coins = self.get_all_coins(limit=limit, sort="created_timestamp", order="DESC")
        if not all_coins:
            return []

        # Filter by time if needed
        recent_tokens = []
        current_time = time.time()
        cutoff = current_time - (hours * 3600)

        for coin in all_coins:
            created = coin.get('created_timestamp', 0)
            if created >= cutoff:
                metadata = {
                    'mint_address': coin.get('mint', ''),
                    'name': coin.get('name', 'Unknown'),
                    'symbol': coin.get('symbol', 'UNKNOWN'),
                    'description': coin.get('description', ''),
                    'creator_address': coin.get('creator', ''),
                    'bonding_curve': coin.get('bonding_curve', ''),
                    'initial_market_cap': coin.get('usd_market_cap', 0),
                    'token_metadata': coin
                }
                recent_tokens.append(metadata)

        logger.info(f"Found {len(recent_tokens)} recent launches")
        return recent_tokens
