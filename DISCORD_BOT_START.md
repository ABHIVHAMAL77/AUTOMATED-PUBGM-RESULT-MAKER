# Start Discord Bot

Your bot is already invited to the Discord server. Now it needs the bot token on this machine or on Hostinger VPS.

## Local test on this laptop

1. Double-click `setup_discord_env.bat`.
2. Paste your Discord bot token.
3. Enter `abhiv@esportscounty.com` as the website/event email unless you want another registered email.
4. Enter your Discord server ID for instant slash command sync.
5. Channel ID is optional.
6. Double-click `run_discord_bot.bat`.
7. In Discord, type `/event` to confirm the bot is connected.

Do not paste the bot token into chat. Do not upload `.env.discord`.

## Get Discord server ID

1. Discord User Settings.
2. Advanced.
3. Enable Developer Mode.
4. Right-click your server name.
5. Copy Server ID.

## Test commands

```text
/event
/results
/standings
/players
/teamss
/overallss
/playerdetails
```

If commands do not appear immediately, set `DISCORD_GUILD_ID` in `.env.discord`, restart the bot, then reopen Discord.

## Hostinger VPS

Use the same values in `.env.hostinger` on the VPS:

```text
DISCORD_BOT_TOKEN=your_token
DISCORD_RESULTS_EMAIL=abhiv@esportscounty.com
DISCORD_GUILD_ID=your_server_id
```

Then deploy with:

```bash
docker compose -f docker-compose.hostinger.yml up -d --build
```
