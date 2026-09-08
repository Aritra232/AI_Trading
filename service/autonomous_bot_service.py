import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any


class AutonomousBotService:
    def __init__(
        self,
        bot_service,
        bot_state_service,
        audit_service=None
    ):
        self.bot_service = bot_service
        self.bot_state_service = bot_state_service
        self.audit_service = audit_service
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._config: dict[str, Any] | None = None

    def _utc_now_iso(self) -> str:
        return datetime.now(
            timezone.utc
        ).isoformat().replace(
            "+00:00",
            "Z"
        )

    def _utc_after_iso(
        self,
        seconds: int
    ) -> str:
        return (
            datetime.now(
                timezone.utc
            )
            + timedelta(
                seconds=seconds
            )
        ).isoformat().replace(
            "+00:00",
            "Z"
        )

    def is_running(self) -> bool:
        return (
            self._task is not None
            and not self._task.done()
        )

    def _build_config(
        self,
        account_id: int,
        symbol: str,
        dry_run: bool,
        account_size: int,
        planned_quantity: int,
        current_mll: float | None,
        best_day_profit: float | None,
        max_risk_per_trade: float | None,
        daily_pnl: float | None,
        evaluation_trading_days: int | None,
        daily_loss_limit: float | None,
        max_position_quantity: int | None,
        max_quote_age_seconds: int,
        order_type: str,
        lookback_hours: int,
        auto_start_realtime: bool,
        realtime_warmup_seconds: int,
        live: bool,
        interval_seconds: int,
        duplicate_order_cooldown_seconds: int,
        phase: str,
        enforce_daily_profit_cap: bool,
        auto_calculate_evaluation_metrics: bool,
        evaluation_start_time: str | None,
        evaluation_lookback_days: int
    ) -> dict[str, Any]:
        return {
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
            "max_quote_age_seconds": max_quote_age_seconds,
            "order_type": order_type,
            "lookback_hours": lookback_hours,
            "auto_start_realtime": auto_start_realtime,
            "realtime_warmup_seconds": realtime_warmup_seconds,
            "live": live,
            "interval_seconds": interval_seconds,
            "duplicate_order_cooldown_seconds": (
                duplicate_order_cooldown_seconds
            ),
            "phase": phase,
            "enforce_daily_profit_cap": enforce_daily_profit_cap,
            "auto_calculate_evaluation_metrics": (
                auto_calculate_evaluation_metrics
            ),
            "evaluation_start_time": evaluation_start_time,
            "evaluation_lookback_days": evaluation_lookback_days
        }

    async def _sleep_or_stop(
        self,
        seconds: int
    ) -> bool:
        if self._stop_event is None:
            return True

        try:
            await asyncio.wait_for(
                self._stop_event.wait(),
                timeout=seconds
            )

            return True

        except asyncio.TimeoutError:
            return False

    async def _run_loop(
        self
    ):
        assert self._config is not None

        config = self._config
        interval_seconds = int(
            config["interval_seconds"]
        )

        try:
            while True:
                if (
                    self._stop_event is not None
                    and self._stop_event.is_set()
                ):
                    break

                state = self.bot_state_service.get_status()

                kill_switch_enabled = bool(
                    state.get(
                        "kill_switch",
                        {}
                    ).get(
                        "enabled",
                        False
                    )
                )

                if kill_switch_enabled:
                    self.bot_state_service.mark_loop_skipped(
                        reason=(
                            "Autonomous loop skipped because "
                            "kill switch is enabled."
                        ),
                        next_run_at=self._utc_after_iso(
                            interval_seconds
                        )
                    )

                    should_stop = await self._sleep_or_stop(
                        interval_seconds
                    )

                    if should_stop:
                        break

                    continue

                await self.bot_service.run_once(
                    account_id=int(
                        config["account_id"]
                    ),
                    symbol=str(
                        config["symbol"]
                    ),
                    dry_run=bool(
                        config["dry_run"]
                    ),
                    account_size=int(
                        config["account_size"]
                    ),
                    planned_quantity=int(
                        config["planned_quantity"]
                    ),
                    current_mll=config.get(
                        "current_mll"
                    ),
                    best_day_profit=config.get(
                        "best_day_profit"
                    ),
                    max_risk_per_trade=config.get(
                        "max_risk_per_trade"
                    ),
                    daily_pnl=config.get(
                        "daily_pnl"
                    ),
                    evaluation_trading_days=config.get(
                        "evaluation_trading_days"
                    ),
                    daily_loss_limit=config.get(
                        "daily_loss_limit"
                    ),
                    max_position_quantity=config.get(
                        "max_position_quantity"
                    ),
                    kill_switch=False,
                    max_quote_age_seconds=int(
                        config["max_quote_age_seconds"]
                    ),
                    order_type=str(
                        config["order_type"]
                    ),
                    lookback_hours=int(
                        config["lookback_hours"]
                    ),
                    auto_start_realtime=bool(
                        config["auto_start_realtime"]
                    ),
                    realtime_warmup_seconds=int(
                        config["realtime_warmup_seconds"]
                    ),
                    live=bool(
                        config["live"]
                    ),
                    duplicate_order_cooldown_seconds=int(
                        config[
                            "duplicate_order_cooldown_seconds"
                        ]
                    ),
                    phase=str(
                        config[
                            "phase"
                        ]
                    ),
                    enforce_daily_profit_cap=bool(
                        config[
                            "enforce_daily_profit_cap"
                        ]
                    ),
                    auto_calculate_evaluation_metrics=bool(
                        config[
                            "auto_calculate_evaluation_metrics"
                        ]
                    ),
                    evaluation_start_time=config.get(
                        "evaluation_start_time"
                    ),
                    evaluation_lookback_days=int(
                        config[
                            "evaluation_lookback_days"
                        ]
                    )
                )

                self.bot_state_service.mark_loop_tick(
                    next_run_at=self._utc_after_iso(
                        interval_seconds
                    )
                )

                should_stop = await self._sleep_or_stop(
                    interval_seconds
                )

                if should_stop:
                    break

            self.bot_state_service.mark_loop_stopped(
                reason="Autonomous loop stopped."
            )

        except asyncio.CancelledError:
            self.bot_state_service.mark_loop_stopped(
                reason="Autonomous loop cancelled."
            )

            raise

        except Exception as exc:
            self.bot_state_service.mark_loop_error(
                error=exc
            )

            if self.audit_service is not None:
                self.audit_service.log_error(
                    event_type="AUTONOMOUS_LOOP_FAILED",
                    error=exc,
                    context=config
                )

    async def start(
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
        max_quote_age_seconds: int = 30,
        order_type: str = "MARKET",
        lookback_hours: int = 72,
        auto_start_realtime: bool = True,
        realtime_warmup_seconds: int = 3,
        live: bool = False,
        interval_seconds: int = 60,
        duplicate_order_cooldown_seconds: int = 300,
        phase: str = "evaluation",
        enforce_daily_profit_cap: bool = True,
        auto_calculate_evaluation_metrics: bool = True,
        evaluation_start_time: str | None = None,
        evaluation_lookback_days: int = 14
    ) -> dict[str, Any]:
        interval_seconds = max(
            int(interval_seconds),
            15
        )

        if self.is_running():
            status = self.status()

            return {
                **status,
                "success": True,
                "started": False,
                "message": "Autonomous loop is already running."
            }

        config = self._build_config(
            account_id=account_id,
            symbol=symbol,
            dry_run=dry_run,
            account_size=account_size,
            planned_quantity=planned_quantity,
            current_mll=current_mll,
            best_day_profit=best_day_profit,
            max_risk_per_trade=max_risk_per_trade,
            daily_pnl=daily_pnl,
            evaluation_trading_days=evaluation_trading_days,
            daily_loss_limit=daily_loss_limit,
            max_position_quantity=max_position_quantity,
            max_quote_age_seconds=max_quote_age_seconds,
            order_type=order_type,
            lookback_hours=lookback_hours,
            auto_start_realtime=auto_start_realtime,
            realtime_warmup_seconds=realtime_warmup_seconds,
            live=live,
            interval_seconds=interval_seconds,
            duplicate_order_cooldown_seconds=(
                duplicate_order_cooldown_seconds
            ),
            phase=phase,
            enforce_daily_profit_cap=enforce_daily_profit_cap,
            auto_calculate_evaluation_metrics=(
                auto_calculate_evaluation_metrics
            ),
            evaluation_start_time=evaluation_start_time,
            evaluation_lookback_days=evaluation_lookback_days
        )

        self._config = config
        self._stop_event = asyncio.Event()

        state = self.bot_state_service.mark_loop_started(
            config=config
        )

        self._task = asyncio.create_task(
            self._run_loop()
        )

        return {
            **state,
            "started": True,
            "runtime_running": self.is_running(),
            "message": "Autonomous loop started."
        }

    async def start_auto(
        self,
        account_id: int,
        symbol: str = "MES",
        dry_run: bool = True,
        live: bool = False,
        phase: str = "evaluation",
        interval_seconds: int = 60
    ) -> dict[str, Any]:
        account = await self.bot_service._resolve_account(
            account_id=account_id
        )

        account_size = self.bot_service._infer_account_size(
            account=account
        )

        auto_config = self.bot_service._build_auto_config(
            account=account,
            account_size=account_size,
            phase=phase
        )

        state = await self.start(
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
            interval_seconds=interval_seconds,
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
            ]
        )

        return {
            **state,
            "auto_mode": True,
            "auto_config": auto_config
        }

    async def stop(
        self
    ) -> dict[str, Any]:
        if not self.is_running():
            state = self.bot_state_service.mark_loop_stopped(
                reason="Autonomous loop is already stopped."
            )

            return {
                **state,
                "stopped": False,
                "runtime_running": False,
                "message": "Autonomous loop is already stopped."
            }

        if self._stop_event is not None:
            self._stop_event.set()

        self.bot_state_service.mark_loop_stop_requested(
            reason="Autonomous loop stop requested."
        )

        if self._task is not None:
            await asyncio.wait(
                {
                    self._task
                },
                timeout=5
            )

        if self.is_running():
            return {
                **self.bot_state_service.get_status(),
                "stopped": False,
                "runtime_running": True,
                "message": (
                    "Autonomous loop stop requested; "
                    "current run is finishing."
                )
            }

        state = self.bot_state_service.mark_loop_stopped(
            reason="Autonomous loop stop requested."
        )

        return {
            **state,
            "stopped": True,
            "runtime_running": self.is_running(),
            "message": "Autonomous loop stop requested."
        }

    def status(
        self
    ) -> dict[str, Any]:
        state = self.bot_state_service.get_status()

        return {
            **state,
            "runtime_running": self.is_running(),
            "runtime_config": self._config
        }
