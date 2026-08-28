# Hostinger Subdomain Setup: result.esportscounty.com

Use this when `portal.esportscounty.com` is already running on the same VPS and you want this app on `result.esportscounty.com`.

## What will happen

- `portal.esportscounty.com` stays on the current portal app.
- `result.esportscounty.com` opens ESPORTS COUNTY PUBGM Result Maker.
- Both domains point to the same VPS IP.
- The VPS reverse proxy routes each domain to the correct app.

## 1. Add the DNS record

In your domain DNS settings, add this record:

```text
Type: A
Name/Host: result
Points to: YOUR_VPS_IP
TTL: default
```

Do not remove the existing `portal` DNS record.

## 2. Upload this project to the VPS

Recommended path on VPS:

```bash
cd /opt
git clone YOUR_PRIVATE_REPO_URL pubgm-result-maker
cd /opt/pubgm-result-maker
```

If you upload manually, place the project folder at `/opt/pubgm-result-maker`.

## 3. Create the Hostinger env file

```bash
cp .env.hostinger.example .env.hostinger
nano .env.hostinger
```

Set at least these values:

```text
DOMAIN_NAME=result.esportscounty.com
DISCORD_BOT_TOKEN=your_real_discord_bot_token
DISCORD_RESULTS_EMAIL=abhiv@esportscounty.com
EC_WEB_SECRET=a-long-random-secret-you-do-not-change
EC_DATA_DIR=/data
PORT=8080
```

## 4. Start only the app container

Because the VPS already has `portal.esportscounty.com`, do not start the extra Caddy container from `docker-compose.hostinger.yml` unless this VPS has no existing proxy.

Use this file instead:

```bash
docker compose -f docker-compose.hostinger-app-only.yml up -d --build
```

It exposes the Result Maker app only inside the VPS at:

```text
http://127.0.0.1:8081
```

## 5. Add reverse proxy rule for result.esportscounty.com

If your VPS uses Caddy for the portal, add this block to the existing Caddyfile:

```caddyfile
result.esportscounty.com {
    reverse_proxy 127.0.0.1:8081
}
```

Then reload Caddy.

If your VPS uses Nginx, add a server block like this:

```nginx
server {
    listen 80;
    server_name result.esportscounty.com;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Then reload Nginx and enable SSL using the same method you used for `portal.esportscounty.com`.

## 6. Check it

```bash
docker compose -f docker-compose.hostinger-app-only.yml ps
docker compose -f docker-compose.hostinger-app-only.yml logs -f
curl http://127.0.0.1:8081/api/health
```

When DNS and the proxy are ready, open:

```text
https://result.esportscounty.com
```

## 7. Add purchased emails

```bash
docker compose -f docker-compose.hostinger-app-only.yml exec result-maker python web_admin.py allow buyer@example.com
```

The buyer can then register that email on the website.
