from service.topstep_service import TopstepService


class OrderService:
    def __init__(
        self,
        client: TopstepService | None = None
    ):
        self.client = client or TopstepService()

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

    async def place_order(
        self,
        payload: dict
    ):
        return await self.client.post(
            "/api/Order/place",
            payload
        )

    async def cancel_order(
        self,
        account_id: int,
        order_id: int
    ):
        return await self.client.post(
            "/api/Order/cancel",
            {
                "accountId": account_id,
                "orderId": order_id
            }
        )

    async def modify_order(
        self,
        account_id: int,
        order_id: int,
        size: int | None = None,
        limit_price: float | None = None,
        stop_price: float | None = None,
        trail_price: float | None = None
    ):
        payload = {
            "accountId": account_id,
            "orderId": order_id
        }

        if size is not None:
            payload["size"] = size

        if limit_price is not None:
            payload["limitPrice"] = limit_price

        if stop_price is not None:
            payload["stopPrice"] = stop_price

        if trail_price is not None:
            payload["trailPrice"] = trail_price

        return await self.client.post(
            "/api/Order/modify",
            payload
        )
