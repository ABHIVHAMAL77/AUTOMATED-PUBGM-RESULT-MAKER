# Deployment Steps Done

This file records the step-by-step setup used to publish ESPORTS COUNTY PUBGM Result Maker from GitHub to a Hostinger VPS.

Live website:

```text
https://result.esportscounty.com
```

GitHub repository:

```text
https://github.com/ABHIVHAMAL77/AUTOMATED-PUBGM-RESULT-MAKER.git
```

Private values such as the VPS IP, Discord bot token, and website secret are intentionally replaced with placeholders.

## 1. GitHub Project Setup

The local project was converted into a clean Git repo and pushed to GitHub.

```bash
git init -b main
git add .
git commit -m "Initial ESPORTS COUNTY PUBG Mobile result maker"
git remote add origin https://github.com/ABHIVHAMAL77/AUTOMATED-PUBGM-RESULT-MAKER.git
git push -u origin main
```

Private files excluded from GitHub:

```text
.env.discord
.env.hostinger
.env.cloud
data/
*.zip
```

## 2. VPS Login

The VPS terminal was opened using SSH:

```bash
ssh root@YOUR_VPS_IP
```

The server setup was checked:

```bash
docker ps
docker compose version
git --version
ls /etc/nginx/sites-enabled
cat /etc/nginx/sites-enabled/portal
```

Existing portal route found:

```text
portal.esportscounty.com -> Nginx -> http://localhost:3000
```

So the result maker was deployed separately on port `8081`.

## 3. DNS Setup

In Hostinger DNS, this record was added:

```text
Type: A
Name/Host: result
Points to: YOUR_VPS_IP
TTL: default
```

The existing `portal` DNS record was not changed.

## 4. Clone Project On VPS

The GitHub repo was cloned on the VPS:

```bash
cd ~
git clone https://github.com/ABHIVHAMAL77/AUTOMATED-PUBGM-RESULT-MAKER.git pubgm-result-maker
cd ~/pubgm-result-maker
ls
```

Expected project files:

```text
Dockerfile
docker-compose.hostinger-app-only.yml
web_app.py
discord_bot.py
HOSTINGER_SUBDOMAIN_SETUP.md
```

## 5. Create Hostinger Env File

The private live environment file was created on the VPS:

```bash
cd ~/pubgm-result-maker
cp .env.hostinger.example .env.hostinger
nano .env.hostinger
```

Example values:

```text
DOMAIN_NAME=result.esportscounty.com
DISCORD_BOT_TOKEN=YOUR_PRIVATE_DISCORD_BOT_TOKEN
DISCORD_RESULTS_EMAIL=YOUR_OWNER_EMAIL
EC_WEB_SECRET=YOUR_LONG_PRIVATE_SECRET
EC_DATA_DIR=/data
PORT=8080
```

Safe check without printing the token:

```bash
grep -v TOKEN .env.hostinger
```

## 6. Start Website And Bot With Docker

The app-only Docker Compose file was used because the VPS already had a portal using Nginx.

```bash
cd ~/pubgm-result-maker
docker compose -f docker-compose.hostinger-app-only.yml up -d --build
```

Check container:

```bash
docker compose -f docker-compose.hostinger-app-only.yml ps
```

Expected port mapping:

```text
127.0.0.1:8081->8080/tcp
```

Health check inside VPS:

```bash
curl http://127.0.0.1:8081/api/health
```

Expected result:

```json
{"ok":true,"service":"ec-pubgm-result-maker"}
```

## 7. Add Nginx Site For Subdomain

A separate Nginx config was created for `result.esportscounty.com`:

```bash
cat > /etc/nginx/sites-available/result <<'EOF'
server {
    listen 80;
    server_name result.esportscounty.com;
    client_max_body_size 30m;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
EOF
```

Enable site and reload Nginx:

```bash
ln -s /etc/nginx/sites-available/result /etc/nginx/sites-enabled/result
nginx -t
systemctl reload nginx
```

Public HTTP test:

```bash
curl http://result.esportscounty.com/api/health
```

## 8. Enable HTTPS SSL

Certbot was used to add HTTPS:

```bash
certbot --nginx -d result.esportscounty.com
```

HTTPS test:

```bash
curl https://result.esportscounty.com/api/health
```

Expected result:

```json
{"ok":true,"service":"ec-pubgm-result-maker"}
```

## 9. Allow Owner Email To Register

The owner email was added to the approved registration list:

```bash
cd ~/pubgm-result-maker
docker compose -f docker-compose.hostinger-app-only.yml exec result-maker python web_admin.py allow YOUR_OWNER_EMAIL
```

Check approved emails:

```bash
docker compose -f docker-compose.hostinger-app-only.yml exec result-maker python web_admin.py list
```

## 10. Worker And Buyer Email Process

Add worker or buyer email:

```bash
cd ~/pubgm-result-maker
docker compose -f docker-compose.hostinger-app-only.yml exec result-maker python web_admin.py allow worker@email.com
```

Then the worker/buyer can register on:

```text
https://result.esportscounty.com
```

See all approved emails:

```bash
docker compose -f docker-compose.hostinger-app-only.yml exec result-maker python web_admin.py list
```

See registered users:

```bash
docker compose -f docker-compose.hostinger-app-only.yml exec result-maker python web_admin.py users
```

Remove someone fully:

```bash
docker compose -f docker-compose.hostinger-app-only.yml exec result-maker python web_admin.py revoke worker@email.com
```

## 11. Share An Event With Workers

If a worker needs access to the owner event:

```text
1. Owner logs in at https://result.esportscounty.com
2. Open Events
3. Select the event
4. Open Event access
5. Add worker email
```

That worker can then log in and work on the shared event.

## 12. Check Logs

Check app and Discord bot logs:

```bash
cd ~/pubgm-result-maker
docker compose -f docker-compose.hostinger-app-only.yml logs --tail=80 result-maker
```

Follow live logs:

```bash
docker compose -f docker-compose.hostinger-app-only.yml logs -f result-maker
```

Expected bot line:

```text
Discord bot logged in as ESPORTS COUNTY Result Bot
```

## 13. Update VPS From GitHub

Whenever code is changed and pushed to GitHub, update VPS like this:

```bash
cd ~/pubgm-result-maker
git pull
docker compose -f docker-compose.hostinger-app-only.yml up -d --build
```

Then test:

```bash
curl https://result.esportscounty.com/api/health
```

## 14. Current Git Commit History

View commit text one by one:

```bash
git log --pretty=format:"%h | %ad | %s" --date=short
```

Important commits:

```text
Show hosted OCR as online in website UI
Add registered user management commands
Respect deployment data directory in web admin helper
Initial ESPORTS COUNTY PUBG Mobile result maker
```

## 15. Important URLs

Website:

```text
https://result.esportscounty.com
```

Health check:

```text
https://result.esportscounty.com/api/health
```

GitHub:

```text
https://github.com/ABHIVHAMAL77/AUTOMATED-PUBGM-RESULT-MAKER
```
