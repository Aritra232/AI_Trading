import os
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
        order_service=None,
        position_service=None
    ):
        self.order_service = order_service
        self.position_service = position_service

    def _env_allows_live_trading(
        self
    ) -> bool:
        return (
            os.getenv(
                "ALLOW_LIVE_TRADING",
                ""
            ).strip().lower()
            == "true"
        )

    def _live_execution_block(
        self,
        prepared: dict,
        confirm_live_execution: bool
    ) -> dict | None:
        env_allowed = self._env_allows_live_trading()

        if (
            env_allowed
            and confirm_live_execution
        ):
            return None

        missing = []

        if not env_allowed:
            missing.append(
                "ALLOW_LIVE_TRADING=true"
            )

        if not confirm_live_execution:
            missing.append(
                "confirm_live_execution=true"
            )

        return {
            **prepared,
            "execution_status": "LIVE_EXECUTION_BLOCKED",
            "submitted": False,
            "dry_run": False,
            "reason": (
                "Live execution blocked. Required gate(s): "
                + ", ".join(
                    missing
                )
            ),
            "live_execution_gate": {
                "allow_live_trading_env": env_allowed,
                "confirm_live_execution": (
                    confirm_live_execution
                ),
                "allowed": False
            },
            "execution_version": (
                "EXECUTION_LIVE_GUARD_V1"
            )
        }

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

    def _extract_position_contract_id(
        self,
        position: dict
    ) -> Optional[str]:
        for key in (
            "contractId",
            "contract_id",
            "contractID",
            "symbolId"
        ):
            value = position.get(
                key
            )

            if value:
                return str(
                    value
                )

        contract = position.get(
            "contract"
        )

        if isinstance(
            contract,
            dict
        ):
            value = (
                contract.get(
                    "id"
                )
                or contract.get(
                    "contractId"
                )
            )

            if value:
                return str(
                    value
                )

        return None

    def _build_close_all_payloads(
        self,
        account_id: int,
        positions: list
    ) -> list[dict]:
        contract_ids = []
        seen = set()

        for position in positions or []:
            contract_id = self._extract_position_contract_id(
                position
            )

            if (
                not contract_id
                or contract_id in seen
            ):
                continue

            seen.add(
                contract_id
            )
            contract_ids.append(
                contract_id
            )

        payloads = []

        for contract_id in contract_ids:
            payloads.append(
                {
                    "accountId": account_id,
                    "contractId": contract_id,
                    "customTag": self._build_custom_tag(
                        account_id=account_id,
                        contract_id=contract_id,
                        action="EXIT"
                    )
                }
            )

        return payloads

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

    def _prepare_allowed_exit(
        self,
        account_id: int,
        contract_id: str,
        final_decision: dict,
        safety_result: dict
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

        close_payload = {
            "accountId": account_id,
            "contractId": contract_id,
            "customTag": self._build_custom_tag(
                account_id=account_id,
                contract_id=contract_id,
                action="EXIT"
            )
        }

        return {
            "success": True,
            "submitted": False,
            "action": "EXIT",
            "close_payload": close_payload,
            "final_decision_summary": {
                "final_status": final_decision.get(
                    "final_status"
                ),
                "action": "EXIT",
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
        action = str(
            (final_decision or {}).get(
                "action",
                "WAIT"
            )
        ).upper()

        if action == "EXIT":
            prepared = self._prepare_allowed_exit(
                account_id=account_id,
                contract_id=contract_id,
                final_decision=final_decision,
                safety_result=safety_result
            )

            prepared["dry_run"] = dry_run

            if prepared.get(
                "execution_status"
            ) == "BLOCKED":
                return prepared

            prepared["execution_status"] = (
                "DRY_RUN_CLOSE_READY"
            )
            prepared["message"] = (
                "Close-position request prepared but not submitted."
            )
            prepared["execution_version"] = (
                "EXECUTION_DRY_RUN_V1"
            )

            return prepared

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
        order_type: str = "MARKET",
        confirm_live_execution: bool = False
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

        live_block = self._live_execution_block(
            prepared=prepared,
            confirm_live_execution=(
                confirm_live_execution
            )
        )

        if live_block is not None:
            return live_block

        if prepared.get(
            "action"
        ) == "EXIT":
            if self.position_service is None:
                return {
                    **prepared,
                    "execution_status": "BLOCKED",
                    "submitted": False,
                    "reason": (
                        "Position service is not configured."
                    ),
                    "execution_version": (
                        "EXECUTION_LIVE_V1"
                    )
                }

            position_response = (
                await self.position_service.close_contract_position(
                    account_id=account_id,
                    contract_id=contract_id
                )
            )

            submitted = bool(
                position_response.get(
                    "success",
                    False
                )
            )

            return {
                **prepared,
                "execution_status": (
                    "CLOSE_SUBMITTED"
                    if submitted
                    else "CLOSE_REJECTED"
                ),
                "dry_run": False,
                "submitted": submitted,
                "message": (
                    "Close-position request submitted to ProjectX."
                    if submitted
                    else "ProjectX rejected the close-position request."
                ),
                "position_response": position_response,
                "execution_version": (
                    "EXECUTION_LIVE_V1"
                )
            }

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

    async def close_all_positions(
        self,
        account_id: int,
        positions: list,
        dry_run: bool = True,
        confirm_live_execution: bool = False,
        reason: str | None = None
    ) -> dict:
        payloads = self._build_close_all_payloads(
            account_id=account_id,
            positions=positions
        )

        if not payloads:
            return {
                "success": True,
                "execution_status": "DONE_FOR_DAY_NO_POSITION",
                "submitted": False,
                "dry_run": dry_run,
                "reason": (
                    reason
                    or "No open positions found to close."
                ),
                "action": "WAIT",
                "close_payloads": [],
                "position_response": None,
                "execution_version": (
                    "EXECUTION_DONE_FOR_DAY_V1"
                )
            }

        prepared = {
            "success": True,
            "submitted": False,
            "action": "EXIT",
            "close_payloads": payloads,
            "reason": (
                reason
                or "Daily profit cap reached; closing all open positions."
            ),
            "dry_run": dry_run,
            "execution_version": "EXECUTION_DRY_RUN_V1"
        }

        if dry_run:
            return {
                **prepared,
                "execution_status": "DRY_RUN_CLOSE_ALL_READY",
                "message": (
                    "Close-all-position requests prepared "
                    "but not submitted."
                )
            }

        live_block = self._live_execution_block(
            prepared=prepared,
            confirm_live_execution=(
                confirm_live_execution
            )
        )

        if live_block is not None:
            return live_block

        if self.position_service is None:
            return {
                **prepared,
                "execution_status": "BLOCKED",
                "submitted": False,
                "reason": (
                    "Position service is not configured."
                ),
                "execution_version": (
                    "EXECUTION_LIVE_V1"
                )
            }

        responses = []

        for payload in payloads:
            response = (
                await self.position_service.close_contract_position(
                    account_id=account_id,
                    contract_id=payload[
                        "contractId"
                    ]
                )
            )

            responses.append(
                {
                    "contractId": payload[
                        "contractId"
                    ],
                    "response": response
                }
            )

        submitted = all(
            bool(
                item.get(
                    "response",
                    {}
                ).get(
                    "success",
                    False
                )
            )
            for item in responses
        )

        return {
            **prepared,
            "execution_status": (
                "CLOSE_ALL_SUBMITTED"
                if submitted
                else "CLOSE_ALL_PARTIAL_OR_REJECTED"
            ),
            "dry_run": False,
            "submitted": submitted,
            "message": (
                "Close-all-position requests submitted to ProjectX."
                if submitted
                else "One or more close-position requests failed."
            ),
            "position_responses": responses,
            "execution_version": (
                "EXECUTION_LIVE_V1"
            )
        }
