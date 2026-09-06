import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()


class TopstepService:
    def __init__(self):
        self.base_url = os.getenv(
            "TOPSTEP_BASE_URL",
            "https://api.topstepx.com"
        ).rstrip("/")

        self.username = os.getenv("TOPSTEP_USERNAME", "").strip()
        self.api_key = os.getenv("TOPSTEP_API_KEY_PRIMARY", "").strip()

        self._token: Optional[str] = None

    def _validate_config(self):
        if not self.username:
            raise RuntimeError("TOPSTEP_USERNAME is missing in .env")

        if not self.api_key:
            raise RuntimeError("TOPSTEP_API_KEY_PRIMARY is missing in .env")

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