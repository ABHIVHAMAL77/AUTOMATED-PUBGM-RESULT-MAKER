"""Small command-line helper for the hosted license server database.

Examples:
    python -m licensing_server.manage create customer@example.com Pass1234 --days 365
    python -m licensing_server.manage list
    python -m licensing_server.manage disable customer@example.com
"""

import argparse

from .app import (ROLE_ADMIN, ROLE_OPERATOR, db, expiry_from, fetch_customer,
                  init_db, iso, password_fields)


def create(args):
    init_db()
    salt, hashed = password_fields(args.password)
    role = args.role if args.role in (ROLE_ADMIN, ROLE_OPERATOR) else ROLE_ADMIN
    expires_at = expiry_from(args.days, args.expires_at)
    with db() as conn:
        conn.execute(
            """INSERT INTO customers
               (email, name, password_salt, password_hash, role, status,
                max_devices, license_expires_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
            (args.email.strip().lower(), args.name, salt, hashed, role,
             args.max_devices, expires_at, iso(), iso()),
        )
    print(f"created {args.email.strip().lower()} expires={expires_at or 'never'}")


def list_customers(_args):
    init_db()
    with db() as conn:
        rows = conn.execute(
            "SELECT email, role, status, max_devices, license_expires_at FROM customers "
            "ORDER BY created_at DESC"
        ).fetchall()
    for row in rows:
        print(
            f"{row['email']} | {row['role']} | {row['status']} | "
            f"{row['max_devices']} device(s) | expires {row['license_expires_at'] or 'never'}"
        )


def disable(args):
    init_db()
    with db() as conn:
        fetch_customer(conn, args.email)
        conn.execute(
            "UPDATE customers SET status = 'disabled', updated_at = ? WHERE email = ?",
            (iso(), args.email.strip().lower()),
        )
    print(f"disabled {args.email.strip().lower()}")


def set_password(args):
    init_db()
    salt, hashed = password_fields(args.password)
    with db() as conn:
        fetch_customer(conn, args.email)
        conn.execute(
            """UPDATE customers
               SET password_salt = ?, password_hash = ?, updated_at = ?
               WHERE email = ?""",
            (salt, hashed, iso(), args.email.strip().lower()),
        )
    print(f"password changed for {args.email.strip().lower()}")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)

    create_cmd = sub.add_parser("create")
    create_cmd.add_argument("email")
    create_cmd.add_argument("password")
    create_cmd.add_argument("--name", default="")
    create_cmd.add_argument("--role", default=ROLE_ADMIN)
    create_cmd.add_argument("--max-devices", type=int, default=1)
    create_cmd.add_argument("--days", type=int, default=365)
    create_cmd.add_argument("--expires-at")
    create_cmd.set_defaults(func=create)

    list_cmd = sub.add_parser("list")
    list_cmd.set_defaults(func=list_customers)

    disable_cmd = sub.add_parser("disable")
    disable_cmd.add_argument("email")
    disable_cmd.set_defaults(func=disable)

    pass_cmd = sub.add_parser("set-password")
    pass_cmd.add_argument("email")
    pass_cmd.add_argument("password")
    pass_cmd.set_defaults(func=set_password)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
