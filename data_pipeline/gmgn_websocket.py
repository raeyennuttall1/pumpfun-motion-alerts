"""
GMGN.ai WebSocket monitor for real-time token data
"""
import asyncio
import json
import websockets
from typing import Callable, Optional, Dict
from loguru import logger
from datetime import datetime


class GMGNWebSocket:
    """WebSocket client for GMGN.ai real-time data"""

    def __init__(
        self,
        websocket_url: str = "wss://gmgn.ai/ws",
        chain: str = "sol",
        on_new_token: Optional[Callable] = None,
        on_trade: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        """
        Initialize GMGN WebSocket monitor

        Args:
            websocket_url: WebSocket endpoint
            chain: Blockchain (sol, eth, base, bsc)
            on_new_token: Callback for new token events
            on_trade: Callback for trade events
            on_error: Callback for errors
        """
        self.websocket_url = websocket_url
        self.chain = chain
        self.on_new_token = on_new_token
        self.on_trade = on_trade
        self.on_error = on_error
        self.websocket = None
        self.running = False
        self.reconnect_delay = 5
        self.max_reconnect_delay = 60
        self.subscribed_tokens = set()

    async def connect(self):
        """Establish WebSocket connection"""
        try:
            # Note: GMGN WebSocket may require authentication or different connection method
            self.websocket = await websockets.connect(
                self.websocket_url,
                ping_interval=20,
                ping_timeout=10
            )
            logger.info(f"GMGN WebSocket connected to {self.websocket_url}")
            return True
        except Exception as e:
            logger.error(f"GMGN WebSocket connection failed: {e}")
            if self.on_error:
                await self.on_error(e)
            return False

    async def subscribe_token_launches(self):
        """Subscribe to new token launch events"""
        if not self.websocket:
            logger.error("WebSocket not connected")
            return

        subscription = {
            "type": "subscribe",
            "channel": "token_launch",
            "chain": self.chain
        }

        try:
            await self.websocket.send(json.dumps(subscription))
            logger.info(f"Subscribed to {self.chain} token launches")
        except Exception as e:
            logger.error(f"Failed to subscribe to token launches: {e}")

    async def subscribe_new_pools(self):
        """Subscribe to new pool creation events"""
        if not self.websocket:
            logger.error("WebSocket not connected")
            return

        subscription = {
            "type": "subscribe",
            "channel": "new_pools",
            "chain": self.chain
        }

        try:
            await self.websocket.send(json.dumps(subscription))
            logger.info(f"Subscribed to {self.chain} new pools")
        except Exception as e:
            logger.error(f"Failed to subscribe to new pools: {e}")

    async def subscribe_pair_updates(self, mint_address: Optional[str] = None):
        """
        Subscribe to trading pair updates

        Args:
            mint_address: Specific token to monitor (optional)
        """
        if not self.websocket:
            logger.error("WebSocket not connected")
            return

        subscription = {
            "type": "subscribe",
            "channel": "pair_update",
            "chain": self.chain
        }

        if mint_address:
            subscription["address"] = mint_address
            self.subscribed_tokens.add(mint_address)

        try:
            await self.websocket.send(json.dumps(subscription))
            logger.debug(f"Subscribed to pair updates" + (f" for {mint_address[:8]}..." if mint_address else ""))
        except Exception as e:
            logger.error(f"Failed to subscribe to pair updates: {e}")

    async def unsubscribe_token(self, mint_address: str):
        """Unsubscribe from specific token updates"""
        if not self.websocket:
            return

        if mint_address in self.subscribed_tokens:
            self.subscribed_tokens.remove(mint_address)

        unsubscription = {
            "type": "unsubscribe",
            "channel": "pair_update",
            "chain": self.chain,
            "address": mint_address
        }

        try:
            await self.websocket.send(json.dumps(unsubscription))
            logger.debug(f"Unsubscribed from {mint_address[:8]}...")
        except Exception as e:
            logger.error(f"Failed to unsubscribe: {e}")

    async def handle_message(self, message: str):
        """
        Process incoming WebSocket message

        Args:
            message: Raw JSON message string
        """
        try:
            data = json.loads(message)

            # Determine message type
            channel = data.get('channel') or data.get('type')

            if channel == 'token_launch' or channel == 'new_pool':
                await self.handle_new_token(data)

            elif channel == 'pair_update':
                await self.handle_trade(data)

            else:
                logger.debug(f"Unknown GMGN message type: {channel}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse GMGN message: {e}")
        except Exception as e:
            logger.error(f"Error handling GMGN message: {e}")
            if self.on_error:
                await self.on_error(e)

    async def handle_new_token(self, data: Dict):
        """Handle new token launch event"""
        try:
            # Parse GMGN token launch data
            token_info = {
                'mint_address': data.get('address') or data.get('token_address') or '',
                'name': data.get('name', 'Unknown'),
                'symbol': data.get('symbol', 'UNKNOWN'),
                'description': data.get('description', ''),
                'creator_address': data.get('creator') or '',
                'bonding_curve': '',  # GMGN may not provide this
                'initial_market_cap': float(data.get('market_cap', 0) or 0),
                'created_timestamp': datetime.utcnow(),
                'metadata': data
            }

            logger.info(f"New token from GMGN: {token_info['symbol']} ({token_info['mint_address'][:8]}...)")

            if self.on_new_token:
                await self.on_new_token(token_info)

        except Exception as e:
            logger.error(f"Error processing new token from GMGN: {e}")

    async def handle_trade(self, data: Dict):
        """Handle trade/pair update event"""
        try:
            # GMGN provides aggregated pair data, not individual trades
            # We'll simulate trade format for compatibility

            mint_address = data.get('address') or data.get('token_address') or ''

            # Extract price and volume changes to infer buy/sell activity
            price_change = data.get('price_change_5m', 0) or 0
            volume_5m = data.get('volume_5m', 0) or 0

            # Create trade-like info from pair update
            trade_info = {
                'signature': f"gmgn_{mint_address}_{datetime.utcnow().timestamp()}",
                'mint_address': mint_address,
                'wallet_address': '',  # GMGN doesn't provide individual wallet
                'is_buy': price_change > 0,  # Infer from price movement
                'sol_amount': volume_5m / 10 if volume_5m > 0 else 0,  # Approximate
                'token_amount': 0,
                'timestamp': datetime.utcnow(),
                'market_cap_at_time': float(data.get('market_cap', 0) or 0),

                # Additional GMGN data
                'price': float(data.get('price', 0) or 0),
                'liquidity': float(data.get('liquidity', 0) or 0),
                'holder_count': int(data.get('holder_count', 0) or 0),
                'volume_24h': float(data.get('volume_24h', 0) or 0),
            }

            if self.on_trade:
                await self.on_trade(trade_info)

        except Exception as e:
            logger.error(f"Error processing trade from GMGN: {e}")

    async def listen(self):
        """Main listening loop"""
        self.running = True
        reconnect_delay = self.reconnect_delay

        while self.running:
            try:
                # Connect if not connected
                if not self.websocket:
                    connected = await self.connect()
                    if not connected:
                        await asyncio.sleep(reconnect_delay)
                        reconnect_delay = min(reconnect_delay * 2, self.max_reconnect_delay)
                        continue

                    # Subscribe to events
                    await self.subscribe_token_launches()
                    await self.subscribe_new_pools()
                    await self.subscribe_pair_updates()
                    reconnect_delay = self.reconnect_delay  # Reset delay

                # Listen for messages
                async for message in self.websocket:
                    await self.handle_message(message)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("GMGN WebSocket connection closed, reconnecting...")
                self.websocket = None
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, self.max_reconnect_delay)

            except Exception as e:
                logger.error(f"GMGN WebSocket error: {e}")
                if self.on_error:
                    await self.on_error(e)
                self.websocket = None
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, self.max_reconnect_delay)

    async def stop(self):
        """Stop the WebSocket listener"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            logger.info("GMGN WebSocket stopped")


# Test function
async def test_gmgn_websocket():
    """Test GMGN WebSocket connection"""

    async def on_token(token):
        print(f"\nNEW TOKEN: {token['symbol']} ({token['name']})")
        print(f"   Address: {token['mint_address']}")
        print(f"   Market Cap: ${token['initial_market_cap']:,.0f}")

    async def on_trade(trade):
        action = "BUY" if trade['is_buy'] else "SELL"
        print(f"{action}: {trade['mint_address'][:8]}... | MC: ${trade['market_cap_at_time']:,.0f}")

    async def on_error(error):
        print(f"Error: {error}")

    print("\n" + "="*60)
    print("Testing GMGN WebSocket Connection")
    print("="*60 + "\n")
    print("Connecting to GMGN.ai WebSocket...")
    print("Press Ctrl+C to stop\n")

    ws = GMGNWebSocket(
        chain='sol',
        on_new_token=on_token,
        on_trade=on_trade,
        on_error=on_error
    )

    try:
        await ws.listen()
    except KeyboardInterrupt:
        print("\n\nStopping...")
        await ws.stop()


if __name__ == "__main__":
    asyncio.run(test_gmgn_websocket())
