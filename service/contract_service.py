from service.topstep_service import TopstepService


class ContractService:
    def __init__(
        self,
        client: TopstepService | None = None
    ):
        self.client = client or TopstepService()

    async def search_contracts(
        self,
        search_text: str,
        live: bool = False
    ):
        return await self.client.post(
            "/api/Contract/search",
            {
                "searchText": search_text,
                "live": live
            }
        )
