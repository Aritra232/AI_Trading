import asyncio
import os
import threading
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

        connection.on_open(
            lambda: print(
                "[REALTIME] User Hub connected"
            )
        )

        connection.on_close(
            lambda: print(
                "[REALTIME] User Hub disconnected"
            )
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
        token = await self.topstep_service.get_token()

        # Stop existing connection first
        if self.user_connection is not None:
            try:
                self.user_connection.stop()
            except Exception:
                pass

        self.user_account_id = account_id

        self.user_connection = (
            self._build_user_connection(token)
        )

        self.user_connection.start()

        # Allow connection to establish
        await asyncio.sleep(2)

        # Official ProjectX subscriptions

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

        return {
            "success": True,
            "message": "User realtime connection started",
            "account_id": account_id,
            "subscriptions": [
                "accounts",
                "orders",
                "positions",
                "trades"
            ]
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

        connection.on_open(
            lambda: print(
                "[REALTIME] Market Hub connected"
            )
        )

        connection.on_close(
            lambda: print(
                "[REALTIME] Market Hub disconnected"
            )
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
        token = await self.topstep_service.get_token()

        # Stop existing connection first
        if self.market_connection is not None:
            try:
                self.market_connection.stop()
            except Exception:
                pass

        self.market_contract_id = contract_id

        self.market_connection = (
            self._build_market_connection(token)
        )

        self.market_connection.start()

        # Allow connection to establish
        await asyncio.sleep(2)

        # Official ProjectX subscriptions

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

        return {
            "success": True,
            "message": "Market realtime connection started",
            "contract_id": contract_id,
            "subscriptions": [
                "quotes",
                "market_trades",
                "market_depth"
            ]
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

        if self.market_connection is not None:
            try:
                self.market_connection.stop()
            except Exception:
                pass

            self.market_connection = None

        return {
            "success": True,
            "message": "Realtime connections stopped"
        }
