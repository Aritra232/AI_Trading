from service.topstep_service import TopstepService


class PositionService:
    def __init__(self):
        self.client = TopstepService()

    async def get_open_positions(
        self,
        account_id: int
    ):
        return await self.client.post(
            "/api/Position/searchOpen",
            {
                "accountId": account_id
            }
        )