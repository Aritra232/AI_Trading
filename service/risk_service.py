class RiskService:
    def evaluate_risk(
        self,
        account: dict,
        contract: dict,
        entry_price: float,
        stop_price: float,
        planned_quantity: int,
        current_mll: float | None = None,
        max_risk_per_trade: float | None = None
    ):
        balance = float(
            account.get("balance", 0)
        )

        can_trade = bool(
            account.get("canTrade", False)
        )

        tick_size = float(
            contract.get("tickSize", 0)
        )

        tick_value = float(
            contract.get("tickValue", 0)
        )

        violations = []
        warnings = []

        # =========================
        # Basic Validation
        # =========================

        if not can_trade:
            violations.append(
                "Account is currently not allowed to trade."
            )

        if planned_quantity <= 0:
            violations.append(
                "Planned quantity must be greater than zero."
            )

        if tick_size <= 0:
            violations.append(
                "Invalid contract tick size."
            )

        if tick_value <= 0:
            violations.append(
                "Invalid contract tick value."
            )

        if entry_price <= 0:
            violations.append(
                "Entry price must be greater than zero."
            )

        if stop_price <= 0:
            violations.append(
                "Stop price must be greater than zero."
            )

        # =========================
        # Stop Distance
        # =========================

        price_distance = abs(
            entry_price - stop_price
        )

        number_of_ticks = 0

        if tick_size > 0:
            number_of_ticks = (
                price_distance / tick_size
            )

        # =========================
        # Dollar Risk
        # =========================

        risk_per_contract = (
            number_of_ticks
            * tick_value
        )

        total_trade_risk = (
            risk_per_contract
            * planned_quantity
        )

        # =========================
        # Maximum Loss Limit
        # =========================

        remaining_mll = None

        if current_mll is not None:
            remaining_mll = (
                balance - current_mll
            )

            if remaining_mll <= 0:
                violations.append(
                    "No Maximum Loss Limit capacity remaining."
                )

            elif total_trade_risk >= remaining_mll:
                violations.append(
                    (
                        f"Trade risk ${total_trade_risk:.2f} "
                        f"is greater than or equal to "
                        f"remaining MLL capacity "
                        f"${remaining_mll:.2f}."
                    )
                )

        else:
            warnings.append(
                "Current Maximum Loss Limit was not provided."
            )

        # =========================
        # Optional Per-Trade Limit
        # =========================

        if max_risk_per_trade is not None:

            if total_trade_risk > max_risk_per_trade:
                violations.append(
                    (
                        f"Trade risk ${total_trade_risk:.2f} "
                        f"exceeds per-trade risk limit "
                        f"${max_risk_per_trade:.2f}."
                    )
                )

        # =========================
        # Maximum Safe Quantity
        # =========================

        max_quantity_by_mll = None

        if (
            remaining_mll is not None
            and remaining_mll > 0
            and risk_per_contract > 0
        ):
            max_quantity_by_mll = int(
                remaining_mll
                // risk_per_contract
            )

        max_quantity_by_trade_limit = None

        if (
            max_risk_per_trade is not None
            and max_risk_per_trade > 0
            and risk_per_contract > 0
        ):
            max_quantity_by_trade_limit = int(
                max_risk_per_trade
                // risk_per_contract
            )

        # =========================
        # Final Status
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

            "contract": {
                "id": contract.get("id"),
                "name": contract.get("name"),
                "tick_size": tick_size,
                "tick_value": tick_value
            },

            "trade": {
                "entry_price": entry_price,
                "stop_price": stop_price,
                "planned_quantity": planned_quantity
            },

            "risk_calculation": {
                "price_distance": price_distance,
                "number_of_ticks": number_of_ticks,
                "risk_per_contract": round(
                    risk_per_contract,
                    2
                ),
                "total_trade_risk": round(
                    total_trade_risk,
                    2
                )
            },

            "account_risk": {
                "balance": balance,
                "current_mll": current_mll,
                "remaining_mll": remaining_mll
            },

            "limits": {
                "max_risk_per_trade": (
                    max_risk_per_trade
                ),
                "max_quantity_by_mll": (
                    max_quantity_by_mll
                ),
                "max_quantity_by_trade_limit": (
                    max_quantity_by_trade_limit
                )
            },

            "violations": violations,

            "warnings": warnings
        }