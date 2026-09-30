class DecisionService:
    def evaluate_decision(
        self,
        strategy_result: dict,
        rule_result: dict | None = None,
        risk_result: dict | None = None,
        planned_quantity: int = 1
    ):
        reasons = []

        # =========================
        # Validate Strategy Result
        # =========================

        if not strategy_result:
            return {
                "success": True,
                "final_status": "BLOCK",
                "action": "WAIT",
                "execution_allowed": False,
                "reason": "Strategy result is missing.",
                "decision_version": "FINAL_DECISION_V1"
            }

        action = str(
            strategy_result.get(
                "action",
                "WAIT"
            )
        ).upper()

        strategy_status = str(
            strategy_result.get(
                "status",
                "WAIT"
            )
        ).upper()

        # =========================
        # AI Says WAIT
        # =========================

        if action == "WAIT":
            return {
                "success": True,

                "final_status": "WAIT",

                "action": "WAIT",

                "execution_allowed": False,

                "strategy": strategy_result,

                "rule": rule_result,

                "risk": risk_result,

                "reason": (
                    "AI strategy did not identify "
                    "a valid trade setup."
                ),

                "decision_version": (
                    "FINAL_DECISION_V1"
                )
            }

        # =========================
        # AI Says EXIT
        # =========================

        if action == "EXIT":
            return {
                "success": True,

                "final_status": "ALLOW",

                "action": "EXIT",

                "execution_allowed": True,

                "planned_quantity": (
                    planned_quantity
                ),

                "strategy": strategy_result,

                "rule": rule_result,

                "risk": risk_result,

                "reason": (
                    "AI strategy requested an exit."
                ),

                "decision_version": (
                    "FINAL_DECISION_V1"
                )
            }

        # =========================
        # Validate BUY / SELL
        # =========================

        if action not in {
            "BUY",
            "SELL"
        }:
            return {
                "success": True,

                "final_status": "BLOCK",

                "action": "WAIT",

                "execution_allowed": False,

                "reason": (
                    f"Unsupported strategy action: "
                    f"{action}"
                ),

                "decision_version": (
                    "FINAL_DECISION_V1"
                )
            }

        # =========================
        # Strategy Must Be Ready
        # =========================

        if strategy_status == "BLOCK":
            reasons.append(
                "Strategy engine blocked the trade."
            )

        elif strategy_status not in {
            "READY",
            "ALLOW"
        }:
            reasons.append(
                (
                    "Strategy engine has not marked "
                    "the trade as ready."
                )
            )

        # =========================
        # Rule Result Required
        # =========================

        if not rule_result:
            reasons.append(
                "Rule-engine result is missing."
            )

        # =========================
        # Risk Result Required
        # =========================

        if not risk_result:
            reasons.append(
                "Risk-engine result is missing."
            )

        # =========================
        # Immediate Missing Data Block
        # =========================

        if (
            not rule_result
            or not risk_result
        ):
            return {
                "success": True,

                "final_status": "BLOCK",

                "action": "WAIT",

                "execution_allowed": False,

                "planned_quantity": planned_quantity,

                "strategy": strategy_result,

                "rule": rule_result,

                "risk": risk_result,

                "reasons": reasons,

                "decision_version": (
                    "FINAL_DECISION_V1"
                )
            }

        rule_status = str(
            rule_result.get(
                "status",
                "BLOCK"
            )
        ).upper()

        risk_status = str(
            risk_result.get(
                "status",
                "BLOCK"
            )
        ).upper()

        # =========================
        # Check Rule Engine
        # =========================

        if rule_status == "BLOCK":
            reasons.append(
                "Rule engine blocked the trade."
            )

        elif rule_status == "REVIEW":
            reasons.append(
                "Rule engine requires review."
            )

        # =========================
        # Check Risk Engine
        # =========================

        if risk_status == "BLOCK":
            reasons.append(
                "Risk engine blocked the trade."
            )

        elif risk_status == "REVIEW":
            reasons.append(
                "Risk engine requires review."
            )

        # =========================
        # Final Decision
        # =========================

        if (
            strategy_status == "BLOCK"
            or rule_status == "BLOCK"
            or risk_status == "BLOCK"
        ):
            final_status = "BLOCK"

            final_action = "WAIT"

            execution_allowed = False

        elif (
            strategy_status not in {
                "READY",
                "ALLOW"
            }
            or rule_status == "REVIEW"
            or risk_status == "REVIEW"
        ):
            final_status = "WAIT"

            final_action = "WAIT"

            execution_allowed = False

        else:
            final_status = "ALLOW"

            final_action = action

            execution_allowed = True

            reasons.append(
                (
                    "AI strategy, rule engine, and "
                    "risk engine all approved the trade."
                )
            )

        # =========================
        # Final Output
        # =========================

        return {
            "success": True,

            "final_status": final_status,

            "action": final_action,

            "execution_allowed": (
                execution_allowed
            ),

            "planned_quantity": (
                planned_quantity
            ),

            "strategy": {
                "status": strategy_result.get(
                    "status"
                ),

                "action": strategy_result.get(
                    "action"
                ),

                "ai_analysis": strategy_result.get(
                    "ai_analysis"
                ),

                "trade_plan": strategy_result.get(
                    "trade_plan"
                )
            },

            "rule": {
                "status": rule_status,

                "violations": rule_result.get(
                    "violations",
                    []
                ),

                "warnings": rule_result.get(
                    "warnings",
                    []
                )
            },

            "risk": {
                "status": risk_status,

                "risk_calculation": (
                    risk_result.get(
                        "risk_calculation"
                    )
                ),

                "violations": risk_result.get(
                    "violations",
                    []
                ),

                "warnings": risk_result.get(
                    "warnings",
                    []
                )
            },

            "reasons": reasons,

            "decision_version": (
                "FINAL_DECISION_V1"
            )
        }
