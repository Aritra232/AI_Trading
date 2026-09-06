from datetime import datetime, timedelta, timezone
from typing import Optional


class MarketStatusService:
    def __init__(
        self,
        account_service,
        contract_service,
        history_service,
        realtime_service
    ):
        self.account_service = account_service
        self.contract_service = contract_service
        self.history_service = history_service
        self.realtime_service = realtime_service

    def _utc_now(self):
        return datetime.now(
            timezone.utc
        )

    def _utc_now_iso(self):
        return self._utc_now().isoformat().replace(
            "+00:00",
            "Z"
        )

    def _utc_lookback_iso(
        self,
        hours: int
    ):
        return (
            self._utc_now()
            - timedelta(
                hours=hours
            )
        ).isoformat().replace(
            "+00:00",
            "Z"
        )

    def _parse_datetime(
        self,
        value: Optional[str]
    ) -> Optional[datetime]:
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(
                value.replace(
                    "Z",
                    "+00:00"
                )
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed

        except Exception:
            return None

    def _age_seconds(
        self,
        value: Optional[str]
    ) -> Optional[float]:
        parsed = self._parse_datetime(
            value
        )

        if parsed is None:
            return None

        return max(
            (
                self._utc_now()
                - parsed
            ).total_seconds(),
            0
        )

    async def _get_account(
        self,
        account_id: int
    ):
        accounts_result = await self.account_service.get_accounts()

        for account in accounts_result.get(
            "accounts",
            []
        ):
            if account.get(
                "id"
            ) == account_id:
                return account

        return None

    async def _resolve_active_contract(
        self,
        symbol: str,
        live: bool
    ):
        contracts_result = (
            await self.contract_service.search_contracts(
                search_text=symbol,
                live=live
            )
        )

        contracts = contracts_result.get(
            "contracts",
            []
        )

        if not contracts:
            return None

        for contract in contracts:
            if contract.get(
                "activeContract"
            ):
                return contract

        return contracts[0]

    async def get_status(
        self,
        account_id: int,
        symbol: str = "MES",
        live: bool = False,
        auto_start_realtime: bool = True,
        realtime_warmup_seconds: int = 3,
        max_quote_age_seconds: int = 30,
        lookback_hours: int = 96
    ):
        account = await self._get_account(
            account_id=account_id
        )

        contract = await self._resolve_active_contract(
            symbol=symbol,
            live=live
        )

        if account is None:
            return {
                "success": True,
                "market_status": "UNKNOWN",
                "tradable": False,
                "reason": "Account was not found.",
                "symbol": symbol
            }

        if contract is None:
            return {
                "success": True,
                "market_status": "UNKNOWN",
                "tradable": False,
                "reason": "Active contract was not found.",
                "symbol": symbol,
                "account": {
                    "canTrade": account.get(
                        "canTrade"
                    )
                }
            }

        contract_id = contract.get(
            "id"
        )

        realtime_started = False

        if auto_start_realtime:
            await self.realtime_service.start_market_hub(
                contract_id=contract_id
            )

            realtime_started = True

        latest = self.realtime_service.get_latest_data().get(
            "data",
            {}
        )

        if (
            auto_start_realtime
            and realtime_warmup_seconds > 0
        ):
            import asyncio

            await asyncio.sleep(
                realtime_warmup_seconds
            )

            latest = self.realtime_service.get_latest_data().get(
                "data",
                {}
            )

        quote = latest.get(
            "quote"
        )

        quote_data = {}

        if quote:
            quote_data = quote.get(
                "data",
                quote
            )

        quote_timestamp = (
            quote_data.get(
                "lastUpdated"
            )
            or quote_data.get(
                "timestamp"
            )
        )

        quote_age_seconds = self._age_seconds(
            quote_timestamp
        )

        history = await self.history_service.get_bars(
            contract_id=contract_id,
            start_time=self._utc_lookback_iso(
                lookback_hours
            ),
            end_time=self._utc_now_iso(),
            unit=2,
            unit_number=5,
            limit=1,
            live=live
        )

        latest_bar = history.get(
            "latest_bar"
        )

        latest_bar_age_seconds = None

        if latest_bar:
            latest_bar_age_seconds = self._age_seconds(
                latest_bar.get(
                    "t"
                )
            )

        account_can_trade = bool(
            account.get(
                "canTrade",
                False
            )
        )

        contract_active = bool(
            contract.get(
                "activeContract",
                False
            )
        )

        blocks = []
        warnings = []

        if not account_can_trade:
            blocks.append(
                "Account is not currently allowed to trade."
            )

        if not contract_active:
            blocks.append(
                "Resolved contract is not marked active."
            )

        if not quote:
            blocks.append(
                "Realtime quote is unavailable."
            )

        elif quote_age_seconds is None:
            blocks.append(
                "Realtime quote timestamp cannot be validated."
            )

        elif quote_age_seconds > max_quote_age_seconds:
            blocks.append(
                (
                    f"Realtime quote is stale. "
                    f"Age={quote_age_seconds:.2f}s, "
                    f"maximum allowed={max_quote_age_seconds}s."
                )
            )

        if not latest_bar:
            warnings.append(
                "Historical latest bar is unavailable."
            )

        if blocks:
            market_status = "STALE_DATA"

            if not quote:
                market_status = "UNKNOWN"

            if (
                not account_can_trade
                or not contract_active
            ):
                market_status = "BLOCKED"

            tradable = False

        else:
            market_status = "OPEN"
            tradable = True

        return {
            "success": True,
            "market_status": market_status,
            "tradable": tradable,
            "symbol": symbol,
            "live": live,
            "realtime_started": realtime_started,
            "account": {
                "id": account.get(
                    "id"
                ),
                "canTrade": account_can_trade,
                "simulated": account.get(
                    "simulated"
                )
            },
            "contract": {
                "id": contract_id,
                "name": contract.get(
                    "name"
                ),
                "description": contract.get(
                    "description"
                ),
                "activeContract": contract_active
            },
            "quote": {
                "available": quote is not None,
                "lastUpdated": quote_timestamp,
                "age_seconds": quote_age_seconds,
                "max_age_seconds": max_quote_age_seconds,
                "lastPrice": quote_data.get(
                    "lastPrice"
                ),
                "bestBid": quote_data.get(
                    "bestBid"
                ),
                "bestAsk": quote_data.get(
                    "bestAsk"
                )
            },
            "history": {
                "latest_bar_time": (
                    latest_bar.get(
                        "t"
                    )
                    if latest_bar
                    else None
                ),
                "latest_bar_age_seconds": (
                    latest_bar_age_seconds
                ),
                "bar_count": history.get(
                    "bar_count"
                )
            },
            "blocks": blocks,
            "warnings": warnings,
            "status_version": "MARKET_STATUS_V1"
        }
