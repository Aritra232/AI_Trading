import asyncio
from typing import Optional

from service.account_service import AccountService
from service.contract_service import ContractService
from service.history_service import HistoryService
from service.position_service import PositionService
from service.order_service import OrderService
from service.realtime_service import RealtimeService


class TradingStateService:
    def __init__(
        self,
        account_service: AccountService,
        contract_service: ContractService,
        history_service: HistoryService,
        position_service: PositionService,
        order_service: OrderService,
        realtime_service: RealtimeService
    ):
        self.account_service = account_service
        self.contract_service = contract_service
        self.history_service = history_service
        self.position_service = position_service
        self.order_service = order_service
        self.realtime_service = realtime_service

    async def get_trading_state(
        self,
        account_id: int,
        contract_id: str,
        search_text: str = "MES",
        live: bool = False,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        unit: int = 2,
        unit_number: int = 5,
        limit: int = 100
    ):

        # =========================
        # Fetch Current REST Data
        # =========================

        (
            accounts_result,
            contracts_result,
            positions_result,
            orders_result
        ) = await asyncio.gather(
            self.account_service.get_accounts(),

            self.contract_service.search_contracts(
                search_text=search_text,
                live=live
            ),

            self.position_service.get_open_positions(
                account_id=account_id
            ),

            self.order_service.get_open_orders(
                account_id=account_id
            )
        )

        # =========================
        # Find Selected Account
        # =========================

        selected_account = None

        for account in accounts_result.get(
            "accounts",
            []
        ):
            if account.get("id") == account_id:
                selected_account = account
                break

        # =========================
        # Find Selected Contract
        # =========================

        selected_contract = None

        for contract in contracts_result.get(
            "contracts",
            []
        ):
            if contract.get("id") == contract_id:
                selected_contract = contract
                break

        # =========================
        # Current Positions
        # =========================

        positions = positions_result.get(
            "positions",
            []
        )

        # =========================
        # Current Open Orders
        # =========================

        open_orders = orders_result.get(
            "orders",
            []
        )

        # =========================
        # Latest Realtime State
        # =========================

        realtime_result = (
            self.realtime_service.get_latest_data()
        )

        realtime_data = realtime_result.get(
            "data",
            {}
        )

        # =========================
        # Optional Historical Data
        # =========================

        historical_bars = None

        if start_time and end_time:
            history_result = (
                await self.history_service.get_bars(
                    contract_id=contract_id,
                    start_time=start_time,
                    end_time=end_time,
                    unit=unit,
                    unit_number=unit_number,
                    limit=limit,
                    live=live
                )
            )

            historical_bars = history_result.get(
                "bars",
                []
            )

        # =========================
        # Build Unified State
        # =========================

        return {
            "success": True,

            "account": selected_account,

            "contract": selected_contract,

            "market": {
                "quote": realtime_data.get(
                    "quote"
                ),
                "market_trade": realtime_data.get(
                    "market_trade"
                ),
                "depth": realtime_data.get(
                    "depth"
                ),
                "historical_bars": historical_bars
            },

            "positions": positions,

            "open_orders": open_orders,

            "realtime": {
                "account_update": realtime_data.get(
                    "account"
                ),
                "order_update": realtime_data.get(
                    "order"
                ),
                "position_update": realtime_data.get(
                    "position"
                ),
                "trade_update": realtime_data.get(
                    "trade"
                )
            },

            "summary": {
                "can_trade": (
                    selected_account.get("canTrade")
                    if selected_account
                    else False
                ),

                "has_open_position": (
                    len(positions) > 0
                ),

                "has_open_orders": (
                    len(open_orders) > 0
                ),

                "realtime_quote_available": (
                    realtime_data.get("quote")
                    is not None
                ),

                "market_depth_available": (
                    realtime_data.get("depth")
                    is not None
                )
            }
        }