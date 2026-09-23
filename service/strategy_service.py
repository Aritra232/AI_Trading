import json
import os
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"


class StrategyService:
    def __init__(self):
        load_dotenv(
            dotenv_path=ENV_PATH,
            override=True
        )

        api_key = os.getenv(
            "OPENAI_API_KEY",
            ""
        ).strip()

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is missing in .env"
            )

        self.client = OpenAI(
            api_key=api_key
        )

        self.model = os.getenv(
            "OPENAI_MODEL",
            "gpt-5.6-terra"
        )

    def _prepare_bars(
        self,
        historical_bars: List[dict],
        max_bars: int = 100
    ):
        if not historical_bars:
            return []

        sorted_bars = sorted(
            historical_bars,
            key=lambda bar: str(
                bar.get(
                    "t",
                    ""
                )
            )
        )

        return sorted_bars[-max_bars:]

    def _to_float(
        self,
        value
    ):
        if value is None:
            return None

        try:
            return float(
                value
            )

        except Exception:
            return None

    def _clamp_confidence(
        self,
        value
    ):
        confidence = self._to_float(
            value
        )

        if confidence is None:
            return 0.0

        return max(
            0.0,
            min(
                confidence,
                1.0
            )
        )

    def _normalize_choice(
        self,
        value,
        allowed_values,
        default
    ):
        normalized = str(
            value or default
        ).upper().strip()

        if normalized not in allowed_values:
            return default

        return normalized

    def _is_protective_order(
        self,
        order: dict
    ) -> bool:
        custom_tag = str(
            order.get(
                "customTag",
                ""
            )
            or ""
        ).upper()

        return bool(
            order.get(
                "parentOrderId"
            )
        ) or custom_tag.endswith(
            "-SL"
        ) or custom_tag.endswith(
            "-TP"
        )

    def _non_protective_open_orders(
        self,
        open_orders: List[dict]
    ) -> List[dict]:
        return [
            order
            for order in open_orders or []
            if not self._is_protective_order(
                order
            )
        ]

    def select_contract_for_auto_trading(
        self,
        contracts: List[dict],
        account_size: int = 50000,
        phase: str = "evaluation"
    ) -> Dict[str, Any]:
        if not contracts:
            raise ValueError(
                "No contracts were provided for AI selection."
            )

        summarized_contracts = []

        for contract in contracts:
            summarized_contracts.append(
                {
                    "id": contract.get("id"),
                    "name": contract.get("name"),
                    "description": contract.get("description"),
                    "tickSize": contract.get("tickSize"),
                    "tickValue": contract.get("tickValue"),
                    "activeContract": contract.get("activeContract"),
                    "symbolId": contract.get("symbolId")
                }
            )

        instructions = """
You are the instrument-selection component of an autonomous
Topstep evaluation trading system.

Choose exactly one contract from the supplied available contracts.

Selection priorities:

1. Only choose a contract from the provided list.
2. Prefer active contracts.
3. Prefer MNQ / Micro E-mini Nasdaq-100 when it is available and
   active because the client requested it for better profit potential.
4. Prefer liquid, common futures instruments suitable for evaluation.
5. Prefer smaller risk instruments when two choices are similar.
6. Do not invent symbols or contract IDs.
7. If the metadata is not enough to identify an advantage, choose the
   safest commonly traded contract from the available list.

Return JSON only with this exact shape:

{
  "selected_contract_id": "",
  "selected_symbol": "",
  "confidence": 0.0,
  "reason": ""
}
"""

        context = {
            "account_size": account_size,
            "phase": phase,
            "contracts": summarized_contracts
        }

        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=json.dumps(
                context,
                default=str
            )
        )

        raw_output = response.output_text

        try:
            result = json.loads(
                raw_output
            )

        except json.JSONDecodeError as exc:
            raise ValueError(
                "AI returned invalid contract-selection JSON."
            ) from exc

        selected_contract_id = str(
            result.get(
                "selected_contract_id",
                ""
            )
        ).strip()

        if not selected_contract_id:
            raise ValueError(
                "AI did not select a contract ID."
            )

        contract_ids = {
            str(
                contract.get(
                    "id",
                    ""
                )
            )
            for contract in contracts
        }

        if selected_contract_id not in contract_ids:
            raise ValueError(
                "AI selected a contract outside the available list."
            )

        return {
            "success": True,
            "selected_contract_id": selected_contract_id,
            "selected_symbol": str(
                result.get(
                    "selected_symbol",
                    ""
                )
            ).strip().upper(),
            "confidence": self._clamp_confidence(
                result.get(
                    "confidence"
                )
            ),
            "reason": str(
                result.get(
                    "reason",
                    ""
                )
            ).strip(),
            "model": self.model,
            "selection_version": (
                "AI_CONTRACT_SELECTOR_V1"
            )
        }

    def _round_to_tick(
        self,
        value,
        tick_size
    ):
        value = self._to_float(
            value
        )

        tick_size = self._to_float(
            tick_size
        )

        if value is None:
            return None

        if (
            tick_size is None
            or tick_size <= 0
        ):
            return value

        return round(
            round(
                value / tick_size
            )
            * tick_size,
            10
        )

    def _fail_closed_strategy(
        self,
        reason,
        raw_output=None,
        ai_used=True,
        current_price=None,
        current_price_source=None,
        historical_bar_count=0
    ):
        result = {
            "success": True,
            "status": "BLOCK",
            "action": "WAIT",
            "reason": reason,
            "ai_analysis": {
                "confidence": 0.0,
                "market_bias": "NEUTRAL",
                "setup_valid": False,
                "data_quality": "INSUFFICIENT",
                "reason": reason
            },
            "trade_plan": {
                "entry_price": None,
                "stop_loss": None,
                "take_profit": None
            },
            "market": {
                "current_price": current_price,
                "current_price_source": current_price_source,
                "historical_bar_count": historical_bar_count
            },
            "strategy_version": (
                "AI_AUTONOMOUS_V2"
            ),
            "model": self.model,
            "ai_used": ai_used
        }

        if raw_output is not None:
            result["raw_output"] = raw_output

        return result

    def _validate_ai_result(
        self,
        ai_result,
        current_price,
        current_price_source,
        historical_bar_count,
        contract
    ):
        if not isinstance(
            ai_result,
            dict
        ):
            return self._fail_closed_strategy(
                reason="AI output was not a JSON object.",
                current_price=current_price,
                current_price_source=current_price_source,
                historical_bar_count=historical_bar_count
            )

        action = self._normalize_choice(
            ai_result.get(
                "action"
            ),
            {
                "BUY",
                "SELL",
                "WAIT",
                "EXIT"
            },
            "WAIT"
        )

        market_bias = self._normalize_choice(
            ai_result.get(
                "market_bias"
            ),
            {
                "BULLISH",
                "BEARISH",
                "NEUTRAL"
            },
            "NEUTRAL"
        )

        data_quality = self._normalize_choice(
            ai_result.get(
                "data_quality"
            ),
            {
                "GOOD",
                "LIMITED",
                "INSUFFICIENT"
            },
            "INSUFFICIENT"
        )

        confidence = self._clamp_confidence(
            ai_result.get(
                "confidence"
            )
        )

        setup_valid = bool(
            ai_result.get(
                "setup_valid",
                False
            )
        )

        reason = str(
            ai_result.get(
                "reason"
            )
            or "AI did not provide a reason."
        ).strip()

        if not reason:
            reason = "AI did not provide a reason."

        tick_size = contract.get(
            "tickSize"
        )

        entry_price = self._round_to_tick(
            ai_result.get(
                "entry_price"
            ),
            tick_size
        )

        stop_loss = self._round_to_tick(
            ai_result.get(
                "stop_loss"
            ),
            tick_size
        )

        take_profit = self._round_to_tick(
            ai_result.get(
                "take_profit"
            ),
            tick_size
        )

        validation_errors = []

        if action == "WAIT":
            setup_valid = False
            entry_price = None
            stop_loss = None
            take_profit = None

        elif action == "EXIT":
            setup_valid = False
            entry_price = None
            stop_loss = None
            take_profit = None

        elif action in {
            "BUY",
            "SELL"
        }:
            if not setup_valid:
                validation_errors.append(
                    "BUY/SELL requires setup_valid=true."
                )

            if confidence <= 0:
                validation_errors.append(
                    "BUY/SELL requires positive confidence."
                )

            if data_quality == "INSUFFICIENT":
                validation_errors.append(
                    "BUY/SELL is not allowed with insufficient data quality."
                )

            if (
                entry_price is None
                or stop_loss is None
                or take_profit is None
            ):
                validation_errors.append(
                    "BUY/SELL requires entry, stop-loss, and take-profit."
                )

            elif action == "BUY":
                if stop_loss >= entry_price:
                    validation_errors.append(
                        "BUY stop-loss must be below entry."
                    )

                if take_profit <= entry_price:
                    validation_errors.append(
                        "BUY take-profit must be above entry."
                    )

            elif action == "SELL":
                if stop_loss <= entry_price:
                    validation_errors.append(
                        "SELL stop-loss must be above entry."
                    )

                if take_profit >= entry_price:
                    validation_errors.append(
                        "SELL take-profit must be below entry."
                    )

        if validation_errors:
            reason = (
                "AI output failed validation: "
                + "; ".join(
                    validation_errors
                )
            )

            return {
                "success": True,
                "status": "BLOCK",
                "action": "WAIT",
                "reason": reason,
                "ai_analysis": {
                    "confidence": confidence,
                    "market_bias": market_bias,
                    "setup_valid": False,
                    "data_quality": data_quality,
                    "reason": reason,
                    "validation_errors": validation_errors
                },
                "trade_plan": {
                    "entry_price": None,
                    "stop_loss": None,
                    "take_profit": None
                },
                "market": {
                    "current_price": current_price,
                    "current_price_source": current_price_source,
                    "historical_bar_count": historical_bar_count
                },
                "strategy_version": (
                    "AI_AUTONOMOUS_V2"
                ),
                "model": self.model,
                "ai_used": True
            }

        return {
            "action": action,
            "confidence": confidence,
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "reason": reason,
            "market_bias": market_bias,
            "setup_valid": setup_valid,
            "data_quality": data_quality
        }

        try:
            return float(
                value
            )

        except Exception:
            return None

    def _resolve_current_price(
        self,
        quote_data: dict
    ):
        last_price = self._to_float(
            quote_data.get(
                "lastPrice"
            )
        )

        if last_price is not None:
            return last_price, "LAST_PRICE"

        best_bid = self._to_float(
            quote_data.get(
                "bestBid"
            )
        )

        best_ask = self._to_float(
            quote_data.get(
                "bestAsk"
            )
        )

        if (
            best_bid is not None
            and best_ask is not None
        ):
            return (
                (best_bid + best_ask) / 2,
                "BID_ASK_MID"
            )

        if best_bid is not None:
            return best_bid, "BID_ONLY"

        if best_ask is not None:
            return best_ask, "ASK_ONLY"

        return None, "UNAVAILABLE"

    def evaluate_strategy(
        self,
        symbol: str,
        contract: dict,
        quote: dict,
        historical_bars: List[dict],
        depth: dict | None,
        positions: List[dict],
        open_orders: List[dict]
    ) -> Dict[str, Any]:

        # =========================
        # Fail Closed
        # =========================

        if not quote:
            return {
                "success": True,
                "status": "BLOCK",
                "action": "WAIT",
                "reason": (
                    "Realtime market quote is unavailable."
                ),
                "ai_used": False
            }

        if not historical_bars:
            return {
                "success": True,
                "status": "BLOCK",
                "action": "WAIT",
                "reason": (
                    "Historical market data is unavailable."
                ),
                "ai_used": False
            }

        quote_data = quote.get(
            "data",
            quote
        )

        current_price, current_price_source = (
            self._resolve_current_price(
                quote_data
            )
        )

        if current_price is None:
            return {
                "success": True,
                "status": "BLOCK",
                "action": "WAIT",
                "reason": (
                    "Current market price is unavailable."
                ),
                "ai_used": False
            }

        # =========================
        # Prepare Context
        # =========================

        bars = self._prepare_bars(
            historical_bars
        )

        market_depth = None
        non_protective_orders = (
            self._non_protective_open_orders(
                open_orders
            )
        )

        if depth:
            market_depth = depth.get(
                "data",
                depth
            )

        context = {
            "instrument": {
                "symbol": symbol,
                "contract_id": contract.get("id"),
                "contract_name": contract.get("name"),
                "tick_size": contract.get("tickSize"),
                "tick_value": contract.get("tickValue")
            },

            "quote": {
                "current_price": current_price,
                "current_price_source": current_price_source,
                "last_price": quote_data.get(
                    "lastPrice"
                ),
                "best_bid": quote_data.get(
                    "bestBid"
                ),
                "best_ask": quote_data.get(
                    "bestAsk"
                ),
                "open": quote_data.get(
                    "open"
                ),
                "high": quote_data.get(
                    "high"
                ),
                "low": quote_data.get(
                    "low"
                ),
                "volume": quote_data.get(
                    "volume"
                ),
                "change": quote_data.get(
                    "change"
                ),
                "change_percent": quote_data.get(
                    "changePercent"
                ),
                "timestamp": quote_data.get(
                    "lastUpdated"
                )
            },

            "historical_bars": bars,

            "market_depth": market_depth,

            "positions": positions,

            "open_orders": non_protective_orders,

            "protective_orders_count": (
                len(open_orders or [])
                - len(non_protective_orders)
            )
        }

        # =========================
        # AI Instructions
        # =========================

        instructions = """
You are the strategy-analysis component of an autonomous
futures trading system.

Analyze only the supplied market and account-state data.

Your responsibility is to produce a structured trading
candidate, not to bypass risk controls.

The system is running in active evaluation mode. Your job is not
to wait for a perfect textbook setup; it is to identify reasonable,
small-risk opportunities when the supplied data supports a
defensible entry with a defined stop-loss and take-profit. The
deterministic rule, risk, and safety layers will block anything
unsafe after your response.

Possible actions:
BUY
SELL
WAIT
EXIT

Important rules:

1. Do not assume missing information.
2. If data is insufficient or contradictory, return WAIT.
3. Do not increase risk to recover previous losses.
4. If there is already an open position, you may return WAIT,
   EXIT, or an opposite BUY/SELL reversal only when the supplied
   data shows the current position is wrong. You may also return
   a same-direction BUY/SELL only when adding another contract is
   independently justified by a fresh setup.
5. Protective stop-loss/take-profit bracket orders for an existing
   position are not duplicate entries. Non-protective open entry
   orders are duplicate risk and should not be repeated.
6. Use current quote, historical OHLCV structure, and market
   depth when available.
7. Produce entry, stop-loss, and take-profit prices only when
   there is a defensible setup.
8. The output will be independently checked by deterministic
   rule, risk, and safety engines.
9. Never claim guaranteed profit or guaranteed evaluation pass.

Trade-selection guidance:

1. BUY/SELL is acceptable with LIMITED data quality when the
   realtime quote is fresh, recent OHLCV structure is usable, and
   a clear invalidation level exists for the stop-loss.
2. Do not reject a setup solely because market depth is thin,
   one-sided, or unavailable. Treat depth as supporting evidence,
   not a hard requirement, unless it directly contradicts price.
3. Do not reject a setup solely because price has moved. A move is
   tradable if there is a breakout, pullback continuation, reversal
   confirmation, or failed-break structure with clear risk.
4. Avoid true chasing: return WAIT when entry would have no nearby
   invalidation point, the stop would be arbitrary, or reward-to-risk
   is poor.
5. Prefer one-contract, defined-risk trades over indefinite WAIT
   when bias, structure, and risk plan align.
6. Reasonable BUY templates include confirmed breakout continuation,
   pullback holding above support, reclaim of prior resistance, or
   bullish reversal from a session low.
7. Reasonable SELL templates include confirmed breakdown continuation,
   pullback failing below resistance, rejection of prior support, or
   bearish reversal from a session high.
8. For BUY/SELL, use confidence that reflects setup quality. Prefer
   BUY/SELL when confidence is about 0.55 or higher and the stop-loss
   and take-profit are logically placed.
9. Return WAIT when the market is stale, conflicting, range-bound
   without edge, or lacks a valid stop-loss/take-profit plan.

Return JSON only with this exact shape:

{
  "action": "BUY | SELL | WAIT | EXIT",
  "confidence": 0.0,
  "entry_price": null,
  "stop_loss": null,
  "take_profit": null,
  "reason": "",
  "market_bias": "BULLISH | BEARISH | NEUTRAL",
  "setup_valid": false,
  "data_quality": "GOOD | LIMITED | INSUFFICIENT"
}
"""

        # =========================
        # OpenAI
        # =========================

        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=json.dumps(
                context,
                default=str
            )
        )

        raw_output = response.output_text

        try:
            result = json.loads(
                raw_output
            )

        except json.JSONDecodeError:
            return self._fail_closed_strategy(
                reason=(
                    "AI returned invalid structured output."
                ),
                raw_output=raw_output,
                ai_used=True,
                current_price=current_price,
                current_price_source=current_price_source,
                historical_bar_count=len(
                    historical_bars
                )
            )

        # =========================
        # Validate AI Output
        # =========================

        validated_result = self._validate_ai_result(
            ai_result=result,
            current_price=current_price,
            current_price_source=current_price_source,
            historical_bar_count=len(
                historical_bars
            ),
            contract=contract
        )

        if validated_result.get(
            "status"
        ) == "BLOCK":
            return validated_result

        action = validated_result[
            "action"
        ]

        # =========================
        # Duplicate Protection
        # =========================

        if non_protective_orders:
            return self._fail_closed_strategy(
                reason=(
                    "Existing open order detected. "
                    "Duplicate entry blocked."
                ),
                ai_used=True,
                current_price=current_price,
                current_price_source=current_price_source,
                historical_bar_count=len(
                    historical_bars
                )
            )

        # =========================
        # Final AI Strategy Result
        # =========================

        return {
            "success": True,

            "status": (
                "READY"
                if action in {
                    "BUY",
                    "SELL",
                    "EXIT"
                }
                else "WAIT"
            ),

            "action": action,

            "instrument": {
                "symbol": symbol,
                "contract_id": contract.get(
                    "id"
                ),
                "contract_name": contract.get(
                    "name"
                )
            },

            "market": {
                "current_price": current_price,
                "current_price_source": current_price_source,
                "historical_bar_count": len(
                    historical_bars
                )
            },

            "ai_analysis": {
                "confidence": validated_result.get(
                    "confidence"
                ),
                "market_bias": validated_result.get(
                    "market_bias"
                ),
                "setup_valid": validated_result.get(
                    "setup_valid"
                ),
                "data_quality": validated_result.get(
                    "data_quality"
                ),
                "reason": validated_result.get(
                    "reason"
                )
            },

            "trade_plan": {
                "entry_price": validated_result.get(
                    "entry_price"
                ),
                "stop_loss": validated_result.get(
                    "stop_loss"
                ),
                "take_profit": validated_result.get(
                    "take_profit"
                )
            },

            "safety_state": {
                "has_open_position": bool(
                    positions
                ),
                "has_open_orders": bool(
                    non_protective_orders
                ),
                "duplicate_entry_blocked": bool(
                    non_protective_orders
                ),
                "protective_orders_count": (
                    len(open_orders or [])
                    - len(non_protective_orders)
                )
            },

            "strategy_version": (
                "AI_AUTONOMOUS_V2"
            ),

            "model": self.model,

            "ai_used": True
        }
