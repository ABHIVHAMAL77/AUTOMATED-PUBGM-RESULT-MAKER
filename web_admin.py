"""Backend helper for manually approving purchased users.

Examples:
    python web_admin.py allow buyer@example.com
    python web_admin.py remove buyer@example.com
    python web_admin.py revoke buyer@example.com
    python web_admin.py list
    python web_admin.py users
"""

import argparse
import json
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("EC_DATA_DIR", Path(__file__).resolve().parent / "data"))
ALLOWLIST_FILE = DATA_DIR / "web_allowlist.json"
USERS_FILE = DATA_DIR / "web_users.json"


def normalize(email: str) -> str:
    return email.strip().lower()


def load() -> list[str]:
    if ALLOWLIST_FILE.exists():
        data = json.loads(ALLOWLIST_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data = data.get("emails", [])
        return sorted({normalize(str(email)) for email in data if str(email).strip()})
    return []


def save(emails: list[str]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ALLOWLIST_FILE.write_text(
        json.dumps(sorted(set(emails)), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def load_users() -> list[dict]:
    if USERS_FILE.exists():
        data = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def save_users(users: list[dict]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(
        json.dumps(users, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def allow(args):
    emails = load()
    email = normalize(args.email)
    if email not in emails:
        emails.append(email)
        save(emails)
    print(f"allowed: {email}")


def remove(args):
    email = normalize(args.email)
    emails = [item for item in load() if item != email]
    save(emails)
    print(f"removed from registration list: {email}")


def revoke(args):
    email = normalize(args.email)
    emails = [item for item in load() if item != email]
    users = [user for user in load_users() if normalize(str(user.get("email", ""))) != email]
    save(emails)
    save_users(users)
    print(f"revoked login access: {email}")


def list_emails(_args):
    for email in load():
        print(email)


def list_users(_args):
    for user in load_users():
        email = normalize(str(user.get("email", "")))
        if email:
            name = str(user.get("name", "")).strip()
            print(f"{email}\t{name}" if name else email)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)

    allow_cmd = sub.add_parser("allow")
    allow_cmd.add_argument("email")
    allow_cmd.set_defaults(func=allow)

    remove_cmd = sub.add_parser("remove")
    remove_cmd.add_argument("email")
    remove_cmd.set_defaults(func=remove)

    revoke_cmd = sub.add_parser("revoke")
    revoke_cmd.add_argument("email")
    revoke_cmd.set_defaults(func=revoke)

    list_cmd = sub.add_parser("list")
    list_cmd.set_defaults(func=list_emails)

    users_cmd = sub.add_parser("users")
    users_cmd.set_defaults(func=list_users)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
