import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BotStateService:
    def __init__(
        self,
        state_dir: str | Path = "state",
        filename: str = "bot_state.json"
    ):
        self.state_dir = Path(state_dir)
        self.state_file = self.state_dir / filename

    def _utc_now_iso(self) -> str:
        return datetime.now(
            timezone.utc
        ).isoformat().replace(
            "+00:00",
            "Z"
        )

    def _default_state(self) -> dict[str, Any]:
        now = self._utc_now_iso()

        return {
            "success": True,
            "bot_status": "STOPPED",
            "kill_switch": {
                "enabled": False,
                "reason": None,
                "updated_at": None,
                "updated_by": None
            },
            "last_run": {
                "state": "NEVER_RUN",
                "started_at": None,
                "completed_at": None,
                "account_id": None,
                "symbol": None,
                "dry_run": None,
                "live": None,
                "strategy_action": None,
                "decision_status": None,
                "safety_status": None,
                "execution_status": None,
                "submitted": None,
                "error": None
            },
            "loop": {
                "running": False,
                "started_at": None,
                "stopped_at": None,
                "last_tick_at": None,
                "next_run_at": None,
                "run_count": 0,
                "interval_seconds": None,
                "config": {},
                "message": None,
                "error": None
            },
            "execution_guard": {
                "recent_intents": []
            },
            "created_at": now,
            "updated_at": now,
            "state_version": "BOT_STATE_V1"
        }

    def _load(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return self._default_state()

        try:
            state = json.loads(
                self.state_file.read_text(
                    encoding="utf-8"
                )
            )

        except Exception:
            state = self._default_state()
            state["last_run"]["error"] = (
                "State file could not be parsed; defaults loaded."
            )

        default = self._default_state()

        merged = {
            **default,
            **state
        }

        merged["kill_switch"] = {
            **default["kill_switch"],
            **state.get(
                "kill_switch",
                {}
            )
        }

        merged["last_run"] = {
            **default["last_run"],
            **state.get(
                "last_run",
                {}
            )
        }

        merged["loop"] = {
            **default["loop"],
            **state.get(
                "loop",
                {}
            )
        }

        merged["execution_guard"] = {
            **default["execution_guard"],
            **state.get(
                "execution_guard",
                {}
            )
        }

        return merged

    def _parse_datetime(
        self,
        value: str | None
    ) -> datetime | None:
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

    def _save(
        self,
        state: dict[str, Any]
    ) -> dict[str, Any]:
        self.state_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        state["success"] = True
        state["updated_at"] = self._utc_now_iso()

        tmp_file = self.state_file.with_suffix(
            ".tmp"
        )

        tmp_file.write_text(
            json.dumps(
                state,
                indent=2,
                default=str
            ),
            encoding="utf-8"
        )

        tmp_file.replace(
            self.state_file
        )

        return {
            **state,
            "state_file": str(
                self.state_file
            )
        }

    def get_status(self) -> dict[str, Any]:
        state = self._load()

        return {
            **state,
            "state_file": str(
                self.state_file
            )
        }

    def enable_kill_switch(
        self,
        reason: str = "Manual emergency stop.",
        updated_by: str = "system"
    ) -> dict[str, Any]:
        state = self._load()

        state["kill_switch"] = {
            "enabled": True,
            "reason": reason,
            "updated_at": self._utc_now_iso(),
            "updated_by": updated_by
        }

        return self._save(
            state
        )

    def disable_kill_switch(
        self,
        reason: str = "Manual reset.",
        updated_by: str = "system"
    ) -> dict[str, Any]:
        state = self._load()

        state["kill_switch"] = {
            "enabled": False,
            "reason": reason,
            "updated_at": self._utc_now_iso(),
            "updated_by": updated_by
        }

        return self._save(
            state
        )

    def mark_run_started(
        self,
        account_id: int,
        symbol: str,
        dry_run: bool,
        live: bool
    ) -> dict[str, Any]:
        state = self._load()

        state["last_run"] = {
            **state.get(
                "last_run",
                {}
            ),
            "state": "RUNNING",
            "started_at": self._utc_now_iso(),
            "completed_at": None,
            "account_id": account_id,
            "symbol": symbol,
            "dry_run": dry_run,
            "live": live,
            "error": None
        }

        return self._save(
            state
        )

    def mark_run_completed(
        self,
        result: dict[str, Any]
    ) -> dict[str, Any]:
        state = self._load()

        strategy = result.get(
            "strategy",
            {}
        )

        decision = result.get(
            "decision",
            {}
        )

        safety = result.get(
            "safety",
            {}
        )

        execution = result.get(
            "execution",
            {}
        )

        state["last_run"] = {
            **state.get(
                "last_run",
                {}
            ),
            "state": "COMPLETED",
            "completed_at": self._utc_now_iso(),
            "strategy_action": strategy.get(
                "action"
            ),
            "decision_status": decision.get(
                "final_status"
            ),
            "safety_status": safety.get(
                "safety_status"
            ),
            "execution_status": execution.get(
                "execution_status"
            ),
            "submitted": execution.get(
                "submitted"
            ),
            "error": None
        }

        return self._save(
            state
        )

    def mark_run_failed(
        self,
        error: Exception | str,
        context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        state = self._load()

        context = context or {}

        state["last_run"] = {
            **state.get(
                "last_run",
                {}
            ),
            "state": "FAILED",
            "completed_at": self._utc_now_iso(),
            "account_id": context.get(
                "account_id",
                state.get(
                    "last_run",
                    {}
                ).get(
                    "account_id"
                )
            ),
            "symbol": context.get(
                "symbol",
                state.get(
                    "last_run",
                    {}
                ).get(
                    "symbol"
                )
            ),
            "dry_run": context.get(
                "dry_run",
                state.get(
                    "last_run",
                    {}
                ).get(
                    "dry_run"
                )
            ),
            "live": context.get(
                "live",
                state.get(
                    "last_run",
                    {}
                ).get(
                    "live"
                )
            ),
            "error": str(
                error
            )
        }

        return self._save(
            state
        )

    def check_duplicate_order_intent(
        self,
        account_id: int,
        contract_id: str,
        action: str,
        cooldown_seconds: int = 300
    ) -> dict[str, Any]:
        state = self._load()

        action = str(
            action
        ).upper()

        cooldown_seconds = max(
            int(cooldown_seconds),
            0
        )

        now = datetime.now(
            timezone.utc
        )

        recent_intents = (
            state.get(
                "execution_guard",
                {}
            ).get(
                "recent_intents",
                []
            )
            or []
        )

        matching_intent = None

        for intent in reversed(
            recent_intents
        ):
            if (
                intent.get(
                    "account_id"
                ) == account_id
                and intent.get(
                    "contract_id"
                ) == contract_id
                and str(
                    intent.get(
                        "action",
                        ""
                    )
                ).upper() == action
            ):
                created_at = self._parse_datetime(
                    intent.get(
                        "created_at"
                    )
                )

                if created_at is None:
                    continue

                age_seconds = max(
                    (
                        now
                        - created_at
                    ).total_seconds(),
                    0
                )

                if age_seconds < cooldown_seconds:
                    matching_intent = {
                        **intent,
                        "age_seconds": age_seconds,
                        "remaining_cooldown_seconds": (
                            cooldown_seconds
                            - age_seconds
                        )
                    }

                break

        if matching_intent:
            return {
                "allowed": False,
                "duplicate": True,
                "reason": (
                    f"Duplicate {action} order intent blocked "
                    f"for account {account_id} and contract "
                    f"{contract_id}. Cooldown "
                    f"{cooldown_seconds}s has not expired."
                ),
                "cooldown_seconds": cooldown_seconds,
                "matched_intent": matching_intent
            }

        return {
            "allowed": True,
            "duplicate": False,
            "reason": None,
            "cooldown_seconds": cooldown_seconds,
            "matched_intent": None
        }

    def record_order_intent(
        self,
        account_id: int,
        contract_id: str,
        action: str,
        dry_run: bool,
        execution_status: str | None,
        submitted: bool | None,
        custom_tag: str | None = None
    ) -> dict[str, Any]:
        state = self._load()

        recent_intents = (
            state.get(
                "execution_guard",
                {}
            ).get(
                "recent_intents",
                []
            )
            or []
        )

        recent_intents.append(
            {
                "account_id": account_id,
                "contract_id": contract_id,
                "action": str(
                    action
                ).upper(),
                "dry_run": dry_run,
                "execution_status": execution_status,
                "submitted": submitted,
                "custom_tag": custom_tag,
                "created_at": self._utc_now_iso()
            }
        )

        state["execution_guard"] = {
            **state.get(
                "execution_guard",
                {}
            ),
            "recent_intents": recent_intents[-100:]
        }

        return self._save(
            state
        )

    def mark_loop_started(
        self,
        config: dict[str, Any]
    ) -> dict[str, Any]:
        state = self._load()

        state["bot_status"] = "RUNNING"
        state["loop"] = {
            **state.get(
                "loop",
                {}
            ),
            "running": True,
            "started_at": self._utc_now_iso(),
            "stopped_at": None,
            "last_tick_at": None,
            "next_run_at": None,
            "run_count": 0,
            "interval_seconds": config.get(
                "interval_seconds"
            ),
            "config": config,
            "message": "Autonomous loop started.",
            "error": None
        }

        return self._save(
            state
        )

    def mark_loop_tick(
        self,
        next_run_at: str | None = None
    ) -> dict[str, Any]:
        state = self._load()

        loop = state.get(
            "loop",
            {}
        )

        state["bot_status"] = "RUNNING"
        state["loop"] = {
            **loop,
            "running": True,
            "last_tick_at": self._utc_now_iso(),
            "next_run_at": next_run_at,
            "run_count": int(
                loop.get(
                    "run_count",
                    0
                )
                or 0
            )
            + 1,
            "message": "Autonomous loop tick completed.",
            "error": None
        }

        return self._save(
            state
        )

    def mark_loop_stopped(
        self,
        reason: str = "Autonomous loop stopped."
    ) -> dict[str, Any]:
        state = self._load()

        state["bot_status"] = "STOPPED"
        state["loop"] = {
            **state.get(
                "loop",
                {}
            ),
            "running": False,
            "stopped_at": self._utc_now_iso(),
            "next_run_at": None,
            "message": reason,
            "error": None
        }

        return self._save(
            state
        )

    def mark_loop_stop_requested(
        self,
        reason: str = "Autonomous loop stop requested."
    ) -> dict[str, Any]:
        state = self._load()

        state["bot_status"] = "STOPPING"
        state["loop"] = {
            **state.get(
                "loop",
                {}
            ),
            "running": True,
            "next_run_at": None,
            "message": reason,
            "error": None
        }

        return self._save(
            state
        )

    def mark_loop_skipped(
        self,
        reason: str,
        next_run_at: str | None = None
    ) -> dict[str, Any]:
        state = self._load()

        loop = state.get(
            "loop",
            {}
        )

        state["bot_status"] = "RUNNING"
        state["loop"] = {
            **loop,
            "running": True,
            "last_tick_at": self._utc_now_iso(),
            "next_run_at": next_run_at,
            "message": reason,
            "error": None
        }

        return self._save(
            state
        )

    def mark_loop_error(
        self,
        error: Exception | str
    ) -> dict[str, Any]:
        state = self._load()

        state["bot_status"] = "ERROR"
        state["loop"] = {
            **state.get(
                "loop",
                {}
            ),
            "running": False,
            "stopped_at": self._utc_now_iso(),
            "next_run_at": None,
            "message": "Autonomous loop stopped with an error.",
            "error": str(
                error
            )
        }

        return self._save(
            state
        )
