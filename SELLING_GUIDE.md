# Selling PUBGM Results Engine

This app is now prepared for a simple sellable setup:

1. Customers pay you.
2. You create an online license account for their email.
3. They install the Windows desktop app.
4. The app logs in against your hosted license server.

The old local `data/users.json` login still works when no hosted license URL is
configured, so you can keep using the app while preparing sales.

## Recommended First Version

For the first 100 customers, keep it simple:

- Payment: Stripe Payment Links.
- Hosting: Render, Railway, or any Python host that can run FastAPI.
- License database: SQLite at first, then Postgres later if needed.
- Desktop app: ship a packaged `.exe` with your license server URL already set.

Useful official docs:

- Stripe Payment Links: https://docs.stripe.com/payment-links
- Render FastAPI deploy: https://render.com/docs/deploy-fastapi
- Railway FastAPI deploy: https://docs.railway.com/guides/fastapi

## Host The License Server

Install server requirements on your host:

```bash
pip install -r server_requirements.txt
```

Set these environment variables on the host:

```bash
LICENSE_SECRET_KEY=use-a-long-random-secret
ADMIN_API_KEY=use-another-long-random-secret
LICENSE_DB=/data/licenses.sqlite3
```

Start command:

```bash
uvicorn licensing_server.app:app --host 0.0.0.0 --port $PORT
```

After deploy, this should return OK:

```text
https://your-server-url/health
```

## Create A Customer

Manual account creation is enough for early sales. After someone pays, run this
from your own machine, replacing the URL and admin key:

```powershell
$body = @{
  email = "customer@example.com"
  password = "TempPass123"
  name = "Customer Name"
  licenseDays = 365
  maxDevices = 1
} | ConvertTo-Json

Invoke-RestMethod `
  -Uri "https://your-server-url/api/v1/admin/customers" `
  -Method Post `
  -Headers @{ "X-Admin-Key" = "your-admin-api-key" } `
  -ContentType "application/json" `
  -Body $body
```

Send the customer:

- The app installer.
- Their email.
- Their temporary password.

## Connect The Desktop App To Hosting

Set `licenseServerUrl` in `data/settings.json` before packaging the customer
build:

```json
{
  "apiUrl": "http://127.0.0.1:10086/gettotalplayerlist",
  "pollingInterval": 2,
  "mockMode": true,
  "licenseServerUrl": "https://your-server-url"
}
```

You can also set this environment variable instead:

```powershell
$env:PUBGM_LICENSE_SERVER_URL = "https://your-server-url"
```

When `licenseServerUrl` is set, the login screen uses hosted email/password
accounts. When it is empty, the app uses local `data/users.json` accounts.

## Manage Customers

Disable a customer:

```powershell
Invoke-RestMethod `
  -Uri "https://your-server-url/api/v1/admin/customers/customer@example.com" `
  -Method Patch `
  -Headers @{ "X-Admin-Key" = "your-admin-api-key" } `
  -ContentType "application/json" `
  -Body '{"status":"disabled"}'
```

Reset a customer's registered device:

```powershell
Invoke-RestMethod `
  -Uri "https://your-server-url/api/v1/admin/customers/customer@example.com/reset-devices" `
  -Method Post `
  -Headers @{ "X-Admin-Key" = "your-admin-api-key" }
```

## Next Upgrade

After the manual version is selling, add a Stripe webhook so paid orders create
license accounts automatically. Manual creation first is safer and much faster
to launch.
