from typing import Optional


class RuleService:
    def __init__(self):
        # Current Topstep Trading Combine rules
        self.rule_packs = {
            50000: {
                "starting_balance": 50000,
                "profit_target": 3000,
                "maximum_loss_limit_distance": 2000,
                "max_mini_contracts": 5,
                "max_micro_contracts": 50,
                "consistency_target_percent": 50
            },

            100000: {
                "starting_balance": 100000,
                "profit_target": 6000,
                "maximum_loss_limit_distance": 3000,
                "max_mini_contracts": 10,
                "max_micro_contracts": 100,
                "consistency_target_percent": 50
            },

            150000: {
                "starting_balance": 150000,
                "profit_target": 9000,
                "maximum_loss_limit_distance": 4500,
                "max_mini_contracts": 15,
                "max_micro_contracts": 150,
                "consistency_target_percent": 50
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
        account_size: int
    ):
        rules = self.rule_packs.get(account_size)

        if not rules:
            raise ValueError(
                f"Unsupported account size: {account_size}"
            )

        return rules

    def evaluate_rules(
        self,
        account: dict,
        account_size: int,
        symbol: str,
        planned_quantity: int,
        current_mll: Optional[float] = None,
        best_day_profit: Optional[float] = None
    ):
        rules = self.get_rule_pack(account_size)

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

            "symbol": symbol,

            "instrument_type": (
                "micro"
                if is_micro
                else "mini_or_other"
            ),

            "planned_quantity": planned_quantity,

            "rules": rules,

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

            "maximum_loss_limit": {
                "current_mll": current_mll,
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