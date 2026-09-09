from fastapi import FastAPI, HTTPException
import asyncio

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
from service.execution_service import ExecutionService
from service.bot_service import BotService
from service.market_status_service import MarketStatusService
from service.audit_service import AuditService
from service.bot_state_service import BotStateService
from service.database_service import DatabaseService
from service.db_bot_state_service import DbBotStateService
from service.autonomous_bot_service import AutonomousBotService
from service.trading_day_service import TradingDayService
from service.topstep_session_service import TopstepSessionService

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

trading_day_service = TradingDayService(
    trade_service=trade_service
)

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

execution_service = ExecutionService(
    order_service=order_service,
    position_service=position_service
)

database_service = DatabaseService()

audit_service = AuditService(
    database_service=database_service
)

bot_state_service = BotStateService()

topstep_session_service = TopstepSessionService(
    database_service=database_service
)

autonomous_services_by_session = {}
bot_state_services_by_session = {}

bot_service = BotService(
    contract_service=contract_service,
    trading_state_service=trading_state_service,
    realtime_service=realtime_service,
    rule_service=rule_service,
    risk_service=risk_service,
    strategy_service=strategy_service,
    decision_service=decision_service,
    safety_service=safety_service,
    execution_service=execution_service,
    trading_day_service=trading_day_service,
    audit_service=audit_service,
    bot_state_service=bot_state_service
)

autonomous_bot_service = AutonomousBotService(
    bot_service=bot_service,
    bot_state_service=bot_state_service,
    audit_service=audit_service
)

market_status_service = MarketStatusService(
    account_service=account_service,
    contract_service=contract_service,
    history_service=history_service,
    realtime_service=realtime_service
)


def get_bot_state_service(
    session_id: str | None
):
    if not session_id:
        raise ValueError(
            "session_id is required. "
            "Please call /topstep/session/login first."
        )

    existing = bot_state_services_by_session.get(
        session_id
    )

    if existing is not None:
        return existing

    session = topstep_session_service.get_session(
        session_id
    )

    if database_service.is_enabled():
        created = DbBotStateService(
            database_service=database_service,
            session_id=session_id,
            user_id=(
                session.get(
                    "user_id"
                )
                if session
                else None
            )
        )

    else:
        created = BotStateService(
            filename=f"bot_state_{session_id}.json"
        )

    bot_state_services_by_session[
        session_id
    ] = created

    return created


def build_runtime(
    session_id: str | None = None
):
    if not session_id:
        raise ValueError(
            "session_id is required. "
            "Please call /topstep/session/login first."
        )

    client = topstep_session_service.get_client(
        session_id
    )

    if client is None:
        raise ValueError(
            "Topstep session was not found. "
            "Please authenticate again."
        )

    session = topstep_session_service.get_session(
        session_id
    )

    runtime_account_service = AccountService(
        client=client
    )
    runtime_contract_service = ContractService(
        client=client
    )
    runtime_history_service = HistoryService(
        client=client
    )
    runtime_position_service = PositionService(
        client=client
    )
    runtime_order_service = OrderService(
        client=client
    )
    runtime_trade_service = TradeService(
        client=client
    )

    runtime_realtime_service = (
        topstep_session_service.get_realtime_service(
            session_id
        )
        if session_id
        else realtime_service
    )

    if runtime_realtime_service is None:
        runtime_realtime_service = RealtimeService(
            topstep_service=client
        )

    runtime_trading_day_service = TradingDayService(
        trade_service=runtime_trade_service
    )

    runtime_trading_state_service = TradingStateService(
        account_service=runtime_account_service,
        contract_service=runtime_contract_service,
        history_service=runtime_history_service,
        position_service=runtime_position_service,
        order_service=runtime_order_service,
        realtime_service=runtime_realtime_service
    )

    runtime_execution_service = ExecutionService(
        order_service=runtime_order_service,
        position_service=runtime_position_service
    )

    runtime_bot_state_service = get_bot_state_service(
        session_id
    )

    runtime_bot_service = BotService(
        contract_service=runtime_contract_service,
        trading_state_service=runtime_trading_state_service,
        realtime_service=runtime_realtime_service,
        rule_service=rule_service,
        risk_service=risk_service,
        strategy_service=strategy_service,
        decision_service=decision_service,
        safety_service=safety_service,
        execution_service=runtime_execution_service,
        trading_day_service=runtime_trading_day_service,
        audit_service=audit_service,
        bot_state_service=runtime_bot_state_service,
        session_id=session_id,
        user_id=(
            session.get(
                "user_id"
            )
            if session
            else None
        )
    )

    runtime_market_status_service = MarketStatusService(
        account_service=runtime_account_service,
        contract_service=runtime_contract_service,
        history_service=runtime_history_service,
        realtime_service=runtime_realtime_service
    )

    return {
        "account_service": runtime_account_service,
        "contract_service": runtime_contract_service,
        "history_service": runtime_history_service,
        "position_service": runtime_position_service,
        "order_service": runtime_order_service,
        "trade_service": runtime_trade_service,
        "trading_day_service": runtime_trading_day_service,
        "trading_state_service": runtime_trading_state_service,
        "realtime_service": runtime_realtime_service,
        "bot_service": runtime_bot_service,
        "market_status_service": runtime_market_status_service
    }


def get_autonomous_service(
    session_id: str | None,
    runtime: dict | None = None
):
    if not session_id:
        raise ValueError(
            "session_id is required. "
            "Please call /topstep/session/login first."
        )

    existing = autonomous_services_by_session.get(
        session_id
    )

    if existing is not None:
        return existing

    if runtime is None:
        runtime = build_runtime(
            session_id=session_id
        )

    created = AutonomousBotService(
        bot_service=runtime[
            "bot_service"
        ],
        bot_state_service=get_bot_state_service(
            session_id
        ),
        audit_service=audit_service
    )

    autonomous_services_by_session[
        session_id
    ] = created

    return created


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


@app.get(
    "/topstep/database/health",
    tags=["System"]
)
def database_health():
    return database_service.health()


@app.on_event(
    "shutdown"
)
async def shutdown_services():
    await autonomous_bot_service.stop()

    for service in autonomous_services_by_session.values():
        await service.stop()

    realtime_service.stop_all()

    for session in topstep_session_service.sessions.values():
        session_realtime_service = session.get(
            "realtime_service"
        )

        if session_realtime_service is not None:
            session_realtime_service.stop_all()


# =========================
# Authentication
# =========================

@app.get(
    "/topstep/auth-test",
    tags=["Authentication"]
)
async def auth_test(
    session_id: str
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        accounts_result = await runtime[
            "account_service"
        ].get_accounts()

        return {
            "success": True,
            "message": "Session authentication succeeded.",
            "session_id": session_id,
            "account_count": len(
                accounts_result.get(
                    "accounts",
                    []
                )
            )
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.post(
    "/topstep/session/login",
    tags=["Authentication"]
)
async def login_topstep_session(
    user_id: str,
    topstep_username: str,
    topstep_api_key: str
):
    try:
        login_result = await topstep_session_service.login(
            username=topstep_username,
            api_key=topstep_api_key,
            user_id=user_id
        )

        runtime = build_runtime(
            session_id=login_result[
                "session_id"
            ]
        )

        accounts_result = (
            await runtime[
                "account_service"
            ].get_accounts()
        )

        accounts = accounts_result.get(
            "accounts",
            []
        )

        accounts_database = topstep_session_service.save_accounts(
            session_id=login_result[
                "session_id"
            ],
            accounts=accounts
        )

        return {
            **login_result,
            "accounts": accounts,
            "accounts_database": accounts_database
        }

    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail=str(exc)
        )


@app.get(
    "/topstep/session/status",
    tags=["Authentication"]
)
async def topstep_session_status(
    session_id: str | None = None
):
    return topstep_session_service.status(
        session_id=session_id
    )


@app.post(
    "/topstep/session/logout",
    tags=["Authentication"]
)
async def logout_topstep_session(
    session_id: str
):
    service = autonomous_services_by_session.pop(
        session_id,
        None
    )

    if service is not None:
        await service.stop()

    bot_state_services_by_session.pop(
        session_id,
        None
    )

    return topstep_session_service.logout(
        session_id=session_id
    )


# =========================
# Accounts
# =========================

@app.get(
    "/topstep/accounts",
    tags=["Accounts"]
)
async def get_accounts(
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        accounts_result = await runtime[
            "account_service"
        ].get_accounts()

        accounts_database = topstep_session_service.save_accounts(
            session_id=session_id,
            accounts=accounts_result.get(
                "accounts",
                []
            )
        )

        return {
            **accounts_result,
            "accounts_database": accounts_database
        }

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
    live: bool = False,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "contract_service"
        ].search_contracts(
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
    live: bool = False,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "history_service"
        ].get_bars(
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


@app.get(
    "/topstep/market/status",
    tags=["Market Data"]
)
async def get_market_status(
    account_id: int,
    symbol: str = "MES",
    live: bool = False,
    auto_start_realtime: bool = True,
    realtime_warmup_seconds: int = 3,
    max_quote_age_seconds: int = 30,
    lookback_hours: int = 96,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "market_status_service"
        ].get_status(
            account_id=account_id,
            symbol=symbol,
            live=live,
            auto_start_realtime=auto_start_realtime,
            realtime_warmup_seconds=realtime_warmup_seconds,
            max_quote_age_seconds=max_quote_age_seconds,
            lookback_hours=lookback_hours
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
    account_id: int,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "position_service"
        ].get_open_positions(
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
    account_id: int,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "order_service"
        ].get_open_orders(
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
    end_timestamp: str | None = None,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "order_service"
        ].get_orders(
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
    end_timestamp: str | None = None,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "trade_service"
        ].get_trades(
            account_id=account_id,
            start_timestamp=start_timestamp,
            end_timestamp=end_timestamp
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.get(
    "/topstep/trading-day/pnl",
    tags=["Trades"]
)
async def get_current_trading_day_pnl(
    account_id: int,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "trading_day_service"
        ].get_current_trading_day_pnl(
            account_id=account_id
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.get(
    "/topstep/evaluation/progress",
    tags=["Rule Engine"]
)
async def get_evaluation_progress(
    account_id: int,
    evaluation_start_time: str | None = None,
    lookback_days: int = 14,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "trading_day_service"
        ].get_evaluation_progress(
            account_id=account_id,
            evaluation_start_time=evaluation_start_time,
            lookback_days=lookback_days
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


# =========================
# Dashboard
# =========================

async def _dashboard_section(
    name: str,
    task
):
    try:
        return await task

    except Exception as exc:
        return {
            "success": False,
            "section": name,
            "error": str(
                exc
            )
        }


@app.get(
    "/topstep/dashboard/summary",
    tags=["Dashboard"]
)
async def get_dashboard_summary(
    session_id: str,
    account_id: int,
    symbol: str = "MES",
    phase: str = "evaluation",
    account_size: int = 50000,
    planned_quantity: int = 1,
    live: bool = False,
    auto_start_realtime: bool = True,
    realtime_warmup_seconds: int = 1,
    max_quote_age_seconds: int = 30,
    lookback_hours: int = 72,
    audit_limit: int = 1
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        session_status = topstep_session_service.status(
            session_id=session_id
        )

        accounts_result = await runtime[
            "account_service"
        ].get_accounts()

        accounts = accounts_result.get(
            "accounts",
            []
        )

        selected_account = None

        for account in accounts:
            if account.get(
                "id"
            ) == account_id:
                selected_account = account
                break

        if selected_account is None:
            raise ValueError(
                f"Account {account_id} not found."
            )

        user_id = session_status.get(
            "user_id"
        )

        market_task = runtime[
            "market_status_service"
        ].get_status(
            account_id=account_id,
            symbol=symbol,
            live=live,
            auto_start_realtime=auto_start_realtime,
            realtime_warmup_seconds=realtime_warmup_seconds,
            max_quote_age_seconds=max_quote_age_seconds,
            lookback_hours=lookback_hours
        )

        positions_task = runtime[
            "position_service"
        ].get_open_positions(
            account_id=account_id
        )

        orders_task = runtime[
            "order_service"
        ].get_open_orders(
            account_id=account_id
        )

        pnl_task = runtime[
            "trading_day_service"
        ].get_current_trading_day_pnl(
            account_id=account_id
        )

        evaluation_task = runtime[
            "trading_day_service"
        ].get_evaluation_progress(
            account_id=account_id,
            evaluation_start_time=None,
            lookback_days=14
        )

        (
            market_status,
            positions_result,
            orders_result,
            trading_day_pnl,
            evaluation_progress
        ) = await asyncio.gather(
            _dashboard_section(
                "market",
                market_task
            ),
            _dashboard_section(
                "positions",
                positions_task
            ),
            _dashboard_section(
                "orders",
                orders_task
            ),
            _dashboard_section(
                "trading_day",
                pnl_task
            ),
            _dashboard_section(
                "evaluation",
                evaluation_task
            )
        )

        rule_pack = rule_service.get_rule_pack(
            account_size=account_size,
            phase=phase,
            enforce_daily_profit_cap=True
        )

        rules = rule_service.evaluate_rules(
            account=selected_account,
            account_size=account_size,
            symbol=symbol,
            planned_quantity=planned_quantity,
            current_mll=rule_pack.get(
                "maximum_loss_limit_floor"
            ),
            best_day_profit=evaluation_progress.get(
                "best_day_profit"
            ),
            daily_pnl=trading_day_pnl.get(
                "current_trading_day_pnl"
            ),
            evaluation_trading_days=evaluation_progress.get(
                "evaluation_trading_days"
            ),
            phase=phase,
            enforce_daily_profit_cap=True
        )

        bot_status = get_autonomous_service(
            session_id=session_id,
            runtime=runtime
        ).status()

        latest_audit = audit_service.read_recent(
            limit=audit_limit,
            session_id=session_id,
            user_id=user_id,
            account_id=account_id,
            symbol=symbol
        )

        last_record = None

        if latest_audit.get(
            "records"
        ):
            last_record = latest_audit[
                "records"
            ][0]

        dashboard_status = "READY"
        blocks = []

        if not session_status.get(
            "authenticated"
        ):
            dashboard_status = "BLOCKED"
            blocks.append(
                "Topstep session is not authenticated."
            )

        if not market_status.get(
            "tradable"
        ):
            dashboard_status = "BLOCKED"
            blocks.extend(
                market_status.get(
                    "blocks",
                    []
                )
            )

        if rules.get(
            "status"
        ) != "ALLOW":
            dashboard_status = "BLOCKED"
            blocks.extend(
                rules.get(
                    "violations",
                    []
                )
            )

        kill_switch_enabled = bool(
            bot_status.get(
                "kill_switch",
                {}
            ).get(
                "enabled",
                False
            )
        )

        if kill_switch_enabled:
            dashboard_status = "BLOCKED"
            blocks.append(
                "Emergency kill switch is enabled."
            )

        return {
            "success": True,
            "summary_version": "DASHBOARD_SUMMARY_V1",
            "dashboard_status": dashboard_status,
            "blocks": blocks,
            "session": session_status,
            "account": selected_account,
            "accounts": accounts,
            "market": market_status,
            "bot": bot_status,
            "rules": rules,
            "trading_day": trading_day_pnl,
            "evaluation": evaluation_progress,
            "positions": positions_result,
            "orders": orders_result,
            "latest_audit": {
                "count": latest_audit.get(
                    "count",
                    0
                ),
                "record": last_record
            }
        }

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
    account_id: int,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "realtime_service"
        ].start_user_hub(
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
    contract_id: str,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "realtime_service"
        ].start_market_hub(
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
def get_latest_realtime_data(
    session_id: str | None = None
):
    runtime = build_runtime(
        session_id=session_id
    )

    return runtime[
        "realtime_service"
    ].get_latest_data()


@app.post(
    "/topstep/realtime/stop",
    tags=["Realtime"]
)
def stop_realtime(
    session_id: str | None = None
):
    runtime = build_runtime(
        session_id=session_id
    )

    return runtime[
        "realtime_service"
    ].stop_all()


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
    limit: int = 100,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "trading_state_service"
        ].get_trading_state(
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
    "/topstep/rules/pack",
    tags=["Rule Engine"]
)
async def get_rule_pack(
    account_size: int = 50000,
    phase: str = "evaluation",
    enforce_daily_profit_cap: bool = True
):
    try:
        return {
            "success": True,
            "rule_pack": rule_service.get_rule_pack(
                account_size=account_size,
                phase=phase,
                enforce_daily_profit_cap=(
                    enforce_daily_profit_cap
                )
            ),
            "rule_version": "TOPSTEP_RULE_PACK_V1"
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


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
    best_day_profit: float | None = None,
    daily_pnl: float | None = None,
    evaluation_trading_days: int | None = None,
    phase: str = "evaluation",
    enforce_daily_profit_cap: bool = True,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        accounts_result = (
            await runtime[
                "account_service"
            ].get_accounts()
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
            best_day_profit=best_day_profit,
            daily_pnl=daily_pnl,
            evaluation_trading_days=(
                evaluation_trading_days
            ),
            phase=phase,
            enforce_daily_profit_cap=(
                enforce_daily_profit_cap
            )
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
    live: bool = False,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        # =========================
        # Fetch Account
        # =========================

        accounts_result = (
            await runtime[
                "account_service"
            ].get_accounts()
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
            await runtime[
                "contract_service"
            ].search_contracts(
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
    live: bool = False,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        state = await runtime[
            "trading_state_service"
        ].get_trading_state(
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

    daily_pnl: float | None = None,

    evaluation_trading_days: int | None = None,

    start_time: str | None = None,
    end_time: str | None = None,

    live: bool = False,

    phase: str = "evaluation",

    enforce_daily_profit_cap: bool = True,

    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        # =========================
        # 1. Get Trading State
        # =========================

        state = (
            await runtime[
                "trading_state_service"
            ].get_trading_state(
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
                ),
                daily_pnl=daily_pnl,
                phase=phase,
                enforce_daily_profit_cap=(
                    enforce_daily_profit_cap
                ),
                evaluation_trading_days=(
                    evaluation_trading_days
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
# Execution Engine
# =========================

@app.post(
    "/topstep/bot/run-auto",
    tags=["Bot"]
)
async def run_bot_auto(
    account_id: int,
    symbol: str = "MES",
    dry_run: bool = True,
    live: bool = False,
    phase: str = "evaluation",
    confirm_live_execution: bool = False,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "bot_service"
        ].run_auto(
            account_id=account_id,
            symbol=symbol,
            dry_run=dry_run,
            live=live,
            phase=phase,
            confirm_live_execution=(
                confirm_live_execution
            )
        )

    except Exception as exc:
        bot_state_service.mark_run_failed(
            error=exc,
            context={
                "account_id": account_id,
                "symbol": symbol,
                "dry_run": dry_run,
                "live": live,
                "phase": phase,
                "session_id": session_id,
                "confirm_live_execution": (
                    confirm_live_execution
                ),
                "auto_mode": True
            }
        )

        audit_service.log_error(
            event_type="BOT_AUTO_RUN_FAILED",
            error=exc,
            context={
                "account_id": account_id,
                "symbol": symbol,
                "dry_run": dry_run,
                "live": live,
                "phase": phase,
                "session_id": session_id,
                "confirm_live_execution": (
                    confirm_live_execution
                ),
                "auto_mode": True
            }
        )

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.post(
    "/topstep/bot/run-once",
    tags=["Bot"]
)
async def run_bot_once(
    account_id: int,

    symbol: str = "MES",

    dry_run: bool = True,

    account_size: int = 50000,

    planned_quantity: int = 1,

    current_mll: float | None = None,

    best_day_profit: float | None = None,

    max_risk_per_trade: float | None = None,

    daily_pnl: float | None = None,

    evaluation_trading_days: int | None = None,

    daily_loss_limit: float | None = None,

    max_position_quantity: int | None = None,

    kill_switch: bool = False,

    max_quote_age_seconds: int = 30,

    order_type: str = "MARKET",

    lookback_hours: int = 72,

    auto_start_realtime: bool = True,

    realtime_warmup_seconds: int = 3,

    live: bool = False,

    duplicate_order_cooldown_seconds: int = 300,

    phase: str = "evaluation",

    enforce_daily_profit_cap: bool = True,

    auto_calculate_evaluation_metrics: bool = True,

    evaluation_start_time: str | None = None,

    evaluation_lookback_days: int = 14,

    confirm_live_execution: bool = False,

    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        return await runtime[
            "bot_service"
        ].run_once(
            account_id=account_id,
            account_size=account_size,
            symbol=symbol,
            dry_run=dry_run,
            planned_quantity=planned_quantity,
            current_mll=current_mll,
            best_day_profit=best_day_profit,
            max_risk_per_trade=max_risk_per_trade,
            daily_pnl=daily_pnl,
            evaluation_trading_days=(
                evaluation_trading_days
            ),
            daily_loss_limit=daily_loss_limit,
            max_position_quantity=max_position_quantity,
            kill_switch=kill_switch,
            max_quote_age_seconds=max_quote_age_seconds,
            order_type=order_type,
            lookback_hours=lookback_hours,
            auto_start_realtime=auto_start_realtime,
            realtime_warmup_seconds=realtime_warmup_seconds,
            live=live,
            duplicate_order_cooldown_seconds=(
                duplicate_order_cooldown_seconds
            ),
            phase=phase,
            enforce_daily_profit_cap=(
                enforce_daily_profit_cap
            ),
            auto_calculate_evaluation_metrics=(
                auto_calculate_evaluation_metrics
            ),
            evaluation_start_time=evaluation_start_time,
            evaluation_lookback_days=(
                evaluation_lookback_days
            ),
            confirm_live_execution=(
                confirm_live_execution
            )
        )

    except Exception as exc:
        bot_state_service.mark_run_failed(
            error=exc,
            context={
                "account_id": account_id,
                "symbol": symbol,
                "dry_run": dry_run,
                "live": live,
                "phase": phase,
                "session_id": session_id,
                "auto_calculate_evaluation_metrics": (
                    auto_calculate_evaluation_metrics
                ),
                "evaluation_start_time": evaluation_start_time,
                "confirm_live_execution": (
                    confirm_live_execution
                )
            }
        )

        audit_service.log_error(
            event_type="BOT_RUN_FAILED",
            error=exc,
            context={
                "account_id": account_id,
                "symbol": symbol,
                "dry_run": dry_run,
                "live": live,
                "phase": phase,
                "session_id": session_id,
                "auto_calculate_evaluation_metrics": (
                    auto_calculate_evaluation_metrics
                ),
                "evaluation_start_time": evaluation_start_time,
                "confirm_live_execution": (
                    confirm_live_execution
                )
            }
        )

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.get(
    "/topstep/bot/status",
    tags=["Bot"]
)
async def get_bot_status(
    session_id: str | None = None
):
    try:
        service = get_autonomous_service(
            session_id=session_id
        )

        return service.status()

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.post(
    "/topstep/bot/start-auto",
    tags=["Bot"]
)
async def start_bot_auto(
    account_id: int,
    symbol: str = "MES",
    dry_run: bool = True,
    live: bool = False,
    phase: str = "evaluation",
    interval_seconds: int = 60,
    confirm_live_execution: bool = False,
    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        runtime_autonomous_bot_service = get_autonomous_service(
            session_id=session_id,
            runtime=runtime
        )

        return await runtime_autonomous_bot_service.start_auto(
            account_id=account_id,
            symbol=symbol,
            dry_run=dry_run,
            live=live,
            phase=phase,
            interval_seconds=interval_seconds,
            confirm_live_execution=(
                confirm_live_execution
            )
        )

    except Exception as exc:
        audit_service.log_error(
            event_type="BOT_AUTO_START_FAILED",
            error=exc,
            context={
                "account_id": account_id,
                "symbol": symbol,
                "dry_run": dry_run,
                "live": live,
                "phase": phase,
                "interval_seconds": interval_seconds,
                "session_id": session_id,
                "confirm_live_execution": (
                    confirm_live_execution
                ),
                "auto_mode": True
            }
        )

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.post(
    "/topstep/bot/start",
    tags=["Bot"]
)
async def start_bot(
    account_id: int,

    symbol: str = "MES",

    dry_run: bool = True,

    account_size: int = 50000,

    planned_quantity: int = 1,

    current_mll: float | None = None,

    best_day_profit: float | None = None,

    max_risk_per_trade: float | None = None,

    daily_pnl: float | None = None,

    evaluation_trading_days: int | None = None,

    daily_loss_limit: float | None = None,

    max_position_quantity: int | None = None,

    max_quote_age_seconds: int = 30,

    order_type: str = "MARKET",

    lookback_hours: int = 72,

    auto_start_realtime: bool = True,

    realtime_warmup_seconds: int = 3,

    live: bool = False,

    interval_seconds: int = 60,

    duplicate_order_cooldown_seconds: int = 300,

    phase: str = "evaluation",

    enforce_daily_profit_cap: bool = True,

    auto_calculate_evaluation_metrics: bool = True,

    evaluation_start_time: str | None = None,

    evaluation_lookback_days: int = 14,

    confirm_live_execution: bool = False,

    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        runtime_autonomous_bot_service = get_autonomous_service(
            session_id=session_id,
            runtime=runtime
        )

        return await runtime_autonomous_bot_service.start(
            account_id=account_id,
            account_size=account_size,
            symbol=symbol,
            dry_run=dry_run,
            planned_quantity=planned_quantity,
            current_mll=current_mll,
            best_day_profit=best_day_profit,
            max_risk_per_trade=max_risk_per_trade,
            daily_pnl=daily_pnl,
            evaluation_trading_days=(
                evaluation_trading_days
            ),
            daily_loss_limit=daily_loss_limit,
            max_position_quantity=max_position_quantity,
            max_quote_age_seconds=max_quote_age_seconds,
            order_type=order_type,
            lookback_hours=lookback_hours,
            auto_start_realtime=auto_start_realtime,
            realtime_warmup_seconds=realtime_warmup_seconds,
            live=live,
            interval_seconds=interval_seconds,
            duplicate_order_cooldown_seconds=(
                duplicate_order_cooldown_seconds
            ),
            phase=phase,
            enforce_daily_profit_cap=(
                enforce_daily_profit_cap
            ),
            auto_calculate_evaluation_metrics=(
                auto_calculate_evaluation_metrics
            ),
            evaluation_start_time=evaluation_start_time,
            evaluation_lookback_days=(
                evaluation_lookback_days
            ),
            confirm_live_execution=(
                confirm_live_execution
            )
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.post(
    "/topstep/bot/stop",
    tags=["Bot"]
)
async def stop_bot(
    session_id: str | None = None
):
    try:
        service = get_autonomous_service(
            session_id=session_id
        )

        return await service.stop()

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.post(
    "/topstep/bot/kill-switch/enable",
    tags=["Bot"]
)
async def enable_bot_kill_switch(
    reason: str = "Manual emergency stop."
):
    try:
        return bot_state_service.enable_kill_switch(
            reason=reason,
            updated_by="api"
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.post(
    "/topstep/bot/kill-switch/disable",
    tags=["Bot"]
)
async def disable_bot_kill_switch(
    reason: str = "Manual reset."
):
    try:
        return bot_state_service.disable_kill_switch(
            reason=reason,
            updated_by="api"
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.get(
    "/topstep/audit/recent",
    tags=["Audit"]
)
async def get_recent_audit_logs(
    limit: int = 50,
    session_id: str | None = None,
    user_id: str | None = None,
    account_id: int | None = None,
    symbol: str | None = None,
    event_type: str | None = None
):
    try:
        return audit_service.read_recent(
            limit=limit,
            session_id=session_id,
            user_id=user_id,
            account_id=account_id,
            symbol=symbol,
            event_type=event_type
        )

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=str(exc)
        )


@app.post(
    "/topstep/execution/dry-run",
    tags=["Execution Engine"]
)
async def dry_run_execution(
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

    evaluation_trading_days: int | None = None,

    daily_loss_limit: float | None = None,

    max_position_quantity: int | None = None,

    kill_switch: bool = False,

    max_quote_age_seconds: int = 30,

    order_type: str = "MARKET",

    start_time: str | None = None,

    end_time: str | None = None,

    live: bool = False,

    phase: str = "evaluation",

    enforce_daily_profit_cap: bool = True,

    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        safety_workflow = await evaluate_safety(
            account_id=account_id,
            contract_id=contract_id,
            account_size=account_size,
            symbol=symbol,
            search_text=search_text,
            planned_quantity=planned_quantity,
            current_mll=current_mll,
            best_day_profit=best_day_profit,
            max_risk_per_trade=max_risk_per_trade,
            daily_pnl=daily_pnl,
            evaluation_trading_days=(
                evaluation_trading_days
            ),
            daily_loss_limit=daily_loss_limit,
            max_position_quantity=max_position_quantity,
            kill_switch=kill_switch,
            max_quote_age_seconds=max_quote_age_seconds,
            start_time=start_time,
            end_time=end_time,
            live=live,
            phase=phase,
            enforce_daily_profit_cap=(
                enforce_daily_profit_cap
            ),
            session_id=session_id
        )

        final_decision = safety_workflow.get(
            "final_decision"
        )

        safety_result = safety_workflow.get(
            "safety",
            safety_workflow
        )

        state = await runtime[
            "trading_state_service"
        ].get_trading_state(
            account_id=account_id,
            contract_id=contract_id,
            search_text=search_text,
            live=live,
            start_time=None,
            end_time=None
        )

        contract = state.get(
            "contract"
        )

        if contract is None:
            raise ValueError(
                "Contract information is unavailable."
            )

        execution_result = (
            runtime[
                "bot_service"
            ].execution_service.prepare_execution(
                account_id=account_id,
                contract_id=contract_id,
                final_decision=final_decision,
                safety_result=safety_result,
                contract=contract,
                dry_run=True,
                order_type=order_type
            )
        )

        return {
            "success": True,
            "workflow": {
                "ready_for_execution": safety_workflow.get(
                    "ready_for_execution",
                    False
                ),
                "safety_status": safety_result.get(
                    "safety_status"
                ),
                "safe_to_execute": safety_result.get(
                    "safe_to_execute"
                )
            },
            "execution": execution_result
        }

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

    evaluation_trading_days: int | None = None,

    daily_loss_limit: float | None = None,

    max_position_quantity: int | None = None,

    kill_switch: bool = False,

    max_quote_age_seconds: int = 30,

    start_time: str | None = None,

    end_time: str | None = None,

    live: bool = False,

    phase: str = "evaluation",

    enforce_daily_profit_cap: bool = True,

    session_id: str | None = None
):
    try:
        runtime = build_runtime(
            session_id=session_id
        )

        # =========================
        # 1. Trading State
        # =========================

        state = (
            await runtime[
                "trading_state_service"
            ].get_trading_state(
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
                ),
                daily_pnl=daily_pnl,
                phase=phase,
                enforce_daily_profit_cap=(
                    enforce_daily_profit_cap
                ),
                evaluation_trading_days=(
                    evaluation_trading_days
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
