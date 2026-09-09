import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()


class TopstepService:
    def __init__(
        self,
        username: str | None = None,
        api_key: str | None = None,
        token: str | None = None
    ):
        self.base_url = os.getenv(
            "TOPSTEP_BASE_URL",
            "https://api.topstepx.com"
        ).rstrip("/")

        self.username = (
            username
            if username is not None
            else os.getenv(
                "TOPSTEP_USERNAME",
                ""
            )
        ).strip()

        self.api_key = (
            api_key
            if api_key is not None
            else os.getenv(
                "TOPSTEP_API_KEY_PRIMARY",
                ""
            )
        ).strip()

        self._token: Optional[str] = token

    def _validate_config(self):
        if not self.username:
            raise RuntimeError(
                "Topstep username is missing."
            )

        if not self.api_key:
            raise RuntimeError(
                "Topstep API key is missing."
            )

    async def authenticate(self):
        self._validate_config()

        url = f"{self.base_url}/api/Auth/loginKey"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={
                    "accept": "text/plain",
                    "Content-Type": "application/json"
                },
                json={
                    "userName": self.username,
                    "apiKey": self.api_key
                }
            )

        data = response.json()

        if response.status_code >= 400:
            raise RuntimeError(
                f"Authentication failed: {data}"
            )

        if not data.get("success") or not data.get("token"):
            raise RuntimeError(
                f"Authentication failed: {data}"
            )

        self._token = data["token"]

        return data

    async def get_token(self):
        if self._token:
            return self._token

        if not self.api_key:
            raise RuntimeError(
                "Topstep session token is missing or expired. "
                "Please authenticate again."
            )

        result = await self.authenticate()

        return result["token"]

    async def post(self, path: str, payload: dict):
        token = await self.get_token()

        url = f"{self.base_url}{path}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "accept": "text/plain",
                    "Content-Type": "application/json"
                },
                json=payload
            )

        # token expired হলে once retry
        if response.status_code == 401:
            self._token = None
            token = await self.get_token()

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "accept": "text/plain",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )

        data = response.json()

        if response.status_code >= 400:
            raise RuntimeError(
                f"Topstep API error: {data}"
            )

        return data
