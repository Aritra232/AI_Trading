from service.topstep_service import TopstepService


class HistoryService:
    def __init__(
        self,
        client: TopstepService | None = None
    ):
        self.client = client or TopstepService()

    def _normalize_bars(self, response: dict):
        bars = response.get(
            "bars",
            []
        )

        if not isinstance(bars, list):
            bars = []

        sorted_bars = sorted(
            bars,
            key=lambda bar: str(
                bar.get(
                    "t",
                    ""
                )
            )
        )

        response["bars"] = sorted_bars
        response["bar_count"] = len(
            sorted_bars
        )
        response["bars_order"] = (
            "oldest_to_newest"
        )
        response["oldest_bar"] = (
            sorted_bars[0]
            if sorted_bars
            else None
        )
        response["latest_bar"] = (
            sorted_bars[-1]
            if sorted_bars
            else None
        )

        return response

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

        response = await self.client.post(
            "/api/History/retrieveBars",
            payload
        )

        return self._normalize_bars(
            response
        )
