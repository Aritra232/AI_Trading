import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditService:
    def __init__(
        self,
        log_dir: str | Path = "logs",
        filename: str = "bot_audit.jsonl"
    ):
        self.log_dir = Path(log_dir)
        self.log_file = self.log_dir / filename

    def _utc_now_iso(self) -> str:
        return datetime.now(
            timezone.utc
        ).isoformat().replace(
            "+00:00",
            "Z"
        )

    def _safe_write(
        self,
        record: dict[str, Any]
    ) -> dict[str, Any]:
        self.log_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        with self.log_file.open(
            "a",
            encoding="utf-8"
        ) as file:
            file.write(
                json.dumps(
                    record,
                    default=str,
                    separators=(
                        ",",
                        ":"
                    )
                )
                + "\n"
            )

        return {
            "success": True,
            "log_file": str(
                self.log_file
            )
        }

    def log_bot_run(
        self,
        result: dict[str, Any],
        request_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        contract = result.get(
            "contract",
            {}
        )

        execution = result.get(
            "execution",
            {}
        )

        record = {
            "event_type": "BOT_RUN_COMPLETED",
            "timestamp": self._utc_now_iso(),
            "request": request_context or {},
            "mode": result.get(
                "mode"
            ),
            "symbol": result.get(
                "symbol"
            ),
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
            "safety": result.get(
                "safety"
            ),
            "ready_for_execution": result.get(
                "ready_for_execution"
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
                "order_response": execution.get(
                    "order_response"
                ),
                "position_response": execution.get(
                    "position_response"
                ),
                "execution_version": execution.get(
                    "execution_version"
                )
            },
            "bot_version": result.get(
                "bot_version"
            )
        }

        return self._safe_write(
            record
        )

    def log_error(
        self,
        event_type: str,
        error: Exception | str,
        context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        record = {
            "event_type": event_type,
            "timestamp": self._utc_now_iso(),
            "success": False,
            "error": str(
                error
            ),
            "context": context or {}
        }

        return self._safe_write(
            record
        )

    def read_recent(
        self,
        limit: int = 50
    ) -> dict[str, Any]:
        limit = max(
            1,
            min(
                int(limit),
                500
            )
        )

        if not self.log_file.exists():
            return {
                "success": True,
                "log_file": str(
                    self.log_file
                ),
                "count": 0,
                "records": []
            }

        lines = self.log_file.read_text(
            encoding="utf-8"
        ).splitlines()

        records = []

        for line in lines[-limit:]:
            try:
                records.append(
                    json.loads(
                        line
                    )
                )

            except json.JSONDecodeError:
                records.append(
                    {
                        "event_type": "AUDIT_PARSE_ERROR",
                        "raw": line
                    }
                )

        return {
            "success": True,
            "log_file": str(
                self.log_file
            ),
            "count": len(
                records
            ),
            "records": records
        }
