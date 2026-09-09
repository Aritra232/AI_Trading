from typing import Optional


class RuleService:
    def __init__(self):
        # Current Topstep Trading Combine rules
        self.rule_packs = {
            50000: {
                "starting_balance": 50000,
                "profit_target": 3000,
                "maximum_loss_limit_distance": 2000,
                "maximum_loss_limit_floor": 48000,
                "daily_loss_limit": 2000,
                "max_mini_contracts": 5,
                "max_micro_contracts": 50,
                "consistency_target_percent": 50,
                "evaluation_daily_profit_cap": 1020,
                "evaluation_minimum_trading_days": 3,
                "evaluation_maximum_trading_days": 10
            },

            100000: {
                "starting_balance": 100000,
                "profit_target": 6000,
                "maximum_loss_limit_distance": 3000,
                "maximum_loss_limit_floor": 97000,
                "daily_loss_limit": 3000,
                "max_mini_contracts": 10,
                "max_micro_contracts": 100,
                "consistency_target_percent": 50,
                "evaluation_daily_profit_cap": 1020,
                "evaluation_minimum_trading_days": 3,
                "evaluation_maximum_trading_days": 10
            },

            150000: {
                "starting_balance": 150000,
                "profit_target": 9000,
                "maximum_loss_limit_distance": 4500,
                "maximum_loss_limit_floor": 145500,
                "daily_loss_limit": 4500,
                "max_mini_contracts": 15,
                "max_micro_contracts": 150,
                "consistency_target_percent": 50,
                "evaluation_daily_profit_cap": 1020,
                "evaluation_minimum_trading_days": 3,
                "evaluation_maximum_trading_days": 10
            }
        }

        self.micro_symbols = {
            "MES",
            "MNQ",
            "MYM",
            "M2K"
        }

    def get_rule_pack(
        self,
        account_size: int,
        phase: str = "evaluation",
        enforce_daily_profit_cap: bool = True
    ):
        base_rules = self.rule_packs.get(
            account_size
        )

        if not base_rules:
            raise ValueError(
                f"Unsupported account size: {account_size}"
            )

        phase = phase.lower().strip()

        if phase not in {
            "evaluation",
            "funded",
            "payout"
        }:
            raise ValueError(
                f"Unsupported trading phase: {phase}"
            )

        rules = {
            **base_rules,
            "phase": phase,
            "trading_day_timezone": "America/Chicago",
            "trading_day_start": "17:00 CT",
            "trading_day_end": "15:10 CT next calendar day",
            "daily_profit_cap_enabled": (
                bool(enforce_daily_profit_cap)
                and phase in {
                    "evaluation",
                    "payout"
                }
            ),
            "daily_profit_cap": (
                base_rules[
                    "evaluation_daily_profit_cap"
                ]
                if phase in {
                    "evaluation",
                    "payout"
                }
                else None
            )
        }

        if phase == "funded":
            rules["daily_profit_cap_enabled"] = False
            rules["daily_profit_cap"] = None

        return rules

    def evaluate_rules(
        self,
        account: dict,
        account_size: int,
        symbol: str,
        planned_quantity: int,
        current_mll: Optional[float] = None,
        best_day_profit: Optional[float] = None,
        daily_pnl: Optional[float] = None,
        phase: str = "evaluation",
        enforce_daily_profit_cap: bool = True,
        evaluation_trading_days: Optional[int] = None
    ):
        rules = self.get_rule_pack(
            account_size=account_size,
            phase=phase,
            enforce_daily_profit_cap=(
                enforce_daily_profit_cap
            )
        )

        current_balance = float(
            account.get("balance", 0)
        )

        can_trade = bool(
            account.get("canTrade", False)
        )

        symbol = symbol.upper().strip()

        is_micro = symbol in self.micro_symbols

        if is_micro:
            max_contracts = rules[
                "max_micro_contracts"
            ]
        else:
            max_contracts = rules[
                "max_mini_contracts"
            ]

        violations = []
        warnings = []

        # =========================
        # Trading Permission
        # =========================

        if not can_trade:
            violations.append(
                "Account is currently not allowed to trade."
            )

        # =========================
        # Position Size Rule
        # =========================

        if planned_quantity <= 0:
            violations.append(
                "Planned quantity must be greater than zero."
            )

        if planned_quantity > max_contracts:
            violations.append(
                (
                    f"Planned quantity {planned_quantity} "
                    f"exceeds maximum allowed "
                    f"{max_contracts} contracts."
                )
            )

        # =========================
        # Profit Target
        # =========================

        total_profit = (
            current_balance
            - rules["starting_balance"]
        )

        profit_target_remaining = max(
            rules["profit_target"]
            - total_profit,
            0
        )

        profit_target_reached = (
            total_profit
            >= rules["profit_target"]
        )

        # =========================
        # Evaluation Timeline
        # =========================

        evaluation_day_status = "NOT_APPLICABLE"
        evaluation_trading_days_value = None

        if rules["phase"] == "evaluation":
            minimum_days = rules[
                "evaluation_minimum_trading_days"
            ]

            maximum_days = rules[
                "evaluation_maximum_trading_days"
            ]

            if evaluation_trading_days is None:
                evaluation_day_status = "UNKNOWN"
                warnings.append(
                    (
                        "Evaluation trading-day count is unavailable, "
                        "so the 3 to 10 trading-day completion window "
                        "cannot be fully verified."
                    )
                )

            else:
                evaluation_trading_days_value = int(
                    evaluation_trading_days
                )

                if evaluation_trading_days_value < 0:
                    violations.append(
                        "Evaluation trading-day count cannot be negative."
                    )

                elif evaluation_trading_days_value < minimum_days:
                    evaluation_day_status = "BELOW_MINIMUM"

                    if profit_target_reached:
                        warnings.append(
                            (
                                "Evaluation profit target is reached, "
                                "but the minimum 3 trading days have "
                                "not been completed yet."
                            )
                        )

                elif evaluation_trading_days_value > maximum_days:
                    evaluation_day_status = "ABOVE_MAXIMUM"

                    if not profit_target_reached:
                        violations.append(
                            (
                                "Evaluation maximum 10 trading-day "
                                "window has passed without reaching "
                                "the profit target."
                            )
                        )

                    else:
                        warnings.append(
                            (
                                "Evaluation profit target is reached, "
                                "but the reported trading-day count is "
                                "above the 10-day target window."
                            )
                        )

                else:
                    evaluation_day_status = "IN_WINDOW"

                if (
                    profit_target_reached
                    and evaluation_trading_days_value is not None
                    and evaluation_trading_days_value >= minimum_days
                ):
                    violations.append(
                        (
                            "Evaluation profit target has been reached "
                            "after the required minimum trading days. "
                            "New entries are blocked to protect the pass."
                        )
                    )

        # =========================
        # Evaluation Daily Profit Cap
        # =========================

        daily_profit_cap = rules.get(
            "daily_profit_cap"
        )

        daily_profit_cap_reached = False

        if rules.get(
            "daily_profit_cap_enabled"
        ):
            if daily_pnl is None:
                warnings.append(
                    (
                        "Evaluation daily profit cap is enabled "
                        "but trading-day P&L is unavailable."
                    )
                )

            else:
                daily_profit_cap_reached = (
                    daily_pnl
                    >= float(
                        daily_profit_cap
                    )
                )

                if daily_profit_cap_reached:
                    violations.append(
                        (
                            "Trading-day profit cap "
                            f"${daily_profit_cap:.2f} has been "
                            "reached. New entries are blocked "
                            "and open positions must be closed."
                        )
                    )

        # =========================
        # Maximum Loss Limit
        # =========================

        mll_remaining = None

        if current_mll is not None:
            mll_remaining = (
                current_balance
                - current_mll
            )

            if current_balance <= current_mll:
                violations.append(
                    "Maximum Loss Limit has been reached or breached."
                )

        else:
            warnings.append(
                (
                    "Current Maximum Loss Limit value was not "
                    "provided, so exact MLL distance cannot "
                    "be verified."
                )
            )

        # =========================
        # Consistency Target
        # =========================

        consistency_percent = None
        consistency_ok = None

        if (
            best_day_profit is not None
            and total_profit > 0
        ):
            consistency_percent = (
                best_day_profit
                / total_profit
            ) * 100

            consistency_ok = (
                consistency_percent
                <= rules[
                    "consistency_target_percent"
                ]
            )

            if not consistency_ok:
                warnings.append(
                    (
                        "Best trading day currently exceeds "
                        "the 50% consistency target."
                    )
                )

        # =========================
        # Final Rule Status
        # =========================

        if violations:
            status = "BLOCK"

        elif warnings:
            status = "REVIEW"

        else:
            status = "ALLOW"

        return {
            "success": True,

            "status": status,

            "account_size": account_size,

            "phase": rules[
                "phase"
            ],

            "symbol": symbol,

            "instrument_type": (
                "micro"
                if is_micro
                else "mini_or_other"
            ),

            "planned_quantity": planned_quantity,

            "rules": rules,

            "trading_day": {
                "timezone": rules[
                    "trading_day_timezone"
                ],
                "start": rules[
                    "trading_day_start"
                ],
                "end": rules[
                    "trading_day_end"
                ]
            },

            "account_state": {
                "balance": current_balance,
                "can_trade": can_trade
            },

            "profit_target": {
                "current_profit": total_profit,
                "target": rules[
                    "profit_target"
                ],
                "remaining": profit_target_remaining,
                "reached": profit_target_reached
            },

            "evaluation_progress": {
                "trading_days": evaluation_trading_days_value,
                "minimum_trading_days": rules.get(
                    "evaluation_minimum_trading_days"
                ),
                "maximum_trading_days": rules.get(
                    "evaluation_maximum_trading_days"
                ),
                "status": evaluation_day_status,
                "target_reached": profit_target_reached
            },

            "daily_profit_cap": {
                "enabled": rules.get(
                    "daily_profit_cap_enabled"
                ),
                "current_trading_day_pnl": daily_pnl,
                "cap": daily_profit_cap,
                "reached": daily_profit_cap_reached
            },

            "maximum_loss_limit": {
                "current_mll": current_mll,
                "floor": rules.get(
                    "maximum_loss_limit_floor"
                ),
                "remaining_distance": mll_remaining
            },

            "consistency": {
                "best_day_profit": best_day_profit,
                "current_percent": consistency_percent,
                "target_percent": rules[
                    "consistency_target_percent"
                ],
                "within_target": consistency_ok
            },

            "position_limit": {
                "maximum_allowed": max_contracts,
                "planned": planned_quantity,
                "within_limit": (
                    planned_quantity
                    <= max_contracts
                )
            },

            "violations": violations,

            "warnings": warnings
        }
