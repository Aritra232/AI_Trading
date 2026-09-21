import asyncio
import os
import threading
import time
from typing import Any, Dict, Optional

from signalrcore.hub_connection_builder import HubConnectionBuilder

from service.topstep_service import TopstepService


class RealtimeService:
    def __init__(self, topstep_service: TopstepService):
        self.topstep_service = topstep_service

        self.user_connection = None
        self.market_connection = None

        self.user_account_id: Optional[int] = None
        self.market_contract_id: Optional[str] = None
        self.user_connected = False
        self.market_connected = False
        self._last_user_start_attempt = 0.0
        self._last_market_start_attempt = 0.0
        self._user_start_lock = asyncio.Lock()
        self._market_start_lock = asyncio.Lock()

        self.latest: Dict[str, Any] = {
            "account": None,
            "order": None,
            "position": None,
            "trade": None,
            "quote": None,
            "market_trade": None,
            "depth": None
        }

        self._lock = threading.Lock()

    # =========================
    # Helpers
    # =========================

    def _debug_enabled(self) -> bool:
        return os.getenv(
            "REALTIME_DEBUG",
            "false"
        ).lower() in {
            "1",
            "true",
            "yes",
            "on"
        }

    def _debug_print(
        self,
        key: str,
        value: Any
    ):
        if not self._debug_enabled():
            return

        print(f"\n[REALTIME] {key}")
        print(value)

    def _reconnect_cooldown_seconds(self) -> float:
        try:
            return float(
                os.getenv(
                    "REALTIME_RECONNECT_COOLDOWN_SECONDS",
                    "15"
                )
            )

        except Exception:
            return 15.0

    def _within_reconnect_cooldown(
        self,
        last_attempt: float
    ) -> bool:
        return (
            time.monotonic() - last_attempt
            < self._reconnect_cooldown_seconds()
        )

    def _set_latest(self, key: str, value: Any):
        with self._lock:
            self.latest[key] = value

        self._debug_print(
            key,
            value
        )

    def _set_latest_quote(self, value: Any):
        with self._lock:
            previous = self.latest.get(
                "quote"
            )

            merged = value

            if (
                isinstance(previous, dict)
                and isinstance(value, dict)
            ):
                previous_data = previous.get(
                    "data",
                    {}
                )

                value_data = value.get(
                    "data",
                    {}
                )

                if (
                    isinstance(previous_data, dict)
                    and isinstance(value_data, dict)
                    and previous.get("contract_id")
                    == value.get("contract_id")
                ):
                    merged_data = {
                        **previous_data,
                        **value_data
                    }

                    merged = {
                        **previous,
                        **value,
                        "data": merged_data
                    }

            self.latest["quote"] = merged

        self._debug_print(
            "quote",
            merged
        )

    def _normalize_single_event(self, args):
        if isinstance(args, list) and len(args) == 1:
            return args[0]

        return args

    def _normalize_market_event(self, args):
        if isinstance(args, list) and len(args) >= 2:
            return {
                "contract_id": args[0],
                "data": args[1]
            }

        return args

    # =========================
    # User Hub
    # =========================

    def _build_user_connection(self, token: str):
        user_hub_url = (
            "https://rtc.topstepx.com/hubs/user"
            f"?access_token={token}"
        )

        connection = (
            HubConnectionBuilder()
            .with_url(
                user_hub_url,
                options={
                    "access_token_factory": lambda: token,
                    "skip_negotiation": True
                }
            )
            .with_automatic_reconnect(
                {
                    "type": "raw",
                    "keep_alive_interval": 10,
                    "reconnect_interval": 5,
                    "max_attempts": 10
                }
            )
            .build()
        )

        # Account updates
        connection.on(
            "GatewayUserAccount",
            lambda args: self._set_latest(
                "account",
                self._normalize_single_event(args)
            )
        )

        # Order updates
        connection.on(
            "GatewayUserOrder",
            lambda args: self._set_latest(
                "order",
                self._normalize_single_event(args)
            )
        )

        # Position updates
        connection.on(
            "GatewayUserPosition",
            lambda args: self._set_latest(
                "position",
                self._normalize_single_event(args)
            )
        )

        # Trade updates
        connection.on(
            "GatewayUserTrade",
            lambda args: self._set_latest(
                "trade",
                self._normalize_single_event(args)
            )
        )

        def on_open():
            self.user_connected = True
            print(
                "[REALTIME] User Hub connected"
            )

        def on_close():
            self.user_connected = False
            print(
                "[REALTIME] User Hub disconnected"
            )

        connection.on_open(
            on_open
        )

        connection.on_close(
            on_close
        )

        connection.on_error(
            lambda error: print(
                f"[REALTIME] User Hub error: {error}"
            )
        )

        return connection

    async def start_user_hub(
        self,
        account_id: int
    ):
        async with self._user_start_lock:
            if (
                self.user_connection is not None
                and self.user_account_id == account_id
                and self.user_connected
            ):
                return {
                    "success": True,
                    "message": (
                        "User realtime connection already active"
                    ),
                    "account_id": account_id,
                    "reused": True
                }

            if (
                self.user_connection is not None
                and self.user_account_id == account_id
                and self._within_reconnect_cooldown(
                    self._last_user_start_attempt
                )
            ):
                return {
                    "success": True,
                    "message": (
                        "User realtime reconnect throttled"
                    ),
                    "account_id": account_id,
                    "reused": True,
                    "throttled": True
                }

            token = await self.topstep_service.get_token()

            if self.user_connection is not None:
                try:
                    self.user_connection.stop()
                except Exception:
                    pass

                self.user_connected = False

            self.user_account_id = account_id
            self._last_user_start_attempt = time.monotonic()

            self.user_connection = (
                self._build_user_connection(token)
            )

            try:
                self.user_connection.start()

                await asyncio.sleep(2)

                self.user_connection.send(
                    "SubscribeAccounts",
                    []
                )

                self.user_connection.send(
                    "SubscribeOrders",
                    [account_id]
                )

                self.user_connection.send(
                    "SubscribePositions",
                    [account_id]
                )

                self.user_connection.send(
                    "SubscribeTrades",
                    [account_id]
                )

            except Exception as exc:
                self.user_connected = False

                return {
                    "success": False,
                    "message": (
                        "User realtime connection failed"
                    ),
                    "account_id": account_id,
                    "error": str(
                        exc
                    )
                }

            return {
                "success": True,
                "message": "User realtime connection started",
                "account_id": account_id,
                "subscriptions": [
                    "accounts",
                    "orders",
                    "positions",
                    "trades"
                ],
                "reused": False
            }

    # =========================
    # Market Hub
    # =========================

    def _build_market_connection(
        self,
        token: str
    ):
        market_hub_url = (
            "https://rtc.topstepx.com/hubs/market"
            f"?access_token={token}"
        )

        connection = (
            HubConnectionBuilder()
            .with_url(
                market_hub_url,
                options={
                    "access_token_factory": lambda: token,
                    "skip_negotiation": True
                }
            )
            .with_automatic_reconnect(
                {
                    "type": "raw",
                    "keep_alive_interval": 10,
                    "reconnect_interval": 5,
                    "max_attempts": 10
                }
            )
            .build()
        )

        # Live quote
        connection.on(
            "GatewayQuote",
            lambda args: self._set_latest_quote(
                self._normalize_market_event(args)
            )
        )

        # Market trade
        connection.on(
            "GatewayTrade",
            lambda args: self._set_latest(
                "market_trade",
                self._normalize_market_event(args)
            )
        )

        # DOM / Market Depth
        connection.on(
            "GatewayDepth",
            lambda args: self._set_latest(
                "depth",
                self._normalize_market_event(args)
            )
        )

        def on_open():
            self.market_connected = True
            print(
                "[REALTIME] Market Hub connected"
            )

        def on_close():
            self.market_connected = False
            print(
                "[REALTIME] Market Hub disconnected"
            )

        connection.on_open(
            on_open
        )

        connection.on_close(
            on_close
        )

        connection.on_error(
            lambda error: print(
                f"[REALTIME] Market Hub error: {error}"
            )
        )

        return connection

    async def start_market_hub(
        self,
        contract_id: str
    ):
        async with self._market_start_lock:
            if (
                self.market_connection is not None
                and self.market_contract_id == contract_id
                and self.market_connected
            ):
                return {
                    "success": True,
                    "message": (
                        "Market realtime connection already active"
                    ),
                    "contract_id": contract_id,
                    "reused": True
                }

            if (
                self.market_connection is not None
                and self.market_contract_id == contract_id
                and self._within_reconnect_cooldown(
                    self._last_market_start_attempt
                )
            ):
                return {
                    "success": True,
                    "message": (
                        "Market realtime reconnect throttled"
                    ),
                    "contract_id": contract_id,
                    "reused": True,
                    "throttled": True
                }

            token = await self.topstep_service.get_token()

            if self.market_connection is not None:
                try:
                    self.market_connection.stop()
                except Exception:
                    pass

                self.market_connected = False

            self.market_contract_id = contract_id
            self._last_market_start_attempt = time.monotonic()

            self.market_connection = (
                self._build_market_connection(token)
            )

            try:
                self.market_connection.start()

                await asyncio.sleep(2)

                self.market_connection.send(
                    "SubscribeContractQuotes",
                    [contract_id]
                )

                self.market_connection.send(
                    "SubscribeContractTrades",
                    [contract_id]
                )

                self.market_connection.send(
                    "SubscribeContractMarketDepth",
                    [contract_id]
                )

            except Exception as exc:
                self.market_connected = False

                return {
                    "success": False,
                    "message": (
                        "Market realtime connection failed"
                    ),
                    "contract_id": contract_id,
                    "error": str(
                        exc
                    )
                }

            return {
                "success": True,
                "message": "Market realtime connection started",
                "contract_id": contract_id,
                "subscriptions": [
                    "quotes",
                    "market_trades",
                    "market_depth"
                ],
                "reused": False
            }

    # =========================
    # Latest Data
    # =========================

    def get_latest_data(self):
        with self._lock:
            return {
                "success": True,
                "user_account_id": self.user_account_id,
                "market_contract_id": self.market_contract_id,
                "data": dict(self.latest)
            }

    # =========================
    # Stop Connections
    # =========================

    def stop_all(self):
        if self.user_connection is not None:
            try:
                self.user_connection.stop()
            except Exception:
                pass

            self.user_connection = None
            self.user_connected = False
            self.user_account_id = None

        if self.market_connection is not None:
            try:
                self.market_connection.stop()
            except Exception:
                pass

            self.market_connection = None
            self.market_connected = False
            self.market_contract_id = None

        return {
            "success": True,
            "message": "Realtime connections stopped"
        }
