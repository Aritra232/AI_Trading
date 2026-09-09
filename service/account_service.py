from service.topstep_service import TopstepService


class AccountService:
    def __init__(
        self,
        client: TopstepService | None = None
    ):
        self.client = client or TopstepService()

    async def get_accounts(self):
        return await self.client.post(
            "/api/Account/search",
            {
                "onlyActiveAccounts": True
            }
        )
