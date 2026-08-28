"""Web version of ESPORTS COUNTY PUBGM RESULT MAKER.

Run locally:
    python -m uvicorn web_app:app --host 127.0.0.1 --port 8080 --reload

Purchased users are controlled with data/web_allowlist.json. Use:
    python web_admin.py allow buyer@example.com
"""

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Annotated

import requests
from fastapi import Cookie, Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field

from core import graphic_themes, result_graphic
from core.event_manager import EventManager
from core.match_tracker import MatchTracker
from core.mock_data import MockDataGenerator
from core.models import parse_snapshot
from core.ocr_pipeline import engine_status, run_results_ocr, run_roster_ocr
from core.ocr_roster import warm_up as warm_up_ocr
from core.scoring import DEFAULT_POINT_SYSTEM, placement_points
from core.sheet_export import export_tournament_sheet

APP_DIR = Path(__file__).resolve().parent
def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


for env_name in (".env", ".env.discord", ".env.hostinger", ".env.cloud"):
    load_env_file(APP_DIR / env_name)

DATA_DIR = Path(os.environ.get("EC_DATA_DIR") or (APP_DIR / "data"))
WEB_DIR = APP_DIR / "web"
WEB_DATA_DIR = DATA_DIR / "web"
WEB_UPLOAD_DIR = DATA_DIR / "web_uploads"
ALLOWLIST_FILE = DATA_DIR / "web_allowlist.json"
USERS_FILE = DATA_DIR / "web_users.json"
SECRET_FILE = DATA_DIR / "web_secret.key"
COOKIE_NAME = "ec_result_maker"
SESSION_SECONDS = 60 * 60 * 24 * 14
ITERATIONS = 200_000
LEGACY_EVENT_ID = "legacy"
EVENTS_DIR_NAME = "events"
ACTIVE_EVENT_FILE_NAME = "active_event.json"
EVENT_ACCESS_FILE_NAME = "access.json"
SHARED_REF_SEP = "::"
EVENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")

app = FastAPI(title="ESPORTS COUNTY PUBGM RESULT MAKER")

# The front-end is a Vite build. `npm run build` in web/ produces web/dist,
# which is what gets served; run_web.bat builds it if it is missing.
WEB_DIST = WEB_DIR / "dist"
if (WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

api_states: dict[str, dict] = {}


@app.on_event("startup")
def _warm_ocr() -> None:
    """Load the OCR models at boot.

    Model load costs several seconds. Paying it inside the first upload of a
    session makes that upload look hung, right at the moment the operator is
    deciding whether the tool works.
    """
    warm_up_ocr()


class RegisterPayload(BaseModel):
    email: str
    password: str = Field(min_length=6)
    name: str = ""


class LoginPayload(BaseModel):
    email: str
    password: str


class EventCreatePayload(BaseModel):
    eventName: str = Field(default="My PUBGM Event", min_length=1, max_length=120)
    stage: str = ""
    totalMatches: int = Field(default=6, ge=1, le=99)


class EventSelectPayload(BaseModel):
    eventId: str


class EventAccessPayload(BaseModel):
    email: str


class EventPayload(BaseModel):
    eventName: str = "My PUBGM Event"
    stage: str = ""
    totalMatches: int = Field(default=6, ge=1, le=99)
    placementPoints: list[int] = Field(default_factory=lambda: [10, 6, 5, 4, 3, 2, 1, 1])
    killPoint: int = Field(default=1, ge=0, le=10)
    teams: list[dict] = Field(default_factory=list)


class PlayerPayload(BaseModel):
    name: str = ""
    kills: int = Field(default=0, ge=0, le=99)


class ManualTeamPayload(BaseModel):
    rank: int = Field(ge=1, le=100)
    slot: int = Field(ge=1, le=100)
    teamName: str
    kills: int = Field(default=0, ge=0, le=999)
    players: list[PlayerPayload] = Field(default_factory=list)


class ManualMatchPayload(BaseModel):
    matchNumber: int = Field(ge=1, le=99)
    map: str = "Erangel"
    teams: list[ManualTeamPayload]


class ApiPollPayload(BaseModel):
    apiUrl: str = "http://127.0.0.1:10086/gettotalplayerlist"
    mockMode: bool = False
    reset: bool = False


class ApiIngestPayload(BaseModel):
    data: dict = Field(default_factory=dict)
    sourceKey: str = "browser-local"
    reset: bool = False


class ApiSavePayload(BaseModel):
    matchNumber: int = Field(ge=1, le=99)
    map: str = "Erangel"


class GraphicsPayload(BaseModel):
    template: str = "midnight-gold"
    accent: str = ""
    text: str = ""
    title: str = ""
    logoPosition: str = "top-right"
    showLogo: bool = True
    scrim: int | None = Field(default=None, ge=0, le=255)
    layout: str = ""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def clean_hex(value: str) -> str:
    """Keep a #rrggbb colour or nothing. The renderer falls back to the
    template's own colour for an empty string, so rejecting junk here means a
    bad value can never reach the drawing code."""
    text = str(value or "").strip()
    return text if re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", text) else ""


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return default


def save_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_allowlist() -> set[str]:
    data = load_json(ALLOWLIST_FILE, [])
    if isinstance(data, dict):
        data = data.get("emails", [])
    return {normalize_email(str(email)) for email in data if str(email).strip()}


def load_users() -> list[dict]:
    return load_json(USERS_FILE, [])


def save_users(users: list[dict]):
    save_json(USERS_FILE, users)


def secret_key() -> bytes:
    env_secret = os.environ.get("EC_WEB_SECRET", "").strip()
    if env_secret:
        return env_secret.encode("utf-8")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SECRET_FILE.exists():
        return SECRET_FILE.read_bytes()
    key = secrets.token_bytes(32)
    SECRET_FILE.write_bytes(key)
    return key


def password_hash(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), ITERATIONS
    ).hex()


def find_user(email: str) -> dict | None:
    email = normalize_email(email)
    for user in load_users():
        if normalize_email(user.get("email", "")) == email:
            return user
    return None


def make_session(email: str) -> str:
    payload = {"email": normalize_email(email), "exp": int(time.time()) + SESSION_SECONDS}
    body = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    sig = hmac.new(secret_key(), body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def read_session(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    body, sig = token.split(".", 1)
    expected = hmac.new(secret_key(), body.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        raw = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return normalize_email(payload.get("email", ""))


def require_user(ec_result_maker: Annotated[str | None, Cookie()] = None) -> str:
    email = read_session(ec_result_maker)
    if not email or find_user(email) is None:
        raise HTTPException(status_code=401, detail="Login required.")
    return email


def user_slug(email: str) -> str:
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()[:16]


def user_data_root(email: str) -> Path:
    return WEB_DATA_DIR / user_slug(email)


def active_event_file(email: str) -> Path:
    return user_data_root(email) / ACTIVE_EVENT_FILE_NAME


def event_access_file(event_dir: Path) -> Path:
    return event_dir / EVENT_ACCESS_FILE_NAME


def legacy_event_exists(root: Path) -> bool:
    results_dir = root / "results"
    return (
        (root / "event.json").exists()
        or any(results_dir.glob("match_*.json"))
        or (root / "exports" / "Tournament Sheet.xlsx").exists()
    )


def event_dir_for_owner(owner_email: str, event_id: str | None) -> Path:
    root = user_data_root(owner_email)
    if not event_id or event_id == LEGACY_EVENT_ID:
        return root
    if not EVENT_ID_RE.fullmatch(event_id):
        raise HTTPException(status_code=400, detail="Invalid event id.")
    return root / EVENTS_DIR_NAME / event_id


def event_dir_for(email: str, event_id: str) -> Path:
    return event_dir_for_owner(email, event_id)


def owned_event_ids(email: str) -> list[str]:
    root = user_data_root(email)
    ids: list[str] = []
    if legacy_event_exists(root):
        ids.append(LEGACY_EVENT_ID)
    events_dir = root / EVENTS_DIR_NAME
    if events_dir.exists():
        for child in sorted(events_dir.iterdir(), key=lambda p: p.name):
            if child.is_dir() and EVENT_ID_RE.fullmatch(child.name) and (child / "event.json").exists():
                ids.append(child.name)
    return ids


def event_ref_id(owner_email: str, event_id: str, viewer_email: str) -> str:
    owner = normalize_email(owner_email)
    viewer = normalize_email(viewer_email)
    if owner == viewer:
        return event_id
    return f"{user_slug(owner)}{SHARED_REF_SEP}{event_id}"


def load_event_access(event_dir: Path, owner_email: str) -> dict:
    data = load_json(event_access_file(event_dir), {})
    owner = normalize_email(owner_email)
    shared_raw = []
    if isinstance(data, dict):
        stored_owner = normalize_email(str(data.get("ownerEmail") or ""))
        if stored_owner:
            owner = stored_owner
        shared_raw = data.get("sharedEmails") or []
    shared = {
        normalize_email(str(item))
        for item in shared_raw
        if normalize_email(str(item)) and normalize_email(str(item)) != owner
    }
    return {"ownerEmail": owner, "sharedEmails": sorted(shared)}


def save_event_access(event_dir: Path, owner_email: str, shared_emails: list[str] | set[str]) -> None:
    owner = normalize_email(owner_email)
    shared = sorted({
        normalize_email(str(item))
        for item in shared_emails
        if normalize_email(str(item)) and normalize_email(str(item)) != owner
    })
    save_json(event_access_file(event_dir), {
        "ownerEmail": owner,
        "sharedEmails": shared,
        "updatedAt": utc_now(),
    })


def purchaser_email_exists(email: str) -> bool:
    target = normalize_email(email)
    return target in load_allowlist() or find_user(target) is not None


def registered_owner_emails() -> list[str]:
    return sorted({
        normalize_email(str(user.get("email") or ""))
        for user in load_users()
        if isinstance(user, dict) and normalize_email(str(user.get("email") or ""))
    })


def build_event_ref(owner_email: str, event_id: str, viewer_email: str, role: str) -> dict:
    owner = normalize_email(owner_email)
    event_dir = event_dir_for_owner(owner, event_id)
    return {
        "id": event_ref_id(owner, event_id, viewer_email),
        "eventId": event_id,
        "ownerEmail": owner,
        "ownerSlug": user_slug(owner),
        "dataDir": event_dir,
        "role": role,
    }


def available_event_refs(email: str) -> list[dict]:
    viewer = normalize_email(email)
    refs: list[dict] = []

    for event_id in owned_event_ids(viewer):
        refs.append(build_event_ref(viewer, event_id, viewer, "owner"))

    for owner_email in registered_owner_emails():
        if owner_email == viewer:
            continue
        for event_id in owned_event_ids(owner_email):
            event_dir = event_dir_for_owner(owner_email, event_id)
            access = load_event_access(event_dir, owner_email)
            if viewer in access["sharedEmails"]:
                refs.append(build_event_ref(owner_email, event_id, viewer, "shared"))

    return refs


def event_ids(email: str) -> list[str]:
    return [ref["id"] for ref in available_event_refs(email)]


def event_ref_by_id(email: str, requested_id: str) -> dict | None:
    requested = str(requested_id or "")
    refs = available_event_refs(email)
    for ref in refs:
        if ref["id"] == requested:
            return ref
    for ref in refs:
        if ref["ownerEmail"] == normalize_email(email) and ref["eventId"] == requested:
            return ref
    return None


def save_active_event_ref(email: str, ref: dict) -> None:
    save_json(active_event_file(email), {
        "eventRef": ref["id"],
        "eventId": ref["eventId"],
        "ownerEmail": ref["ownerEmail"],
        "ownerSlug": ref["ownerSlug"],
        "selectedAt": utc_now(),
    })


def write_active_event_id(email: str, event_id: str) -> None:
    ref = event_ref_by_id(email, event_id)
    if not ref:
        raise HTTPException(status_code=404, detail="Event not found.")
    save_active_event_ref(email, ref)


def read_active_event_ref(email: str) -> dict | None:
    data = load_json(active_event_file(email), {})
    requested_ref = ""
    requested_event_id = ""
    requested_owner = ""
    if isinstance(data, dict):
        requested_ref = str(data.get("eventRef") or data.get("ref") or data.get("eventId") or "")
        requested_event_id = str(data.get("eventId") or "")
        requested_owner = normalize_email(str(data.get("ownerEmail") or ""))
    elif isinstance(data, str):
        requested_ref = data
        requested_event_id = data

    refs = available_event_refs(email)
    if not refs:
        return None

    for ref in refs:
        if ref["id"] == requested_ref:
            return ref
    if requested_owner and requested_event_id:
        for ref in refs:
            if ref["ownerEmail"] == requested_owner and ref["eventId"] == requested_event_id:
                save_active_event_ref(email, ref)
                return ref
    if requested_event_id:
        for ref in refs:
            if ref["ownerEmail"] == normalize_email(email) and ref["eventId"] == requested_event_id:
                save_active_event_ref(email, ref)
                return ref

    save_active_event_ref(email, refs[0])
    return refs[0]


def read_active_event_id(email: str) -> str | None:
    ref = read_active_event_ref(email)
    return ref["id"] if ref else None


def slugify_event_name(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    return base[:42].strip("-") or "event"


def unique_event_id(email: str, name: str) -> str:
    events_dir = user_data_root(email) / EVENTS_DIR_NAME
    base = slugify_event_name(name)
    candidate = base
    suffix = 2
    while candidate in owned_event_ids(email) or (events_dir / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def create_event_workspace(
    email: str,
    event_name: str,
    stage: str = "",
    total_matches: int = 6,
) -> tuple[str, EventManager]:
    owner = normalize_email(email)
    event_id = unique_event_id(owner, event_name)
    em = EventManager(event_dir_for_owner(owner, event_id))
    em.event.update({
        "eventName": event_name.strip() or "My PUBGM Event",
        "stage": stage.strip(),
        "totalMatches": max(1, min(99, int(total_matches or 6))),
    })
    em.save_event()
    save_event_access(em.data_dir, owner, [])
    write_active_event_id(owner, event_id)
    return event_id, em


def ensure_active_event_ref(email: str) -> dict:
    active = read_active_event_ref(email)
    if active:
        return active
    event_id, _ = create_event_workspace(email, "My PUBGM Event")
    ref = event_ref_by_id(email, event_id)
    if not ref:
        raise HTTPException(status_code=404, detail="Event not found.")
    return ref


def ensure_active_event_id(email: str) -> str:
    return ensure_active_event_ref(email)["id"]


def manager_for(email: str) -> EventManager:
    ref = ensure_active_event_ref(email)
    return EventManager(ref["dataDir"])


def active_event_ref_or_404(email: str) -> dict:
    ref = read_active_event_ref(email)
    if not ref:
        raise HTTPException(status_code=404, detail="Create or select an event first.")
    return ref


def event_updated_at(em: EventManager) -> str:
    paths = [em.event_file, *em.results_dir.glob("match_*.json")]
    newest = max((p.stat().st_mtime for p in paths if p.exists()), default=0)
    if newest <= 0:
        return ""
    return datetime.fromtimestamp(newest, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def event_summary(ref: dict, active_id: str | None) -> dict:
    em = EventManager(ref["dataDir"])
    access = load_event_access(ref["dataDir"], ref["ownerEmail"])
    return {
        "id": ref["id"],
        "eventId": ref["eventId"],
        "eventName": em.event.get("eventName", "My PUBGM Event"),
        "stage": em.event.get("stage", ""),
        "totalMatches": em.event.get("totalMatches", 6),
        "teams": len(em.event.get("teams", []) or []),
        "matches": len(em.list_match_numbers()),
        "updatedAt": event_updated_at(em),
        "active": ref["id"] == active_id,
        "ownerEmail": ref["ownerEmail"],
        "accessRole": ref["role"],
        "sharedCount": len(access["sharedEmails"]),
        "canManageAccess": ref["role"] == "owner",
    }


def events_payload(email: str) -> dict:
    refs = available_event_refs(email)
    active = read_active_event_id(email)
    return {
        "activeEventId": active,
        "events": [event_summary(ref, active) for ref in refs],
    }


def event_access_payload(email: str) -> dict:
    ref = active_event_ref_or_404(email)
    em = EventManager(ref["dataDir"])
    access = load_event_access(ref["dataDir"], ref["ownerEmail"])
    can_manage = ref["ownerEmail"] == normalize_email(email)
    return {
        "eventId": ref["id"],
        "eventName": em.event.get("eventName", "My PUBGM Event"),
        "ownerEmail": ref["ownerEmail"],
        "sharedEmails": access["sharedEmails"] if can_manage else [],
        "sharedCount": len(access["sharedEmails"]),
        "canManageAccess": can_manage,
        "accessRole": ref["role"],
    }


def owner_event_ref_or_403(email: str) -> dict:
    ref = active_event_ref_or_404(email)
    if ref["ownerEmail"] != normalize_email(email):
        raise HTTPException(status_code=403, detail="Only the event owner can manage access.")
    return ref

def public_event(em: EventManager) -> dict:
    event = dict(em.event)
    ps = event.get("pointSystem", DEFAULT_POINT_SYSTEM)
    event["placementPoints"] = ps.get("placementPoints", DEFAULT_POINT_SYSTEM["placementPoints"])
    event["killPoint"] = ps.get("killPoint", 1)
    return event


def branding_dir(em: EventManager) -> Path:
    return em.branding_dir


def branding_for(em: EventManager) -> graphic_themes.Branding:
    return em.branding()


def save_exports(em: EventManager):
    export_tournament_sheet(em)
    branding = branding_for(em)
    matches = em.list_match_numbers()
    for number in matches:
        match = em.load_match(number)
        if match:
            result_graphic.render_match_results(
                match,
                em.exports_dir / f"match_{match['matchNumber']:02d}_results.png",
                branding,
            )
    result_graphic.render_overall_standings(
        em.overall_standings(),
        em.event.get("eventName", "PUBGM Event"),
        len(matches),
        em.exports_dir / "overall_standings.png",
        branding,
    )


def upload_dir_for(email: str) -> Path:
    path = WEB_UPLOAD_DIR / user_slug(email) / str(int(time.time() * 1000))
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_uploads(email: str, files: list[UploadFile]) -> list[Path]:
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one screenshot.")
    out_dir = upload_dir_for(email)
    paths = []
    allowed = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    for idx, file in enumerate(files, start=1):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in allowed:
            raise HTTPException(status_code=400, detail=f"Unsupported image type: {file.filename}")
        path = out_dir / f"screenshot_{idx:02d}{suffix}"
        with path.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        paths.append(path)
    return paths


def team_short_name(name: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", name.upper())
    if not words:
        return ""
    if len(words) == 1:
        return words[0][:5]
    return "".join(w[0] for w in words[:4])[:5]


def manual_result(entry: ManualTeamPayload, point_system: dict) -> dict:
    pp = placement_points(entry.rank, point_system)
    kp = entry.kills * int(point_system.get("killPoint", 1))
    players = []
    if entry.players:
        for player in entry.players:
            if not player.name.strip():
                continue
            players.append({
                "playerName": player.name.strip(),
                "uId": "",
                "kills": player.kills,
                "damage": 0,
                "knockouts": 0,
                "headshots": 0,
                "assists": 0,
                "damageReceived": 0,
                "survivalTime": 0,
                "heal": 0,
                "rescues": 0,
                "longestKill": 0,
                "grenadeKills": 0,
                "raw": {},
            })
    return {
        "teamId": entry.slot,
        "teamName": entry.teamName.strip() or f"Team {entry.slot}",
        "placement": entry.rank,
        "kills": entry.kills,
        "placementPoints": pp,
        "killPoints": kp,
        "totalPoints": pp + kp,
        "wwcd": entry.rank == 1,
        "players": players,
    }


def duplicate_values(values: list[int]) -> list[int]:
    seen = set()
    dupes = set()
    for value in values:
        if value in seen:
            dupes.add(value)
        seen.add(value)
    return sorted(dupes)


def api_state(email: str) -> dict:
    ref = ensure_active_event_ref(email)
    key = f"{ref['ownerSlug']}:{ref['eventId']}"
    state = api_states.setdefault(key, {
        "tracker": MatchTracker(),
        "mock": MockDataGenerator(),
        "lastResults": [],
        "lastStatus": "Ready",
        "lastError": "",
        "sourceKey": "",
    })
    return state


def reset_api_state(state: dict, source_key: str) -> None:
    state["tracker"] = MatchTracker()
    state["mock"] = MockDataGenerator()
    state["lastResults"] = []
    state["lastStatus"] = "Ready"
    state["lastError"] = ""
    state["sourceKey"] = source_key


def observer_results_from_snapshot(state: dict, email: str, snap, status: str) -> dict:
    team_states = snap.team_states()
    if not team_states:
        state["lastResults"] = []
        state["lastStatus"] = "No team data received"
        state["lastError"] = "Live feed returned no team/player list."
        raise HTTPException(
            status_code=422,
            detail="Live feed connected, but no team/player data was found. Check that the match is running and the endpoint returns player data.",
        )

    tracker = state["tracker"]
    tracker.update(team_states)
    em = manager_for(email)
    results = tracker.build_results(
        em.event.get("pointSystem", DEFAULT_POINT_SYSTEM),
        em.team_name_overrides(),
    )
    state["lastResults"] = results
    state["lastStatus"] = status
    state["lastError"] = ""
    return {
        "status": status,
        "aliveTeams": tracker.alive_team_count,
        "isMatchOver": tracker.is_match_over,
        "seenAnyData": tracker.seen_any_data,
        "results": results,
    }


@app.get("/api/health")
def health_check():
    return {"ok": True, "service": "ec-pubgm-result-maker"}

@app.get("/")
def index():
    return spa_shell()


@app.post("/api/auth/register")
def register(payload: RegisterPayload, response: Response):
    email = normalize_email(payload.email)
    if email not in load_allowlist():
        raise HTTPException(
            status_code=403,
            detail="This email is not on the purchased user list. Contact ESPORTS COUNTY.",
        )
    if find_user(email):
        raise HTTPException(status_code=409, detail="This email is already registered.")
    users = load_users()
    salt = secrets.token_hex(16)
    users.append({
        "email": email,
        "name": payload.name.strip(),
        "salt": salt,
        "hash": password_hash(payload.password, salt),
        "createdAt": utc_now(),
    })
    save_users(users)
    response.set_cookie(COOKIE_NAME, make_session(email), httponly=True, samesite="lax")
    return {"email": email, "name": payload.name.strip()}


@app.post("/api/auth/login")
def login(payload: LoginPayload, response: Response):
    user = find_user(payload.email)
    if user is None:
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    if not hmac.compare_digest(password_hash(payload.password, user["salt"]), user["hash"]):
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    response.set_cookie(COOKIE_NAME, make_session(user["email"]), httponly=True, samesite="lax")
    return {"email": user["email"], "name": user.get("name", "")}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.get("/api/me")
def me(email: Annotated[str, Cookie(alias=COOKIE_NAME)] = None):
    session_email = read_session(email)
    if not session_email:
        return {"authenticated": False}
    user = find_user(session_email)
    if not user:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "email": user["email"],
        "name": user.get("name", ""),
        "ocrEngine": engine_status(),
    }


@app.get("/api/ocr/engine")
def ocr_engine(email: Annotated[str, Depends(require_user)]):
    """Which OCR engine will actually run, so the UI can say so."""
    return engine_status()


@app.get("/api/events")
def list_events(email: Annotated[str, Depends(require_user)]):
    return events_payload(email)


@app.post("/api/events")
def create_event(payload: EventCreatePayload, email: Annotated[str, Depends(require_user)]):
    create_event_workspace(email, payload.eventName, payload.stage, payload.totalMatches)
    return events_payload(email)


@app.post("/api/events/select")
def select_event(payload: EventSelectPayload, email: Annotated[str, Depends(require_user)]):
    write_active_event_id(email, payload.eventId)
    return events_payload(email)


@app.get("/api/events/access")
def get_event_access(email: Annotated[str, Depends(require_user)]):
    return event_access_payload(email)


@app.post("/api/events/access")
def add_event_access(payload: EventAccessPayload, email: Annotated[str, Depends(require_user)]):
    ref = owner_event_ref_or_403(email)
    target = normalize_email(payload.email)
    if not target or "@" not in target:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if target == normalize_email(email):
        raise HTTPException(status_code=400, detail="The owner already has access.")
    if not purchaser_email_exists(target):
        raise HTTPException(status_code=403, detail="Add this email to the purchased user list first.")

    access = load_event_access(ref["dataDir"], ref["ownerEmail"])
    shared = set(access["sharedEmails"])
    shared.add(target)
    save_event_access(ref["dataDir"], ref["ownerEmail"], shared)
    return event_access_payload(email)


@app.delete("/api/events/access")
def remove_event_access(payload: EventAccessPayload, email: Annotated[str, Depends(require_user)]):
    ref = owner_event_ref_or_403(email)
    target = normalize_email(payload.email)
    access = load_event_access(ref["dataDir"], ref["ownerEmail"])
    shared = set(access["sharedEmails"])
    shared.discard(target)
    save_event_access(ref["dataDir"], ref["ownerEmail"], shared)
    return event_access_payload(email)

@app.get("/api/event")
def get_event(email: Annotated[str, Depends(require_user)]):
    em = manager_for(email)
    return public_event(em)


@app.put("/api/event")
def update_event(payload: EventPayload, email: Annotated[str, Depends(require_user)]):
    em = manager_for(email)
    teams = []
    for item in payload.teams:
        try:
            slot = int(item.get("teamId") or item.get("slot") or 0)
        except (TypeError, ValueError):
            continue
        name = str(item.get("teamName") or "").strip()
        short = str(item.get("shortName") or team_short_name(name)).strip()
        players = item.get("players") or []
        if slot > 0 and (name or short or players):
            teams.append({
                "teamId": slot,
                "teamName": name or f"Team {slot}",
                "shortName": short,
                "players": players,
            })
    em.event.update({
        "eventName": payload.eventName.strip() or "My PUBGM Event",
        "stage": payload.stage.strip(),
        "totalMatches": payload.totalMatches,
        "pointSystem": {
            "placementPoints": payload.placementPoints,
            "killPoint": payload.killPoint,
        },
        "teams": sorted(teams, key=lambda t: t["teamId"]),
    })
    em.save_event()
    save_exports(em)
    return public_event(em)


@app.post("/api/manual/ocr-roster")
async def ocr_roster(
    files: Annotated[list[UploadFile], File()],
    email: Annotated[str, Depends(require_user)],
):
    paths = await save_uploads(email, files)
    parsed = run_roster_ocr(paths)
    cards = parsed["cards"]
    errors = parsed["errors"]

    em = manager_for(email)
    by_slot = {int(t.get("teamId", 0)): t for t in em.event.get("teams", [])}
    applied = 0
    for card in cards:
        slot = card.get("slot")
        if not slot:
            continue
        players = [p for p in card.get("players", []) if p]
        tag = card.get("tag") or ""
        entry = by_slot.setdefault(slot, {"teamId": slot, "teamName": "", "shortName": ""})
        entry["players"] = players
        if tag and not entry.get("shortName"):
            entry["shortName"] = tag
        if tag and not entry.get("teamName"):
            entry["teamName"] = tag
        applied += 1
    if applied:
        em.event["teams"] = [by_slot[k] for k in sorted(by_slot)]
        em.save_event()
        save_exports(em)

    return {
        "cards": cards,
        "errors": errors,
        "applied": applied,
        "engineUsed": parsed["engineUsed"],
        "event": public_event(em),
    }


@app.post("/api/manual/ocr-results")
async def ocr_results(
    files: Annotated[list[UploadFile], File()],
    email: Annotated[str, Depends(require_user)],
):
    paths = await save_uploads(email, files)
    em = manager_for(email)
    return run_results_ocr(paths, em.event.get("teams", []))


@app.post("/api/manual/match")
def save_manual_match(payload: ManualMatchPayload, email: Annotated[str, Depends(require_user)]):
    if not payload.teams:
        raise HTTPException(status_code=400, detail="Add at least one team result.")
    ranks = [team.rank for team in payload.teams]
    slots = [team.slot for team in payload.teams]
    duplicate_ranks = duplicate_values(ranks)
    duplicate_slots = duplicate_values(slots)
    if duplicate_ranks:
        raise HTTPException(
            status_code=400,
            detail="Duplicate rank(s): " + ", ".join(str(v) for v in duplicate_ranks),
        )
    if duplicate_slots:
        raise HTTPException(
            status_code=400,
            detail="Duplicate slot(s): " + ", ".join(str(v) for v in duplicate_slots),
        )

    em = manager_for(email)
    ps = em.event.get("pointSystem", DEFAULT_POINT_SYSTEM)
    results = [manual_result(team, ps) for team in sorted(payload.teams, key=lambda t: t.rank)]
    em.save_match_result(payload.matchNumber, payload.map, results)

    by_slot = {int(t.get("teamId", 0)): t for t in em.event.get("teams", [])}
    for result in results:
        entry = by_slot.setdefault(result["teamId"], {
            "teamId": result["teamId"],
            "teamName": result["teamName"],
            "shortName": team_short_name(result["teamName"]),
        })
        entry["teamName"] = result["teamName"]
        entry.setdefault("shortName", team_short_name(result["teamName"]))
    em.event["teams"] = [by_slot[k] for k in sorted(by_slot)]
    em.save_event()
    save_exports(em)
    return dashboard_payload(em)


@app.get("/api/dashboard")
def dashboard(email: Annotated[str, Depends(require_user)]):
    return dashboard_payload(manager_for(email))


def dashboard_payload(em: EventManager) -> dict:
    matches = []
    for number in em.list_match_numbers():
        match = em.load_match(number)
        if match:
            matches.append({
                "matchNumber": match.get("matchNumber"),
                "map": match.get("map", ""),
                "finalizedAt": match.get("finalizedAt", ""),
                "teams": len(match.get("results", [])),
                "winner": (match.get("results") or [{}])[0].get("teamName", ""),
            })
    return {
        "event": public_event(em),
        "matches": matches,
        "standings": em.overall_standings(),
        "players": em.player_stats(),
        "nextMatch": em.next_match_number(),
    }


@app.delete("/api/matches/{match_number}")
def delete_match(match_number: int, email: Annotated[str, Depends(require_user)]):
    em = manager_for(email)
    em.delete_match(match_number)
    save_exports(em)
    return dashboard_payload(em)


@app.post("/api/observer/poll")
def poll_api(payload: ApiPollPayload, email: Annotated[str, Depends(require_user)]):
    state = api_state(email)
    api_url = payload.apiUrl.strip()
    if not payload.mockMode and not api_url:
        raise HTTPException(status_code=400, detail="Paste a live endpoint before polling.")

    source_key = "demo" if payload.mockMode else f"server:{api_url}"
    if payload.reset or state.get("sourceKey") != source_key:
        reset_api_state(state, source_key)

    try:
        if payload.mockMode:
            snap = state["mock"].fetch()
            status = "Demo sample data"
        else:
            resp = requests.get(api_url, timeout=5)
            resp.raise_for_status()
            snap = parse_snapshot(resp.json())
            status = "Live feed connected"
    except Exception as exc:
        state["lastResults"] = []
        state["lastError"] = str(exc)
        state["lastStatus"] = "Connection failed"
        raise HTTPException(status_code=502, detail=f"Live feed fetch failed: {exc}") from exc

    return observer_results_from_snapshot(state, email, snap, status)


@app.post("/api/observer/ingest")
def ingest_api(payload: ApiIngestPayload, email: Annotated[str, Depends(require_user)]):
    state = api_state(email)
    source_hint = re.sub(r"\s+", "", payload.sourceKey.strip())[:240] or "browser-local"
    source_key = f"browser:{source_hint}"
    if payload.reset or state.get("sourceKey") != source_key:
        reset_api_state(state, source_key)

    try:
        snap = parse_snapshot(payload.data)
    except Exception as exc:
        state["lastResults"] = []
        state["lastError"] = str(exc)
        state["lastStatus"] = "Live data could not be read"
        raise HTTPException(status_code=422, detail=f"Live feed data could not be read: {exc}") from exc

    return observer_results_from_snapshot(state, email, snap, "Browser live feed connected")

@app.post("/api/observer/save")
def save_api_match(payload: ApiSavePayload, email: Annotated[str, Depends(require_user)]):
    state = api_state(email)
    results = state.get("lastResults") or []
    if not results:
        raise HTTPException(status_code=400, detail="Poll API data before saving.")
    em = manager_for(email)
    em.save_match_result(payload.matchNumber, payload.map, results)
    save_exports(em)
    state["tracker"] = MatchTracker()
    state["lastResults"] = []
    return dashboard_payload(em)


# --------------------------------------------------------------------------
# result graphics: templates, custom artwork, live preview
# --------------------------------------------------------------------------

ARTWORK_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
MAX_ARTWORK_BYTES = 12 * 1024 * 1024


@app.get("/api/graphics/templates")
def graphics_templates(email: Annotated[str, Depends(require_user)]):
    em = manager_for(email)
    return {
        "templates": graphic_themes.catalogue(),
        "graphics": em.event.get("graphics") or {},
        "logoPositions": ["top-left", "top-right", "bottom-left", "bottom-right"],
    }


@app.put("/api/graphics")
def update_graphics(payload: GraphicsPayload, email: Annotated[str, Depends(require_user)]):
    """Save the template choice. Artwork filenames are owned by the upload
    endpoint and are deliberately not settable from here — otherwise a client
    could point the renderer at any file on disk."""
    em = manager_for(email)
    known = {theme["key"] for theme in graphic_themes.catalogue()}
    if payload.template not in known:
        raise HTTPException(status_code=400, detail="Unknown template.")

    graphics = dict(em.event.get("graphics") or {})
    graphics.update({
        "template": payload.template,
        "accent": clean_hex(payload.accent),
        "text": clean_hex(payload.text),
        "title": clean_hex(payload.title),
        "logoPosition": (payload.logoPosition
                         if payload.logoPosition in
                         ("top-left", "top-right", "bottom-left", "bottom-right")
                         else "top-right"),
        "showLogo": bool(payload.showLogo),
        "scrim": None if payload.scrim is None else max(0, min(255, int(payload.scrim))),
        "layout": payload.layout if payload.layout in ("", "1", "2") else "",
    })
    em.event["graphics"] = graphics
    em.save_event()
    save_exports(em)
    return {"graphics": graphics, "event": public_event(em)}


@app.post("/api/graphics/artwork/{kind}")
async def upload_artwork(
    kind: str,
    file: Annotated[UploadFile, File()],
    email: Annotated[str, Depends(require_user)],
):
    """Store the operator's background or logo for this event."""
    if kind not in ("background", "logo"):
        raise HTTPException(status_code=404, detail="Unknown artwork slot.")

    suffix = ARTWORK_TYPES.get((file.content_type or "").lower())
    if suffix is None:
        raise HTTPException(
            status_code=400,
            detail="Upload a PNG, JPG or WEBP image.")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(payload) > MAX_ARTWORK_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Keep artwork under {MAX_ARTWORK_BYTES // (1024 * 1024)} MB.")

    # Validate before touching disk. Deleting the old artwork first meant a
    # rejected upload destroyed the working background the operator already
    # had, leaving the event with no artwork and an error message.
    try:
        with Image.open(BytesIO(payload)) as image:
            image.verify()
    except Exception:                                   # noqa: BLE001
        raise HTTPException(
            status_code=400, detail="That file is not a readable image.") from None

    em = manager_for(email)
    directory = branding_dir(em)
    # The stored name is generated, never taken from the upload: a filename is
    # attacker-controlled input and this path is later read back from disk.
    for existing in directory.glob(f"{kind}.*"):
        existing.unlink(missing_ok=True)
    (directory / f"{kind}{suffix}").write_bytes(payload)

    graphics = dict(em.event.get("graphics") or {})
    graphics[kind] = f"{kind}{suffix}"
    if kind == "background" and graphics.get("template") in ("", None):
        graphics["template"] = graphic_themes.CUSTOM_KEY
    em.event["graphics"] = graphics
    em.save_event()
    save_exports(em)
    return {"graphics": graphics, "event": public_event(em)}


@app.delete("/api/graphics/artwork/{kind}")
def delete_artwork(kind: str, email: Annotated[str, Depends(require_user)]):
    if kind not in ("background", "logo"):
        raise HTTPException(status_code=404, detail="Unknown artwork slot.")
    em = manager_for(email)
    for existing in branding_dir(em).glob(f"{kind}.*"):
        existing.unlink(missing_ok=True)
    graphics = dict(em.event.get("graphics") or {})
    graphics[kind] = ""
    em.event["graphics"] = graphics
    em.save_event()
    save_exports(em)
    return {"graphics": graphics, "event": public_event(em)}


@app.get("/api/graphics/preview/{template}")
def graphics_preview(template: str, email: Annotated[str, Depends(require_user)]):
    """A small sample render of one template, using this event's artwork and
    colours so the picker shows what will actually be produced."""
    known = {theme["key"] for theme in graphic_themes.catalogue()}
    if template not in known:
        raise HTTPException(status_code=404, detail="Unknown template.")

    em = manager_for(email)
    branding = branding_for(em)
    branding.template = template

    cache = em.exports_dir / "previews"
    cache.mkdir(parents=True, exist_ok=True)
    out = cache / f"{template}.png"

    # Re-render when the event's artwork or colours are newer than the cache;
    # otherwise a colour change would keep showing the previous preview.
    sources = [em.event_file, *branding_dir(em).glob("*")]
    newest = max((path.stat().st_mtime for path in sources if path.exists()), default=0)
    if not out.exists() or out.stat().st_mtime < newest:
        result_graphic.render_preview(branding, out, width=640)

    return FileResponse(out, media_type="image/png",
                        headers={"Cache-Control": "no-cache"})


@app.get("/api/download/{kind}")
def download(kind: str, email: Annotated[str, Depends(require_user)]):
    em = manager_for(email)
    filename = ""
    if kind == "sheet":
        path = em.exports_dir / "Tournament Sheet.xlsx"
    elif kind == "overall-png":
        path = em.exports_dir / "overall_standings.png"
    elif kind == "match-png":
        latest = em.list_match_numbers()[-1] if em.list_match_numbers() else 0
        path = em.exports_dir / f"match_{latest:02d}_results.png"
    elif kind == "player-details":
        path = em.exports_dir / "csv" / "player_stats.csv"
        filename = "player_details.csv"
    else:
        raise HTTPException(status_code=404, detail="Unknown download.")
    if not path.exists():
        save_exports(em)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File is not ready yet.")
    return FileResponse(path, filename=filename or path.name)


NOT_BUILT_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Build the web app first</title>
<style>body{background:#0b0908;color:#f0ded0;font:16px/1.6 system-ui;padding:3rem;max-width:44rem;margin:auto}
code{background:#1a1614;padding:.15rem .4rem;border-radius:4px;color:#e1ad63}</style></head>
<body><h1>The web interface has not been built yet</h1>
<p>The front-end is compiled with Vite. From the project folder, run:</p>
<pre><code>cd web
npm install
npm run build</code></pre>
<p>Then restart this server. <code>run_web.bat</code> does all of that for you.</p>
</body></html>"""


def spa_shell():
    """The built SPA shell, or instructions when the front-end is not built."""
    shell = WEB_DIST / "index.html"
    if not shell.exists():
        return HTMLResponse(NOT_BUILT_PAGE, status_code=503)
    return FileResponse(shell)



@app.get("/{asset_name}")
def web_root_asset(asset_name: str):
    """Serve root-level Vite assets such as /ec-logo.png.

    Vite copies files from web/public into web/dist root. The SPA fallback must
    still handle app routes, but real files at the build root should be served
    as files so browser icons and brand assets load correctly.
    """
    if "/" in asset_name or "\\" in asset_name:
        raise HTTPException(status_code=404, detail="Not found.")
    path = (WEB_DIST / asset_name).resolve()
    try:
        path.relative_to(WEB_DIST.resolve())
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found.") from None
    if path.is_file() and path.name != "index.html":
        return FileResponse(path)
    return spa_shell()

@app.get("/{_:path}")
def spa_fallback(_: str, request: Request):
    """Every non-API path returns the SPA shell so client-side routes work on
    a hard refresh or a pasted link."""
    if request.url.path.startswith("/api/"):
        raise HTTPException(status_code=404, detail="Not found.")
    return spa_shell()


