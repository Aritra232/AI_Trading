import uuid
from datetime import datetime, timezone
from typing import Any

from service.realtime_service import RealtimeService
from service.topstep_service import TopstepService


class TopstepSessionService:
    def __init__(
        self,
        database_service=None
    ):
        self.sessions: dict[str, dict[str, Any]] = {}
        self.database_service = database_service

    def _utc_now_iso(self) -> str:
        return datetime.now(
            timezone.utc
        ).isoformat().replace(
            "+00:00",
            "Z"
        )

    async def login(
        self,
        username: str,
        api_key: str,
        user_id: str
    ) -> dict[str, Any]:
        client = TopstepService(
            username=username,
            api_key=api_key
        )

        auth_result = await client.authenticate()

        session_id = uuid.uuid4().hex

        self.sessions[session_id] = {
            "client": client,
            "realtime_service": RealtimeService(
                topstep_service=client
            ),
            "user_id": user_id,
            "username": username,
            "created_at": self._utc_now_iso(),
            "last_used_at": self._utc_now_iso()
        }

        db_result = None

        if self.database_service is not None:
            db_result = self.database_service.upsert_session(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "topstep_username": username,
                    "topstep_token": auth_result.get(
                        "token"
                    ),
                    "is_active": True,
                    "created_at": self._utc_now_iso(),
                    "last_used_at": self._utc_now_iso()
                }
            )

        return {
            "success": True,
            "session_id": session_id,
            "user_id": user_id,
            "token_received": bool(
                auth_result.get(
                    "token"
                )
            ),
            "username": username,
            "message": "Topstep session authenticated.",
            "database": db_result
        }

    def _restore_session_from_db(
        self,
        session_id: str
    ) -> dict[str, Any] | None:
        if self.database_service is None:
            return None

        document = self.database_service.get_session(
            session_id
        )

        if not document:
            return None

        token = document.get(
            "topstep_token"
        )

        username = document.get(
            "topstep_username"
        )

        if not token or not username:
            return None

        client = TopstepService(
            username=username,
            api_key="",
            token=token
        )

        session = {
            "client": client,
            "realtime_service": RealtimeService(
                topstep_service=client
            ),
            "user_id": document.get(
                "user_id"
            ),
            "username": username,
            "created_at": document.get(
                "created_at"
            ),
            "last_used_at": self._utc_now_iso(),
            "restored_from_database": True
        }

        self.sessions[session_id] = session

        return session

    def get_session(
        self,
        session_id: str | None
    ) -> dict[str, Any] | None:
        if not session_id:
            return None

        session = self.sessions.get(
            session_id
        )

        if not session:
            session = self._restore_session_from_db(
                session_id
            )

        if session:
            session["last_used_at"] = self._utc_now_iso()

        return session

    def get_client(
        self,
        session_id: str | None
    ) -> TopstepService | None:
        session = self.get_session(
            session_id
        )

        if not session:
            return None

        return session.get(
            "client"
        )

    def get_realtime_service(
        self,
        session_id: str | None
    ) -> RealtimeService | None:
        session = self.get_session(
            session_id
        )

        if not session:
            return None

        return session.get(
            "realtime_service"
        )

    def status(
        self,
        session_id: str | None = None
    ) -> dict[str, Any]:
        if session_id:
            session = self.get_session(
                session_id
            )

            if not session:
                return {
                    "success": False,
                    "authenticated": False,
                    "reason": "Session was not found."
                }

            return {
                "success": True,
                "authenticated": True,
                "session_id": session_id,
                "user_id": session.get(
                    "user_id"
                ),
                "username": session.get(
                    "username"
                ),
                "created_at": session.get(
                    "created_at"
                ),
                "last_used_at": session.get(
                    "last_used_at"
                ),
                "restored_from_database": session.get(
                    "restored_from_database",
                    False
                )
            }

        return {
            "success": True,
            "session_count": len(
                self.sessions
            ),
            "sessions": [
                {
                    "session_id": key,
                    "user_id": value.get(
                        "user_id"
                    ),
                    "username": value.get(
                        "username"
                    ),
                    "created_at": value.get(
                        "created_at"
                    ),
                    "last_used_at": value.get(
                        "last_used_at"
                    )
                }
                for key, value in self.sessions.items()
            ]
        }

    def logout(
        self,
        session_id: str
    ) -> dict[str, Any]:
        session = self.sessions.pop(
            session_id,
            None
        )

        if not session:
            if self.database_service is not None:
                db_result = (
                    self.database_service
                    .deactivate_session(
                        session_id
                    )
                )

                return {
                    "success": bool(
                        db_result.get(
                            "updated"
                        )
                    ),
                    "logged_out": bool(
                        db_result.get(
                            "updated"
                        )
                    ),
                    "session_id": session_id,
                    "database": db_result
                }

            return {
                "success": False,
                "logged_out": False,
                "reason": "Session was not found."
            }

        realtime_service = session.get(
            "realtime_service"
        )

        if realtime_service is not None:
            realtime_service.stop_all()

        db_result = None

        if self.database_service is not None:
            db_result = self.database_service.deactivate_session(
                session_id
            )

        return {
            "success": True,
            "logged_out": True,
            "session_id": session_id,
            "database": db_result
        }

    def save_accounts(
        self,
        session_id: str,
        accounts: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        if self.database_service is None:
            return None

        session = self.get_session(
            session_id
        )

        if not session:
            return {
                "success": False,
                "stored": False,
                "error": "Session was not found."
            }

        return self.database_service.upsert_accounts(
            user_id=session.get(
                "user_id"
            ),
            session_id=session_id,
            accounts=accounts
        )
