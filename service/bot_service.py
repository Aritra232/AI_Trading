import asyncio
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

    def _evaluate_market_gate(
        self,
        market: dict,
        max_quote_age_seconds: int
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

        return {
            "account_size": account_size,
            "planned_quantity": 1,
            "current_mll": current_mll,
            "current_mll_source": current_mll_source,
            "max_risk_per_trade": 100,
            "daily_loss_limit": daily_loss_limit,
            "daily_loss_limit_source": daily_loss_limit_source,
            "max_position_quantity": 1,
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
            max_quote_age_seconds=max_quote_age_seconds
        )

        if not account:
            raise ValueError(
                "Account state is unavailable."
            )

        if not contract:
            raise ValueError(
                "Contract state is unavailable."
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
            max_position_quantity=max_position_quantity,
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
        symbol: str = "MES",
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
            "account_id": account_id,
            "symbol": symbol,
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

        contract = await self._resolve_active_contract(
            symbol=symbol,
            live=live
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
                else "live_blocked"
            ),
            "symbol": symbol,
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
        symbol: str = "MES",
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
