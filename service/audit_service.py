from datetime import datetime, timezone
from typing import Any


class AuditService:
    def __init__(
        self,
        database_service=None
    ):
        self.database_service = database_service

    def _utc_now_iso(self) -> str:
        return datetime.now(
            timezone.utc
        ).isoformat().replace(
            "+00:00",
            "Z"
        )

    def _session_user_id(
        self,
        session_id: str | None
    ) -> str | None:
        if not session_id or self.database_service is None:
            return None

        session = self.database_service.get_session(
            session_id
        )

        if not session:
            return None

        return session.get(
            "user_id"
        )

    def _store(
        self,
        record: dict[str, Any]
    ) -> dict[str, Any]:
        if self.database_service is None:
            return {
                "success": False,
                "stored": False,
                "collection": "bot_audit_logs",
                "error": "Database service is not configured."
            }

        return self.database_service.insert_audit_log(
            record
        )

    def log_bot_run(
        self,
        result: dict[str, Any],
        request_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        request_context = request_context or {}

        contract = result.get(
            "contract",
            {}
        )

        execution = result.get(
            "execution",
            {}
        )

        session_id = request_context.get(
            "session_id"
        )

        user_id = (
            request_context.get(
                "user_id"
            )
            or self._session_user_id(
                session_id
            )
        )

        account_id = request_context.get(
            "account_id"
        )

        record = {
            "event_type": "BOT_RUN_COMPLETED",
            "timestamp": self._utc_now_iso(),
            "user_id": user_id,
            "session_id": session_id,
            "account_id": account_id,
            "symbol": result.get(
                "symbol"
            ),
            "mode": result.get(
                "mode"
            ),
            "phase": result.get(
                "phase"
            ),
            "request": request_context,
            "contract": {
                "id": contract.get(
                    "id"
                ),
                "name": contract.get(
                    "name"
                )
            },
            "history": result.get(
                "history"
            ),
            "strategy": result.get(
                "strategy"
            ),
            "decision": result.get(
                "decision"
            ),
            "pre_trade_rules": result.get(
                "pre_trade_rules"
            ),
            "daily_profit_lock": result.get(
                "daily_profit_lock"
            ),
            "rule": result.get(
                "rule"
            ),
            "risk": result.get(
                "risk"
            ),
            "safety": result.get(
                "safety"
            ),
            "ready_for_execution": result.get(
                "ready_for_execution"
            ),
            "execution_guard": result.get(
                "execution_guard"
            ),
            "evaluation_metrics": result.get(
                "evaluation_metrics"
            ),
            "execution": {
                "execution_status": execution.get(
                    "execution_status"
                ),
                "dry_run": execution.get(
                    "dry_run"
                ),
                "submitted": execution.get(
                    "submitted"
                ),
                "reason": execution.get(
                    "reason"
                ),
                "message": execution.get(
                    "message"
                ),
                "action": execution.get(
                    "action"
                ),
                "order_payload": execution.get(
                    "order_payload"
                ),
                "close_payload": execution.get(
                    "close_payload"
                ),
                "close_payloads": execution.get(
                    "close_payloads"
                ),
                "order_response": execution.get(
                    "order_response"
                ),
                "position_response": execution.get(
                    "position_response"
                ),
                "position_responses": execution.get(
                    "position_responses"
                ),
                "live_execution_gate": execution.get(
                    "live_execution_gate"
                ),
                "execution_version": execution.get(
                    "execution_version"
                )
            },
            "bot_version": result.get(
                "bot_version"
            )
        }

        return self._store(
            record
        )

    def log_error(
        self,
        event_type: str,
        error: Exception | str,
        context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        context = context or {}
        session_id = context.get(
            "session_id"
        )

        record = {
            "event_type": event_type,
            "timestamp": self._utc_now_iso(),
            "success": False,
            "user_id": (
                context.get(
                    "user_id"
                )
                or self._session_user_id(
                    session_id
                )
            ),
            "session_id": session_id,
            "account_id": context.get(
                "account_id"
            ),
            "symbol": context.get(
                "symbol"
            ),
            "error": str(
                error
            ),
            "context": context
        }

        return self._store(
            record
        )

    def read_recent(
        self,
        limit: int = 50,
        session_id: str | None = None,
        user_id: str | None = None,
        account_id: int | None = None,
        symbol: str | None = None,
        event_type: str | None = None
    ) -> dict[str, Any]:
        if self.database_service is None:
            return {
                "success": False,
                "collection": "bot_audit_logs",
                "count": 0,
                "records": [],
                "error": "Database service is not configured."
            }

        return self.database_service.read_audit_logs(
            limit=limit,
            session_id=session_id,
            user_id=user_id,
            account_id=account_id,
            symbol=symbol,
            event_type=event_type
        )
