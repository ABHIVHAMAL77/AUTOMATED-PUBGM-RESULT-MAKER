# 24/7 Cloud Discord Bot Setup

This project can run the website and Discord bot together from one always-on cloud service.
That matters because the bot reads the same event, result, export, and access files that the website writes.

## Recommended setup

Use a long-running Docker service with a persistent disk mounted at `/data`.
Good fits are Railway, Fly.io, Render, or a small VPS.
Avoid Vercel/Cloudflare serverless for this current bot because the bot uses Discord's Gateway connection and must stay online continuously.

## Required cloud variables

Set these in the cloud dashboard:

```text
DISCORD_BOT_TOKEN=your_discord_bot_token_here
DISCORD_RESULTS_EMAIL=abhiv@esportscounty.com
EC_WEB_SECRET=use-a-long-random-secret
EC_DATA_DIR=/data
PORT=8080
```

Optional:

```text
DISCORD_ANNOUNCE_CHANNEL_ID=your_channel_id
OBSERVER_API_URL=http://127.0.0.1:10086/gettotalplayerlist
OBSERVER_POLL_SECONDS=3
```

Important: on cloud, `127.0.0.1` means the cloud machine, not your laptop or game PC.
For Live API automation, the PUBG observer API must be reachable by the cloud server through a public HTTPS URL, VPN, or tunnel.
Manual OCR uploads and saved results work normally from the website.

## Discord permissions

In the Discord Developer Portal, invite the bot with:

- Scope: `bot`
- Scope: `applications.commands`
- Permissions: `View Channels`, `Send Messages`, `Attach Files`, `Read Message History`, `Use Application Commands`
- Bot intent: enable `Message Content Intent` if you want `!` commands or mention commands

## Railway quick path

1. Push this project to GitHub.
2. Create a Railway project from that repo.
3. Railway will use the `Dockerfile`.
4. Add a Volume and mount it at `/data`.
5. Add the required variables above.
6. Set health check path to `/api/health` if Railway does not read `railway.toml` automatically.
7. Deploy one replica only.

## Fly.io quick path

1. Copy `fly.example.toml` to `fly.toml`.
2. Change the `app` name to a unique name.
3. Create a volume named `ec_pubgm_data` in the same region.
4. Set secrets:

```bash
fly secrets set DISCORD_BOT_TOKEN="your_token" DISCORD_RESULTS_EMAIL="abhiv@esportscounty.com" EC_WEB_SECRET="long_random_secret"
```

5. Deploy:

```bash
fly deploy
```

Keep `auto_stop_machines = "off"` so the Discord bot stays online.

## VPS quick path

On a Linux VPS with Docker:

```bash
git clone <your-repo-url>
cd "PUBGM Results Engine"
cp .env.cloud.example .env.cloud
nano .env.cloud
docker compose up -d --build
```

The app will run on port `8080`. Put Nginx or Cloudflare Tunnel in front of it if you want HTTPS and a domain.

## Bot commands

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

## Safety notes

- Keep only one running instance of the bot token.
- Back up `/data` regularly.
- Do not put `DISCORD_BOT_TOKEN`, `EC_WEB_SECRET`, `web_users.json`, or `web_allowlist.json` in GitHub.
