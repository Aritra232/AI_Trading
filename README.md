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

## 4. Test in this order

### Health

```text
GET /health
```

### Authentication

```text
GET /topstep/auth-test
```

The JWT/session token is intentionally not returned to the browser.

### Fetch active accounts

```text
GET /topstep/accounts
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
