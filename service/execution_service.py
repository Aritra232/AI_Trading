from datetime import datetime, timezone
from typing import Optional


class ExecutionService:
    ORDER_TYPES = {
        "LIMIT": 1,
        "MARKET": 2,
        "STOP": 4,
        "TRAILING_STOP": 5,
        "JOIN_BID": 6,
        "JOIN_ASK": 7
    }

    SIDES = {
        "BUY": 0,
        "SELL": 1
    }

    def __init__(
        self,
        order_service=None
    ):
        self.order_service = order_service

    def _build_custom_tag(
        self,
        account_id: int,
        contract_id: str,
        action: str
    ) -> str:
        timestamp = datetime.now(
            timezone.utc
        ).strftime(
            "%Y%m%d%H%M%S%f"
        )

        safe_contract = (
            contract_id
            .replace(".", "_")
            .replace("-", "_")
        )

        return (
            f"ai_{account_id}_{safe_contract}_"
            f"{action.lower()}_{timestamp}"
        )

    def _ticks_between(
        self,
        price_a: Optional[float],
        price_b: Optional[float],
        tick_size: Optional[float]
    ) -> Optional[int]:
        if (
            price_a is None
            or price_b is None
            or tick_size is None
            or tick_size <= 0
        ):
            return None

        ticks = round(
            abs(
                float(price_a)
                - float(price_b)
            )
            / float(tick_size)
        )

        if ticks <= 0:
            return None

        return int(ticks)

    def build_order_payload(
        self,
        account_id: int,
        contract_id: str,
        action: str,
        quantity: int,
        order_type: str = "MARKET",
        entry_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        tick_size: Optional[float] = None
    ) -> dict:
        action = action.upper().strip()
        order_type = order_type.upper().strip()

        if action not in self.SIDES:
            raise ValueError(
                f"Unsupported executable action: {action}"
            )

        if order_type not in self.ORDER_TYPES:
            raise ValueError(
                f"Unsupported order type: {order_type}"
            )

        if quantity <= 0:
            raise ValueError(
                "Order quantity must be greater than zero."
            )

        order_type_id = self.ORDER_TYPES[
            order_type
        ]

        payload = {
            "accountId": account_id,
            "contractId": contract_id,
            "type": order_type_id,
            "side": self.SIDES[action],
            "size": quantity,
            "limitPrice": None,
            "stopPrice": None,
            "trailPrice": None,
            "customTag": self._build_custom_tag(
                account_id=account_id,
                contract_id=contract_id,
                action=action
            ),
            "stopLossBracket": None,
            "takeProfitBracket": None
        }

        if order_type == "LIMIT":
            payload["limitPrice"] = entry_price

        if order_type == "STOP":
            payload["stopPrice"] = entry_price

        stop_ticks = self._ticks_between(
            entry_price,
            stop_loss,
            tick_size
        )

        if stop_ticks is not None:
            payload["stopLossBracket"] = {
                "ticks": stop_ticks,
                "type": self.ORDER_TYPES["STOP"]
            }

        take_profit_ticks = self._ticks_between(
            entry_price,
            take_profit,
            tick_size
        )

        if take_profit_ticks is not None:
            payload["takeProfitBracket"] = {
                "ticks": take_profit_ticks,
                "type": self.ORDER_TYPES["LIMIT"]
            }

        return payload

    def _prepare_allowed_order(
        self,
        account_id: int,
        contract_id: str,
        final_decision: dict,
        safety_result: dict,
        contract: dict,
        order_type: str = "MARKET"
    ) -> dict:
        if not final_decision:
            return {
                "success": True,
                "execution_status": "BLOCKED",
                "submitted": False,
                "reason": "Final decision is unavailable."
            }

        if not safety_result:
            return {
                "success": True,
                "execution_status": "BLOCKED",
                "submitted": False,
                "reason": "Safety result is unavailable."
            }

        execution_allowed = bool(
            final_decision.get(
                "execution_allowed",
                False
            )
        )

        safe_to_execute = bool(
            safety_result.get(
                "safe_to_execute",
                False
            )
        )

        if not execution_allowed or not safe_to_execute:
            return {
                "success": True,
                "execution_status": "BLOCKED",
                "submitted": False,
                "reason": (
                    "Execution is blocked by final decision "
                    "or safety validation."
                ),
                "execution_allowed": execution_allowed,
                "safe_to_execute": safe_to_execute
            }

        action = str(
            final_decision.get(
                "action",
                "WAIT"
            )
        ).upper()

        if action not in {
            "BUY",
            "SELL"
        }:
            return {
                "success": True,
                "execution_status": "BLOCKED",
                "submitted": False,
                "reason": (
                    f"Action {action} is not supported "
                    "by order execution yet."
                )
            }

        strategy = final_decision.get(
            "strategy",
            {}
        )

        trade_plan = strategy.get(
            "trade_plan",
            {}
        )

        payload = self.build_order_payload(
            account_id=account_id,
            contract_id=contract_id,
            action=action,
            quantity=int(
                final_decision.get(
                    "planned_quantity",
                    1
                )
            ),
            order_type=order_type,
            entry_price=trade_plan.get(
                "entry_price"
            ),
            stop_loss=trade_plan.get(
                "stop_loss"
            ),
            take_profit=trade_plan.get(
                "take_profit"
            ),
            tick_size=contract.get(
                "tickSize"
            )
        )

        return {
            "success": True,
            "submitted": False,
            "action": action,
            "order_payload": payload,
            "final_decision_summary": {
                "final_status": final_decision.get(
                    "final_status"
                ),
                "action": action,
                "execution_allowed": execution_allowed
            },
            "safety_summary": {
                "safety_status": safety_result.get(
                    "safety_status"
                ),
                "safe_to_execute": safe_to_execute
            },
            "execution_version": "EXECUTION_DRY_RUN_V1"
        }

    def prepare_execution(
        self,
        account_id: int,
        contract_id: str,
        final_decision: dict,
        safety_result: dict,
        contract: dict,
        dry_run: bool = True,
        order_type: str = "MARKET"
    ) -> dict:
        prepared = self._prepare_allowed_order(
            account_id=account_id,
            contract_id=contract_id,
            final_decision=final_decision,
            safety_result=safety_result,
            contract=contract,
            order_type=order_type
        )

        prepared["dry_run"] = dry_run

        if prepared.get(
            "execution_status"
        ) == "BLOCKED":
            return prepared

        prepared["execution_status"] = (
            "DRY_RUN_READY"
        )
        prepared["message"] = (
            "Order payload prepared but not submitted."
        )
        prepared["execution_version"] = (
            "EXECUTION_DRY_RUN_V1"
        )

        return prepared

    async def execute(
        self,
        account_id: int,
        contract_id: str,
        final_decision: dict,
        safety_result: dict,
        contract: dict,
        dry_run: bool = True,
        order_type: str = "MARKET"
    ) -> dict:
        prepared = self.prepare_execution(
            account_id=account_id,
            contract_id=contract_id,
            final_decision=final_decision,
            safety_result=safety_result,
            contract=contract,
            dry_run=dry_run,
            order_type=order_type
        )

        if (
            dry_run
            or prepared.get(
                "execution_status"
            ) == "BLOCKED"
        ):
            return prepared

        if self.order_service is None:
            return {
                **prepared,
                "execution_status": "BLOCKED",
                "submitted": False,
                "reason": (
                    "Order service is not configured."
                ),
                "execution_version": (
                    "EXECUTION_LIVE_V1"
                )
            }

        order_response = await self.order_service.place_order(
            prepared["order_payload"]
        )

        submitted = bool(
            order_response.get(
                "success",
                False
            )
        )

        return {
            **prepared,
            "execution_status": (
                "SUBMITTED"
                if submitted
                else "REJECTED"
            ),
            "dry_run": False,
            "submitted": submitted,
            "message": (
                "Order submitted to ProjectX."
                if submitted
                else "ProjectX rejected the order."
            ),
            "order_response": order_response,
            "execution_version": (
                "EXECUTION_LIVE_V1"
            )
        }
