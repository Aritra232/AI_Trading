from service.topstep_service import TopstepService


class HistoryService:
    def __init__(self):
        self.client = TopstepService()

    async def get_bars(
        self,
        contract_id: str,
        start_time: str,
        end_time: str,
        unit: int = 2,
        unit_number: int = 5,
        limit: int = 100,
        live: bool = False,
        include_partial_bar: bool = False
    ):
        payload = {
            "contractId": contract_id,
            "live": live,
            "startTime": start_time,
            "endTime": end_time,
            "unit": unit,
            "unitNumber": unit_number,
            "limit": limit,
            "includePartialBar": include_partial_bar
        }

        return await self.client.post(
            "/api/History/retrieveBars",
            payload
        )