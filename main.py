from fastapi import FastAPI, HTTPException

from service.topstep_service import TopstepService
from service.account_service import AccountService
from service.contract_service import ContractService
from service.history_service import HistoryService
from service.position_service import PositionService
from service.order_service import OrderService
from service.trade_service import TradeService
from service.realtime_service import RealtimeService
from service.trading_state_service import TradingStateService
from service.rule_service import RuleService
from service.risk_service import RiskService
from service.strategy_service import StrategyService
from service.decision_service import DecisionService
from service.safety_service import SafetyService

app = FastAPI(
    title="TopstepX API Test",
    version="1.4.0"
)


topstep_service = TopstepService()

account_service = AccountService()

contract_service = ContractService()

history_service = HistoryService()

position_service = PositionService()

order_service = OrderService()

trade_service = TradeService()

realtime_service = RealtimeService(
    topstep_service=topstep_service
)

trading_state_service = TradingStateService(
    account_service=account_service,
    contract_service=contract_service,
    history_service=history_service,
    position_service=position_service,
    order_service=order_service,
    realtime_service=realtime_service
)

rule_service = RuleService()

risk_service = RiskService()

strategy_service = StrategyService()

decision_service = DecisionService()

safety_service = SafetyService()

# =========================
# System
# =========================

@app.get(
    "/health",
    tags=["System"]
)
def health():
    return {
        "status": "ok"
    }


# =========================
# Authentication
# =========================

@app.get(
    "/topstep/auth-test",
    tags=["Authentication"]
)
async def auth_test():
    try:
        result = await topstep_service.authenticate()

        return {
            "success": True,
            "message": "Authentication succeeded",
            "token_received": bool(
                result.get("token")
            )
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


# =========================
# Accounts
# =========================

@app.get(
    "/topstep/accounts",
    tags=["Accounts"]
)
async def get_accounts():
    try:
        return await account_service.get_accounts()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


# =========================
# Contracts
# =========================

@app.get(
    "/topstep/contracts",
    tags=["Contracts"]
)
async def search_contracts(
    search_text: str = "MES",
    live: bool = False
):
    try:
        return await contract_service.search_contracts(
            search_text=search_text,
            live=live
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


# =========================
# Market Data
# =========================

@app.get(
    "/topstep/history",
    tags=["Market Data"]
)
async def get_history(
    contract_id: str,
    start_time: str,
    end_time: str,
    unit: int = 2,
    unit_number: int = 5,
    limit: int = 100,
    live: bool = False
):
    try:
        return await history_service.get_bars(
            contract_id=contract_id,
            start_time=start_time,
            end_time=end_time,
            unit=unit,
            unit_number=unit_number,
            limit=limit,
            live=live
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


# =========================
# Positions
# =========================

@app.get(
    "/topstep/positions",
    tags=["Positions"]
)
async def get_positions(
    account_id: int
):
    try:
        return await position_service.get_open_positions(
            account_id=account_id
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


# =========================
# Orders
# =========================

@app.get(
    "/topstep/orders/open",
    tags=["Orders"]
)
async def get_open_orders(
    account_id: int
):
    try:
        return await order_service.get_open_orders(
            account_id=account_id
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.get(
    "/topstep/orders",
    tags=["Orders"]
)
async def get_orders(
    account_id: int,
    start_timestamp: str,
    end_timestamp: str | None = None
):
    try:
        return await order_service.get_orders(
            account_id=account_id,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


# =========================
# Trades
# =========================

@app.get(
    "/topstep/trades",
    tags=["Trades"]
)
async def get_trades(
    account_id: int,
    start_timestamp: str,
    end_timestamp: str | None = None
):
    try:
        return await trade_service.get_trades(
            account_id=account_id,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


# =========================
# Realtime
# =========================

@app.post(
    "/topstep/realtime/user/start",
    tags=["Realtime"]
)
async def start_user_realtime(
    account_id: int
):
    try:
        return await realtime_service.start_user_hub(
            account_id=account_id
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.post(
    "/topstep/realtime/market/start",
    tags=["Realtime"]
)
async def start_market_realtime(
    contract_id: str
):
    try:
        return await realtime_service.start_market_hub(
            contract_id=contract_id
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.get(
    "/topstep/realtime/latest",
    tags=["Realtime"]
)
def get_latest_realtime_data():
    return realtime_service.get_latest_data()


@app.post(
    "/topstep/realtime/stop",
    tags=["Realtime"]
)
def stop_realtime():
    return realtime_service.stop_all()


# =========================
# Trading State
# =========================

@app.get(
    "/topstep/trading-state",
    tags=["Trading State"]
)
async def get_trading_state(
    account_id: int,
    contract_id: str,
    search_text: str = "MES",
    live: bool = False,
    start_time: str | None = None,
    end_time: str | None = None,
    unit: int = 2,
    unit_number: int = 5,
    limit: int = 100
):
    try:
        return await trading_state_service.get_trading_state(
            account_id=account_id,
            contract_id=contract_id,
            search_text=search_text,
            live=live,
            start_time=start_time,
            end_time=end_time,
            unit=unit,
            unit_number=unit_number,
            limit=limit
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


# =========================
# Rule Engine
# =========================

@app.get(
    "/topstep/rules/evaluate",
    tags=["Rule Engine"]
)
async def evaluate_rules(
    account_id: int,
    account_size: int = 50000,
    symbol: str = "MES",
    planned_quantity: int = 1,
    current_mll: float | None = None,
    best_day_profit: float | None = None
):
    try:
        accounts_result = (
            await account_service.get_accounts()
        )

        selected_account = None

        for account in accounts_result.get(
            "accounts",
            []
        ):
            if account.get("id") == account_id:
                selected_account = account
                break

        if selected_account is None:
            raise ValueError(
                f"Account {account_id} not found."
            )

        return rule_service.evaluate_rules(
            account=selected_account,
            account_size=account_size,
            symbol=symbol,
            planned_quantity=planned_quantity,
            current_mll=current_mll,
            best_day_profit=best_day_profit
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


# =========================
# Risk Engine
# =========================

@app.get(
    "/topstep/risk/evaluate",
    tags=["Risk Engine"]
)
async def evaluate_risk(
    account_id: int,
    contract_id: str,
    search_text: str = "MES",
    entry_price: float = 7715,
    stop_price: float = 7710,
    planned_quantity: int = 1,
    current_mll: float | None = None,
    max_risk_per_trade: float | None = None,
    live: bool = False
):
    try:
        # =========================
        # Fetch Account
        # =========================

        accounts_result = (
            await account_service.get_accounts()
        )

        selected_account = None

        for account in accounts_result.get(
            "accounts",
            []
        ):
            if account.get("id") == account_id:
                selected_account = account
                break

        if selected_account is None:
            raise ValueError(
                f"Account {account_id} not found."
            )

        # =========================
        # Fetch Contract
        # =========================

        contracts_result = (
            await contract_service.search_contracts(
                search_text=search_text,
                live=live
            )
        )

        selected_contract = None

        for contract in contracts_result.get(
            "contracts",
            []
        ):
            if contract.get("id") == contract_id:
                selected_contract = contract
                break

        if selected_contract is None:
            raise ValueError(
                f"Contract {contract_id} not found."
            )

        # =========================
        # Evaluate Risk
        # =========================

        return risk_service.evaluate_risk(
            account=selected_account,
            contract=selected_contract,
            entry_price=entry_price,
            stop_price=stop_price,
            planned_quantity=planned_quantity,
            current_mll=current_mll,
            max_risk_per_trade=max_risk_per_trade
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


# =========================
# AI Strategy Engine
# =========================

@app.get(
    "/topstep/strategy/evaluate",
    tags=["AI Strategy Engine"]
)
async def evaluate_strategy(
    account_id: int,
    contract_id: str,
    symbol: str = "MES",
    search_text: str = "MES",
    start_time: str | None = None,
    end_time: str | None = None,
    live: bool = False
):
    try:

        state = await trading_state_service.get_trading_state(
            account_id=account_id,
            contract_id=contract_id,
            search_text=search_text,
            live=live,
            start_time=start_time,
            end_time=end_time,
            unit=2,
            unit_number=5,
            limit=100
        )

        contract = state.get(
            "contract"
        )

        market = state.get(
            "market",
            {}
        )

        positions = state.get(
            "positions",
            []
        )

        open_orders = state.get(
            "open_orders",
            []
        )

        if contract is None:
            raise ValueError(
                "Contract information is unavailable."
            )

        return strategy_service.evaluate_strategy(
            symbol=symbol,
            contract=contract,
            quote=market.get(
                "quote"
            ),
            historical_bars=market.get(
                "historical_bars"
            ) or [],
            depth=market.get(
                "depth"
            ),
            positions=positions,
            open_orders=open_orders
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )



# =========================
# Final Decision Engine
# =========================

@app.get(
    "/topstep/decision/evaluate",
    tags=["Final Decision Engine"]
)
async def evaluate_final_decision(
    account_id: int,
    contract_id: str,

    account_size: int = 50000,

    symbol: str = "MES",
    search_text: str = "MES",

    planned_quantity: int = 1,

    current_mll: float | None = None,

    best_day_profit: float | None = None,

    max_risk_per_trade: float | None = None,

    start_time: str | None = None,
    end_time: str | None = None,

    live: bool = False
):
    try:

        # =========================
        # 1. Get Trading State
        # =========================

        state = (
            await trading_state_service.get_trading_state(
                account_id=account_id,
                contract_id=contract_id,
                search_text=search_text,
                live=live,
                start_time=start_time,
                end_time=end_time,
                unit=2,
                unit_number=5,
                limit=100
            )
        )

        account = state.get(
            "account"
        )

        contract = state.get(
            "contract"
        )

        market = state.get(
            "market",
            {}
        )

        positions = state.get(
            "positions",
            []
        )

        open_orders = state.get(
            "open_orders",
            []
        )

        if account is None:
            raise ValueError(
                "Account information is unavailable."
            )

        if contract is None:
            raise ValueError(
                "Contract information is unavailable."
            )

        # =========================
        # 2. AI Strategy Analysis
        # =========================

        strategy_result = (
            strategy_service.evaluate_strategy(
                symbol=symbol,
                contract=contract,
                quote=market.get(
                    "quote"
                ),
                historical_bars=market.get(
                    "historical_bars"
                ) or [],
                depth=market.get(
                    "depth"
                ),
                positions=positions,
                open_orders=open_orders
            )
        )

        ai_action = str(
            strategy_result.get(
                "action",
                "WAIT"
            )
        ).upper()

        # =========================
        # If AI Says WAIT
        # =========================

        if ai_action == "WAIT":

            return decision_service.evaluate_decision(
                strategy_result=(
                    strategy_result
                ),
                rule_result=None,
                risk_result=None,
                planned_quantity=(
                    planned_quantity
                )
            )

        # =========================
        # If AI Says EXIT
        # =========================

        if ai_action == "EXIT":

            return decision_service.evaluate_decision(
                strategy_result=(
                    strategy_result
                ),
                rule_result=None,
                risk_result=None,
                planned_quantity=(
                    planned_quantity
                )
            )

        # =========================
        # 3. Rule Engine
        # =========================

        rule_result = (
            rule_service.evaluate_rules(
                account=account,
                account_size=account_size,
                symbol=symbol,
                planned_quantity=(
                    planned_quantity
                ),
                current_mll=current_mll,
                best_day_profit=(
                    best_day_profit
                )
            )
        )

        # =========================
        # 4. Extract AI Trade Plan
        # =========================

        trade_plan = (
            strategy_result.get(
                "trade_plan",
                {}
            )
        )

        entry_price = trade_plan.get(
            "entry_price"
        )

        stop_loss = trade_plan.get(
            "stop_loss"
        )

        # =========================
        # Missing Entry / Stop
        # =========================

        if (
            entry_price is None
            or stop_loss is None
        ):

            return {
                "success": True,

                "final_status": "BLOCK",

                "action": "WAIT",

                "execution_allowed": False,

                "reason": (
                    "AI strategy did not provide "
                    "a valid entry price and stop loss."
                ),

                "strategy": strategy_result,

                "rule": rule_result
            }

        # =========================
        # 5. Risk Engine
        # =========================

        risk_result = (
            risk_service.evaluate_risk(
                account=account,
                contract=contract,
                entry_price=float(
                    entry_price
                ),
                stop_price=float(
                    stop_loss
                ),
                planned_quantity=(
                    planned_quantity
                ),
                current_mll=current_mll,
                max_risk_per_trade=(
                    max_risk_per_trade
                )
            )
        )

        # =========================
        # 6. Final Decision
        # =========================

        return decision_service.evaluate_decision(
            strategy_result=(
                strategy_result
            ),

            rule_result=(
                rule_result
            ),

            risk_result=(
                risk_result
            ),

            planned_quantity=(
                planned_quantity
            )
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )



# =========================
# Safety Engine
# =========================

@app.get(
    "/topstep/safety/evaluate",
    tags=["Safety Engine"]
)
async def evaluate_safety(
    account_id: int,
    contract_id: str,

    account_size: int = 50000,

    symbol: str = "MES",
    search_text: str = "MES",

    planned_quantity: int = 1,

    current_mll: float | None = None,

    best_day_profit: float | None = None,

    max_risk_per_trade: float | None = None,

    daily_pnl: float | None = None,

    daily_loss_limit: float | None = None,

    max_position_quantity: int | None = None,

    kill_switch: bool = False,

    max_quote_age_seconds: int = 30,

    start_time: str | None = None,

    end_time: str | None = None,

    live: bool = False
):
    try:

        # =========================
        # 1. Trading State
        # =========================

        state = (
            await trading_state_service.get_trading_state(
                account_id=account_id,
                contract_id=contract_id,
                search_text=search_text,
                live=live,
                start_time=start_time,
                end_time=end_time,
                unit=2,
                unit_number=5,
                limit=100
            )
        )

        account = state.get(
            "account"
        )

        contract = state.get(
            "contract"
        )

        market = state.get(
            "market",
            {}
        )

        positions = state.get(
            "positions",
            []
        )

        open_orders = state.get(
            "open_orders",
            []
        )

        if not account:
            raise ValueError(
                "Account state is unavailable."
            )

        if not contract:
            raise ValueError(
                "Contract state is unavailable."
            )

        # =========================
        # 2. AI Strategy
        # =========================

        strategy_result = (
            strategy_service.evaluate_strategy(
                symbol=symbol,
                contract=contract,
                quote=market.get(
                    "quote"
                ),
                historical_bars=market.get(
                    "historical_bars"
                ) or [],
                depth=market.get(
                    "depth"
                ),
                positions=positions,
                open_orders=open_orders
            )
        )

        ai_action = str(
            strategy_result.get(
                "action",
                "WAIT"
            )
        ).upper()

        # =========================
        # AI WAIT
        # =========================

        if ai_action == "WAIT":

            final_decision = (
                decision_service.evaluate_decision(
                    strategy_result=(
                        strategy_result
                    ),
                    rule_result=None,
                    risk_result=None,
                    planned_quantity=(
                        planned_quantity
                    )
                )
            )

            return safety_service.evaluate_safety(
                final_decision=(
                    final_decision
                ),
                trading_state=state,
                planned_quantity=(
                    planned_quantity
                ),
                kill_switch=(
                    kill_switch
                ),
                daily_pnl=(
                    daily_pnl
                ),
                daily_loss_limit=(
                    daily_loss_limit
                ),
                current_mll=(
                    current_mll
                ),
                max_position_quantity=(
                    max_position_quantity
                ),
                max_quote_age_seconds=(
                    max_quote_age_seconds
                )
            )

        # =========================
        # AI EXIT
        # =========================

        if ai_action == "EXIT":

            final_decision = (
                decision_service.evaluate_decision(
                    strategy_result=(
                        strategy_result
                    ),
                    rule_result=None,
                    risk_result=None,
                    planned_quantity=(
                        planned_quantity
                    )
                )
            )

            return safety_service.evaluate_safety(
                final_decision=(
                    final_decision
                ),
                trading_state=state,
                planned_quantity=(
                    planned_quantity
                ),
                kill_switch=(
                    kill_switch
                ),
                daily_pnl=(
                    daily_pnl
                ),
                daily_loss_limit=(
                    daily_loss_limit
                ),
                current_mll=(
                    current_mll
                ),
                max_position_quantity=(
                    max_position_quantity
                ),
                max_quote_age_seconds=(
                    max_quote_age_seconds
                )
            )

        # =========================
        # 3. Rule Engine
        # =========================

        rule_result = (
            rule_service.evaluate_rules(
                account=account,
                account_size=account_size,
                symbol=symbol,
                planned_quantity=(
                    planned_quantity
                ),
                current_mll=(
                    current_mll
                ),
                best_day_profit=(
                    best_day_profit
                )
            )
        )

        # =========================
        # 4. AI Trade Plan
        # =========================

        trade_plan = (
            strategy_result.get(
                "trade_plan",
                {}
            )
        )

        entry_price = (
            trade_plan.get(
                "entry_price"
            )
        )

        stop_loss = (
            trade_plan.get(
                "stop_loss"
            )
        )

        # =========================
        # Missing Critical Data
        # =========================

        if (
            entry_price is None
            or stop_loss is None
        ):

            final_decision = {
                "success": True,
                "final_status": "BLOCK",
                "action": "WAIT",
                "execution_allowed": False,
                "reason": (
                    "AI strategy did not provide "
                    "valid entry and stop-loss data."
                )
            }

            return safety_service.evaluate_safety(
                final_decision=(
                    final_decision
                ),
                trading_state=state,
                planned_quantity=(
                    planned_quantity
                ),
                kill_switch=(
                    kill_switch
                ),
                daily_pnl=(
                    daily_pnl
                ),
                daily_loss_limit=(
                    daily_loss_limit
                ),
                current_mll=(
                    current_mll
                ),
                max_position_quantity=(
                    max_position_quantity
                ),
                max_quote_age_seconds=(
                    max_quote_age_seconds
                )
            )

        # =========================
        # 5. Risk Engine
        # =========================

        risk_result = (
            risk_service.evaluate_risk(
                account=account,
                contract=contract,
                entry_price=float(
                    entry_price
                ),
                stop_price=float(
                    stop_loss
                ),
                planned_quantity=(
                    planned_quantity
                ),
                current_mll=(
                    current_mll
                ),
                max_risk_per_trade=(
                    max_risk_per_trade
                )
            )
        )

        # =========================
        # 6. Final Decision
        # =========================

        final_decision = (
            decision_service.evaluate_decision(
                strategy_result=(
                    strategy_result
                ),
                rule_result=(
                    rule_result
                ),
                risk_result=(
                    risk_result
                ),
                planned_quantity=(
                    planned_quantity
                )
            )
        )

        # =========================
        # 7. Safety Validation
        # =========================

        safety_result = (
            safety_service.evaluate_safety(
                final_decision=(
                    final_decision
                ),
                trading_state=state,
                planned_quantity=(
                    planned_quantity
                ),
                kill_switch=(
                    kill_switch
                ),
                daily_pnl=(
                    daily_pnl
                ),
                daily_loss_limit=(
                    daily_loss_limit
                ),
                current_mll=(
                    current_mll
                ),
                max_position_quantity=(
                    max_position_quantity
                ),
                max_quote_age_seconds=(
                    max_quote_age_seconds
                )
            )
        )

        return {
            "success": True,

            "final_decision": (
                final_decision
            ),

            "safety": (
                safety_result
            ),

            "ready_for_execution": (
                final_decision.get(
                    "execution_allowed",
                    False
                )
                and safety_result.get(
                    "safe_to_execute",
                    False
                )
            )
        }

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )