"""
WebSocket monitor for real-time Pump.fun data
"""
import asyncio
import json
import websockets
from typing import Callable, Optional, Dict
from loguru import logger
from datetime import datetime


class PumpFunWebSocket:
    """WebSocket client for Pump.fun real-time data"""

    def __init__(
        self,
        websocket_url: str = "wss://pumpportal.fun/api/data",
        on_new_token: Optional[Callable] = None,
        on_trade: Optional[Callable] = None,
        on_error: Optional[Callable] = None
    ):
        """
        Initialize WebSocket monitor

        Args:
            websocket_url: WebSocket endpoint
            on_new_token: Callback for new token events
            on_trade: Callback for trade events
            on_error: Callback for errors
        """
        self.websocket_url = websocket_url
        self.on_new_token = on_new_token
        self.on_trade = on_trade
        self.on_error = on_error
        self.websocket = None
        self.running = False
        self.reconnect_delay = 5
        self.max_reconnect_delay = 60

    async def connect(self):
        """Establish WebSocket connection"""
        try:
            self.websocket = await websockets.connect(
                self.websocket_url,
                ping_interval=20,
                ping_timeout=10
            )
            logger.info(f"WebSocket connected to {self.websocket_url}")
            return True
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            if self.on_error:
                await self.on_error(e)
            return False

    async def subscribe_new_tokens(self):
        """Subscribe to new token creation events"""
        if not self.websocket:
            logger.error("WebSocket not connected")
            return

        subscription = {
            "method": "subscribeNewToken"
        }
        await self.websocket.send(json.dumps(subscription))
        logger.info("Subscribed to new token events")

    async def subscribe_token_trades(self, mint_address: Optional[str] = None):
        """
        Subscribe to token trade events

        Args:
            mint_address: Specific token to monitor (REQUIRED by API)
        """
        if not self.websocket:
            logger.error("WebSocket not connected")
            return

        subscription = {
            "method": "subscribeTokenTrade",
            "keys": [mint_address] if mint_address else []
        }

        await self.websocket.send(json.dumps(subscription))
        logger.debug(f"Subscribed to trade events" + (f" for {mint_address[:8]}..." if mint_address else ""))

    async def unsubscribe_token_trades(self, mint_address: str):
        """Unsubscribe from specific token trades"""
        if not self.websocket:
            return

        unsubscription = {
            "method": "unsubscribeTokenTrade",
            "keys": [mint_address]
        }
        await self.websocket.send(json.dumps(unsubscription))
        logger.debug(f"Unsubscribed from {mint_address}")

    async def handle_message(self, message: str):
        """
        Process incoming WebSocket message

        Args:
            message: Raw JSON message string
        """
        try:
            data = json.loads(message)

            # DEBUG: Log trade messages fully for diagnostics
            if 'signature' in data and 'traderPublicKey' in data:
                logger.debug(f"TRADE MSG: {data}")

            # Handle different message types
            if isinstance(data, dict):
                msg_type = data.get('txType') or data.get('type')

                # Check txType first (most reliable)
                if msg_type == 'create':
                    # New token creation
                    await self.handle_new_token(data)

                elif msg_type in ['buy', 'sell']:
                    # Trade event (buy or sell)
                    await self.handle_trade(data)

                else:
                    logger.debug(f"Unknown message type: {msg_type}, keys: {list(data.keys())[:5]}")

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            if self.on_error:
                await self.on_error(e)

    async def handle_new_token(self, data: Dict):
        """Handle new token creation event"""
        try:
            token_info = {
                'mint_address': data.get('mint', ''),
                'name': data.get('name', 'Unknown'),
                'symbol': data.get('symbol', 'UNKNOWN'),
                'description': data.get('description', ''),
                'creator_address': data.get('traderPublicKey', ''),
                'bonding_curve': data.get('bondingCurveKey', ''),
                'initial_market_cap': 0,
                'created_timestamp': datetime.utcnow(),
                'metadata': data
            }

            logger.info(f"New token: {token_info['symbol']} ({token_info['mint_address']})")

            if self.on_new_token:
                await self.on_new_token(token_info)

        except Exception as e:
            logger.error(f"Error processing new token: {e}")

    async def handle_trade(self, data: Dict):
        """Handle trade event"""
        try:
            trade_info = {
                'signature': data.get('signature', ''),
                'mint_address': data.get('mint', ''),
                'wallet_address': data.get('traderPublicKey', ''),
                'is_buy': data.get('txType') == 'buy',
                'sol_amount': float(data.get('solAmount', 0)),
                'token_amount': float(data.get('tokenAmount', 0)),
                'timestamp': datetime.utcnow(),
                'market_cap_at_time': float(data.get('marketCapSol', 0))
            }

            if self.on_trade:
                await self.on_trade(trade_info)

        except Exception as e:
            logger.error(f"Error processing trade: {e}")

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
                    await self.subscribe_new_tokens()
                    # Note: Will subscribe to specific token trades as new tokens are detected
                    reconnect_delay = self.reconnect_delay  # Reset delay on successful connection

                # Listen for messages
                async for message in self.websocket:
                    await self.handle_message(message)

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed, reconnecting...")
                self.websocket = None
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, self.max_reconnect_delay)

            except Exception as e:
                logger.error(f"WebSocket error: {e}")
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
            logger.info("WebSocket stopped")


# Standalone function for testing
async def test_websocket():
    """Test WebSocket connection"""

    async def on_token(token):
        print(f"NEW TOKEN: {token['symbol']} - {token['mint_address']}")

    async def on_trade(trade):
        action = "BUY" if trade['is_buy'] else "SELL"
        print(f"{action}: {trade['sol_amount']:.2f} SOL - {trade['mint_address'][:8]}...")

    ws = PumpFunWebSocket(
        on_new_token=on_token,
        on_trade=on_trade
    )

    try:
        await ws.listen()
    except KeyboardInterrupt:
        await ws.stop()


if __name__ == "__main__":
    # Test the WebSocket
    asyncio.run(test_websocket())
