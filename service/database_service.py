import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()


class DatabaseService:
    def __init__(self):
        self.url = os.getenv(
            "DATABASE_URL",
            ""
        ).strip().strip('"').strip("'")
        self.database_name = os.getenv(
            "DATABASE_NAME",
            ""
        ).strip().strip('"').strip("'")
        self.client = None
        self.db = None
        self.error = None

        if not self.url or not self.database_name:
            self.error = (
                "DATABASE_URL or DATABASE_NAME is missing."
            )
            return

        try:
            from pymongo import MongoClient

            self.client = MongoClient(
                self.url,
                serverSelectionTimeoutMS=5000
            )
            self.db = self.client[
                self.database_name
            ]
            self._ensure_indexes()

        except Exception as exc:
            self.error = str(
                exc
            )

    def _utc_now_iso(self) -> str:
        return datetime.now(
            timezone.utc
        ).isoformat().replace(
            "+00:00",
            "Z"
        )

    def is_enabled(self) -> bool:
        return self.db is not None

    def _ensure_indexes(self):
        try:
            self.db.topstep_sessions.create_index(
                "session_id",
                unique=True
            )
            self.db.topstep_accounts.create_index(
                [
                    (
                        "user_id",
                        1
                    ),
                    (
                        "account_id",
                        1
                    )
                ],
                unique=True
            )
            self.db.bot_state.create_index(
                "session_id",
                unique=True
            )
            self.db.bot_audit_logs.create_index(
                [
                    (
                        "timestamp",
                        -1
                    )
                ]
            )
            self.db.bot_audit_logs.create_index(
                [
                    (
                        "session_id",
                        1
                    ),
                    (
                        "timestamp",
                        -1
                    )
                ]
            )
            self.db.bot_audit_logs.create_index(
                [
                    (
                        "user_id",
                        1
                    ),
                    (
                        "account_id",
                        1
                    ),
                    (
                        "timestamp",
                        -1
                    )
                ]
            )

        except Exception:
            pass

    def health(self) -> dict[str, Any]:
        if not self.is_enabled():
            return {
                "success": False,
                "enabled": False,
                "error": self.error
            }

        try:
            self.client.admin.command(
                "ping"
            )

            return {
                "success": True,
                "enabled": True,
                "database": self.database_name
            }

        except Exception as exc:
            return {
                "success": False,
                "enabled": True,
                "database": self.database_name,
                "error": str(
                    exc
                )
            }

    def upsert_session(
        self,
        session: dict[str, Any]
    ) -> dict[str, Any]:
        if not self.is_enabled():
            return {
                "success": False,
                "stored": False,
                "error": self.error
            }

        now = self._utc_now_iso()
        document = {
            **session,
            "updated_at": now
        }

        if "created_at" not in document:
            document["created_at"] = now

        try:
            self.db.topstep_sessions.update_one(
                {
                    "session_id": document[
                        "session_id"
                    ]
                },
                {
                    "$set": document
                },
                upsert=True
            )

        except Exception as exc:
            return {
                "success": False,
                "stored": False,
                "collection": "topstep_sessions",
                "error": str(
                    exc
                )
            }

        return {
            "success": True,
            "stored": True,
            "collection": "topstep_sessions"
        }

    def get_session(
        self,
        session_id: str
    ) -> dict[str, Any] | None:
        if not self.is_enabled():
            return None

        try:
            document = self.db.topstep_sessions.find_one(
                {
                    "session_id": session_id,
                    "is_active": True
                },
                {
                    "_id": 0
                }
            )

        except Exception:
            return None

        return document

    def deactivate_session(
        self,
        session_id: str
    ) -> dict[str, Any]:
        if not self.is_enabled():
            return {
                "success": False,
                "updated": False,
                "error": self.error
            }

        try:
            result = self.db.topstep_sessions.update_one(
                {
                    "session_id": session_id
                },
                {
                    "$set": {
                        "is_active": False,
                        "logged_out_at": self._utc_now_iso(),
                        "updated_at": self._utc_now_iso()
                    }
                }
            )

        except Exception as exc:
            return {
                "success": False,
                "updated": False,
                "collection": "topstep_sessions",
                "error": str(
                    exc
                )
            }

        return {
            "success": True,
            "updated": result.modified_count > 0,
            "collection": "topstep_sessions"
        }

    def upsert_accounts(
        self,
        user_id: str,
        session_id: str,
        accounts: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not self.is_enabled():
            return {
                "success": False,
                "stored": False,
                "error": self.error
            }

        now = self._utc_now_iso()

        try:
            for account in accounts:
                self.db.topstep_accounts.update_one(
                    {
                        "user_id": user_id,
                        "account_id": account.get(
                            "id"
                        )
                    },
                    {
                        "$set": {
                            "user_id": user_id,
                            "session_id": session_id,
                            "account_id": account.get(
                                "id"
                            ),
                            "account": account,
                            "last_synced_at": now
                        }
                    },
                    upsert=True
                )

        except Exception as exc:
            return {
                "success": False,
                "stored": False,
                "collection": "topstep_accounts",
                "error": str(
                    exc
                )
            }

        return {
            "success": True,
            "stored": True,
            "collection": "topstep_accounts",
            "count": len(
                accounts
            )
        }

    def upsert_bot_state(
        self,
        user_id: str | None,
        session_id: str,
        state: dict[str, Any]
    ) -> dict[str, Any]:
        if not self.is_enabled():
            return {
                "success": False,
                "stored": False,
                "error": self.error
            }

        try:
            self.db.bot_state.update_one(
                {
                    "session_id": session_id
                },
                {
                    "$set": {
                        "user_id": user_id,
                        "session_id": session_id,
                        "state": state,
                        "updated_at": self._utc_now_iso()
                    },
                    "$setOnInsert": {
                        "created_at": self._utc_now_iso()
                    }
                },
                upsert=True
            )

        except Exception as exc:
            return {
                "success": False,
                "stored": False,
                "collection": "bot_state",
                "error": str(
                    exc
                )
            }

        return {
            "success": True,
            "stored": True,
            "collection": "bot_state"
        }

    def get_bot_state(
        self,
        session_id: str
    ) -> dict[str, Any] | None:
        if not self.is_enabled():
            return None

        try:
            document = self.db.bot_state.find_one(
                {
                    "session_id": session_id
                },
                {
                    "_id": 0
                }
            )

        except Exception:
            return None

        if not document:
            return None

        return document.get(
            "state"
        )

    def insert_audit_log(
        self,
        record: dict[str, Any]
    ) -> dict[str, Any]:
        if not self.is_enabled():
            return {
                "success": False,
                "stored": False,
                "error": self.error
            }

        document = {
            **record,
            "created_at": self._utc_now_iso()
        }

        try:
            result = self.db.bot_audit_logs.insert_one(
                document
            )

        except Exception as exc:
            return {
                "success": False,
                "stored": False,
                "collection": "bot_audit_logs",
                "error": str(
                    exc
                )
            }

        return {
            "success": True,
            "stored": True,
            "collection": "bot_audit_logs",
            "id": str(
                result.inserted_id
            )
        }

    def read_audit_logs(
        self,
        limit: int = 50,
        session_id: str | None = None,
        user_id: str | None = None,
        account_id: int | None = None,
        symbol: str | None = None,
        event_type: str | None = None
    ) -> dict[str, Any]:
        limit = max(
            1,
            min(
                int(limit),
                500
            )
        )

        if not self.is_enabled():
            return {
                "success": False,
                "enabled": False,
                "collection": "bot_audit_logs",
                "count": 0,
                "records": [],
                "error": self.error
            }

        session_id = (
            session_id.strip()
            if isinstance(
                session_id,
                str
            )
            else session_id
        )
        user_id = (
            user_id.strip()
            if isinstance(
                user_id,
                str
            )
            else user_id
        )
        symbol = (
            symbol.strip().upper()
            if isinstance(
                symbol,
                str
            )
            else symbol
        )
        event_type = (
            event_type.strip().upper()
            if isinstance(
                event_type,
                str
            )
            else event_type
        )

        query: dict[str, Any] = {}

        if session_id:
            query["session_id"] = session_id

        if user_id:
            query["user_id"] = user_id

        if account_id is not None:
            query["account_id"] = account_id

        if symbol:
            query["symbol"] = symbol

        if event_type:
            query["event_type"] = event_type

        try:
            records = list(
                self.db.bot_audit_logs.find(
                    query,
                    {
                        "_id": 0
                    }
                ).sort(
                    "timestamp",
                    -1
                ).limit(
                    limit
                )
            )

        except Exception as exc:
            return {
                "success": False,
                "enabled": True,
                "collection": "bot_audit_logs",
                "count": 0,
                "records": [],
                "error": str(
                    exc
                )
            }

        return {
            "success": True,
            "enabled": True,
            "collection": "bot_audit_logs",
            "count": len(
                records
            ),
            "filters": query,
            "records": records
        }
