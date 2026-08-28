from __future__ import annotations

import getpass
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
OUT = APP_DIR / ".env.discord"


def ask(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{label}{suffix}: ").strip()
    return value or default


def clean_token(raw: str) -> str:
    token = raw.strip().strip('"').strip("'")
    if "DISCORD_BOT_TOKEN=" in token:
        token = token.split("DISCORD_BOT_TOKEN=", 1)[1].strip()
    if token.lower().startswith("bot "):
        token = token[4:].strip()
    return token.strip().strip('"').strip("'")


def looks_like_bot_token(token: str) -> bool:
    if not 50 <= len(token) <= 120:
        return False
    if token.count(".") < 2:
        return False
    if re.search(r"\s", token):
        return False
    if token.startswith("mfa."):
        return False
    return True


def main() -> None:
    print("ESPORTS COUNTY Discord Bot Setup")
    print("This saves your private bot settings to .env.discord.")
    print("Do not upload .env.discord to GitHub or share it.\n")
    print("Use Discord Developer Portal > Application > Bot > Reset Token > Copy.")
    print("Do not use Application ID, Public Key, Client Secret, or OAuth invite URL.\n")

    while True:
        token = clean_token(getpass.getpass("Paste Discord BOT TOKEN: "))
        if not token:
            raise SystemExit("Bot token is required.")
        if looks_like_bot_token(token):
            break
        print("\nThat does not look like a Discord bot token.")
        print(f"Saved length would be {len(token)} characters with {token.count('.')} dots.")
        retry = input("Paste again? [Y/n]: ").strip().lower()
        if retry in {"n", "no"}:
            break

    email = ask("Website/event email", "abhiv@esportscounty.com")
    guild_id = ask("Discord server ID for instant slash commands", "")
    channel_id = ask("Announcement channel ID (optional)", "")
    api_url = ask("Observer API URL", "http://127.0.0.1:10086/gettotalplayerlist")

    lines = [
        "# Private local Discord bot config. Do not commit this file.",
        f"DISCORD_BOT_TOKEN={token}",
        f"DISCORD_RESULTS_EMAIL={email}",
        f"DISCORD_GUILD_ID={guild_id}",
        f"DISCORD_ANNOUNCE_CHANNEL_ID={channel_id}",
        f"OBSERVER_API_URL={api_url}",
        "OBSERVER_POLL_SECONDS=3",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nSaved: {OUT}")
    print("Next: run run_discord_bot.bat, or tell Codex: done")


if __name__ == "__main__":
    main()
