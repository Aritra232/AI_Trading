from typing import Any

from service.bot_state_service import BotStateService


class DbBotStateService(BotStateService):
    def __init__(
        self,
        database_service,
        session_id: str,
        user_id: str | None = None
    ):
        super().__init__(
            filename=f"bot_state_{session_id}.json"
        )
        self.database_service = database_service
        self.session_id = session_id
        self.user_id = user_id

    def _load(self) -> dict[str, Any]:
        state = self.database_service.get_bot_state(
            self.session_id
        )

        if not state:
            return self._default_state()

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

    def _save(
        self,
        state: dict[str, Any]
    ) -> dict[str, Any]:
        state["success"] = True
        state["updated_at"] = self._utc_now_iso()

        self.database_service.upsert_bot_state(
            user_id=self.user_id,
            session_id=self.session_id,
            state=state
        )

        return {
            **state,
            "state_backend": "database",
            "state_collection": "bot_state",
            "session_id": self.session_id
        }

    def get_status(self) -> dict[str, Any]:
        state = self._load()

        return {
            **state,
            "state_backend": "database",
            "state_collection": "bot_state",
            "session_id": self.session_id
        }
