import json
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()


class StrategyService:
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")

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

        current_price = quote_data.get(
            "lastPrice"
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
            return {
                "success": True,
                "status": "BLOCK",
                "action": "WAIT",
                "reason": (
                    "AI returned invalid structured output."
                ),
                "raw_output": raw_output,
                "ai_used": True
            }

        # =========================
        # Validate AI Output
        # =========================

        allowed_actions = {
            "BUY",
            "SELL",
            "WAIT",
            "EXIT"
        }

        action = str(
            result.get(
                "action",
                "WAIT"
            )
        ).upper()

        if action not in allowed_actions:
            action = "WAIT"

        setup_valid = bool(
            result.get(
                "setup_valid",
                False
            )
        )

        if not setup_valid:
            action = "WAIT"

        entry_price = result.get(
            "entry_price"
        )

        stop_loss = result.get(
            "stop_loss"
        )

        take_profit = result.get(
            "take_profit"
        )

        # BUY / SELL must have risk levels
        if action in {
            "BUY",
            "SELL"
        }:
            if (
                entry_price is None
                or stop_loss is None
            ):
                action = "WAIT"

        # =========================
        # Duplicate Protection
        # =========================

        if open_orders:
            action = "WAIT"

            result["reason"] = (
                "Existing open order detected. "
                "Duplicate entry blocked."
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
                "historical_bar_count": len(
                    historical_bars
                )
            },

            "ai_analysis": {
                "confidence": result.get(
                    "confidence"
                ),
                "market_bias": result.get(
                    "market_bias"
                ),
                "setup_valid": result.get(
                    "setup_valid"
                ),
                "data_quality": result.get(
                    "data_quality"
                ),
                "reason": result.get(
                    "reason"
                )
            },

            "trade_plan": {
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit
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
                "AI_AUTONOMOUS_V1"
            ),

            "model": self.model,

            "ai_used": True
        }
