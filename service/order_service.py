from service.topstep_service import TopstepService


class OrderService:
    def __init__(self):
        self.client = TopstepService()

    async def get_open_orders(
        self,
        account_id: int
    ):
        return await self.client.post(
            "/api/Order/searchOpen",
            {
                "accountId": account_id
            }
        )

    async def get_orders(
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
            "/api/Order/search",
            payload
        )