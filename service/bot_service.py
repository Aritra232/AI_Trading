import asyncio
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
        audit_service=None,
        bot_state_service=None
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
        self.audit_service = audit_service
        self.bot_state_service = bot_state_service

    def _utc_now_iso(self):
        return datetime.now(
            timezone.utc
        ).isoformat().replace(
            "+00:00",
            "Z"
        )

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
        daily_loss_limit: float | None,
        max_position_quantity: int | None,
        kill_switch: bool,
        max_quote_age_seconds: int,
        start_time: str | None,
        end_time: str | None,
        live: bool
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

        if not account:
            raise ValueError(
                "Account state is unavailable."
            )

        if not contract:
            raise ValueError(
                "Contract state is unavailable."
            )

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
                best_day_profit=best_day_profit
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
            )
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
        daily_loss_limit: float | None = None,
        max_position_quantity: int | None = None,
        kill_switch: bool = False,
        max_quote_age_seconds: int = 30,
        order_type: str = "MARKET",
        lookback_hours: int = 72,
        auto_start_realtime: bool = True,
        realtime_warmup_seconds: int = 3,
        live: bool = False
    ):
        request_context = {
            "account_id": account_id,
            "symbol": symbol,
            "dry_run": dry_run,
            "account_size": account_size,
            "planned_quantity": planned_quantity,
            "current_mll": current_mll,
            "best_day_profit": best_day_profit,
            "max_risk_per_trade": max_risk_per_trade,
            "daily_pnl": daily_pnl,
            "daily_loss_limit": daily_loss_limit,
            "max_position_quantity": max_position_quantity,
            "kill_switch": kill_switch,
            "max_quote_age_seconds": max_quote_age_seconds,
            "order_type": order_type,
            "lookback_hours": lookback_hours,
            "auto_start_realtime": auto_start_realtime,
            "realtime_warmup_seconds": realtime_warmup_seconds,
            "live": live
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
            daily_loss_limit=daily_loss_limit,
            max_position_quantity=max_position_quantity,
            kill_switch=effective_kill_switch,
            max_quote_age_seconds=max_quote_age_seconds,
            start_time=start_time,
            end_time=end_time,
            live=live
        )

        execution_result = await self.execution_service.execute(
            account_id=account_id,
            contract_id=contract_id,
            final_decision=workflow.get(
                "final_decision"
            ),
            safety_result=workflow.get(
                "safety"
            ),
            contract=contract,
            dry_run=dry_run,
            order_type=order_type
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

        final_decision = workflow.get(
            "final_decision",
            {}
        )

        safety = workflow.get(
            "safety",
            {}
        )

        result = {
            "success": True,
            "mode": (
                "dry_run"
                if dry_run
                else "live_blocked"
            ),
            "symbol": symbol,
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
                "log_file": audit.get(
                    "log_file"
                )
            }

        return result
