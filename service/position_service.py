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

    async def close_contract_position(
        self,
        account_id: int,
        contract_id: str
    ):
        return await self.client.post(
            "/api/Position/closeContract",
            {
                "accountId": account_id,
                "contractId": contract_id
            }
        )

    async def partial_close_contract_position(
        self,
        account_id: int,
        contract_id: str,
        size: int
    ):
        return await self.client.post(
            "/api/Position/partialCloseContract",
            {
                "accountId": account_id,
                "contractId": contract_id,
                "size": size
            }
        )
