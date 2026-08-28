"""Online license authentication for sellable desktop builds.

Set ``licenseServerUrl`` in data/settings.json, or set the
PUBGM_LICENSE_SERVER_URL environment variable, to make the app log in against
your hosted license server instead of local data/users.json accounts.
"""

import json
import os
import secrets
from pathlib import Path
from urllib.parse import urljoin

import requests

from .auth import ROLE_ADMIN, ROLE_OPERATOR

DEVICE_FILE = "device.json"
SESSION_FILE = "license_session.json"
TIMEOUT_SECONDS = 15


def configured_license_server_url(settings: dict) -> str:
    """Return the configured hosted auth URL, with environment taking priority."""
    return (os.environ.get("PUBGM_LICENSE_SERVER_URL")
            or settings.get("licenseServerUrl", "") or "").strip().rstrip("/")


class RemoteAuthManager:
    """Client for the hosted licensing server.

    The public shape intentionally matches the local AuthManager.verify()
    method so LoginDialog can use either implementation.
    """

    login_label = "Email:"
    login_hint = "Use the email and password from your purchase/license account."

    def __init__(self, data_dir, server_url: str):
        self.data_dir = Path(data_dir)
        self.server_url = server_url.rstrip("/")
        self.device_id = self._load_device_id()
        self.session_file = self.data_dir / SESSION_FILE
        self.last_error = ""

    def _load_device_id(self) -> str:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        path = self.data_dir / DEVICE_FILE
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                device_id = str(data.get("deviceId", "")).strip()
                if device_id:
                    return device_id
            except (json.JSONDecodeError, OSError):
                pass
        device_id = secrets.token_hex(16)
        path.write_text(json.dumps({"deviceId": device_id}, indent=2), encoding="utf-8")
        return device_id

    def _endpoint(self, path: str) -> str:
        return urljoin(self.server_url + "/", path.lstrip("/"))

    def verify(self, username: str, password: str) -> dict | None:
        self.last_error = ""
        try:
            resp = requests.post(
                self._endpoint("/api/v1/login"),
                json={
                    "email": username.strip(),
                    "password": password,
                    "deviceId": self.device_id,
                    "appVersion": "desktop",
                },
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            self.last_error = f"Cannot reach license server: {exc}"
            return None

        if resp.status_code != 200:
            self.last_error = self._error_from_response(resp)
            return None

        try:
            data = resp.json()
        except ValueError:
            self.last_error = "License server returned an invalid response."
            return None

        token = data.get("accessToken") or data.get("access_token")
        user = data.get("user") or {}
        email = user.get("email") or username.strip()
        role = user.get("role") or ROLE_ADMIN
        if role not in (ROLE_ADMIN, ROLE_OPERATOR):
            role = ROLE_ADMIN

        self._save_session(data)
        return {
            "username": email,
            "role": role,
            "license": data.get("license", {}),
            "accessToken": token,
        }

    def _save_session(self, data: dict):
        try:
            self.session_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _error_from_response(resp: requests.Response) -> str:
        try:
            data = resp.json()
            detail = data.get("detail")
            if isinstance(detail, str) and detail:
                return detail
        except ValueError:
            pass
        if resp.status_code == 401:
            return "Wrong email or password."
        if resp.status_code == 403:
            return "This license is inactive, expired, or over the device limit."
        return f"License login failed ({resp.status_code})."
