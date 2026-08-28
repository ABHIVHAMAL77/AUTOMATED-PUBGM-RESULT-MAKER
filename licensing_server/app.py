"""FastAPI license server for PUBGM Results Engine customers.

Deploy this folder to a Python host, set LICENSE_SECRET_KEY and ADMIN_API_KEY,
then create customer accounts through the admin endpoints.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

DB_PATH = Path(os.environ.get("LICENSE_DB", "licenses.sqlite3"))
SECRET_KEY = os.environ.get("LICENSE_SECRET_KEY", "change-me-before-deploying")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")
TOKEN_HOURS = int(os.environ.get("TOKEN_HOURS", "24"))
ITERATIONS = 200_000
ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"

app = FastAPI(title="PUBGM Results Engine License Server", version="1.0")


class LoginRequest(BaseModel):
    email: str
    password: str
    deviceId: str = Field(min_length=6)
    appVersion: str = "desktop"


class CustomerCreate(BaseModel):
    email: str
    password: str = Field(min_length=6)
    name: str = ""
    role: str = ROLE_ADMIN
    status: str = "active"
    maxDevices: int = Field(default=1, ge=1, le=10)
    licenseDays: int | None = Field(default=365, ge=1)
    licenseExpiresAt: str | None = None


class CustomerUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=6)
    name: str | None = None
    role: str | None = None
    status: str | None = None
    maxDevices: int | None = Field(default=None, ge=1, le=10)
    licenseDays: int | None = Field(default=None, ge=1)
    licenseExpiresAt: str | None = None


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime | None = None) -> str:
    dt = dt or now_utc()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def expiry_from(days: int | None, explicit: str | None) -> str | None:
    if explicit:
        return iso(parse_time(explicit))
    if days:
        return iso(now_utc() + timedelta(days=days))
    return None


def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            name TEXT NOT NULL DEFAULT '',
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            status TEXT NOT NULL DEFAULT 'active',
            max_devices INTEGER NOT NULL DEFAULT 1,
            license_expires_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            device_id TEXT NOT NULL,
            app_version TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE(customer_id, device_id),
            FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE
        );
        """)


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
    ).hex()


def password_fields(password: str) -> tuple[str, str]:
    salt = secrets.token_hex(16)
    return salt, hash_password(password, salt)


def check_password(password: str, customer: sqlite3.Row) -> bool:
    expected = hash_password(password, customer["password_salt"])
    return hmac.compare_digest(expected, customer["password_hash"])


def require_admin_key(x_admin_key: Annotated[str, Header()] = ""):
    if not ADMIN_API_KEY or not hmac.compare_digest(x_admin_key, ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid admin API key.")


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def make_token(customer: sqlite3.Row) -> str:
    payload = {
        "sub": customer["id"],
        "email": customer["email"],
        "role": customer["role"],
        "exp": int((now_utc() + timedelta(hours=TOKEN_HOURS)).timestamp()),
    }
    body = b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = b64(hmac.new(SECRET_KEY.encode("utf-8"), body.encode("ascii"),
                       hashlib.sha256).digest())
    return f"{body}.{sig}"


def read_token(authorization: Annotated[str, Header()] = "") -> sqlite3.Row:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        body, sig = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid token.") from exc
    expected = b64(hmac.new(SECRET_KEY.encode("utf-8"), body.encode("ascii"),
                            hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=401, detail="Invalid token.")
    try:
        payload = json.loads(unb64(body))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token.") from exc
    if int(payload.get("exp", 0)) < int(now_utc().timestamp()):
        raise HTTPException(status_code=401, detail="Token expired.")
    with db() as conn:
        customer = conn.execute(
            "SELECT * FROM customers WHERE id = ?", (payload.get("sub"),)
        ).fetchone()
    if customer is None:
        raise HTTPException(status_code=401, detail="Customer not found.")
    ensure_customer_can_login(customer)
    return customer


def ensure_customer_can_login(customer: sqlite3.Row):
    if customer["status"] != "active":
        raise HTTPException(status_code=403, detail="This license is not active.")
    expires_at = parse_time(customer["license_expires_at"])
    if expires_at and expires_at < now_utc():
        raise HTTPException(status_code=403, detail="This license has expired.")


def public_customer(customer: sqlite3.Row) -> dict:
    return {
        "email": customer["email"],
        "name": customer["name"],
        "role": customer["role"],
        "status": customer["status"],
    }


def license_payload(customer: sqlite3.Row) -> dict:
    return {
        "status": customer["status"],
        "maxDevices": customer["max_devices"],
        "expiresAt": customer["license_expires_at"],
    }


def customer_response(customer: sqlite3.Row) -> dict:
    return {"user": public_customer(customer), "license": license_payload(customer)}


def fetch_customer(conn: sqlite3.Connection, email: str) -> sqlite3.Row:
    customer = conn.execute("SELECT * FROM customers WHERE email = ?",
                            (email.strip().lower(),)).fetchone()
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    return customer


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"ok": True, "service": "pubgm-license-server"}


@app.post("/api/v1/login")
def login(req: LoginRequest):
    init_db()
    email = req.email.strip().lower()
    with db() as conn:
        customer = conn.execute("SELECT * FROM customers WHERE email = ?",
                                (email,)).fetchone()
        if customer is None or not check_password(req.password, customer):
            raise HTTPException(status_code=401, detail="Wrong email or password.")
        ensure_customer_can_login(customer)
        device = conn.execute(
            "SELECT * FROM devices WHERE customer_id = ? AND device_id = ?",
            (customer["id"], req.deviceId),
        ).fetchone()
        if device is None:
            count = conn.execute(
                "SELECT COUNT(*) FROM devices WHERE customer_id = ?",
                (customer["id"],),
            ).fetchone()[0]
            if count >= customer["max_devices"]:
                raise HTTPException(
                    status_code=403,
                    detail="Device limit reached. Ask support to reset your license devices.",
                )
            conn.execute(
                """INSERT INTO devices
                   (customer_id, device_id, app_version, created_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (customer["id"], req.deviceId, req.appVersion, iso(), iso()),
            )
        else:
            conn.execute(
                "UPDATE devices SET app_version = ?, last_seen_at = ? WHERE id = ?",
                (req.appVersion, iso(), device["id"]),
            )
        customer = fetch_customer(conn, email)
    payload = customer_response(customer)
    payload["accessToken"] = make_token(customer)
    return payload


@app.get("/api/v1/me")
def me(customer: Annotated[sqlite3.Row, Depends(read_token)]):
    return customer_response(customer)


@app.post("/api/v1/admin/customers", dependencies=[Depends(require_admin_key)])
def create_customer(req: CustomerCreate):
    init_db()
    role = req.role if req.role in (ROLE_ADMIN, ROLE_OPERATOR) else ROLE_ADMIN
    status = req.status if req.status in ("active", "disabled") else "active"
    salt, hashed = password_fields(req.password)
    email = req.email.strip().lower()
    expires_at = expiry_from(req.licenseDays, req.licenseExpiresAt)
    with db() as conn:
        try:
            conn.execute(
                """INSERT INTO customers
                   (email, name, password_salt, password_hash, role, status,
                    max_devices, license_expires_at, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (email, req.name.strip(), salt, hashed, role, status, req.maxDevices,
                 expires_at, iso(), iso()),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Customer already exists.") from exc
        customer = fetch_customer(conn, email)
    return customer_response(customer)


@app.get("/api/v1/admin/customers", dependencies=[Depends(require_admin_key)])
def list_customers():
    init_db()
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM customers ORDER BY created_at DESC"
        ).fetchall()
    return [customer_response(row) for row in rows]


@app.patch("/api/v1/admin/customers/{email:path}", dependencies=[Depends(require_admin_key)])
def update_customer(email: str, req: CustomerUpdate):
    init_db()
    updates = []
    values = []
    if req.password:
        salt, hashed = password_fields(req.password)
        updates += ["password_salt = ?", "password_hash = ?"]
        values += [salt, hashed]
    if req.name is not None:
        updates.append("name = ?")
        values.append(req.name.strip())
    if req.role is not None:
        if req.role not in (ROLE_ADMIN, ROLE_OPERATOR):
            raise HTTPException(status_code=400, detail="Invalid role.")
        updates.append("role = ?")
        values.append(req.role)
    if req.status is not None:
        if req.status not in ("active", "disabled"):
            raise HTTPException(status_code=400, detail="Invalid status.")
        updates.append("status = ?")
        values.append(req.status)
    if req.maxDevices is not None:
        updates.append("max_devices = ?")
        values.append(req.maxDevices)
    if req.licenseDays is not None or req.licenseExpiresAt is not None:
        updates.append("license_expires_at = ?")
        values.append(expiry_from(req.licenseDays, req.licenseExpiresAt))
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")
    updates.append("updated_at = ?")
    values.append(iso())
    values.append(email.strip().lower())
    with db() as conn:
        fetch_customer(conn, email)
        conn.execute(f"UPDATE customers SET {', '.join(updates)} WHERE email = ?", values)
        customer = fetch_customer(conn, email)
    return customer_response(customer)


@app.post("/api/v1/admin/customers/{email:path}/reset-devices",
          dependencies=[Depends(require_admin_key)])
def reset_devices(email: str):
    init_db()
    with db() as conn:
        customer = fetch_customer(conn, email)
        conn.execute("DELETE FROM devices WHERE customer_id = ?", (customer["id"],))
    return {"ok": True}
