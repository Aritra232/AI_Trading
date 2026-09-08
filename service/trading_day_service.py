from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TradingDayService:
    def __init__(
        self,
        trade_service,
        trading_timezone: str = "America/Chicago"
    ):
        self.trade_service = trade_service
        self.trading_timezone = trading_timezone
        self.session_start = time(
            17,
            0
        )
        self.session_end = time(
            15,
            10
        )

        self.pnl_fields = (
            "profitAndLoss",
            "profitLoss",
            "realizedPnl",
            "realizedPnL",
            "realizedPL",
            "pnl",
            "pNl",
            "netPnl",
            "netPnL",
            "grossProfit",
            "profit"
        )

        self.timestamp_fields = (
            "timestamp",
            "createdAt",
            "created_at",
            "time",
            "tradeTime",
            "executionTime",
            "filledAt",
            "fillTime"
        )

    def _nth_weekday_of_month(
        self,
        year: int,
        month: int,
        weekday: int,
        occurrence: int
    ):
        current = datetime(
            year,
            month,
            1
        ).date()

        days_until_weekday = (
            weekday
            - current.weekday()
        ) % 7

        return (
            current
            + timedelta(
                days=(
                    days_until_weekday
                    + (occurrence - 1) * 7
                )
            )
        )

    def _fallback_central_timezone(
        self,
        reference_utc: datetime
    ) -> timezone:
        year = reference_utc.year

        dst_start_day = self._nth_weekday_of_month(
            year=year,
            month=3,
            weekday=6,
            occurrence=2
        )

        dst_end_day = self._nth_weekday_of_month(
            year=year,
            month=11,
            weekday=6,
            occurrence=1
        )

        dst_start_utc = datetime.combine(
            dst_start_day,
            time(
                8,
                0
            ),
            tzinfo=timezone.utc
        )

        dst_end_utc = datetime.combine(
            dst_end_day,
            time(
                7,
                0
            ),
            tzinfo=timezone.utc
        )

        if dst_start_utc <= reference_utc < dst_end_utc:
            return timezone(
                timedelta(
                    hours=-5
                ),
                "CDT"
            )

        return timezone(
            timedelta(
                hours=-6
            ),
            "CST"
        )

    def _get_trading_timezone(
        self,
        reference_utc: datetime
    ):
        try:
            return ZoneInfo(
                self.trading_timezone
            )

        except ZoneInfoNotFoundError:
            return self._fallback_central_timezone(
                reference_utc=reference_utc
            )

    def _parse_datetime(
        self,
        value: str | None
    ) -> datetime | None:
        if not value:
            return None

        try:
            parsed = datetime.fromisoformat(
                str(value).replace(
                    "Z",
                    "+00:00"
                )
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed.astimezone(
                timezone.utc
            )

        except Exception:
            return None

    def _utc_iso(
        self,
        value: datetime
    ) -> str:
        return value.astimezone(
            timezone.utc
        ).isoformat().replace(
            "+00:00",
            "Z"
        )

    def _trading_day_label(
        self,
        value: datetime
    ) -> str:
        local_value = value.astimezone(
            self._get_trading_timezone(
                value
            )
        )

        if local_value.time() >= self.session_start:
            return local_value.date().isoformat()

        return (
            local_value.date()
            - timedelta(
                days=1
            )
        ).isoformat()

    def get_trading_day_window(
        self,
        now: datetime | None = None
    ) -> dict[str, Any]:
        now_utc = now or datetime.now(
            timezone.utc
        )

        if now_utc.tzinfo is None:
            now_utc = now_utc.replace(
                tzinfo=timezone.utc
            )

        tz = self._get_trading_timezone(
            now_utc
        )

        local_now = now_utc.astimezone(
            tz
        )

        local_date = local_now.date()
        local_time = local_now.time()

        if local_now.weekday() == 5:
            trading_start_date = (
                local_date
                - timedelta(
                    days=1
                )
            )

        elif (
            local_now.weekday() == 6
            and local_time < self.session_start
        ):
            trading_start_date = (
                local_date
                - timedelta(
                    days=2
                )
            )

        elif local_time >= self.session_start:
            trading_start_date = local_date

        else:
            trading_start_date = (
                local_date
                - timedelta(
                    days=1
                )
            )

        start_local = datetime.combine(
            trading_start_date,
            self.session_start,
            tzinfo=tz
        )

        end_local = datetime.combine(
            trading_start_date
            + timedelta(
                days=1
            ),
            self.session_end,
            tzinfo=tz
        )

        session_open = (
            start_local
            <= local_now
            <= end_local
        )

        return {
            "timezone": self.trading_timezone,
            "start": self._utc_iso(
                start_local
            ),
            "end": self._utc_iso(
                end_local
            ),
            "start_local": start_local.isoformat(),
            "end_local": end_local.isoformat(),
            "label": trading_start_date.isoformat(),
            "session_open": session_open
        }

    def _extract_trades(
        self,
        trades_result: dict[str, Any]
    ) -> list[dict[str, Any]]:
        trades = trades_result.get(
            "trades"
        )

        if isinstance(
            trades,
            list
        ):
            return [
                trade
                for trade in trades
                if isinstance(
                    trade,
                    dict
                )
            ]

        data = trades_result.get(
            "data"
        )

        if isinstance(
            data,
            list
        ):
            return [
                trade
                for trade in data
                if isinstance(
                    trade,
                    dict
                )
            ]

        return []

    def _extract_timestamp(
        self,
        trade: dict[str, Any]
    ) -> datetime | None:
        for field in self.timestamp_fields:
            parsed = self._parse_datetime(
                trade.get(
                    field
                )
            )

            if parsed is not None:
                return parsed

        return None

    def _extract_pnl(
        self,
        trade: dict[str, Any]
    ) -> float | None:
        for field in self.pnl_fields:
            value = trade.get(
                field
            )

            if value is None:
                continue

            try:
                return float(
                    value
                )

            except (
                TypeError,
                ValueError
            ):
                continue

        return None

    def _summarize_trades(
        self,
        trades: list[dict[str, Any]]
    ) -> dict[str, Any]:
        total_pnl = 0.0
        pnl_available = 0
        missing_pnl = 0
        missing_timestamp = 0
        trading_days: dict[str, dict[str, Any]] = {}

        for trade in trades:
            timestamp = self._extract_timestamp(
                trade
            )

            pnl = self._extract_pnl(
                trade
            )

            if timestamp is None:
                missing_timestamp += 1
                day_label = "unknown"

            else:
                day_label = self._trading_day_label(
                    timestamp
                )

            day = trading_days.setdefault(
                day_label,
                {
                    "trade_count": 0,
                    "pnl": 0.0,
                    "pnl_available": 0,
                    "missing_pnl": 0
                }
            )

            day["trade_count"] += 1

            if pnl is None:
                missing_pnl += 1
                day["missing_pnl"] += 1
                continue

            pnl_available += 1
            total_pnl += pnl
            day["pnl"] += pnl
            day["pnl_available"] += 1

        known_days = {
            key: value
            for key, value in trading_days.items()
            if key != "unknown"
        }

        best_day_profit = None

        if known_days:
            best_day_profit = max(
                day["pnl"]
                for day in known_days.values()
            )

        return {
            "total_pnl": total_pnl,
            "pnl_available_count": pnl_available,
            "missing_pnl_count": missing_pnl,
            "missing_timestamp_count": missing_timestamp,
            "trading_day_count": len(
                known_days
            ),
            "best_day_profit": best_day_profit,
            "days": known_days
        }

    async def get_current_trading_day_pnl(
        self,
        account_id: int
    ) -> dict[str, Any]:
        window = self.get_trading_day_window()

        trades_result = await self.trade_service.get_trades(
            account_id=account_id,
            start_timestamp=window[
                "start"
            ],
            end_timestamp=window[
                "end"
            ]
        )

        trades = self._extract_trades(
            trades_result
        )

        summary = self._summarize_trades(
            trades
        )

        warnings = []

        pnl_trusted = (
            not trades
            or summary["pnl_available_count"] > 0
        )

        if not pnl_trusted:
            warnings.append(
                (
                    "Trade records were found, but no recognized "
                    "realized P&L field was available."
                )
            )

        return {
            "success": True,
            "account_id": account_id,
            "trading_day": window,
            "current_trading_day_pnl": (
                summary[
                    "total_pnl"
                ]
                if pnl_trusted
                else None
            ),
            "trade_count": len(
                trades
            ),
            "pnl_available_count": summary[
                "pnl_available_count"
            ],
            "missing_pnl_count": summary[
                "missing_pnl_count"
            ],
            "warnings": warnings,
            "source": "TOPSTEP_TRADE_SEARCH",
            "raw_success": trades_result.get(
                "success"
            )
        }

    async def get_evaluation_progress(
        self,
        account_id: int,
        evaluation_start_time: str | None = None,
        lookback_days: int = 14
    ) -> dict[str, Any]:
        now = datetime.now(
            timezone.utc
        )

        start = self._parse_datetime(
            evaluation_start_time
        )

        if start is None:
            start = now - timedelta(
                days=max(
                    int(lookback_days),
                    1
                )
            )

        trades_result = await self.trade_service.get_trades(
            account_id=account_id,
            start_timestamp=self._utc_iso(
                start
            ),
            end_timestamp=self._utc_iso(
                now
            )
        )

        trades = self._extract_trades(
            trades_result
        )

        summary = self._summarize_trades(
            trades
        )

        current_day_result = (
            await self.get_current_trading_day_pnl(
                account_id=account_id
            )
        )

        warnings = []

        if evaluation_start_time is None:
            warnings.append(
                (
                    "evaluation_start_time was not provided; "
                    f"using last {lookback_days} calendar days."
                )
            )

        pnl_trusted = (
            not trades
            or summary["pnl_available_count"] > 0
        )

        if not pnl_trusted:
            warnings.append(
                (
                    "Trade records were found, but no recognized "
                    "realized P&L field was available."
                )
            )

        warnings.extend(
            current_day_result.get(
                "warnings",
                []
            )
        )

        return {
            "success": True,
            "account_id": account_id,
            "evaluation_start_time": self._utc_iso(
                start
            ),
            "evaluation_end_time": self._utc_iso(
                now
            ),
            "lookback_days": lookback_days,
            "current_trading_day": current_day_result.get(
                "trading_day"
            ),
            "current_trading_day_pnl": (
                current_day_result.get(
                    "current_trading_day_pnl"
                )
            ),
            "evaluation_trading_days": summary[
                "trading_day_count"
            ],
            "best_day_profit": (
                summary[
                    "best_day_profit"
                ]
                if pnl_trusted
                else None
            ),
            "total_trade_count": len(
                trades
            ),
            "pnl_available_count": summary[
                "pnl_available_count"
            ],
            "missing_pnl_count": summary[
                "missing_pnl_count"
            ],
            "days": summary[
                "days"
            ],
            "warnings": warnings,
            "source": "TOPSTEP_TRADE_SEARCH",
            "raw_success": trades_result.get(
                "success"
            )
        }
