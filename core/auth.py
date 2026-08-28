"""Local user accounts with hashed passwords.

Accounts live in data/users.json. Passwords are stored as PBKDF2-HMAC-SHA256
hashes with a per-user random salt — never in plain text. Roles:

    admin     full access: event setup, exports, deleting matches, user management
    operator  run matches and save results only

Honest note: this protects against operators/staff using features they should
not, but someone with full file access to the PC could delete users.json to
reset it. For remote, revocable access control an online auth server would be
needed.
"""

import hashlib
import json
import secrets
from datetime import datetime
from pathlib import Path

ITERATIONS = 200_000
ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"


class AuthError(Exception):
    pass


class AuthManager:
    def __init__(self, data_dir):
        self.file = Path(data_dir) / "users.json"
        self.file.parent.mkdir(parents=True, exist_ok=True)
        self.users = self._load()

    def _load(self) -> list:
        if self.file.exists():
            try:
                return json.loads(self.file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def save(self):
        self.file.write_text(json.dumps(self.users, indent=2), encoding="utf-8")

    # ---- helpers -----------------------------------------------------------
    @staticmethod
    def _hash(password: str, salt_hex: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"),
            bytes.fromhex(salt_hex), ITERATIONS).hex()

    def _find(self, username: str) -> dict | None:
        uname = username.strip().lower()
        for u in self.users:
            if u["username"].lower() == uname:
                return u
        return None

    def has_users(self) -> bool:
        return bool(self.users)

    def admin_count(self) -> int:
        return sum(1 for u in self.users if u["role"] == ROLE_ADMIN)

    # ---- operations ---------------------------------------------------------
    def add_user(self, username: str, password: str, role: str):
        username = username.strip()
        if len(username) < 3:
            raise AuthError("Username must be at least 3 characters.")
        if len(password) < 4:
            raise AuthError("Password must be at least 4 characters.")
        if role not in (ROLE_ADMIN, ROLE_OPERATOR):
            raise AuthError(f"Unknown role: {role}")
        if self._find(username):
            raise AuthError(f"User '{username}' already exists.")
        salt = secrets.token_hex(16)
        self.users.append({
            "username": username,
            "salt": salt,
            "hash": self._hash(password, salt),
            "role": role,
            "createdAt": datetime.now().isoformat(timespec="seconds"),
        })
        self.save()

    def verify(self, username: str, password: str) -> dict | None:
        u = self._find(username)
        if u is None:
            return None
        if secrets.compare_digest(self._hash(password, u["salt"]), u["hash"]):
            return {"username": u["username"], "role": u["role"]}
        return None

    def remove_user(self, username: str, acting_user: str):
        u = self._find(username)
        if u is None:
            raise AuthError(f"User '{username}' not found.")
        if u["username"].lower() == acting_user.strip().lower():
            raise AuthError("You cannot delete the account you are logged in with.")
        if u["role"] == ROLE_ADMIN and self.admin_count() <= 1:
            raise AuthError("Cannot delete the last admin account.")
        self.users.remove(u)
        self.save()

    def set_password(self, username: str, new_password: str):
        u = self._find(username)
        if u is None:
            raise AuthError(f"User '{username}' not found.")
        if len(new_password) < 4:
            raise AuthError("Password must be at least 4 characters.")
        u["salt"] = secrets.token_hex(16)
        u["hash"] = self._hash(new_password, u["salt"])
        self.save()

    def list_users(self) -> list:
        return [{"username": u["username"], "role": u["role"],
                 "createdAt": u.get("createdAt", "")} for u in self.users]
