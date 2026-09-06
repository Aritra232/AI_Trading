from datetime import datetime, timezone
from typing import Optional


class SafetyService:
    def _parse_datetime(
        self,
        value: Optional[str]
    ) -> Optional[datetime]:

        if not value:
            return None

        try:
            value = value.replace(
                "Z",
                "+00:00"
            )

            return datetime.fromisoformat(
                value
            )

        except Exception:
            return None

    def _get_quote_age_seconds(
        self,
        quote: dict
    ) -> Optional[float]:

        if not quote:
            return None

        quote_data = quote.get(
            "data",
            quote
        )

        timestamp = quote_data.get(
            "lastUpdated"
        )

        parsed = self._parse_datetime(
            timestamp
        )

        if parsed is None:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        now = datetime.now(
            timezone.utc
        )

        return max(
            (
                now - parsed
            ).total_seconds(),
            0
        )

    def _get_total_position_quantity(
        self,
        positions: list
    ) -> int:

        total = 0

        for position in positions or []:

            quantity = (
                position.get("size")
                or position.get("quantity")
                or position.get("qty")
                or 0
            )

            try:
                total += abs(
                    int(quantity)
                )
            except Exception:
                pass

        return total

    def evaluate_safety(
        self,
        final_decision: dict,
        trading_state: dict,

        planned_quantity: int,

        kill_switch: bool = False,

        daily_pnl: Optional[float] = None,
        daily_loss_limit: Optional[float] = None,

        current_mll: Optional[float] = None,

        max_position_quantity: Optional[int] = None,

        max_quote_age_seconds: int = 30
    ):

        blocks = []
        warnings = []

        # =========================
        # Final Decision
        # =========================

        final_status = str(
            final_decision.get(
                "final_status",
                "BLOCK"
            )
        ).upper()

        action = str(
            final_decision.get(
                "action",
                "WAIT"
            )
        ).upper()

        decision_execution_allowed = bool(
            final_decision.get(
                "execution_allowed",
                False
            )
        )

        if final_status != "ALLOW":
            blocks.append(
                (
                    "Final Decision Engine has "
                    "not approved execution."
                )
            )

        if not decision_execution_allowed:
            blocks.append(
                (
                    "Final Decision Engine returned "
                    "execution_allowed=false."
                )
            )

        if action not in {
            "BUY",
            "SELL",
            "EXIT"
        }:
            blocks.append(
                f"Action {action} is not executable."
            )

        # =========================
        # Emergency Kill Switch
        # =========================

        if kill_switch:
            blocks.append(
                "Emergency kill switch is enabled."
            )

        # =========================
        # Trading State
        # =========================

        account = trading_state.get(
            "account"
        )

        market = trading_state.get(
            "market",
            {}
        )

        positions = trading_state.get(
            "positions",
            []
        )

        open_orders = trading_state.get(
            "open_orders",
            []
        )

        if not account:
            blocks.append(
                "Account state is unavailable."
            )

        # =========================
        # Account Permission
        # =========================

        if account:

            if not account.get(
                "canTrade",
                False
            ):
                blocks.append(
                    (
                        "Topstep account is currently "
                        "not allowed to trade."
                    )
                )

        # =========================
        # Realtime Quote
        # =========================

        quote = market.get(
            "quote"
        )

        if not quote:

            blocks.append(
                "Realtime quote is unavailable."
            )

            quote_age_seconds = None

        else:

            quote_age_seconds = (
                self._get_quote_age_seconds(
                    quote
                )
            )

            if quote_age_seconds is None:

                blocks.append(
                    (
                        "Realtime quote timestamp "
                        "cannot be validated."
                    )
                )

            elif (
                quote_age_seconds
                > max_quote_age_seconds
            ):

                blocks.append(
                    (
                        f"Realtime quote is stale. "
                        f"Age={quote_age_seconds:.2f}s, "
                        f"maximum allowed="
                        f"{max_quote_age_seconds}s."
                    )
                )

        # =========================
        # Duplicate Order Protection
        # =========================

        if (
            action in {
                "BUY",
                "SELL"
            }
            and len(open_orders) > 0
        ):

            blocks.append(
                (
                    "Existing open order detected. "
                    "Duplicate entry is blocked."
                )
            )

        # =========================
        # Position Limit
        # =========================

        current_position_quantity = (
            self._get_total_position_quantity(
                positions
            )
        )

        projected_position_quantity = (
            current_position_quantity
            + planned_quantity
        )

        if (
            action in {
                "BUY",
                "SELL"
            }
            and max_position_quantity
            is not None
        ):

            if (
                projected_position_quantity
                > max_position_quantity
            ):

                blocks.append(
                    (
                        f"Projected position quantity "
                        f"{projected_position_quantity} "
                        f"exceeds safety limit "
                        f"{max_position_quantity}."
                    )
                )

        # =========================
        # Daily Loss Lockout
        # =========================

        if (
            daily_pnl is not None
            and daily_loss_limit is not None
        ):

            if (
                daily_pnl
                <= -abs(
                    daily_loss_limit
                )
            ):

                blocks.append(
                    (
                        "Daily loss limit reached. "
                        "Trading is locked."
                    )
                )

        elif daily_loss_limit is not None:

            warnings.append(
                (
                    "Daily loss limit is configured "
                    "but daily P&L is unavailable."
                )
            )

        # =========================
        # Maximum Loss Limit
        # =========================

        remaining_mll = None

        if (
            current_mll is not None
            and account
        ):

            balance = float(
                account.get(
                    "balance",
                    0
                )
            )

            remaining_mll = (
                balance
                - current_mll
            )

            if remaining_mll <= 0:

                blocks.append(
                    (
                        "Maximum Loss Limit has "
                        "been reached."
                    )
                )

        else:

            warnings.append(
                (
                    "Current Maximum Loss Limit "
                    "was not provided."
                )
            )

        # =========================
        # Final Safety Result
        # =========================

        if blocks:

            safety_status = "BLOCK"

            safe_to_execute = False

        elif warnings:

            safety_status = "REVIEW"

            safe_to_execute = False

        else:

            safety_status = "PASS"

            safe_to_execute = True

        return {
            "success": True,

            "safety_status": (
                safety_status
            ),

            "safe_to_execute": (
                safe_to_execute
            ),

            "action": action,

            "kill_switch": (
                kill_switch
            ),

            "market_safety": {
                "quote_available": (
                    quote is not None
                ),
                "quote_age_seconds": (
                    quote_age_seconds
                ),
                "max_quote_age_seconds": (
                    max_quote_age_seconds
                )
            },

            "position_safety": {
                "current_quantity": (
                    current_position_quantity
                ),
                "planned_quantity": (
                    planned_quantity
                ),
                "projected_quantity": (
                    projected_position_quantity
                ),
                "max_position_quantity": (
                    max_position_quantity
                )
            },

            "account_safety": {
                "daily_pnl": (
                    daily_pnl
                ),
                "daily_loss_limit": (
                    daily_loss_limit
                ),
                "current_mll": (
                    current_mll
                ),
                "remaining_mll": (
                    remaining_mll
                )
            },

            "blocks": blocks,

            "warnings": warnings,

            "safety_version": (
                "SAFETY_V1"
            )
        }