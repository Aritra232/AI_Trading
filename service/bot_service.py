import asyncio
import os
import re
from datetime import datetime, timedelta, timezone


class BotService:
    def __init__(
        self,
        contract_service,
        trading_state_service,
        realtime_service,
        rule_service,
        risk_service,
        strategy_service,
        decision_service,
        safety_service,
        execution_service,
        trading_day_service=None,
        audit_service=None,
        bot_state_service=None,
        session_id: str | None = None,
        user_id: str | None = None
    ):
        self.contract_service = contract_service
        self.trading_state_service = trading_state_service
        self.realtime_service = realtime_service
        self.rule_service = rule_service
        self.risk_service = risk_service
        self.strategy_service = strategy_service
        self.decision_service = decision_service
        self.safety_service = safety_service
        self.execution_service = execution_service
        self.trading_day_service = trading_day_service
        self.audit_service = audit_service
        self.bot_state_service = bot_state_service
        self.session_id = session_id
        self.user_id = user_id

    def _utc_now_iso(self):
        return datetime.now(
            timezone.utc
        ).isoformat().replace(
            "+00:00",
            "Z"
        )

    def _parse_datetime(
        self,
        value: str | None
    ):
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00"
                )
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed

        except Exception:
            return None

    def _age_seconds(
        self,
        value: str | None
    ):
        parsed = self._parse_datetime(
            value
        )

        if parsed is None:
            return None

        return max(
            (
                datetime.now(
                    timezone.utc
                )
                - parsed
            ).total_seconds(),
            0
        )

    def _to_float(
        self,
        value
    ):
        if value is None:
            return None

        try:
            return float(
                value
            )

        except Exception:
            return None

    def _env_int(
        self,
        name: str,
        default: int,
        minimum: int | None = None
    ) -> int:
        try:
            value = int(
                os.getenv(
                    name,
                    str(default)
                )
            )

            if minimum is not None:
                value = max(
                    value,
                    minimum
                )

            return value

        except Exception:
            return default

    def _env_float(
        self,
        name: str,
        default: float
    ) -> float:
        try:
            return float(
                os.getenv(
                    name,
                    str(default)
                )
            )

        except Exception:
            return default

    def _env_bool(
        self,
        name: str,
        default: bool
    ) -> bool:
        raw = os.getenv(
            name
        )

        if raw is None:
            return default

        return raw.strip().lower() in {
            "1",
            "true",
            "yes",
            "on"
        }

    def _min_trade_confidence(
        self
    ) -> float:
        return max(
            0.0,
            min(
                self._env_float(
                    "MIN_TRADE_CONFIDENCE",
                    0.60
                ),
                1.0
            )
        )

    def _extract_position_contract_id(
        self,
        position: dict
    ) -> str | None:
        for key in (
            "contractId",
            "contract_id",
            "contractID",
            "symbolId"
        ):
            value = position.get(
                key
            )

            if value:
                return str(
                    value
                )

        return None

    def _extract_position_quantity(
        self,
        position: dict
    ) -> int:
        for key in (
            "size",
            "quantity",
            "qty"
        ):
            value = position.get(
                key
            )

            try:
                return abs(
                    int(
                        value
                    )
                )

            except Exception:
                continue

        return 0

    def _extract_position_action_side(
        self,
        position: dict
    ) -> str | None:
        raw_type = position.get(
            "type"
        )

        try:
            numeric_type = int(
                raw_type
            )

            if numeric_type == 1:
                return "BUY"

            if numeric_type == 2:
                return "SELL"

        except Exception:
            pass

        text = str(
            position.get(
                "side",
                ""
            )
            or position.get(
                "positionType",
                ""
            )
            or ""
        ).upper()

        if "LONG" in text or "BUY" in text:
            return "BUY"

        if "SHORT" in text or "SELL" in text:
            return "SELL"

        return None

    def _extract_position_root_symbol(
        self,
        position: dict
    ) -> str | None:
        for key in (
            "symbolId",
            "contractId",
            "contract_id",
            "contractID"
        ):
            value = str(
                position.get(
                    key,
                    ""
                )
                or ""
            ).strip().upper()

            if not value:
                continue

            parts = value.split(".")

            if (
                key == "symbolId"
                and parts
            ):
                return parts[-1]

            if len(parts) >= 3:
                return parts[-2]

            if len(parts) >= 1:
                return parts[-1]

        for key in (
            "contractDisplayName",
            "contractName",
            "symbol",
            "name"
        ):
            value = str(
                position.get(
                    key,
                    ""
                )
                or ""
            ).strip().upper().lstrip("/")

            if not value:
                continue

            match = re.match(
                r"^([A-Z0-9]+?)[FGHJKMNQUVXZ]\d{1,2}$",
                value
            )

            if match:
                return match.group(1)

            return value

        return None

    def _position_exposure_by_root(
        self,
        positions: list
    ) -> dict:
        exposure = {}

        for position in positions or []:
            root = self._extract_position_root_symbol(
                position
            )

            if not root:
                continue

            exposure[root] = (
                exposure.get(
                    root,
                    0
                )
                + self._extract_position_quantity(
                    position
                )
            )

        return exposure

    def _position_field_pnl(
        self,
        position: dict
    ) -> float | None:
        for key in (
            "profitAndLoss",
            "profitLoss",
            "pnl",
            "P&L",
            "unrealizedPnl",
            "unrealizedPnL"
        ):
            value = self._to_float(
                position.get(
                    key
                )
            )

            if value is not None:
                return value

        return None

    def _position_age_hours(
        self,
        position: dict
    ) -> float | None:
        for key in (
            "creationTimestamp",
            "createdAt",
            "created_at",
            "openTime",
            "timestamp",
            "time"
        ):
            age_seconds = self._age_seconds(
                position.get(
                    key
                )
            )

            if age_seconds is not None:
                return age_seconds / 3600

        return None

    def _position_sort_key(
        self,
        position: dict
    ):
        age = self._position_age_hours(
            position
        )

        return (
            -1
            if age is None
            else -age
        )

    def _supported_auto_roots(
        self
    ) -> set[str]:
        return {
            item.strip().upper()
            for item in (
                os.getenv(
                    "AUTO_TRADE_CONTRACT_SEARCH_TEXTS",
                    "MNQ,MES,MYM,M2K"
                )
            ).split(",")
            if item.strip()
        }

    def _root_max_position_quantity(
        self,
        root_symbol: str | None,
        default_max: int | None
    ) -> int:
        root = str(
            root_symbol or ""
        ).upper()

        if root == "MNQ":
            return self._env_int(
                "AUTO_MNQ_MAX_POSITION_QUANTITY",
                2,
                minimum=1
            )

        return (
            default_max
            if default_max is not None
            else self._env_int(
                "AUTO_MAX_POSITION_QUANTITY",
                3,
                minimum=1
            )
        )

    def _contract_max_position_quantity(
        self,
        contract: dict,
        default_max: int | None
    ) -> int:
        return self._root_max_position_quantity(
            root_symbol=self._contract_root_symbol(
                contract
            ),
            default_max=default_max
        )

    def _root_position_pnl_from_fields(
        self,
        positions: list,
        root_symbol: str
    ) -> float | None:
        values = []

        for position in positions or []:
            if (
                self._extract_position_root_symbol(
                    position
                )
                != root_symbol
            ):
                continue

            pnl = self._position_field_pnl(
                position
            )

            if pnl is not None:
                values.append(
                    pnl
                )

        if not values:
            return None

        return sum(
            values
        )

    def _contract_position_pnl(
        self,
        positions: list,
        contract: dict,
        current_price: float | None
    ) -> float | None:
        values = []

        for position in positions or []:
            if not self._position_matches_contract(
                position=position,
                contract=contract
            ):
                continue

            pnl = self._calculate_position_pnl(
                position=position,
                contract=contract,
                current_price=current_price
            )

            if pnl is not None:
                values.append(
                    pnl
                )

        if not values:
            return None

        return sum(
            values
        )

    def _mnq_allows_additional_position(
        self,
        quantity: int,
        pnl: float | None,
        max_quantity: int
    ) -> bool:
        if quantity <= 0:
            return True

        if quantity >= max_quantity:
            return False

        return (
            pnl is not None
            and pnl > self._env_float(
                "AUTO_MNQ_SECOND_POSITION_MIN_PROFIT_USD",
                0.0
            )
        )

    def _position_matches_contract(
        self,
        position: dict,
        contract: dict
    ) -> bool:
        position_contract_id = (
            self._extract_position_contract_id(
                position
            )
        )
        contract_id = str(
            contract.get(
                "id",
                ""
            )
        )
        symbol_id = str(
            contract.get(
                "symbolId",
                ""
            )
        )

        return position_contract_id in {
            contract_id,
            symbol_id
        }

    def _calculate_position_pnl(
        self,
        position: dict,
        contract: dict,
        current_price: float | None
    ) -> float | None:
        if current_price is None:
            return None

        entry_price = self._to_float(
            position.get(
                "averagePrice"
            )
            or position.get(
                "avgPrice"
            )
            or position.get(
                "entryPrice"
            )
        )
        tick_size = self._to_float(
            contract.get(
                "tickSize"
            )
        )
        tick_value = self._to_float(
            contract.get(
                "tickValue"
            )
        )
        quantity = self._extract_position_quantity(
            position
        )
        side = self._extract_position_action_side(
            position
        )

        if (
            entry_price is None
            or tick_size is None
            or tick_value is None
            or tick_size <= 0
            or quantity <= 0
            or side is None
        ):
            return None

        price_delta = (
            current_price
            - entry_price
        )

        if side == "SELL":
            price_delta = -price_delta

        return (
            price_delta
            / tick_size
            * tick_value
            * quantity
        )

    def _opposite_action(
        self,
        action: str | None
    ) -> str | None:
        normalized = str(
            action or ""
        ).upper()

        if normalized == "BUY":
            return "SELL"

        if normalized == "SELL":
            return "BUY"

        return None

    def _resolve_current_price(
        self,
        quote_data: dict
    ):
        last_price = self._to_float(
            quote_data.get(
                "lastPrice"
            )
        )

        if last_price is not None:
            return last_price, "LAST_PRICE"

        best_bid = self._to_float(
            quote_data.get(
                "bestBid"
            )
        )

        best_ask = self._to_float(
            quote_data.get(
                "bestAsk"
            )
        )

        if (
            best_bid is not None
            and best_ask is not None
        ):
            return (
                (best_bid + best_ask) / 2,
                "BID_ASK_MID"
            )

        if best_bid is not None:
            return best_bid, "BID_ONLY"

        if best_ask is not None:
            return best_ask, "ASK_ONLY"

        return None, "UNAVAILABLE"

    def _bar_close_price(
        self,
        bar: dict | None
    ) -> float | None:
        if not isinstance(
            bar,
            dict
        ):
            return None

        return self._to_float(
            bar.get(
                "c"
            )
            or bar.get(
                "close"
            )
        )

    def _price_scale_tolerance(
        self
    ) -> float:
        return max(
            0.01,
            self._env_float(
                "AUTO_CONTRACT_PRICE_SCALE_TOLERANCE",
                0.25
            )
        )

    def _price_scale_block(
        self,
        current_price: float | None,
        latest_bar_close: float | None,
        symbol: str
    ) -> str | None:
        if (
            current_price is None
            or latest_bar_close is None
            or latest_bar_close <= 0
        ):
            return None

        relative_difference = abs(
            current_price - latest_bar_close
        ) / latest_bar_close

        tolerance = self._price_scale_tolerance()

        if relative_difference <= tolerance:
            return None

        return (
            f"{symbol} quote/history price-scale mismatch. "
            f"Quote={current_price}, latest_bar_close="
            f"{latest_bar_close}, tolerance={tolerance:.2f}."
        )

    def _evaluate_market_gate(
        self,
        market: dict,
        max_quote_age_seconds: int,
        expected_contract_id: str | None = None
    ):
        quote = market.get(
            "quote"
        )

        quote_data = {}

        if quote:
            quote_data = quote.get(
                "data",
                quote
            )

        quote_contract_id = None

        if isinstance(
            quote,
            dict
        ):
            quote_contract_id = quote.get(
                "contract_id"
            ) or quote.get(
                "contractId"
            )

        quote_timestamp = (
            quote_data.get(
                "lastUpdated"
            )
            or quote_data.get(
                "timestamp"
            )
        )

        quote_age_seconds = self._age_seconds(
            quote_timestamp
        )

        current_price, current_price_source = (
            self._resolve_current_price(
                quote_data
            )
        )

        blocks = []

        if not quote:
            blocks.append(
                "Realtime quote is unavailable."
            )

        elif (
            expected_contract_id
            and quote_contract_id
            and str(
                quote_contract_id
            ) != str(
                expected_contract_id
            )
        ):
            blocks.append(
                (
                    "Realtime quote contract mismatch. "
                    f"Expected={expected_contract_id}, "
                    f"received={quote_contract_id}."
                )
            )

        elif quote_age_seconds is None:
            blocks.append(
                "Realtime quote timestamp cannot be validated."
            )

        elif quote_age_seconds > max_quote_age_seconds:
            blocks.append(
                (
                    f"Realtime quote is stale. "
                    f"Age={quote_age_seconds:.2f}s, "
                    f"maximum allowed={max_quote_age_seconds}s."
                )
            )

        if quote and current_price is None:
            blocks.append(
                "Current market price is unavailable."
            )

        status = (
            "BLOCK"
            if blocks
            else "PASS"
        )

        return {
            "success": True,
            "status": status,
            "tradable": not blocks,
            "blocks": blocks,
            "quote": {
                "available": quote is not None,
                "contract_id": quote_contract_id,
                "expected_contract_id": expected_contract_id,
                "lastUpdated": quote_timestamp,
                "age_seconds": quote_age_seconds,
                "max_age_seconds": max_quote_age_seconds,
                "currentPrice": current_price,
                "currentPriceSource": current_price_source,
                "lastPrice": quote_data.get(
                    "lastPrice"
                ),
                "bestBid": quote_data.get(
                    "bestBid"
                ),
                "bestAsk": quote_data.get(
                    "bestAsk"
                )
            },
            "market_gate_version": "MARKET_GATE_V1"
        }

    def _utc_lookback_iso(
        self,
        hours: int
    ):
        return (
            datetime.now(
                timezone.utc
            )
            - timedelta(
                hours=hours
            )
        ).isoformat().replace(
            "+00:00",
            "Z"
        )

    def _auto_symbol_candidates(
        self
    ):
        raw = (
            os.getenv(
                "AUTO_TRADE_CONTRACT_SEARCH_TEXTS",
                ""
            )
            or os.getenv(
                "AUTO_TRADE_SYMBOLS",
                ""
            )
        )

        candidates = []
        seen = set()

        for item in raw.split(","):
            symbol = item.strip()

            if (
                not symbol
                or symbol in seen
            ):
                continue

            seen.add(
                symbol
            )
            candidates.append(
                symbol
            )

        return candidates or [
            "MNQ",
            "MES",
            "MYM",
            "M2K"
        ]

    def _auto_contract_limit(
        self
    ) -> int:
        try:
            return max(
                int(
                    os.getenv(
                        "AUTO_TRADE_CONTRACT_LIMIT",
                        "80"
                    )
                ),
                1
            )

        except Exception:
            return 80

    def _max_trade_quantity(
        self
    ) -> int:
        return self._env_int(
            "AUTO_MAX_TRADE_QUANTITY",
            2,
            minimum=1
        )

    def _normalize_planned_quantity(
        self,
        planned_quantity: int,
        max_position_quantity: int | None
    ) -> int:
        quantity = max(
            int(
                planned_quantity
            ),
            1
        )

        quantity = min(
            quantity,
            self._max_trade_quantity()
        )

        if max_position_quantity is not None:
            quantity = min(
                quantity,
                max_position_quantity
            )

        return max(
            quantity,
            1
        )

    def _contract_root_symbol(
        self,
        contract: dict
    ) -> str:
        symbol_id = str(
            contract.get(
                "symbolId",
                ""
            )
        ).strip()

        if symbol_id:
            return symbol_id.split(".")[-1].upper()

        name = str(
            contract.get(
                "name",
                ""
            )
        ).strip().upper()

        match = re.match(
            r"^(.+?)[FGHJKMNQUVXZ]\d{1,2}$",
            name
        )

        if match:
            return match.group(1)

        return name

    def _summarize_contract(
        self,
        contract: dict,
        position_exposure: dict | None = None,
        max_position_quantity: int | None = None
    ) -> dict:
        root_symbol = self._contract_root_symbol(
            contract
        )
        root_quantity = (
            position_exposure
            or {}
        ).get(
            root_symbol,
            0
        )
        root_max_quantity = self._root_max_position_quantity(
            root_symbol=root_symbol,
            default_max=max_position_quantity
        )

        return {
            "id": contract.get(
                "id"
            ),
            "name": contract.get(
                "name"
            ),
            "description": contract.get(
                "description"
            ),
            "tickSize": contract.get(
                "tickSize"
            ),
            "tickValue": contract.get(
                "tickValue"
            ),
            "activeContract": contract.get(
                "activeContract"
            ),
            "symbolId": contract.get(
                "symbolId"
            ),
            "rootSymbol": root_symbol,
            "currentPositionQuantity": root_quantity,
            "maxPositionQuantity": root_max_quantity,
            "needsMoreExposure": (
                root_quantity < root_max_quantity
            )
        }

    def _rotation_enabled(
        self
    ) -> bool:
        return (
            os.getenv(
                "INSTRUMENT_ROTATION_ENABLED",
                "true"
            ).strip().lower()
            == "true"
        )

    def _rotation_loss_threshold(
        self
    ) -> int:
        try:
            return max(
                int(
                    os.getenv(
                        "INSTRUMENT_ROTATION_LOSS_THRESHOLD",
                        "3"
                    )
                ),
                1
            )

        except Exception:
            return 3

    def _rotation_cooldown_minutes(
        self
    ) -> int:
        try:
            return max(
                int(
                    os.getenv(
                        "INSTRUMENT_ROTATION_COOLDOWN_MINUTES",
                        "1440"
                    )
                ),
                1
            )

        except Exception:
            return 1440

    def _rotation_lookback_days(
        self
    ) -> int:
        try:
            return max(
                int(
                    os.getenv(
                        "INSTRUMENT_ROTATION_LOOKBACK_DAYS",
                        "14"
                    )
                ),
                1
            )

        except Exception:
            return 14

    def _rotation_refresh_interval_seconds(
        self
    ) -> int:
        try:
            return max(
                int(
                    os.getenv(
                        "INSTRUMENT_ROTATION_REFRESH_SECONDS",
                        "300"
                    )
                ),
                0
            )

        except Exception:
            return 300

    def _extract_trade_contract_id(
        self,
        trade: dict
    ) -> str | None:
        for key in (
            "contractId",
            "contract_id",
            "contractID",
            "symbolId",
            "symbol"
        ):
            value = trade.get(
                key
            )

            if value:
                return str(
                    value
                )

        contract = trade.get(
            "contract"
        )

        if isinstance(
            contract,
            dict
        ):
            value = (
                contract.get(
                    "id"
                )
                or contract.get(
                    "contractId"
                )
                or contract.get(
                    "symbolId"
                )
                or contract.get(
                    "name"
                )
            )

            if value:
                return str(
                    value
                )

        return None

    def _extract_trade_symbol(
        self,
        trade: dict,
        contract_id: str | None = None
    ) -> str | None:
        for key in (
            "symbol",
            "symbolId",
            "contractName",
            "contract_name",
            "name"
        ):
            value = trade.get(
                key
            )

            if value:
                return str(
                    value
                ).upper()

        if contract_id:
            return str(
                contract_id
            ).split(".")[-1].upper()

        return None

    def _prune_rotation_blocks(
        self,
        blocked_contracts: dict
    ) -> dict:
        now = datetime.now(
            timezone.utc
        )

        active = {}

        for contract_id, data in (
            blocked_contracts or {}
        ).items():
            blocked_until = self._parse_datetime(
                data.get(
                    "blocked_until"
                )
            )

            if (
                blocked_until is not None
                and blocked_until > now
            ):
                active[contract_id] = data

        return active

    async def _refresh_instrument_rotation(
        self,
        account_id: int
    ) -> dict:
        if (
            not self._rotation_enabled()
            or self.bot_state_service is None
            or self.trading_day_service is None
            or getattr(
                self.trading_day_service,
                "trade_service",
                None
            ) is None
        ):
            return {
                "enabled": self._rotation_enabled(),
                "updated": False,
                "reason": (
                    "Instrument rotation prerequisites "
                    "are not configured."
                ),
                "blocked_contracts": {}
            }

        loss_threshold = self._rotation_loss_threshold()
        cooldown_minutes = self._rotation_cooldown_minutes()
        lookback_days = self._rotation_lookback_days()
        refresh_interval_seconds = (
            self._rotation_refresh_interval_seconds()
        )

        now = datetime.now(
            timezone.utc
        )

        existing = (
            self.bot_state_service
            .get_instrument_rotation()
        )

        last_checked_at = self._parse_datetime(
            existing.get(
                "last_checked_at"
            )
        )

        if (
            last_checked_at is not None
            and refresh_interval_seconds > 0
            and (
                now - last_checked_at
            ).total_seconds() < refresh_interval_seconds
        ):
            pruned_blocks = self._prune_rotation_blocks(
                existing.get(
                    "blocked_contracts",
                    {}
                )
            )

            if pruned_blocks != existing.get(
                "blocked_contracts",
                {}
            ):
                existing = (
                    self.bot_state_service
                    .update_instrument_rotation(
                        {
                            **existing,
                            "blocked_contracts": pruned_blocks
                        }
                    )
                    .get(
                        "instrument_rotation",
                        existing
                    )
                )

            return {
                **existing,
                "enabled": True,
                "refreshed": False,
                "refresh_interval_seconds": (
                    refresh_interval_seconds
                )
            }

        start_time = (
            now
            - timedelta(
                days=lookback_days
            )
        ).isoformat().replace(
            "+00:00",
            "Z"
        )

        end_time = now.isoformat().replace(
            "+00:00",
            "Z"
        )

        trades_result = (
            await self.trading_day_service.trade_service.get_trades(
                account_id=account_id,
                start_timestamp=start_time,
                end_timestamp=end_time
            )
        )

        trades = self.trading_day_service._extract_trades(
            trades_result
        )

        grouped = {}

        for trade in trades:
            contract_id = self._extract_trade_contract_id(
                trade
            )

            if not contract_id:
                continue

            timestamp = self.trading_day_service._extract_timestamp(
                trade
            )

            pnl = self.trading_day_service._extract_pnl(
                trade
            )

            if pnl is None:
                continue

            grouped.setdefault(
                contract_id,
                []
            ).append(
                {
                    "timestamp": timestamp,
                    "pnl": float(
                        pnl
                    ),
                    "symbol": self._extract_trade_symbol(
                        trade,
                        contract_id=contract_id
                    )
                }
            )

        blocked_contracts = self._prune_rotation_blocks(
            existing.get(
                "blocked_contracts",
                {}
            )
        )

        rotation_events = []

        for contract_id, items in grouped.items():
            sorted_items = sorted(
                items,
                key=lambda item: (
                    item.get(
                        "timestamp"
                    )
                    or datetime.min.replace(
                        tzinfo=timezone.utc
                    )
                ),
                reverse=True
            )

            consecutive_losses = 0
            latest_loss_at = None
            symbol = None

            for item in sorted_items:
                pnl = item.get(
                    "pnl"
                )

                if pnl < 0:
                    consecutive_losses += 1
                    latest_loss_at = (
                        latest_loss_at
                        or item.get(
                            "timestamp"
                        )
                    )
                    symbol = (
                        symbol
                        or item.get(
                            "symbol"
                        )
                    )
                    continue

                break

            if consecutive_losses >= loss_threshold:
                blocked_until_dt = (
                    now
                    + timedelta(
                        minutes=cooldown_minutes
                    )
                )

                blocked_until = blocked_until_dt.isoformat().replace(
                    "+00:00",
                    "Z"
                )

                blocked_contracts[contract_id] = {
                    "contract_id": contract_id,
                    "symbol": symbol,
                    "loss_count": consecutive_losses,
                    "loss_threshold": loss_threshold,
                    "blocked_at": end_time,
                    "blocked_until": blocked_until,
                    "latest_loss_at": (
                        latest_loss_at.isoformat().replace(
                            "+00:00",
                            "Z"
                        )
                        if latest_loss_at
                        else None
                    ),
                    "reason": (
                        f"{consecutive_losses} consecutive "
                        "realized losing trades detected."
                    )
                }

                rotation_events.append(
                    blocked_contracts[contract_id]
                )

        rotation = {
            "enabled": True,
            "loss_threshold": loss_threshold,
            "cooldown_minutes": cooldown_minutes,
            "lookback_days": lookback_days,
            "refresh_interval_seconds": (
                refresh_interval_seconds
            ),
            "blocked_contracts": blocked_contracts,
            "last_checked_at": end_time,
            "refreshed": True,
            "trade_count": len(
                trades
            ),
            "source": "TOPSTEP_TRADE_SEARCH",
            "raw_success": trades_result.get(
                "success"
            ),
            "events": rotation_events
        }

        saved = self.bot_state_service.update_instrument_rotation(
            rotation
        )

        return saved.get(
            "instrument_rotation",
            rotation
        )

    def _is_contract_rotation_blocked(
        self,
        contract: dict,
        rotation: dict | None
    ) -> dict | None:
        if not rotation:
            return None

        blocked_contracts = rotation.get(
            "blocked_contracts",
            {}
        )

        contract_id = str(
            contract.get(
                "id",
                ""
            )
        )

        if contract_id in blocked_contracts:
            return blocked_contracts[
                contract_id
            ]

        symbol = self._contract_root_symbol(
            contract
        )

        for data in blocked_contracts.values():
            if str(
                data.get(
                    "symbol",
                    ""
                )
            ).upper() == symbol:
                return data

        return None

    async def _discover_auto_contracts(
        self,
        live: bool,
        rotation: dict | None = None
    ):
        search_terms = self._auto_symbol_candidates()
        discovered = []
        checked = []
        seen_ids = set()

        for search_term in search_terms:
            try:
                contracts_result = (
                    await self.contract_service.search_contracts(
                        search_text=search_term,
                        live=live
                    )
                )

                contracts = contracts_result.get(
                    "contracts",
                    []
                )

                checked.append(
                    {
                        "search_text": search_term,
                        "count": len(
                            contracts
                        ),
                        "success": contracts_result.get(
                            "success"
                        )
                    }
                )

                for contract in contracts:
                    contract_id = contract.get(
                        "id"
                    )

                    if (
                        not contract_id
                        or contract_id in seen_ids
                    ):
                        continue

                    if not contract.get(
                        "activeContract",
                        False
                    ):
                        continue

                    if self._is_contract_rotation_blocked(
                        contract=contract,
                        rotation=rotation
                    ):
                        continue

                    seen_ids.add(
                        contract_id
                    )
                    discovered.append(
                        contract
                    )

            except Exception as exc:
                checked.append(
                    {
                        "search_text": search_term,
                        "count": 0,
                        "success": False,
                        "error": str(
                            exc
                        )
                    }
                )

        limit = self._auto_contract_limit()

        return {
            "contracts": discovered[:limit],
            "checked": checked,
            "search_terms": search_terms,
            "limit": limit,
            "total_active_found": len(
                discovered
            )
        }

    async def _evaluate_auto_contract_health(
        self,
        contract: dict,
        live: bool,
        max_quote_age_seconds: int,
        lookback_hours: int,
        realtime_warmup_seconds: int
    ) -> dict:
        contract_id = contract.get(
            "id"
        )
        symbol = contract.get(
            "name"
        ) or self._contract_root_symbol(
            contract
        )
        blocks = []
        warnings = []
        latest_bar = None
        latest_bar_close = None

        if not contract_id:
            return {
                "symbol": symbol,
                "contract_id": contract_id,
                "tradable": False,
                "blocks": [
                    "Contract id is unavailable."
                ],
                "warnings": warnings
            }

        try:
            await self.realtime_service.start_market_hub(
                contract_id=contract_id
            )

            if realtime_warmup_seconds > 0:
                await asyncio.sleep(
                    realtime_warmup_seconds
                )

            latest = self.realtime_service.get_latest_data().get(
                "data",
                {}
            )
            quote = latest.get(
                "quote"
            )
            market_gate = self._evaluate_market_gate(
                market={
                    "quote": quote
                },
                max_quote_age_seconds=max_quote_age_seconds,
                expected_contract_id=contract_id
            )

            blocks.extend(
                market_gate.get(
                    "blocks",
                    []
                )
            )

            try:
                history = await (
                    self.trading_state_service
                    .history_service
                    .get_bars(
                        contract_id=contract_id,
                        start_time=self._utc_lookback_iso(
                            lookback_hours
                        ),
                        end_time=self._utc_now_iso(),
                        unit=2,
                        unit_number=5,
                        limit=1,
                        live=live
                    )
                )
                latest_bar = history.get(
                    "latest_bar"
                )
                latest_bar_close = self._bar_close_price(
                    latest_bar
                )

            except Exception as exc:
                warnings.append(
                    (
                        "Historical bar health check failed: "
                        f"{exc}"
                    )
                )

            scale_block = self._price_scale_block(
                current_price=market_gate.get(
                    "quote",
                    {}
                ).get(
                    "currentPrice"
                ),
                latest_bar_close=latest_bar_close,
                symbol=str(
                    symbol
                )
            )

            if scale_block:
                blocks.append(
                    scale_block
                )

            return {
                "symbol": symbol,
                "contract_id": contract_id,
                "tradable": len(
                    blocks
                ) == 0,
                "blocks": blocks,
                "warnings": warnings,
                "quote": market_gate.get(
                    "quote"
                ),
                "latest_bar": latest_bar,
                "latest_bar_close": latest_bar_close,
                "health_version": (
                    "AUTO_CONTRACT_HEALTH_V1"
                )
            }

        except Exception as exc:
            return {
                "symbol": symbol,
                "contract_id": contract_id,
                "tradable": False,
                "blocks": [
                    (
                        "Contract market-health check failed: "
                        f"{exc}"
                    )
                ],
                "warnings": warnings,
                "health_version": (
                    "AUTO_CONTRACT_HEALTH_V1"
                )
            }

    async def _filter_auto_contracts_by_market_health(
        self,
        contracts: list,
        live: bool,
        max_quote_age_seconds: int,
        lookback_hours: int
    ) -> tuple[list, list]:
        if not self._env_bool(
            "AUTO_CONTRACT_HEALTH_CHECK_ENABLED",
            True
        ):
            return contracts, []

        warmup_seconds = self._env_int(
            "AUTO_CONTRACT_HEALTH_WARMUP_SECONDS",
            2,
            minimum=0
        )

        health_results = []
        healthy_contracts = []

        for contract in contracts:
            health = await self._evaluate_auto_contract_health(
                contract=contract,
                live=live,
                max_quote_age_seconds=max_quote_age_seconds,
                lookback_hours=lookback_hours,
                realtime_warmup_seconds=warmup_seconds
            )
            health_results.append(
                health
            )

            if health.get(
                "tradable",
                False
            ):
                healthy_contracts.append(
                    contract
                )

        if healthy_contracts:
            return healthy_contracts, health_results

        return contracts, health_results

    def _is_auto_symbol(
        self,
        symbol: str
    ) -> bool:
        return str(
            symbol or ""
        ).strip().upper() in {
            "AUTO",
            "AI",
            "BEST"
        }

    async def _resolve_auto_symbol(
        self,
        account_id: int,
        live: bool,
        account_size: int = 50000,
        phase: str = "evaluation",
        max_position_quantity: int | None = None,
        max_quote_age_seconds: int = 30,
        lookback_hours: int = 72
    ):
        rotation = await self._refresh_instrument_rotation(
            account_id=account_id
        )

        discovery = await self._discover_auto_contracts(
            live=live,
            rotation=rotation
        )

        contracts = discovery.get(
            "contracts",
            []
        )

        if not contracts:
            raise ValueError(
                (
                    "No active contracts found from Topstep "
                    "contract search after applying "
                    "instrument-rotation blocks."
                )
            )

        positions = []

        try:
            positions_result = (
                await self.trading_state_service
                .position_service
                .get_open_positions(
                    account_id=account_id
                )
            )
            positions = positions_result.get(
                "positions",
                []
            )

        except Exception:
            positions = []

        position_exposure = self._position_exposure_by_root(
            positions
        )

        available_contracts = []

        for contract in contracts:
            root_symbol = self._contract_root_symbol(
                contract
            )
            current_quantity = position_exposure.get(
                root_symbol,
                0
            )
            root_max_quantity = self._root_max_position_quantity(
                root_symbol=root_symbol,
                default_max=max_position_quantity
            )

            if current_quantity >= root_max_quantity:
                continue

            if root_symbol == "MNQ":
                root_pnl = self._root_position_pnl_from_fields(
                    positions=positions,
                    root_symbol=root_symbol
                )

                if not self._mnq_allows_additional_position(
                    quantity=current_quantity,
                    pnl=root_pnl,
                    max_quantity=root_max_quantity
                ):
                    continue

            available_contracts.append(
                contract
            )

        if not available_contracts:
            available_contracts = contracts

        available_contracts = sorted(
            available_contracts,
            key=lambda contract: (
                position_exposure.get(
                    self._contract_root_symbol(
                        contract
                    ),
                    0
                ),
                self._contract_root_symbol(
                    contract
                )
                == "MNQ"
            )
        )

        market_health = []

        (
            available_contracts,
            market_health
        ) = await self._filter_auto_contracts_by_market_health(
            contracts=available_contracts,
            live=live,
            max_quote_age_seconds=max_quote_age_seconds,
            lookback_hours=lookback_hours
        )

        ai_selection = (
            self.strategy_service
            .select_contract_for_auto_trading(
                contracts=available_contracts,
                account_size=account_size,
                phase=phase,
                position_exposure=position_exposure,
                open_positions=positions,
                max_position_quantity=max_position_quantity
            )
        )

        selected_contract_id = ai_selection[
            "selected_contract_id"
        ]

        selected_contract = None

        for contract in available_contracts:
            if str(
                contract.get(
                    "id"
                )
            ) == selected_contract_id:
                selected_contract = contract
                break

        if selected_contract is None:
            selected_contract = available_contracts[0]

        selected_symbol = (
            ai_selection.get(
                "selected_symbol"
            )
            or self._contract_root_symbol(
                selected_contract
            )
        ).upper()

        return {
            "requested_symbol": "AUTO",
            "selected_symbol": selected_symbol,
            "contract": selected_contract,
            "contract_universe_count": len(
                contracts
            ),
            "topstep_active_contract_count": discovery.get(
                "total_active_found"
            ),
            "checked": discovery.get(
                "checked",
                []
            ),
            "instrument_rotation": rotation,
            "candidate_contracts": [
                self._summarize_contract(
                    contract,
                    position_exposure=position_exposure,
                    max_position_quantity=max_position_quantity
                )
                for contract in contracts
            ],
            "eligible_contracts": [
                self._summarize_contract(
                    contract,
                    position_exposure=position_exposure,
                    max_position_quantity=max_position_quantity
                )
                for contract in available_contracts
            ],
            "market_health": market_health,
            "position_exposure": position_exposure,
            "max_position_quantity": max_position_quantity,
            "ai_selection": ai_selection,
            "selection_version": (
                "DYNAMIC_AI_CONTRACT_SELECTOR_V1"
            ),
            "reason": ai_selection.get(
                "reason"
            )
        }

    async def _resolve_open_position_contract(
        self,
        account_id: int,
        live: bool
    ) -> dict | None:
        try:
            positions_result = (
                await self.trading_state_service
                .position_service
                .get_open_positions(
                    account_id=account_id
                )
            )

        except Exception:
            return None

        positions = positions_result.get(
            "positions",
            []
        )
        supported_roots = self._supported_auto_roots()

        managed_positions = [
            position
            for position in positions or []
            if (
                self._extract_position_root_symbol(
                    position
                )
                in supported_roots
            )
        ]

        if not managed_positions:
            return None

        managed_positions = sorted(
            managed_positions,
            key=self._position_sort_key
        )
        position = managed_positions[0]
        root_symbol = self._extract_position_root_symbol(
            position
        )

        if not root_symbol:
            return None

        contract = await self._resolve_active_contract(
            symbol=root_symbol,
            live=live
        )

        return {
            "requested_symbol": "AUTO",
            "selected_symbol": contract.get(
                "name"
            )
            or root_symbol,
            "contract": contract,
            "open_position_first": True,
            "managed_position": position,
            "position_exposure": self._position_exposure_by_root(
                positions
            ),
            "selection_version": (
                "OPEN_POSITION_FIRST_SELECTOR_V1"
            ),
            "reason": (
                "Existing open position is managed before "
                "selecting a new instrument."
            )
        }

    async def _resolve_active_contract(
        self,
        symbol: str,
        live: bool = False
    ):
        contracts_result = (
            await self.contract_service.search_contracts(
                search_text=symbol,
                live=live
            )
        )

        contracts = contracts_result.get(
            "contracts",
            []
        )

        if not contracts:
            raise ValueError(
                f"No contract found for symbol {symbol}."
            )

        for contract in contracts:
            if contract.get(
                "activeContract"
            ):
                return contract

        return contracts[0]

    async def _resolve_account(
        self,
        account_id: int
    ) -> dict:
        accounts_result = (
            await self.trading_state_service
            .account_service
            .get_accounts()
        )

        for account in accounts_result.get(
            "accounts",
            []
        ):
            if account.get(
                "id"
            ) == account_id:
                return account

        raise ValueError(
            f"Account {account_id} not found."
        )

    def _infer_account_size(
        self,
        account: dict
    ) -> int:
        supported_sizes = sorted(
            self.rule_service.rule_packs.keys()
        )

        text_parts = []

        for value in account.values():
            if isinstance(
                value,
                (
                    str,
                    int,
                    float
                )
            ):
                text_parts.append(
                    str(
                        value
                    )
                )

        account_text = " ".join(
            text_parts
        ).upper()

        for size in supported_sizes:
            size_in_k = int(
                size / 1000
            )

            if re.search(
                rf"(?<!\d){size_in_k}\s*K\b",
                account_text
            ):
                return size

            if str(
                size
            ) in account_text:
                return size

        balance = account.get(
            "balance"
        )

        try:
            balance = float(
                balance
            )

            return min(
                supported_sizes,
                key=lambda size: abs(
                    size
                    - balance
                )
            )

        except (
            TypeError,
            ValueError
        ):
            return 50000

    def _extract_number(
        self,
        source: dict,
        keys: tuple[str, ...]
    ) -> float | None:
        for key in keys:
            value = source.get(
                key
            )

            if value is None:
                continue

            try:
                return float(
                    value
                )

            except (
                TypeError,
                ValueError
            ):
                continue

        return None

    def _build_auto_config(
        self,
        account: dict,
        account_size: int,
        phase: str
    ) -> dict:
        rules = self.rule_service.get_rule_pack(
            account_size=account_size,
            phase=phase,
            enforce_daily_profit_cap=True
        )

        current_mll = self._extract_number(
            account,
            (
                "currentMll",
                "currentMLL",
                "mll",
                "maximumLossLimit",
                "maxLossLimit",
                "trailingThreshold",
                "liquidationThreshold"
            )
        )

        current_mll_source = "ACCOUNT"

        if current_mll is None:
            current_mll = float(
                rules[
                    "maximum_loss_limit_floor"
                ]
            )
            current_mll_source = "RULE_PACK_FLOOR"

        daily_loss_limit = self._extract_number(
            account,
            (
                "dailyLossLimit",
                "daily_loss_limit",
                "dll",
                "personalDailyLossLimit"
            )
        )

        daily_loss_limit_source = "ACCOUNT"

        if daily_loss_limit is None:
            daily_loss_limit = float(
                rules[
                    "daily_loss_limit"
                ]
            )
            daily_loss_limit_source = "RULE_PACK"

        planned_quantity = self._env_int(
            "AUTO_PLANNED_QUANTITY",
            1,
            minimum=1
        )
        max_position_quantity = self._env_int(
            "AUTO_MAX_POSITION_QUANTITY",
            3,
            minimum=1
        )

        planned_quantity = self._normalize_planned_quantity(
            planned_quantity=planned_quantity,
            max_position_quantity=max_position_quantity
        )

        return {
            "account_size": account_size,
            "planned_quantity": planned_quantity,
            "current_mll": current_mll,
            "current_mll_source": current_mll_source,
            "max_risk_per_trade": 100,
            "daily_loss_limit": daily_loss_limit,
            "daily_loss_limit_source": daily_loss_limit_source,
            "max_position_quantity": max_position_quantity,
            "max_quote_age_seconds": 30,
            "order_type": "MARKET",
            "lookback_hours": 72,
            "auto_start_realtime": True,
            "realtime_warmup_seconds": 3,
            "duplicate_order_cooldown_seconds": 300,
            "enforce_daily_profit_cap": True,
            "auto_calculate_evaluation_metrics": True,
            "evaluation_lookback_days": 14
        }

    def _build_pre_trade_rules(
        self,
        account: dict | None,
        account_size: int,
        symbol: str,
        planned_quantity: int,
        current_mll: float | None,
        best_day_profit: float | None,
        daily_pnl: float | None,
        evaluation_trading_days: int | None,
        phase: str,
        enforce_daily_profit_cap: bool
    ) -> dict:
        if not account:
            return {
                "success": False,
                "status": "UNKNOWN",
                "reason": "Account state is unavailable."
            }

        rule_result = self.rule_service.evaluate_rules(
            account=account,
            account_size=account_size,
            symbol=symbol,
            planned_quantity=planned_quantity,
            current_mll=current_mll,
            best_day_profit=best_day_profit,
            daily_pnl=daily_pnl,
            evaluation_trading_days=(
                evaluation_trading_days
            ),
            phase=phase,
            enforce_daily_profit_cap=(
                enforce_daily_profit_cap
            )
        )

        return {
            "success": True,
            "status": rule_result.get(
                "status"
            ),
            "phase": rule_result.get(
                "phase"
            ),
            "account_size": rule_result.get(
                "account_size"
            ),
            "symbol": rule_result.get(
                "symbol"
            ),
            "account_state": rule_result.get(
                "account_state"
            ),
            "profit_target": rule_result.get(
                "profit_target"
            ),
            "evaluation_progress": rule_result.get(
                "evaluation_progress"
            ),
            "daily_profit_cap": rule_result.get(
                "daily_profit_cap"
            ),
            "maximum_loss_limit": rule_result.get(
                "maximum_loss_limit"
            ),
            "position_limit": rule_result.get(
                "position_limit"
            ),
            "violations": rule_result.get(
                "violations",
                []
            ),
            "warnings": rule_result.get(
                "warnings",
                []
            )
        }

    def _build_daily_profit_lock(
        self,
        pre_trade_rules: dict,
        positions: list
    ) -> dict:
        daily_cap = (
            pre_trade_rules
            or {}
        ).get(
            "daily_profit_cap",
            {}
        )

        cap_enabled = bool(
            daily_cap.get(
                "enabled",
                False
            )
        )

        cap_reached = bool(
            daily_cap.get(
                "reached",
                False
            )
        )

        position_count = len(
            positions
            or []
        )

        status = (
            "DONE_FOR_DAY"
            if cap_enabled
            and cap_reached
            else "ACTIVE"
        )

        return {
            "enabled": cap_enabled,
            "status": status,
            "done_for_day": (
                status == "DONE_FOR_DAY"
            ),
            "current_trading_day_pnl": daily_cap.get(
                "current_trading_day_pnl"
            ),
            "cap": daily_cap.get(
                "cap"
            ),
            "position_count": position_count,
            "close_open_positions": (
                status == "DONE_FOR_DAY"
                and position_count > 0
            ),
            "reason": (
                (
                    "Trading-day profit cap reached. "
                    "New entries are blocked and open "
                    "positions must be closed."
                )
                if status == "DONE_FOR_DAY"
                else None
            )
        }

    def _build_position_management(
        self,
        contract: dict,
        positions: list,
        market_gate: dict | None,
        strategy: dict | None
    ) -> dict:
        quote = (
            market_gate
            or {}
        ).get(
            "quote",
            {}
        )
        current_price = self._to_float(
            quote.get(
                "currentPrice"
            )
        )

        profit_exit_usd = self._env_float(
            "POSITION_PROFIT_EXIT_USD",
            45.0
        )
        rescan_loss_usd = abs(
            self._env_float(
                "POSITION_RESCAN_LOSS_USD",
                50.0
            )
        )
        hard_loss_exit_usd = abs(
            self._env_float(
                "POSITION_HARD_LOSS_EXIT_USD",
                100.0
            )
        )
        min_hold_hours = self._env_float(
            "POSITION_MIN_HOLD_HOURS",
            10.0
        )
        max_hold_hours = self._env_float(
            "POSITION_MAX_HOLD_HOURS",
            12.0
        )

        matched_positions = [
            position
            for position in positions or []
            if self._position_matches_contract(
                position=position,
                contract=contract
            )
        ]

        if not matched_positions:
            return {
                "enabled": True,
                "status": "NO_POSITION",
                "action": "NONE",
                "reason": None,
                "profit_exit_usd": profit_exit_usd,
                "rescan_loss_usd": rescan_loss_usd,
                "hard_loss_exit_usd": hard_loss_exit_usd,
                "min_hold_hours": min_hold_hours,
                "max_hold_hours": max_hold_hours
            }

        details = []
        total_pnl = 0.0
        pnl_available = True
        primary_side = None

        for position in matched_positions:
            pnl = self._calculate_position_pnl(
                position=position,
                contract=contract,
                current_price=current_price
            )

            if pnl is None:
                pnl_available = False
            else:
                total_pnl += pnl

            primary_side = (
                primary_side
                or self._extract_position_action_side(
                    position
                )
            )

            details.append(
                {
                    "contract_id": (
                        self._extract_position_contract_id(
                            position
                        )
                    ),
                    "side": self._extract_position_action_side(
                        position
                    ),
                    "quantity": self._extract_position_quantity(
                        position
                    ),
                    "average_price": position.get(
                        "averagePrice"
                    ),
                    "age_hours": self._position_age_hours(
                        position
                    ),
                    "estimated_pnl": pnl
                }
            )

        expired_positions = [
            detail
            for detail in details
            if (
                detail.get(
                    "age_hours"
                )
                is not None
                and detail.get(
                    "age_hours"
                )
                >= max_hold_hours
            )
        ]

        if expired_positions:
            oldest_age = max(
                detail.get(
                    "age_hours"
                )
                or 0
                for detail in expired_positions
            )

            return {
                "enabled": True,
                "status": "TIME_BRACKET_EXIT",
                "action": "EXIT",
                "estimated_pnl": total_pnl,
                "current_price": current_price,
                "positions": details,
                "reason": (
                    f"Client 10-12 hour holding bracket reached: "
                    f"oldest position age {oldest_age:.2f}h >= "
                    f"{max_hold_hours:.2f}h."
                ),
                "profit_exit_usd": profit_exit_usd,
                "rescan_loss_usd": rescan_loss_usd,
                "hard_loss_exit_usd": hard_loss_exit_usd,
                "min_hold_hours": min_hold_hours,
                "max_hold_hours": max_hold_hours
            }

        if not pnl_available:
            return {
                "enabled": True,
                "status": "PENDING",
                "action": "NONE",
                "reason": (
                    "Position P&L could not be calculated from "
                    "the current quote and position details."
                ),
                "current_price": current_price,
                "positions": details,
                "profit_exit_usd": profit_exit_usd,
                "rescan_loss_usd": rescan_loss_usd,
                "hard_loss_exit_usd": hard_loss_exit_usd
            }

        if total_pnl >= profit_exit_usd:
            return {
                "enabled": True,
                "status": "PROFIT_EXIT",
                "action": "EXIT",
                "estimated_pnl": total_pnl,
                "current_price": current_price,
                "positions": details,
                "reason": (
                    f"Client profit target reached: "
                    f"${total_pnl:.2f} >= ${profit_exit_usd:.2f}."
                ),
                "profit_exit_usd": profit_exit_usd,
                "rescan_loss_usd": rescan_loss_usd,
                "hard_loss_exit_usd": hard_loss_exit_usd
            }

        if total_pnl <= -hard_loss_exit_usd:
            return {
                "enabled": True,
                "status": "HARD_LOSS_EXIT",
                "action": "EXIT",
                "estimated_pnl": total_pnl,
                "current_price": current_price,
                "positions": details,
                "reason": (
                    f"Client hard loss limit reached: "
                    f"${total_pnl:.2f} <= -${hard_loss_exit_usd:.2f}."
                ),
                "profit_exit_usd": profit_exit_usd,
                "rescan_loss_usd": rescan_loss_usd,
                "hard_loss_exit_usd": hard_loss_exit_usd
            }

        strategy_action = str(
            (
                strategy
                or {}
            ).get(
                "action",
                "WAIT"
            )
        ).upper()
        opposite_action = self._opposite_action(
            primary_side
        )

        if (
            total_pnl <= -rescan_loss_usd
            and strategy_action == opposite_action
        ):
            return {
                "enabled": True,
                "status": "REVERSAL_READY",
                "action": "REVERSE",
                "reverse_action": opposite_action,
                "estimated_pnl": total_pnl,
                "current_price": current_price,
                "positions": details,
                "reason": (
                    f"Client rescan loss threshold reached: "
                    f"${total_pnl:.2f} <= -${rescan_loss_usd:.2f}; "
                    f"AI confirmed opposite action {opposite_action}."
                ),
                "profit_exit_usd": profit_exit_usd,
                "rescan_loss_usd": rescan_loss_usd,
                "hard_loss_exit_usd": hard_loss_exit_usd
            }

        if total_pnl <= -rescan_loss_usd:
            return {
                "enabled": True,
                "status": "RESCAN_HOLD",
                "action": "NONE",
                "estimated_pnl": total_pnl,
                "current_price": current_price,
                "positions": details,
                "reason": (
                    f"Client rescan loss threshold reached: "
                    f"${total_pnl:.2f} <= -${rescan_loss_usd:.2f}, "
                    "but AI did not confirm a reversal."
                ),
                "profit_exit_usd": profit_exit_usd,
                "rescan_loss_usd": rescan_loss_usd,
                "hard_loss_exit_usd": hard_loss_exit_usd
            }

        return {
            "enabled": True,
            "status": "ACTIVE",
            "action": "NONE",
            "estimated_pnl": total_pnl,
            "current_price": current_price,
            "positions": details,
            "reason": None,
            "profit_exit_usd": profit_exit_usd,
            "rescan_loss_usd": rescan_loss_usd,
            "hard_loss_exit_usd": hard_loss_exit_usd
        }

    def _management_exit_decision(
        self,
        reason: str
    ) -> tuple[dict, dict]:
        final_decision = {
            "success": True,
            "final_status": "ALLOW",
            "action": "EXIT",
            "execution_allowed": True,
            "reason": reason,
            "decision_version": (
                "FINAL_DECISION_POSITION_MANAGEMENT_V1"
            )
        }

        safety = {
            "success": True,
            "safety_status": "PASS",
            "safe_to_execute": True,
            "action": "EXIT",
            "blocks": [],
            "warnings": [],
            "safety_version": (
                "SAFETY_POSITION_MANAGEMENT_V1"
            )
        }

        return final_decision, safety

    async def _run_decision_safety_workflow(
        self,
        account_id: int,
        contract_id: str,
        account_size: int,
        symbol: str,
        search_text: str,
        planned_quantity: int,
        current_mll: float | None,
        best_day_profit: float | None,
        max_risk_per_trade: float | None,
        daily_pnl: float | None,
        evaluation_trading_days: int | None,
        daily_loss_limit: float | None,
        max_position_quantity: int | None,
        kill_switch: bool,
        max_quote_age_seconds: int,
        start_time: str | None,
        end_time: str | None,
        live: bool,
        phase: str,
        enforce_daily_profit_cap: bool
    ):
        state = await self.trading_state_service.get_trading_state(
            account_id=account_id,
            contract_id=contract_id,
            search_text=search_text,
            live=live,
            start_time=start_time,
            end_time=end_time,
            unit=2,
            unit_number=5,
            limit=100
        )

        account = state.get(
            "account"
        )

        contract = state.get(
            "contract"
        )

        market = state.get(
            "market",
            {}
        )

        positions = state.get(
            "positions",
            []
        )

        open_orders = state.get(
            "open_orders",
            []
        )

        market_gate = self._evaluate_market_gate(
            market=market,
            max_quote_age_seconds=max_quote_age_seconds,
            expected_contract_id=contract_id
        )

        if not account:
            raise ValueError(
                "Account state is unavailable."
            )

        if not contract:
            raise ValueError(
                "Contract state is unavailable."
            )

        effective_max_position_quantity = (
            self._contract_max_position_quantity(
                contract=contract,
                default_max=max_position_quantity
            )
        )

        if not market_gate.get(
            "tradable",
            False
        ):
            gate_blocks = market_gate.get(
                "blocks",
                []
            )

            reason = (
                "Market data is not fresh enough for "
                "AI trade evaluation."
            )

            if gate_blocks:
                reason = gate_blocks[0]

            strategy_result = {
                "success": True,
                "status": "BLOCK",
                "action": "WAIT",
                "ai_used": False,
                "reason": reason,
                "market": {
                    "current_price": market_gate.get(
                        "quote",
                        {}
                    ).get(
                        "currentPrice"
                    ),
                    "current_price_source": market_gate.get(
                        "quote",
                        {}
                    ).get(
                        "currentPriceSource"
                    )
                },
                "ai_analysis": {
                    "confidence": 0,
                    "market_bias": "UNKNOWN",
                    "setup_valid": False,
                    "data_quality": "STALE",
                    "validation_errors": gate_blocks,
                    "reason": reason
                },
                "strategy_version": "MARKET_GATE_V1",
                "model": None
            }

            final_decision = {
                "success": True,
                "final_status": "BLOCK",
                "action": "WAIT",
                "execution_allowed": False,
                "reason": reason,
                "market_gate": market_gate,
                "decision_version": (
                    "FINAL_DECISION_MARKET_GATE_V1"
                )
            }

            safety_result = {
                "success": True,
                "safety_status": "BLOCK",
                "safe_to_execute": False,
                "action": "WAIT",
                "blocks": gate_blocks,
                "warnings": [],
                "market_gate": market_gate,
                "safety_version": "SAFETY_MARKET_GATE_V1"
            }

            return {
                "success": True,
                "state": state,
                "strategy": strategy_result,
                "rule": None,
                "risk": None,
                "final_decision": final_decision,
                "safety": safety_result,
                "ready_for_execution": False,
                "market_gate": market_gate
            }

        strategy_result = self.strategy_service.evaluate_strategy(
            symbol=symbol,
            contract=contract,
            quote=market.get(
                "quote"
            ),
            historical_bars=market.get(
                "historical_bars"
            ) or [],
            depth=market.get(
                "depth"
            ),
            positions=positions,
            open_orders=open_orders
        )

        ai_action = str(
            strategy_result.get(
                "action",
                "WAIT"
            )
        ).upper()

        if ai_action in {
            "BUY",
            "SELL"
        }:
            min_confidence = self._min_trade_confidence()
            confidence = self._to_float(
                strategy_result.get(
                    "ai_analysis",
                    {}
                ).get(
                    "confidence"
                )
            )

            if (
                confidence is None
                or confidence < min_confidence
            ):
                reason = (
                    "Trade confidence is below required threshold: "
                    f"{confidence if confidence is not None else 'N/A'} "
                    f"< {min_confidence:.2f}."
                )
                strategy_result = {
                    **strategy_result,
                    "status": "BLOCK",
                    "action": "WAIT",
                    "reason": reason,
                    "ai_analysis": {
                        **strategy_result.get(
                            "ai_analysis",
                            {}
                        ),
                        "setup_valid": False,
                        "reason": reason
                    }
                }
                ai_action = "WAIT"

        if ai_action in {
            "BUY",
            "SELL"
        }:
            root_symbol = self._contract_root_symbol(
                contract
            )
            current_contract_quantity = sum(
                self._extract_position_quantity(
                    position
                )
                for position in positions or []
                if self._position_matches_contract(
                    position=position,
                    contract=contract
                )
            )

            if (
                root_symbol == "MNQ"
                and not self._mnq_allows_additional_position(
                    quantity=current_contract_quantity,
                    pnl=self._contract_position_pnl(
                        positions=positions,
                        contract=contract,
                        current_price=market_gate.get(
                            "quote",
                            {}
                        ).get(
                            "currentPrice"
                        )
                    ),
                    max_quantity=effective_max_position_quantity
                )
            ):
                reason = (
                    "MNQ is treated as the high-volatility "
                    "instrument: only one MNQ position is allowed "
                    "initially, and a second MNQ position is allowed "
                    "only after the first is profitable."
                )
                strategy_result = {
                    **strategy_result,
                    "status": "BLOCK",
                    "action": "WAIT",
                    "reason": reason,
                    "ai_analysis": {
                        **strategy_result.get(
                            "ai_analysis",
                            {}
                        ),
                        "setup_valid": False,
                        "reason": reason
                    }
                }
                ai_action = "WAIT"

        rule_result = None
        risk_result = None

        if ai_action in {
            "BUY",
            "SELL"
        }:
            rule_result = self.rule_service.evaluate_rules(
                account=account,
                account_size=account_size,
                symbol=symbol,
                planned_quantity=planned_quantity,
                current_mll=current_mll,
                best_day_profit=best_day_profit,
                daily_pnl=daily_pnl,
                phase=phase,
                enforce_daily_profit_cap=(
                    enforce_daily_profit_cap
                ),
                evaluation_trading_days=(
                    evaluation_trading_days
                )
            )

            trade_plan = strategy_result.get(
                "trade_plan",
                {}
            )

            entry_price = trade_plan.get(
                "entry_price"
            )

            stop_loss = trade_plan.get(
                "stop_loss"
            )

            if (
                entry_price is not None
                and stop_loss is not None
            ):
                risk_result = self.risk_service.evaluate_risk(
                    account=account,
                    contract=contract,
                    entry_price=float(
                        entry_price
                    ),
                    stop_price=float(
                        stop_loss
                    ),
                    planned_quantity=planned_quantity,
                    current_mll=current_mll,
                    max_risk_per_trade=max_risk_per_trade
                )

        final_decision = self.decision_service.evaluate_decision(
            strategy_result=strategy_result,
            rule_result=rule_result,
            risk_result=risk_result,
            planned_quantity=planned_quantity
        )

        safety_result = self.safety_service.evaluate_safety(
            final_decision=final_decision,
            trading_state=state,
            planned_quantity=planned_quantity,
            kill_switch=kill_switch,
            daily_pnl=daily_pnl,
            daily_loss_limit=daily_loss_limit,
            current_mll=current_mll,
            max_position_quantity=effective_max_position_quantity,
            max_quote_age_seconds=max_quote_age_seconds
        )

        return {
            "success": True,
            "state": state,
            "strategy": strategy_result,
            "rule": rule_result,
            "risk": risk_result,
            "final_decision": final_decision,
            "safety": safety_result,
            "ready_for_execution": (
                final_decision.get(
                    "execution_allowed",
                    False
                )
                and safety_result.get(
                    "safe_to_execute",
                    False
                )
            ),
            "market_gate": market_gate
        }

    async def run_once(
        self,
        account_id: int,
        symbol: str = "AUTO",
        dry_run: bool = True,
        account_size: int = 50000,
        planned_quantity: int = 1,
        current_mll: float | None = None,
        best_day_profit: float | None = None,
        max_risk_per_trade: float | None = None,
        daily_pnl: float | None = None,
        evaluation_trading_days: int | None = None,
        daily_loss_limit: float | None = None,
        max_position_quantity: int | None = None,
        kill_switch: bool = False,
        max_quote_age_seconds: int = 30,
        order_type: str = "MARKET",
        lookback_hours: int = 72,
        auto_start_realtime: bool = True,
        realtime_warmup_seconds: int = 3,
        live: bool = False,
        duplicate_order_cooldown_seconds: int = 300,
        phase: str = "evaluation",
        enforce_daily_profit_cap: bool = True,
        auto_calculate_evaluation_metrics: bool = True,
        evaluation_start_time: str | None = None,
        evaluation_lookback_days: int = 14,
        confirm_live_execution: bool = False
    ):
        evaluation_metrics = None
        requested_symbol = symbol
        symbol_selection = None
        resolved_contract = None

        if max_position_quantity is None:
            max_position_quantity = self._env_int(
                "AUTO_MAX_POSITION_QUANTITY",
                3,
                minimum=1
            )

        planned_quantity = self._normalize_planned_quantity(
            planned_quantity=planned_quantity,
            max_position_quantity=max_position_quantity
        )

        if self._is_auto_symbol(
            symbol
        ):
            symbol_selection = (
                await self._resolve_open_position_contract(
                    account_id=account_id,
                    live=live
                )
            )

            if symbol_selection is None:
                symbol_selection = await self._resolve_auto_symbol(
                    account_id=account_id,
                    live=live,
                    account_size=account_size,
                    phase=phase,
                    max_position_quantity=max_position_quantity,
                    max_quote_age_seconds=max_quote_age_seconds,
                    lookback_hours=lookback_hours
                )

            symbol = symbol_selection[
                "selected_symbol"
            ]
            resolved_contract = symbol_selection[
                "contract"
            ]

        normalized_phase = str(
            phase
        ).lower().strip()

        if (
            auto_calculate_evaluation_metrics
            and self.trading_day_service is not None
            and (
                daily_pnl is None
                or (
                    normalized_phase == "evaluation"
                    and (
                        best_day_profit is None
                        or evaluation_trading_days is None
                    )
                )
            )
        ):
            try:
                if normalized_phase == "evaluation":
                    evaluation_metrics = (
                        await self.trading_day_service
                        .get_evaluation_progress(
                            account_id=account_id,
                            evaluation_start_time=(
                                evaluation_start_time
                            ),
                            lookback_days=evaluation_lookback_days
                        )
                    )

                else:
                    evaluation_metrics = (
                        await self.trading_day_service
                        .get_current_trading_day_pnl(
                            account_id=account_id
                        )
                    )

            except Exception as exc:
                evaluation_metrics = {
                    "success": False,
                    "error": str(
                        exc
                    ),
                    "warnings": [
                        (
                            "Trading-day metrics could not be "
                            "auto-calculated."
                        )
                    ]
                }

            else:
                if daily_pnl is None:
                    daily_pnl = evaluation_metrics.get(
                        "current_trading_day_pnl"
                    )

                if (
                    normalized_phase == "evaluation"
                    and best_day_profit is None
                ):
                    best_day_profit = evaluation_metrics.get(
                        "best_day_profit"
                    )

                if (
                    normalized_phase == "evaluation"
                    and evaluation_trading_days is None
                ):
                    evaluation_trading_days = (
                        evaluation_metrics.get(
                            "evaluation_trading_days"
                        )
                    )

        request_context = {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "requested_symbol": requested_symbol,
            "account_id": account_id,
            "symbol": symbol,
            "symbol_selection": symbol_selection,
            "dry_run": dry_run,
            "account_size": account_size,
            "planned_quantity": planned_quantity,
            "current_mll": current_mll,
            "best_day_profit": best_day_profit,
            "max_risk_per_trade": max_risk_per_trade,
            "daily_pnl": daily_pnl,
            "evaluation_trading_days": evaluation_trading_days,
            "daily_loss_limit": daily_loss_limit,
            "max_position_quantity": max_position_quantity,
            "kill_switch": kill_switch,
            "max_quote_age_seconds": max_quote_age_seconds,
            "order_type": order_type,
            "lookback_hours": lookback_hours,
            "auto_start_realtime": auto_start_realtime,
            "realtime_warmup_seconds": realtime_warmup_seconds,
            "live": live,
            "duplicate_order_cooldown_seconds": (
                duplicate_order_cooldown_seconds
            ),
            "phase": phase,
            "enforce_daily_profit_cap": (
                enforce_daily_profit_cap
            ),
            "auto_calculate_evaluation_metrics": (
                auto_calculate_evaluation_metrics
            ),
            "evaluation_start_time": evaluation_start_time,
            "evaluation_lookback_days": evaluation_lookback_days,
            "confirm_live_execution": (
                confirm_live_execution
            )
        }

        state_snapshot = None
        persistent_kill_switch = False

        if self.bot_state_service is not None:
            state_snapshot = self.bot_state_service.mark_run_started(
                account_id=account_id,
                symbol=symbol,
                dry_run=dry_run,
                live=live
            )

            persistent_kill_switch = bool(
                state_snapshot.get(
                    "kill_switch",
                    {}
                ).get(
                    "enabled",
                    False
                )
            )

        effective_kill_switch = (
            kill_switch
            or persistent_kill_switch
        )

        request_context["request_kill_switch"] = kill_switch
        request_context["persistent_kill_switch"] = (
            persistent_kill_switch
        )
        request_context["kill_switch"] = effective_kill_switch

        contract = (
            resolved_contract
            or await self._resolve_active_contract(
                symbol=symbol,
                live=live
            )
        )

        contract_id = contract.get(
            "id"
        )

        if not contract_id:
            raise ValueError(
                "Resolved contract does not include an id."
            )

        realtime_started = False

        if auto_start_realtime:
            await self.realtime_service.start_user_hub(
                account_id=account_id
            )

            await self.realtime_service.start_market_hub(
                contract_id=contract_id
            )

            realtime_started = True

            await asyncio.sleep(
                max(
                    realtime_warmup_seconds,
                    0
                )
            )

        start_time = self._utc_lookback_iso(
            lookback_hours
        )

        end_time = self._utc_now_iso()

        workflow = await self._run_decision_safety_workflow(
            account_id=account_id,
            contract_id=contract_id,
            account_size=account_size,
            symbol=symbol,
            search_text=symbol,
            planned_quantity=planned_quantity,
            current_mll=current_mll,
            best_day_profit=best_day_profit,
            max_risk_per_trade=max_risk_per_trade,
            daily_pnl=daily_pnl,
            evaluation_trading_days=(
                evaluation_trading_days
            ),
            daily_loss_limit=daily_loss_limit,
            max_position_quantity=max_position_quantity,
            kill_switch=effective_kill_switch,
            max_quote_age_seconds=max_quote_age_seconds,
            start_time=start_time,
            end_time=end_time,
            live=live,
            phase=phase,
            enforce_daily_profit_cap=(
                enforce_daily_profit_cap
            )
        )

        state = workflow.get(
            "state",
            {}
        )

        market = state.get(
            "market",
            {}
        )

        strategy = workflow.get(
            "strategy",
            {}
        )

        strategy_analysis = strategy.get(
            "ai_analysis",
            {}
        )

        rule = workflow.get(
            "rule"
        )

        risk = workflow.get(
            "risk"
        )

        positions = state.get(
            "positions",
            []
        )

        pre_trade_rules = self._build_pre_trade_rules(
            account=state.get(
                "account"
            ),
            account_size=account_size,
            symbol=symbol,
            planned_quantity=planned_quantity,
            current_mll=current_mll,
            best_day_profit=best_day_profit,
            daily_pnl=daily_pnl,
            evaluation_trading_days=(
                evaluation_trading_days
            ),
            phase=phase,
            enforce_daily_profit_cap=(
                enforce_daily_profit_cap
            )
        )

        daily_profit_lock = self._build_daily_profit_lock(
            pre_trade_rules=pre_trade_rules,
            positions=positions
        )

        final_decision = workflow.get(
            "final_decision",
            {}
        )

        safety = workflow.get(
            "safety",
            {}
        )

        market_gate = workflow.get(
            "market_gate"
        )

        execution_guard = None
        position_management = self._build_position_management(
            contract=contract,
            positions=positions,
            market_gate=market_gate,
            strategy=strategy
        )

        if daily_profit_lock.get(
            "done_for_day"
        ):
            close_positions = bool(
                daily_profit_lock.get(
                    "close_open_positions"
                )
            )

            final_decision = {
                "success": True,
                "final_status": "DONE_FOR_DAY",
                "action": (
                    "EXIT"
                    if close_positions
                    else "WAIT"
                ),
                "execution_allowed": close_positions,
                "reason": daily_profit_lock.get(
                    "reason"
                ),
                "decision_version": (
                    "FINAL_DECISION_DAILY_PROFIT_LOCK_V1"
                )
            }

            safety = {
                "success": True,
                "safety_status": (
                    "PASS"
                    if close_positions
                    else "BLOCK"
                ),
                "safe_to_execute": close_positions,
                "action": final_decision[
                    "action"
                ],
                "blocks": (
                    []
                    if close_positions
                    else [
                        (
                            "Trading-day profit cap reached "
                            "and no open positions remain."
                        )
                    ]
                ),
                "warnings": [],
                "safety_version": (
                    "SAFETY_DAILY_PROFIT_LOCK_V1"
                )
            }

            workflow["final_decision"] = final_decision
            workflow["safety"] = safety
            workflow["ready_for_execution"] = (
                close_positions
            )

            execution_result = (
                await self.execution_service.close_all_positions(
                    account_id=account_id,
                    positions=positions,
                    dry_run=dry_run,
                    confirm_live_execution=(
                        confirm_live_execution
                    ),
                    reason=daily_profit_lock.get(
                        "reason"
                    )
                )
            )

        elif position_management.get(
            "action"
        ) in {
            "EXIT",
            "REVERSE"
        }:
            management_reason = (
                position_management.get(
                    "reason"
                )
                or "Client position-management rule triggered."
            )

            final_decision, safety = self._management_exit_decision(
                reason=management_reason
            )

            workflow["final_decision"] = final_decision
            workflow["safety"] = safety
            workflow["ready_for_execution"] = True

            close_result = await self.execution_service.execute(
                account_id=account_id,
                contract_id=contract_id,
                final_decision=final_decision,
                safety_result=safety,
                contract=contract,
                dry_run=dry_run,
                order_type=order_type,
                confirm_live_execution=(
                    confirm_live_execution
                )
            )

            execution_result = close_result

            if (
                position_management.get(
                    "action"
                )
                == "REVERSE"
            ):
                reverse_action = position_management.get(
                    "reverse_action"
                )
                reverse_decision = {
                    **workflow.get(
                        "final_decision",
                        {}
                    ),
                    "success": True,
                    "final_status": "ALLOW",
                    "action": reverse_action,
                    "execution_allowed": True,
                    "planned_quantity": planned_quantity,
                    "reason": management_reason,
                    "strategy": {
                        "status": "READY",
                        "action": reverse_action,
                        "ai_analysis": strategy.get(
                            "ai_analysis",
                            {}
                        ),
                        "trade_plan": strategy.get(
                            "trade_plan",
                            {}
                        )
                    },
                    "decision_version": (
                        "FINAL_DECISION_POSITION_REVERSAL_V1"
                    )
                }
                reverse_safety = {
                    "success": True,
                    "safety_status": "PASS",
                    "safe_to_execute": True,
                    "action": reverse_action,
                    "blocks": [],
                    "warnings": [
                        (
                            "Reverse order allowed only after "
                            "the close-position request succeeds."
                        )
                    ],
                    "safety_version": (
                        "SAFETY_POSITION_REVERSAL_V1"
                    )
                }

                close_ok = (
                    dry_run
                    or close_result.get(
                        "submitted",
                        False
                    )
                )

                reverse_result = None

                if close_ok:
                    reverse_result = (
                        await self.execution_service.execute(
                            account_id=account_id,
                            contract_id=contract_id,
                            final_decision=reverse_decision,
                            safety_result=reverse_safety,
                            contract=contract,
                            dry_run=dry_run,
                            order_type=order_type,
                            confirm_live_execution=(
                                confirm_live_execution
                            )
                        )
                    )

                execution_result = {
                    "success": True,
                    "execution_status": (
                        "REVERSE_SUBMITTED"
                        if (
                            close_ok
                            and reverse_result
                            and reverse_result.get(
                                "submitted",
                                False
                            )
                        )
                        else (
                            "DRY_RUN_REVERSE_READY"
                            if dry_run
                            else "REVERSE_BLOCKED"
                        )
                    ),
                    "submitted": (
                        bool(
                            reverse_result.get(
                                "submitted",
                                False
                            )
                        )
                        if reverse_result
                        else False
                    ),
                    "dry_run": dry_run,
                    "action": "REVERSE",
                    "close_result": close_result,
                    "reverse_result": reverse_result,
                    "reason": management_reason
                }

        else:

            action_for_guard = str(
                final_decision.get(
                    "action",
                    "WAIT"
                )
            ).upper()

            if (
                self.bot_state_service is not None
                and action_for_guard in {
                    "BUY",
                    "SELL"
                }
                and final_decision.get(
                    "execution_allowed",
                    False
                )
                and safety.get(
                    "safe_to_execute",
                    False
                )
            ):
                execution_guard = (
                    self.bot_state_service
                    .check_duplicate_order_intent(
                        account_id=account_id,
                        contract_id=contract_id,
                        action=action_for_guard,
                        cooldown_seconds=(
                            duplicate_order_cooldown_seconds
                        )
                    )
                )

                if not execution_guard.get(
                    "allowed",
                    False
                ):
                    guard_reason = execution_guard.get(
                        "reason",
                        "Duplicate order intent blocked."
                    )

                    safety_blocks = list(
                        safety.get(
                            "blocks",
                            []
                        )
                    )

                    safety_blocks.append(
                        guard_reason
                    )

                    safety = {
                        **safety,
                        "safety_status": "BLOCK",
                        "safe_to_execute": False,
                        "blocks": safety_blocks
                    }

                    final_decision = {
                        **final_decision,
                        "execution_allowed": False,
                        "duplicate_order_blocked": True
                    }

                    workflow["safety"] = safety
                    workflow["final_decision"] = final_decision
                    workflow["ready_for_execution"] = False

            execution_result = await self.execution_service.execute(
                account_id=account_id,
                contract_id=contract_id,
                final_decision=final_decision,
                safety_result=safety,
                contract=contract,
                dry_run=dry_run,
                order_type=order_type,
                confirm_live_execution=(
                    confirm_live_execution
                )
            )

        execution_action = str(
            execution_result.get(
                "action",
                ""
            )
        ).upper()

        if (
            self.bot_state_service is not None
            and execution_action in {
                "BUY",
                "SELL"
            }
            and execution_result.get(
                "execution_status"
            )
            in {
                "DRY_RUN_READY",
                "SUBMITTED",
                "REJECTED"
            }
        ):
            order_payload = execution_result.get(
                "order_payload",
                {}
            )

            self.bot_state_service.record_order_intent(
                account_id=account_id,
                contract_id=contract_id,
                action=execution_action,
                dry_run=dry_run,
                execution_status=execution_result.get(
                    "execution_status"
                ),
                submitted=execution_result.get(
                    "submitted"
                ),
                custom_tag=order_payload.get(
                    "customTag"
                )
            )

        if execution_guard is None:
            execution_guard = {
                "checked": False,
                "duplicate": False,
                "cooldown_seconds": (
                    duplicate_order_cooldown_seconds
                )
            }

        else:
            execution_guard = {
                "checked": True,
                **execution_guard
            }

        result = {
            "success": True,
            "mode": (
                "dry_run"
                if dry_run
                else (
                    "live"
                    if live
                    else "evaluation_live"
                )
            ),
            "symbol": symbol,
            "requested_symbol": requested_symbol,
            "symbol_selection": symbol_selection,
            "phase": phase,
            "contract": {
                "id": contract_id,
                "name": contract.get(
                    "name"
                ),
                "description": contract.get(
                    "description"
                ),
                "tickSize": contract.get(
                    "tickSize"
                ),
                "tickValue": contract.get(
                    "tickValue"
                )
            },
            "realtime_started": realtime_started,
            "history": {
                "start_time": start_time,
                "end_time": end_time,
                "bar_count": len(
                    market.get(
                        "historical_bars"
                    )
                    or []
                )
            },
            "strategy": {
                "status": strategy.get(
                    "status"
                ),
                "action": strategy.get(
                    "action"
                ),
                "ai_used": strategy.get(
                    "ai_used"
                ),
                "current_price": strategy.get(
                    "market",
                    {}
                ).get(
                    "current_price"
                ),
                "current_price_source": strategy.get(
                    "market",
                    {}
                ).get(
                    "current_price_source"
                ),
                "confidence": strategy_analysis.get(
                    "confidence"
                ),
                "market_bias": strategy_analysis.get(
                    "market_bias"
                ),
                "setup_valid": strategy_analysis.get(
                    "setup_valid"
                ),
                "data_quality": strategy_analysis.get(
                    "data_quality"
                ),
                "validation_errors": strategy_analysis.get(
                    "validation_errors",
                    []
                ),
                "reason": (
                    strategy.get(
                        "reason"
                    )
                    or strategy.get(
                        "ai_analysis",
                        {}
                    ).get(
                        "reason"
                    )
                ),
                "strategy_version": strategy.get(
                    "strategy_version"
                ),
                "model": strategy.get(
                    "model"
                )
            },
            "decision": {
                "final_status": final_decision.get(
                    "final_status"
                ),
                "action": final_decision.get(
                    "action"
                ),
                "execution_allowed": final_decision.get(
                    "execution_allowed"
                )
            },
            "market_gate": market_gate,
            "pre_trade_rules": pre_trade_rules,
            "daily_profit_lock": daily_profit_lock,
            "position_management": position_management,
            "rule": rule,
            "risk": risk,
            "safety": {
                "safety_status": safety.get(
                    "safety_status"
                ),
                "safe_to_execute": safety.get(
                    "safe_to_execute"
                ),
                "blocks": safety.get(
                    "blocks",
                    []
                )
            },
            "ready_for_execution": workflow.get(
                "ready_for_execution",
                False
            ),
            "execution_guard": execution_guard,
            "evaluation_metrics": evaluation_metrics,
            "execution": execution_result,
            "bot_version": "RUN_ONCE_V1",
            "bot_state": {
                "persistent_kill_switch": persistent_kill_switch,
                "effective_kill_switch": effective_kill_switch,
                "last_run_state": (
                    state_snapshot.get(
                        "last_run",
                        {}
                    ).get(
                        "state"
                    )
                    if state_snapshot
                    else None
                )
            }
        }

        if self.bot_state_service is not None:
            state_update = self.bot_state_service.mark_run_completed(
                result=result
            )

            result["bot_state"] = {
                "persistent_kill_switch": bool(
                    state_update.get(
                        "kill_switch",
                        {}
                    ).get(
                        "enabled",
                        False
                    )
                ),
                "effective_kill_switch": effective_kill_switch,
                "last_run_state": state_update.get(
                    "last_run",
                    {}
                ).get(
                    "state"
                ),
                "state_file": state_update.get(
                    "state_file"
                ),
                "state_backend": state_update.get(
                    "state_backend"
                ),
                "state_collection": state_update.get(
                    "state_collection"
                )
            }

        if self.audit_service is not None:
            audit = self.audit_service.log_bot_run(
                result=result,
                request_context=request_context
            )

            result["audit"] = {
                "logged": audit.get(
                    "success",
                    False
                ),
                "stored": audit.get(
                    "stored",
                    False
                ),
                "collection": audit.get(
                    "collection"
                ),
                "id": audit.get(
                    "id"
                ),
                "error": audit.get(
                    "error"
                )
            }

        return result

    async def run_auto(
        self,
        account_id: int,
        symbol: str = "AUTO",
        dry_run: bool = True,
        live: bool = False,
        phase: str = "evaluation",
        confirm_live_execution: bool = False
    ):
        phase = str(
            phase
        ).lower().strip()

        account = await self._resolve_account(
            account_id=account_id
        )

        account_size = self._infer_account_size(
            account=account
        )

        auto_config = self._build_auto_config(
            account=account,
            account_size=account_size,
            phase=phase
        )
        auto_config["confirm_live_execution"] = (
            confirm_live_execution
        )

        result = await self.run_once(
            account_id=account_id,
            symbol=symbol,
            dry_run=dry_run,
            account_size=auto_config[
                "account_size"
            ],
            planned_quantity=auto_config[
                "planned_quantity"
            ],
            current_mll=auto_config[
                "current_mll"
            ],
            best_day_profit=None,
            max_risk_per_trade=auto_config[
                "max_risk_per_trade"
            ],
            daily_pnl=None,
            evaluation_trading_days=None,
            daily_loss_limit=auto_config[
                "daily_loss_limit"
            ],
            max_position_quantity=auto_config[
                "max_position_quantity"
            ],
            kill_switch=False,
            max_quote_age_seconds=auto_config[
                "max_quote_age_seconds"
            ],
            order_type=auto_config[
                "order_type"
            ],
            lookback_hours=auto_config[
                "lookback_hours"
            ],
            auto_start_realtime=auto_config[
                "auto_start_realtime"
            ],
            realtime_warmup_seconds=auto_config[
                "realtime_warmup_seconds"
            ],
            live=live,
            duplicate_order_cooldown_seconds=(
                auto_config[
                    "duplicate_order_cooldown_seconds"
                ]
            ),
            phase=phase,
            enforce_daily_profit_cap=auto_config[
                "enforce_daily_profit_cap"
            ],
            auto_calculate_evaluation_metrics=(
                auto_config[
                    "auto_calculate_evaluation_metrics"
                ]
            ),
            evaluation_start_time=None,
            evaluation_lookback_days=auto_config[
                "evaluation_lookback_days"
            ],
            confirm_live_execution=(
                confirm_live_execution
            )
        )

        return {
            **result,
            "auto_mode": True,
            "auto_config": auto_config
        }
