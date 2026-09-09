# TopstepX FastAPI Connectivity Check

This project only checks whether TopstepX / ProjectX Gateway API authentication and data fetching work.

## Structure

```text
topstep_fastapi_check/
├── main.py
├── .env
├── requirements.txt
├── README.md
└── service/
    ├── __init__.py
    └── topstep_service.py
```

## 1. Configure `.env`

```env
TOPSTEP_USERNAME=your_topstep_username
TOPSTEP_API_KEY_PRIMARY=your_full_api_key
TOPSTEP_API_KEY_SECONDARY=optional_second_key
DATABASE_URL=your_mongodb_connection_string
DATABASE_NAME=your_database_name
```

You do not need the client's normal Topstep password for this test.

If the client created two API keys, one valid key is enough. This sample supports the second key only as a fallback.

## 2. Install

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 3. Run

```powershell
uvicorn main:app --reload
```

Open Swagger:

```text
http://127.0.0.1:8000/docs
```

## Live Execution Safety

By default, real TopstepX order submission is blocked even if an endpoint is called with `dry_run=false`.

To allow live order submission, both gates must be enabled:

```env
ALLOW_LIVE_TRADING=true
```

And the request must include:

```text
confirm_live_execution=true
```

If either gate is missing, the bot returns `LIVE_EXECUTION_BLOCKED` and no order is submitted.

## Daily Profit Lock

During `evaluation` and `payout` phases, the bot uses a `$1020` trading-day profit cap based on the client requirement: `$1000` profit plus `$20` commission.

When the cap is reached:

- New BUY/SELL entries are blocked.
- If open positions exist, the bot prepares close-all-position requests.
- In `dry_run=true`, close requests are prepared only and not submitted.
- In live mode, close requests still require the live execution safety gates above.

## 4. Test in this order

### Health

```text
GET /health
```

### Database Health

```text
GET /topstep/database/health
```

Expected when MongoDB is configured correctly:

```json
{
  "success": true,
  "enabled": true,
  "database": "your_database_name"
}
```

### Session Authentication

For dashboard or multi-user use, authenticate the trader first:

```text
POST /topstep/session/login
```

Inputs:

```text
user_id = dashboard user id
topstep_username = trader Topstep username
topstep_api_key = trader TopstepX API key
```

The response returns a `session_id`. Pass that `session_id` to Topstep data, market, bot, and realtime endpoints so the backend uses that trader's own Topstep credentials.

```text
GET /topstep/accounts?session_id=...
POST /topstep/bot/run-auto?session_id=...
```

The API key is not returned by the backend response and is not stored in the database. The database stores the dashboard `user_id`, `session_id`, Topstep username, Topstep session token, account snapshots, and per-session bot state.

Topstep data and bot endpoints require `session_id`. Without it, they will not fall back to `.env` credentials.

### Audit Logs

Bot audit logs are stored in MongoDB only.

Collection:

```text
bot_audit_logs
```

Read recent logs:

```text
GET /topstep/audit/recent?session_id=...
GET /topstep/audit/recent?user_id=123
GET /topstep/audit/recent?account_id=26968948
```

Supported filters:

```text
limit
session_id
user_id
account_id
symbol
event_type
```

### Dashboard Summary

The dashboard can load the main MVP trading screen with one read-only call:

```text
GET /topstep/dashboard/summary?session_id=...&account_id=26968948&symbol=MES
```

Optional inputs:

```text
phase=evaluation
account_size=50000
planned_quantity=1
live=false
```

This returns the active session, selected account, market status, bot status, rules/evaluation progress, trading-day PnL, open positions/orders, and the latest audit record.

### Session Auth Test

```text
GET /topstep/auth-test?session_id=...
```

This verifies the active session by fetching accounts using the stored session token.

### Fetch active accounts

```text
GET /topstep/accounts?session_id=...
```

### Search MES contracts

```text
GET /topstep/contracts?search_text=MES&live=false
```

You can also try `MNQ`, `M2K`, or `MYM`.

## Official API calls used

- `POST /api/Auth/loginKey`
- `POST /api/Account/search`
- `POST /api/Contract/search`

This sample does not place, modify, or cancel any trades.
