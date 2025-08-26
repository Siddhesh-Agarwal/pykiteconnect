# -*- coding: utf-8 -*-
"""
ticker.py

Modern WebSocket implementation for Kite ticker using Python's websockets library

:copyright: (c) 2021 by Zerodha Technology Pvt. Ltd.
:license: see LICENSE for details.
"""

from asyncio import iscoroutinefunction, sleep
from json import JSONDecodeError, loads, dumps
from logging import getLogger
from ssl import create_default_context
from struct import unpack
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Callable
from urllib.parse import urlencode
from websockets import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from .__version__ import __version__, __title__

log = getLogger(__name__)


class KiteTicker:
    """
    Modern WebSocket client for connecting to Kite Connect's streaming quotes service.

    Getting started:
    ---------------
        import asyncio
        import logging
        from kiteconnect import KiteTicker

        logging.basicConfig(level=logging.DEBUG)

        # Initialise
        kws = KiteTicker("your_api_key", "your_access_token")

        async def on_ticks(ws, ticks):
            # Callback to receive ticks.
            logging.debug(f"Ticks: {ticks}")

        async def on_connect(ws):
            # Callback on successful connect.
            # Subscribe to a list of instrument_tokens (RELIANCE and ACC here).
            await ws.subscribe([738561, 5633])
            # Set RELIANCE to tick in `full` mode.
            await ws.set_mode(ws.MODE_FULL, [738561])

        async def on_close(ws, code, reason):
            # On connection close
            logging.info(f"Connection closed: {code} - {reason}")

        # Assign the callbacks.
        kws.on_ticks = on_ticks
        kws.on_connect = on_connect
        kws.on_close = on_close

        # Connect and run
        asyncio.run(kws.connect())
    """

    EXCHANGE_MAP = {
        "nse": 1,
        "nfo": 2,
        "cds": 3,
        "bse": 4,
        "bfo": 5,
        "bcd": 6,
        "mcx": 7,
        "mcxsx": 8,
        "indices": 9,
        "bsecds": 6,  # Deprecated, use bcd
    }

    # Connection settings
    CONNECT_TIMEOUT = 30
    PING_INTERVAL = 2.5
    PING_TIMEOUT = 10
    RECONNECT_MAX_DELAY = 60
    RECONNECT_MAX_TRIES = 50
    ROOT_URI = "wss://ws.kite.trade"

    # Streaming modes
    MODE_FULL = "full"
    MODE_QUOTE = "quote"
    MODE_LTP = "ltp"

    # Message constants
    _message_subscribe = "subscribe"
    _message_unsubscribe = "unsubscribe"
    _message_setmode = "mode"

    def __init__(
        self,
        api_key: str,
        access_token: str,
        debug: bool = False,
        root: Optional[str] = None,
        reconnect: bool = True,
        reconnect_max_tries: int = RECONNECT_MAX_TRIES,
        reconnect_max_delay: int = RECONNECT_MAX_DELAY,
        connect_timeout: int = CONNECT_TIMEOUT,
        ping_interval: float = PING_INTERVAL,
        ping_timeout: float = PING_TIMEOUT,
    ):
        """
        Initialize WebSocket client.

        Args:
            api_key: API key from Kite Connect
            access_token: Access token from login flow
            debug: Enable debug logging
            root: WebSocket endpoint URL
            reconnect: Enable auto-reconnection
            reconnect_max_tries: Maximum reconnection attempts
            reconnect_max_delay: Maximum delay between reconnections
            connect_timeout: Connection timeout in seconds
        """
        self.api_key = api_key
        self.access_token = access_token
        self.debug = debug
        self.root = root or self.ROOT_URI
        self.reconnect = reconnect
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.reconnect_max_tries = min(reconnect_max_tries, 300)
        self.reconnect_max_delay = max(reconnect_max_delay, 5)
        self.connect_timeout = connect_timeout

        # Connection state
        self.ws: Optional[ClientConnection] = None
        self._running = False
        self._reconnect_attempts = 0
        self._last_pong = None
        self.subscribed_tokens: Dict[int, str] = {}

        # Callbacks - can be sync or async
        self.on_ticks: Optional[Callable] = None
        self.on_open: Optional[Callable] = None
        self.on_close: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_connect: Optional[Callable] = None
        self.on_message: Optional[Callable] = None
        self.on_reconnect: Optional[Callable] = None
        self.on_noreconnect: Optional[Callable] = None
        self.on_order_update: Optional[Callable] = None

    def _build_url(self) -> str:
        """Build WebSocket URL with authentication."""
        params = {"api_key": self.api_key, "access_token": self.access_token}
        return f"{self.root}?{urlencode(params)}"

    def _get_user_agent(self) -> str:
        """Get user agent string."""
        return f"{__title__}-python/{__version__}"

    async def _call_callback(self, callback: Optional[Callable], *args, **kwargs):
        """Call callback function (sync or async)."""
        if callback:
            try:
                if iscoroutinefunction(callback):
                    await callback(*args, **kwargs)
                else:
                    callback(*args, **kwargs)
            except Exception as e:
                log.error(f"Error in callback: {e}")

    async def connect(self) -> None:
        """Connect to WebSocket and handle reconnections."""
        self._running = True

        while self._running:
            try:
                await self._connect_once()
                if not self.reconnect or not self._running:
                    break

                # Calculate reconnect delay with exponential backoff
                delay = min(2**self._reconnect_attempts, self.reconnect_max_delay)
                log.info(
                    f"Reconnecting in {delay} seconds... (attempt {self._reconnect_attempts + 1})"
                )

                await self._call_callback(
                    self.on_reconnect, self._reconnect_attempts + 1
                )
                await sleep(delay)

                self._reconnect_attempts += 1

                if self._reconnect_attempts >= self.reconnect_max_tries:
                    log.error(
                        f"Maximum reconnection attempts ({self.reconnect_max_tries}) reached"
                    )
                    await self._call_callback(self.on_noreconnect)
                    break

            except KeyboardInterrupt:
                log.info("Connection interrupted by user")
                break
            except Exception as e:
                log.error(f"Unexpected error: {e}")
                break

    async def _connect_once(self) -> None:
        """Single connection attempt."""
        url = self._build_url()
        headers = {"User-Agent": self._get_user_agent(), "X-Kite-Version": "3"}

        # SSL context
        ssl_context = create_default_context()

        try:
            async with connect(
                url,
                extra_headers=headers,
                ssl=ssl_context,
                ping_interval=self.PING_INTERVAL,
                ping_timeout=self.PING_TIMEOUT,
                close_timeout=self.connect_timeout,
                max_size=None,
            ) as websocket:
                self.ws = websocket
                log.info("WebSocket connected successfully")

                # Reset reconnect counter on successful connection
                self._reconnect_attempts = 0

                await self._call_callback(self.on_connect, self)
                await self._call_callback(self.on_open, self)

                # Resubscribe to existing tokens
                if self.subscribed_tokens:
                    await self._resubscribe()

                # Handle messages
                async for message in websocket:
                    await self._handle_message(message)

        except ConnectionClosed as e:
            log.warning(f"WebSocket connection closed: {e}")
            await self._call_callback(self.on_close, self, e.code, e.reason)

        except Exception as e:
            log.error(f"WebSocket connection error: {e}")
            await self._call_callback(self.on_error, self, 0, str(e))

    async def _handle_message(self, message) -> None:
        """Handle incoming WebSocket message."""
        try:
            await self._call_callback(
                self.on_message, self, message, isinstance(message, bytes)
            )

            if isinstance(message, bytes):
                # Binary market data
                if len(message) > 4 and self.on_ticks:
                    ticks = self._parse_binary(message)
                    await self._call_callback(self.on_ticks, self, ticks)
            else:
                # Text message
                await self._parse_text_message(message)

        except Exception as e:
            log.error(f"Error handling message: {e}")

    async def _parse_text_message(self, message: str) -> None:
        """Parse text message from WebSocket."""
        try:
            data = loads(message)

            # Handle order updates
            if (
                data.get("type") == "order"
                and data.get("data")
                and self.on_order_update
            ):
                await self._call_callback(self.on_order_update, self, data["data"])

            # Handle errors
            elif data.get("type") == "error":
                await self._call_callback(self.on_error, self, 0, data.get("data"))

        except JSONDecodeError as e:
            log.error(f"Failed to parse text message: {e}")

    async def _resubscribe(self) -> None:
        """Resubscribe to all previously subscribed tokens."""
        if not self.subscribed_tokens:
            return

        # Group tokens by mode
        modes: Dict[str, List[int]] = {}
        for token, mode in self.subscribed_tokens.items():
            modes.setdefault(mode, []).append(token)

        # Subscribe and set modes
        for mode, tokens in modes.items():
            if mode not in ["full", "quote", "ltp"]:
                log.warning(f"Unknown mode: {mode}")
                continue
            log.debug(f"Resubscribing to {len(tokens)} tokens in {mode} mode")
            await self.subscribe(tokens)
            await self.set_mode(mode, tokens)  # pyright: ignore[reportArgumentType]

    async def subscribe(self, instrument_tokens: List[int]) -> bool:
        """Subscribe to instrument tokens."""
        if self.ws is None:
            return False

        try:
            message = dumps({"a": self._message_subscribe, "v": instrument_tokens})
            await self.ws.send(message)

            # Update subscribed tokens
            for token in instrument_tokens:
                self.subscribed_tokens[token] = self.MODE_QUOTE

            return True

        except Exception as e:
            log.error(f"Error subscribing: {e}")
            await self.close()
            return False

    async def unsubscribe(self, instrument_tokens: List[int]) -> bool:
        """Unsubscribe from instrument tokens."""
        if self.ws is None:
            return False

        try:
            message = dumps({"a": self._message_unsubscribe, "v": instrument_tokens})
            await self.ws.send(message)

            # Remove from subscribed tokens
            for token in instrument_tokens:
                self.subscribed_tokens.pop(token, None)

            return True

        except Exception as e:
            log.error(f"Error unsubscribing: {e}")
            await self.close()
            return False

    async def set_mode(
        self, mode: Literal["full", "quote", "ltp"], instrument_tokens: List[int]
    ) -> bool:
        """Set streaming mode for instrument tokens."""
        if self.ws is None:
            return False

        try:
            message = dumps(
                {"a": self._message_setmode, "v": [mode, instrument_tokens]}
            )
            await self.ws.send(message)

            # Update modes
            for token in instrument_tokens:
                self.subscribed_tokens[token] = mode

            return True

        except Exception as e:
            log.error(f"Error setting mode: {e}")
            await self.close()
            return False

    async def close(self) -> None:
        """Close WebSocket connection."""
        self._running = False
        if self.ws:
            await self.ws.close()

    def _parse_binary(self, data: bytes) -> List[Dict[str, Any]]:
        """Parse binary market data into tick structures."""
        packets = self._split_packets(data)
        ticks = []

        for packet in packets:
            if len(packet) < 4:
                continue

            instrument_token = self._unpack_int(packet, 0, 4)
            segment = instrument_token & 0xFF

            # Price divisor based on segment
            if segment == self.EXCHANGE_MAP["cds"]:
                divisor = 10000000.0
            elif segment == self.EXCHANGE_MAP["bcd"]:
                divisor = 10000.0
            else:
                divisor = 100.0

            tradable = segment != self.EXCHANGE_MAP["indices"]
            tick = {"tradable": tradable, "instrument_token": instrument_token}

            # Parse different packet sizes
            if len(packet) == 8:
                # LTP mode
                tick.update(
                    {
                        "mode": self.MODE_LTP,
                        "last_price": self._unpack_int(packet, 4, 8) / divisor,
                    }
                )

            elif len(packet) in (28, 32):
                # Index quote/full mode
                tick.update(
                    {
                        "mode": self.MODE_FULL
                        if len(packet) == 32
                        else self.MODE_QUOTE,
                        "last_price": self._unpack_int(packet, 4, 8) / divisor,
                        "ohlc": {
                            "high": self._unpack_int(packet, 8, 12) / divisor,
                            "low": self._unpack_int(packet, 12, 16) / divisor,
                            "open": self._unpack_int(packet, 16, 20) / divisor,
                            "close": self._unpack_int(packet, 20, 24) / divisor,
                        },
                    }
                )

                # Calculate change percentage
                close = tick["ohlc"]["close"]
                if close != 0:
                    tick["change"] = (tick["last_price"] - close) * 100 / close
                else:
                    tick["change"] = 0

                # Full mode timestamp
                if len(packet) == 32:
                    try:
                        tick["exchange_timestamp"] = datetime.fromtimestamp(
                            self._unpack_int(packet, 28, 32)
                        )
                    except (ValueError, OSError):
                        tick["exchange_timestamp"] = None

            elif len(packet) in (44, 184):
                # Regular quote/full mode
                tick.update(
                    {
                        "mode": self.MODE_FULL
                        if len(packet) == 184
                        else self.MODE_QUOTE,
                        "last_price": self._unpack_int(packet, 4, 8) / divisor,
                        "last_traded_quantity": self._unpack_int(packet, 8, 12),
                        "average_traded_price": self._unpack_int(packet, 12, 16)
                        / divisor,
                        "volume_traded": self._unpack_int(packet, 16, 20),
                        "total_buy_quantity": self._unpack_int(packet, 20, 24),
                        "total_sell_quantity": self._unpack_int(packet, 24, 28),
                        "ohlc": {
                            "open": self._unpack_int(packet, 28, 32) / divisor,
                            "high": self._unpack_int(packet, 32, 36) / divisor,
                            "low": self._unpack_int(packet, 36, 40) / divisor,
                            "close": self._unpack_int(packet, 40, 44) / divisor,
                        },
                    }
                )

                # Calculate change percentage
                close = tick["ohlc"]["close"]
                if close != 0:
                    tick["change"] = (tick["last_price"] - close) * 100 / close
                else:
                    tick["change"] = 0

                # Full mode additional data
                if len(packet) == 184:
                    try:
                        tick["last_trade_time"] = datetime.fromtimestamp(
                            self._unpack_int(packet, 44, 48)
                        )
                    except (ValueError, OSError):
                        tick["last_trade_time"] = None

                    tick.update(
                        {
                            "oi": self._unpack_int(packet, 48, 52),
                            "oi_day_high": self._unpack_int(packet, 52, 56),
                            "oi_day_low": self._unpack_int(packet, 56, 60),
                        }
                    )

                    try:
                        tick["exchange_timestamp"] = datetime.fromtimestamp(
                            self._unpack_int(packet, 60, 64)
                        )
                    except (ValueError, OSError):
                        tick["exchange_timestamp"] = None

                    # Market depth
                    depth = {"buy": [], "sell": []}
                    for i, pos in enumerate(range(64, len(packet), 12)):
                        if pos + 12 > len(packet):
                            break

                        entry = {
                            "quantity": self._unpack_int(packet, pos, pos + 4),
                            "price": self._unpack_int(packet, pos + 4, pos + 8)
                            / divisor,
                            "orders": self._unpack_int(packet, pos + 8, pos + 10, "H"),
                        }

                        if i < 5:
                            depth["buy"].append(entry)
                        else:
                            depth["sell"].append(entry)

                    tick["depth"] = depth

            ticks.append(tick)

        return ticks

    def _split_packets(self, data: bytes) -> List[bytes]:
        """Split binary data into individual tick packets."""
        if len(data) < 2:
            return []

        packets = []
        packet_count = self._unpack_int(data, 0, 2, "H")
        pos = 2

        for _ in range(packet_count):
            if pos + 2 > len(data):
                break

            packet_length = self._unpack_int(data, pos, pos + 2, "H")
            pos += 2

            if pos + packet_length > len(data):
                break

            packets.append(data[pos : pos + packet_length])
            pos += packet_length

        return packets

    def _unpack_int(
        self, data: bytes, start: int, end: int, byte_format: Literal["H", "I"] = "I"
    ) -> int:
        """Unpack binary data as unsigned integer."""
        if end > len(data):
            return 0
        return unpack(">" + byte_format, data[start:end])[0]
