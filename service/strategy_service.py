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

            "open_orders": open_orders
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

Possible actions:
BUY
SELL
WAIT
EXIT

Important rules:

1. Do not assume missing information.
2. If data is insufficient or contradictory, return WAIT.
3. Do not increase risk to recover previous losses.
4. If there is already an open position, determine whether
   the appropriate action is HOLD/WAIT or EXIT. Do not create
   a duplicate entry.
5. If there is an existing open order, do not create another
   duplicate entry.
6. Use current quote, historical OHLCV structure, and market
   depth when available.
7. Produce entry, stop-loss, and take-profit prices only when
   there is a defensible setup.
8. The output will be independently checked by deterministic
   rule, risk, and safety engines.
9. Never claim guaranteed profit or guaranteed evaluation pass.

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

        if open_orders:
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
                    open_orders
                ),
                "duplicate_entry_blocked": bool(
                    open_orders
                )
            },

            "strategy_version": (
                "AI_AUTONOMOUS_V2"
            ),

            "model": self.model,

            "ai_used": True
        }
