"""
Solana RPC client for on-chain token data queries
"""
import requests
from typing import Optional, Dict, Any, List
from loguru import logger
import time


class SolanaRPC:
    """Client for Solana JSON-RPC API"""

    def __init__(self, rpc_url: str = "https://api.mainnet-beta.solana.com"):
        """
        Initialize Solana RPC client

        Args:
            rpc_url: Solana RPC endpoint
                     Public: https://api.mainnet-beta.solana.com (limited)
                     Helius: https://mainnet.helius-rpc.com/?api-key=YOUR_KEY (recommended)
                     QuickNode: Your QuickNode endpoint
        """
        self.rpc_url = rpc_url
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json'
        })
        self.last_request_time = 0
        self.min_request_interval = 0.5  # 500ms between requests

    def _make_request(self, method: str, params: List[Any]) -> Optional[Dict]:
        """
        Make JSON-RPC request

        Args:
            method: RPC method name
            params: Method parameters

        Returns:
            Response result or None on error
        """
        # Rate limiting
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params
        }

        try:
            response = self.session.post(self.rpc_url, json=payload, timeout=15)
            self.last_request_time = time.time()

            response.raise_for_status()
            data = response.json()

            if 'error' in data:
                logger.error(f"Solana RPC error: {data['error']}")
                return None

            return data.get('result')

        except requests.exceptions.RequestException as e:
            logger.error(f"Solana RPC request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Solana RPC unexpected error: {e}")
            return None

    def get_token_supply(self, mint_address: str) -> Optional[float]:
        """
        Get total supply of a token

        Args:
            mint_address: Token mint address

        Returns:
            Total supply (adjusted for decimals) or None
        """
        result = self._make_request("getTokenSupply", [mint_address])

        if result and 'value' in result:
            ui_amount = result['value'].get('uiAmount')
            if ui_amount is not None:
                return float(ui_amount)

        return None

    def get_token_largest_accounts(
        self,
        mint_address: str,
        limit: int = 20
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get largest token holders

        Args:
            mint_address: Token mint address
            limit: Number of accounts to return (max 20)

        Returns:
            List of {address, amount, decimals, uiAmount} or None
        """
        result = self._make_request("getTokenLargestAccounts", [mint_address])

        if result and 'value' in result:
            accounts = result['value'][:limit]
            logger.debug(f"Retrieved {len(accounts)} largest holders for {mint_address[:8]}...")
            return accounts

        return None

    def get_top_holder_concentration(
        self,
        mint_address: str,
        top_n: int = 10
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate what percentage of supply the top N holders own

        Args:
            mint_address: Token mint address
            top_n: Number of top holders to check (default 10)

        Returns:
            Dict with concentration metrics or None
        """
        # Get total supply
        total_supply = self.get_token_supply(mint_address)
        if not total_supply:
            logger.warning(f"Could not get supply for {mint_address}")
            return None

        # Get largest holders
        largest = self.get_token_largest_accounts(mint_address, limit=top_n)
        if not largest:
            logger.warning(f"Could not get largest holders for {mint_address}")
            return None

        # Calculate concentration
        top_n_supply = sum(float(holder.get('uiAmount', 0)) for holder in largest[:top_n])
        concentration_pct = (top_n_supply / total_supply) * 100

        # Get individual holder percentages
        holder_percentages = [
            {
                'address': holder.get('address'),
                'amount': holder.get('uiAmount'),
                'percentage': (float(holder.get('uiAmount', 0)) / total_supply) * 100
            }
            for holder in largest[:top_n]
        ]

        result = {
            'mint_address': mint_address,
            'total_supply': total_supply,
            'top_n': top_n,
            'top_n_supply': top_n_supply,
            'concentration_pct': concentration_pct,
            'holders': holder_percentages,
            'passes_40pct_check': concentration_pct < 40.0
        }

        logger.info(f"Top {top_n} holders own {concentration_pct:.2f}% of {mint_address[:8]}...")

        return result

    def get_token_account_count(self, mint_address: str) -> Optional[int]:
        """
        Get approximate number of token holders (may be slow/expensive)

        Args:
            mint_address: Token mint address

        Returns:
            Approximate holder count or None

        Note: This uses getProgramAccounts which can be expensive.
              Prefer using gmgn.ai for holder count when possible.
        """
        # This is a heavy query - use sparingly
        params = [
            "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",  # Token Program ID
            {
                "encoding": "jsonParsed",
                "filters": [
                    {
                        "dataSize": 165  # Token account size
                    },
                    {
                        "memcmp": {
                            "offset": 0,
                            "bytes": mint_address
                        }
                    }
                ]
            }
        ]

        result = self._make_request("getProgramAccounts", params)

        if result and isinstance(result, list):
            # Filter out empty accounts
            non_zero_accounts = [
                acc for acc in result
                if acc.get('account', {}).get('data', {}).get('parsed', {})
                   .get('info', {}).get('tokenAmount', {}).get('uiAmount', 0) > 0
            ]
            holder_count = len(non_zero_accounts)
            logger.info(f"Found {holder_count} holders for {mint_address[:8]}...")
            return holder_count

        return None

    def check_mint_and_freeze_authority(self, mint_address: str) -> Optional[Dict[str, Any]]:
        """
        Check if mint authority and freeze authority are disabled (security check)

        Args:
            mint_address: Token mint address

        Returns:
            Dict with authority status or None
        """
        result = self._make_request("getAccountInfo", [
            mint_address,
            {"encoding": "jsonParsed"}
        ])

        if result and 'value' in result:
            data = result['value'].get('data', {})
            if isinstance(data, dict) and 'parsed' in data:
                info = data['parsed'].get('info', {})

                return {
                    'mint_address': mint_address,
                    'mint_authority': info.get('mintAuthority'),
                    'freeze_authority': info.get('freezeAuthority'),
                    'mint_authority_disabled': info.get('mintAuthority') is None,
                    'freeze_authority_disabled': info.get('freezeAuthority') is None,
                    'is_immutable': (info.get('mintAuthority') is None and
                                   info.get('freezeAuthority') is None)
                }

        return None


# Test function
def test_solana_rpc():
    """Test Solana RPC functionality"""
    rpc = SolanaRPC()

    print("\n=== Testing Solana RPC ===\n")

    # Use a known token for testing (USDC)
    test_mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    print(f"Testing with USDC mint: {test_mint}\n")

    # Test 1: Get token supply
    print("1. Getting token supply...")
    supply = rpc.get_token_supply(test_mint)
    if supply:
        print(f"   Total supply: {supply:,.0f}")

    # Test 2: Get largest holders
    print("\n2. Getting top 10 holders...")
    largest = rpc.get_token_largest_accounts(test_mint, limit=10)
    if largest:
        for i, holder in enumerate(largest[:5], 1):
            print(f"   {i}. {holder['address'][:8]}... : {holder['uiAmount']:,.0f}")

    # Test 3: Calculate concentration
    print("\n3. Calculating top 10 holder concentration...")
    concentration = rpc.get_top_holder_concentration(test_mint, top_n=10)
    if concentration:
        print(f"   Top 10 holders own: {concentration['concentration_pct']:.2f}% of supply")
        print(f"   Passes 40% check: {concentration['passes_40pct_check']}")

    # Test 4: Check authorities
    print("\n4. Checking mint/freeze authorities...")
    authorities = rpc.check_mint_and_freeze_authority(test_mint)
    if authorities:
        print(f"   Mint authority disabled: {authorities['mint_authority_disabled']}")
        print(f"   Freeze authority disabled: {authorities['freeze_authority_disabled']}")
        print(f"   Is immutable: {authorities['is_immutable']}")

    print("\n=== Test Complete ===\n")


if __name__ == "__main__":
    test_solana_rpc()
