# Hostinger VPS Deployment

Use this when you want the ESPORTS COUNTY PUBGM Result Maker website and Discord bot online 24/7 from Hostinger.

## Important

Use Hostinger VPS, not normal shared/web hosting.

Shared hosting can upload static websites, but this app needs:

- Python FastAPI backend
- Manual OCR processing
- user login and saved event data
- generated result images and sheets
- a Discord bot that stays connected all day

Those need a long-running server. Hostinger VPS with Docker is the clean setup.

## 1. Choose the VPS setup

### Same VPS as portal.esportscounty.com

If `portal.esportscounty.com` already runs on this VPS, use the app-only compose file and connect it through your existing reverse proxy.

Use this for the Result Maker app:

```bash
docker compose -f docker-compose.hostinger-app-only.yml up -d --build
```

Then point your existing Caddy/Nginx/Apache proxy for `result.esportscounty.com` to:

```text
http://127.0.0.1:8081
```

See `HOSTINGER_SUBDOMAIN_SETUP.md` for the exact step-by-step setup.

### Fresh VPS only for this app

If this VPS is only for the Result Maker app, you can use the full compose file:

```bash
docker compose -f docker-compose.hostinger.yml up -d --build
```

That file starts its own Caddy reverse proxy on ports `80` and `443`.

## 2. Point your domain or subdomain

For your requested setup, create this DNS record:

```text
Type: A
Name/Host: result
Points to: your VPS IP
TTL: default
```

Keep the existing `portal` record as it is.

DNS can take up to 24 hours, but often works sooner.

## 3. Upload the project

Best way: push this project to a private GitHub repo, then on the VPS:

```bash
cd /opt
git clone YOUR_PRIVATE_REPO_URL pubgm-result-maker
cd /opt/pubgm-result-maker
```

If you do not use GitHub, upload the project folder using Hostinger file tools or SFTP.

## 4. Create env file

On the VPS:

```bash
cp .env.hostinger.example .env.hostinger
nano .env.hostinger
```

Set these values:

```text
DOMAIN_NAME=result.esportscounty.com
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DISCORD_RESULTS_EMAIL=abhiv@esportscounty.com
EC_WEB_SECRET=make-a-long-random-secret
EC_DATA_DIR=/data
PORT=8080
```

Keep `EC_WEB_SECRET` stable after launch. If you change it, users will need to log in again.

## 5. Start website and bot

For the same VPS as `portal.esportscounty.com`:

```bash
docker compose -f docker-compose.hostinger-app-only.yml up -d --build
```

For a fresh VPS only used by this app:

```bash
docker compose -f docker-compose.hostinger.yml up -d --build
```

If your VPS uses the older command, replace `docker compose` with `docker-compose`.

## 6. Add purchased emails

Same-VPS setup:

```bash
docker compose -f docker-compose.hostinger-app-only.yml exec result-maker python web_admin.py allow buyer@example.com
```

Fresh-VPS setup:

```bash
docker compose -f docker-compose.hostinger.yml exec result-maker python web_admin.py allow buyer@example.com
```

Then the buyer can register that email on your website.

## 7. Discord bot commands

After the bot is online, use:

```text
/teamss
/teamss 1
/overallss
/playerdetails
/results
/standings
/players
/event
/autostart
/autostop
/autostatus
```

## Live API warning

For `/autostart` and Live API automation, the PUBG observer API must be reachable by the Hostinger VPS.

This will not work from cloud:

```text
http://127.0.0.1:10086/gettotalplayerlist
```

unless the observer API is running on the Hostinger VPS itself.

If the observer API is on your gaming PC, you need a public URL or tunnel, then use that URL in the website/bot.

## Useful VPS commands

For same-VPS setup, replace the compose file name as needed:

```bash
docker compose -f docker-compose.hostinger-app-only.yml ps
docker compose -f docker-compose.hostinger-app-only.yml logs -f
docker compose -f docker-compose.hostinger-app-only.yml restart
docker compose -f docker-compose.hostinger-app-only.yml up -d --build
curl http://127.0.0.1:8081/api/health
```

Back up data:

```bash
docker run --rm -v pubgm-result-maker_ec_pubgm_data:/data -v "$PWD":/backup alpine tar czf /backup/ec-pubgm-data-backup.tar.gz /data
```

## Do not commit these

Never upload secrets publicly:

- `.env.hostinger`
- `data/web_users.json`
- `data/web_allowlist.json`
- `data/web_secret.key`

## Live API from the game PC

For website Live API, use **This browser** mode when the observer feed is on your gaming PC:

```text
http://127.0.0.1:10086/gettotalplayerlist
```

That makes Chrome read the local feed from the game PC and sends the JSON to Hostinger for scoring every second. If Chrome blocks the direct local read, run `run_live_bridge.bat` on the game PC and use:

```text
http://127.0.0.1:8765/gettotalplayerlist
```

For Discord `/autostart`, or for server-side polling from Hostinger, the observer API must still be reachable by the VPS through a public URL, VPN, or tunnel.
