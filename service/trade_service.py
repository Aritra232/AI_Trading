from service.topstep_service import TopstepService


class TradeService:
    def __init__(self):
        self.client = TopstepService()

    async def get_trades(
        self,
        account_id: int,
        start_timestamp: str,
        end_timestamp: str | None = None
    ):
        payload = {
            "accountId": account_id,
            "startTimestamp": start_timestamp,
            "endTimestamp": end_timestamp
        }

        return await self.client.post(
            "/api/Trade/search",
            payload
        )