"""Discord companion bot for ESPORTS COUNTY PUBGM RESULT MAKER.

The bot reads and writes the same per-user event folder as the web app. It can
answer result/standing/player commands and can run an observer API polling loop
that auto-saves a match when the API says the game is over.

Required environment:
    DISCORD_BOT_TOKEN=your bot token

Useful optional environment:
    DISCORD_RESULTS_EMAIL=buyer/event email to expose in Discord
    DISCORD_ANNOUNCE_CHANNEL_ID=channel id for auto-save announcements
    OBSERVER_API_URL=http://127.0.0.1:10086/gettotalplayerlist
    OBSERVER_POLL_SECONDS=3
    DISCORD_GUILD_ID=server id for instant slash-command sync
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from core import discord_tables, result_graphic
from core.event_manager import EventManager
from core.match_tracker import MatchTracker
from core.mock_data import MockDataGenerator
from core.models import parse_snapshot
from core.scoring import DEFAULT_POINT_SYSTEM
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
WEB_DATA_DIR = DATA_DIR / "web"
ALLOWLIST_FILE = DATA_DIR / "web_allowlist.json"
USERS_FILE = DATA_DIR / "web_users.json"

DEFAULT_EMAIL = "abhiv@esportscounty.com"
DEFAULT_API_URL = "http://127.0.0.1:10086/gettotalplayerlist"
DEFAULT_POLL_SECONDS = 3
DISCORD_LIMIT = 1900
PUBLIC_EVENT_NOT_READY = "Please wait, event details are not available yet. Try again after the organizer sets up the event."
PUBLIC_MATCHES_NOT_READY = "Please wait, match list is not available yet. Try again after the organizer updates the event."
PUBLIC_RESULTS_NOT_READY = "Please wait, results are not available yet. Try again after the organizer updates the match results."
PUBLIC_STANDINGS_NOT_READY = "Please wait, standings are not available yet. Try again after the organizer updates the match results."
PUBLIC_PLAYERS_NOT_READY = "Please wait, player stats are not available yet. Try again after the organizer updates the match results."
PUBLIC_TEAM_SS_NOT_READY = "Please wait, team screenshot is not available yet. Try again after the organizer posts the match result."
PUBLIC_OVERALL_SS_NOT_READY = "Please wait, overall screenshot is not available yet. Try again after the organizer posts the standings."
PUBLIC_PLAYER_DETAILS_NOT_READY = "Please wait, player details are not available yet. Try again after the organizer posts the match result."
LEGACY_EVENT_ID = "legacy"
EVENTS_DIR_NAME = "events"
ACTIVE_EVENT_FILE_NAME = "active_event.json"
EVENT_ACCESS_FILE_NAME = "access.json"
SHARED_REF_SEP = "::"


def normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def user_slug(email: str) -> str:
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()[:16]


def load_json(path: Path, default: Any) -> Any:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default
    return default


def configured_email() -> str:
    for key in ("DISCORD_RESULTS_EMAIL", "EC_RESULTS_EMAIL"):
        value = normalize_email(os.environ.get(key, ""))
        if value:
            return value

    users = load_json(USERS_FILE, [])
    if isinstance(users, list):
        for user in users:
            email = normalize_email(user.get("email", "") if isinstance(user, dict) else "")
            if email:
                return email

    allowlist = load_json(ALLOWLIST_FILE, [])
    if isinstance(allowlist, dict):
        allowlist = allowlist.get("emails", [])
    if isinstance(allowlist, list):
        for email in allowlist:
            normalized = normalize_email(str(email))
            if normalized:
                return normalized

    return DEFAULT_EMAIL


def user_data_root(email: str) -> Path:
    return WEB_DATA_DIR / user_slug(email)


def event_access_file(event_dir: Path) -> Path:
    return event_dir / EVENT_ACCESS_FILE_NAME


def legacy_event_exists(root: Path) -> bool:
    return (
        (root / "event.json").exists()
        or any((root / "results").glob("match_*.json"))
        or (root / "exports" / "Tournament Sheet.xlsx").exists()
    )


def event_dir_for_owner(owner_email: str, event_id: str | None) -> Path:
    root = user_data_root(owner_email)
    if not event_id or event_id == LEGACY_EVENT_ID:
        return root
    return root / EVENTS_DIR_NAME / event_id


def owned_event_ids(email: str) -> list[str]:
    root = user_data_root(email)
    ids: list[str] = []
    if legacy_event_exists(root):
        ids.append(LEGACY_EVENT_ID)
    events_dir = root / EVENTS_DIR_NAME
    if events_dir.exists():
        ids.extend(sorted(
            child.name
            for child in events_dir.iterdir()
            if child.is_dir() and (child / "event.json").exists()
        ))
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


def registered_owner_emails() -> list[str]:
    users = load_json(USERS_FILE, [])
    if not isinstance(users, list):
        return []
    return sorted({
        normalize_email(str(user.get("email") or ""))
        for user in users
        if isinstance(user, dict) and normalize_email(str(user.get("email") or ""))
    })


def build_event_ref(owner_email: str, event_id: str, viewer_email: str, role: str) -> dict:
    owner = normalize_email(owner_email)
    return {
        "id": event_ref_id(owner, event_id, viewer_email),
        "eventId": event_id,
        "ownerEmail": owner,
        "ownerSlug": user_slug(owner),
        "dataDir": event_dir_for_owner(owner, event_id),
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


def active_event_ref(email: str) -> dict | None:
    data = load_json(user_data_root(email) / ACTIVE_EVENT_FILE_NAME, {})
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
                return ref
    if requested_event_id:
        for ref in refs:
            if ref["ownerEmail"] == normalize_email(email) and ref["eventId"] == requested_event_id:
                return ref
    return refs[0]


def active_event_id(email: str) -> str | None:
    ref = active_event_ref(email)
    return ref["id"] if ref else None


def event_dir_for(email: str, event_id: str | None) -> Path:
    if event_id:
        for ref in available_event_refs(email):
            if ref["id"] == event_id:
                return ref["dataDir"]
    return event_dir_for_owner(email, event_id)


def manager_for(email: str | None = None) -> EventManager:
    selected_email = email or configured_email()
    ref = active_event_ref(selected_email)
    if ref:
        return EventManager(ref["dataDir"])
    return EventManager(event_dir_for_owner(selected_email, None))

def save_exports(em: EventManager) -> None:
    export_tournament_sheet(em)
    branding = em.branding()
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


def safe_int(value: Any, default: int, minimum: int = 1, maximum: int = 999) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def compact_team(name: str, limit: int = 22) -> str:
    text = " ".join(str(name or "").split()) or "Unknown Team"
    return text if len(text) <= limit else text[: limit - 1] + "."


def code_table(headers: list[str], rows: list[list[Any]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(str(value)))

    def line(values: list[Any]) -> str:
        return " ".join(str(value).ljust(widths[idx]) for idx, value in enumerate(values))

    body = [line(headers), line(["-" * width for width in widths])]
    body.extend(line(row) for row in rows)
    return "```" + "\n".join(body) + "```"


def chunk_message(text: str, limit: int = DISCORD_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > limit and current:
            chunks.append(current.rstrip())
            current = ""
        current += line
    if current.strip():
        chunks.append(current.rstrip())
    return chunks or [text[:limit]]


def latest_match_number(em: EventManager | None) -> int | None:
    if em is None:
        return None
    numbers = em.list_match_numbers()
    return numbers[-1] if numbers else None


def match_image_path(em: EventManager | None, match_number: int | None = None) -> Path | None:
    if em is None:
        return None
    number = match_number or latest_match_number(em)
    if number is None:
        return None
    save_exports(em)
    path = em.exports_dir / f"match_{int(number):02d}_results.png"
    return path if path.exists() else None


def overall_image_path(em: EventManager | None) -> Path | None:
    if em is None:
        return None
    save_exports(em)
    path = em.exports_dir / "overall_standings.png"
    return path if path.exists() else None


def player_details_csv_path(em: EventManager | None) -> Path | None:
    if em is None:
        return None
    save_exports(em)
    path = em.exports_dir / "csv" / "player_stats.csv"
    return path if path.exists() else None


def discord_exports_dir(em: EventManager) -> Path:
    path = em.exports_dir / "discord"
    path.mkdir(parents=True, exist_ok=True)
    return path


def match_table_filename(match_number: int | None) -> str:
    number = safe_int(match_number, 0, 0, 99)
    return f"match_{number:02d}_table.png" if number else "match_results_table.png"


def discord_match_table_path(
    em: EventManager | None,
    match_number: int | None = None,
    limit: int = 16,
) -> Path | None:
    if em is None:
        return None
    number = match_number or latest_match_number(em)
    if number is None:
        return None
    match = em.load_match(number)
    if not match:
        return None
    path = discord_exports_dir(em) / f"match_{int(number):02d}_table.png"
    return discord_tables.render_match_results_table(
        match,
        path,
        branding=em.branding(),
        limit=safe_int(limit, 16, 1, 50),
    )


def discord_overall_table_path(em: EventManager | None, top: int = 16) -> Path | None:
    if em is None:
        return None
    standings = em.overall_standings()
    if not standings:
        return None
    chosen_top = safe_int(top, 16, 1, 50)
    path = discord_exports_dir(em) / f"overall_top_{chosen_top:02d}_table.png"
    return discord_tables.render_overall_table(
        standings,
        em.event.get("eventName", "PUBGM Event"),
        len(em.list_match_numbers()),
        path,
        branding=em.branding(),
        limit=chosen_top,
    )


def discord_players_table_path(em: EventManager | None, top: int = 10) -> Path | None:
    if em is None:
        return None
    players = em.player_stats()
    if not players:
        return None
    chosen_top = safe_int(top, 10, 1, 50)
    path = discord_exports_dir(em) / f"top_players_{chosen_top:02d}_table.png"
    return discord_tables.render_players_table(
        players,
        em.event.get("eventName", "PUBGM Event"),
        path,
        branding=em.branding(),
        limit=chosen_top,
    )


def discord_matches_table_path(em: EventManager | None, limit: int = 10) -> Path | None:
    if em is None:
        return None
    numbers = em.list_match_numbers()
    if not numbers:
        return None
    chosen_limit = safe_int(limit, 10, 1, 50)
    matches = []
    for number in numbers[-chosen_limit:]:
        match = em.load_match(number)
        if match:
            matches.append(match)
    if not matches:
        return None
    path = discord_exports_dir(em) / "saved_matches_table.png"
    return discord_tables.render_matches_table(
        matches,
        em.event.get("eventName", "PUBGM Event"),
        path,
        branding=em.branding(),
        limit=chosen_limit,
    )


def discord_event_table_path(em: EventManager | None) -> Path | None:
    if em is None:
        return None
    matches = em.list_match_numbers()
    path = discord_exports_dir(em) / "event_details_table.png"
    return discord_tables.render_event_table(
        em.event,
        len(matches),
        em.next_match_number(),
        path,
        branding=em.branding(),
    )


def discord_live_table_path(
    em: EventManager | None,
    results: list[dict],
    limit: int = 16,
) -> Path | None:
    if not results:
        return None
    base = discord_exports_dir(em) if em is not None else (DATA_DIR / "discord_exports")
    base.mkdir(parents=True, exist_ok=True)
    path = base / "live_result_check_table.png"
    return discord_tables.render_live_results_table(
        results,
        path,
        branding=em.branding() if em is not None else None,
        limit=safe_int(limit, 16, 1, 50),
    )


def match_result_filename(match_number: int | None) -> str:
    number = safe_int(match_number, 0, 0, 99)
    return f"match_{number:02d}_results.png" if number else "match_results.png"


def match_result_caption(em: EventManager | None, match_number: int | None) -> str:
    if em is None or match_number is None:
        return "**Match Results**"

    match = em.load_match(match_number) or {}
    event_name = em.event.get("eventName") or "PUBGM Event"
    title = f"**{event_name}**\nMatch {match_number} Results"
    if match.get("map"):
        title += f" - {match['map']}"

    winner = (match.get("results") or [{}])[0]
    if winner.get("teamName"):
        title += (
            f"\nWinner: **{winner.get('teamName')}**"
            f" | Elims: `{winner.get('kills', 0)}`"
            f" | Total: `{winner.get('totalPoints', 0)}`"
        )
    return title


def overall_standings_caption(em: EventManager | None) -> str:
    if em is None:
        return "**Overall Standings**"

    event_name = em.event.get("eventName") or "PUBGM Event"
    matches_played = len(em.list_match_numbers())
    title = f"**{event_name}**\nOverall Standings - After {matches_played} match{'es' if matches_played != 1 else ''}"
    leader = (em.overall_standings() or [{}])[0]
    if leader.get("teamName"):
        title += (
            f"\nLeader: **{leader.get('teamName')}**"
            f" | WWCD: `{leader.get('wwcd', 0)}`"
            f" | Total: `{leader.get('totalPoints', 0)}`"
        )
    return title


def format_matches(em: EventManager | None, limit: int = 10) -> str:
    if em is None:
        return PUBLIC_MATCHES_NOT_READY
    numbers = em.list_match_numbers()
    if not numbers:
        return PUBLIC_MATCHES_NOT_READY

    rows = []
    for number in numbers[-limit:]:
        match = em.load_match(number)
        if not match:
            continue
        results = match.get("results") or []
        winner = results[0].get("teamName", "") if results else ""
        rows.append([
            f"#{number}",
            match.get("map", ""),
            compact_team(winner, 24),
            len(results),
        ])

    return "**Saved Matches**\n" + code_table(["Match", "Map", "Winner", "Teams"], rows)


def format_results(em: EventManager | None, match_number: int | None = None, limit: int = 16) -> str:
    if em is None:
        return PUBLIC_RESULTS_NOT_READY
    number = match_number or latest_match_number(em)
    if number is None:
        return PUBLIC_RESULTS_NOT_READY

    match = em.load_match(number)
    if not match:
        return f"Please wait, match {number} is not available yet. Try again after the organizer updates the match results."

    rows = []
    for result in (match.get("results") or [])[:limit]:
        rows.append([
            result.get("placement", ""),
            compact_team(result.get("teamName", "")),
            result.get("kills", 0),
            result.get("placementPoints", 0),
            result.get("totalPoints", 0),
        ])

    title = f"**Match {number} Results"
    if match.get("map"):
        title += f" - {match['map']}"
    title += "**"
    return title + "\n" + code_table(["#", "Team", "Elims", "PP", "Total"], rows)


def format_standings(em: EventManager | None, top: int = 16) -> str:
    if em is None:
        return PUBLIC_STANDINGS_NOT_READY
    standings = em.overall_standings()
    if not standings:
        return PUBLIC_STANDINGS_NOT_READY

    rows = []
    for row in standings[:top]:
        rows.append([
            row.get("rank", ""),
            compact_team(row.get("teamName", "")),
            row.get("wwcd", 0),
            row.get("kills", 0),
            row.get("placementPoints", 0),
            row.get("totalPoints", 0),
        ])
    return "**Overall Standings**\n" + code_table(["#", "Team", "WWCD", "Elims", "PP", "Total"], rows)


def format_players(em: EventManager | None, top: int = 10) -> str:
    if em is None:
        return PUBLIC_PLAYERS_NOT_READY
    players = em.player_stats()
    if not players:
        return PUBLIC_PLAYERS_NOT_READY

    rows = []
    for row in players[:top]:
        rows.append([
            row.get("rank", ""),
            compact_team(row.get("playerName", ""), 20),
            compact_team(row.get("teamName", ""), 16),
            row.get("kills", 0),
            row.get("matches", 0),
        ])
    return "**Top Players**\n" + code_table(["#", "Player", "Team", "Elims", "M"], rows)


def format_event(em: EventManager | None) -> str:
    if em is None:
        return PUBLIC_EVENT_NOT_READY
    event = em.event
    matches = em.list_match_numbers()
    return (
        f"**{event.get('eventName', 'PUBGM Event')}**\n"
        f"Stage: {event.get('stage') or 'Not set'}\n"
        f"Teams: {len(event.get('teams') or [])}\n"
        f"Matches: {len(matches)} / {event.get('totalMatches', '?')}\n"
        f"Next match: {em.next_match_number()}"
    )

def format_live_results(results: list[dict], limit: int = 8) -> str:
    if not results:
        return "No live result rows were returned."
    rows = []
    for result in results[:limit]:
        rows.append([
            result.get("placement", ""),
            compact_team(result.get("teamName", "")),
            result.get("kills", 0),
            result.get("totalPoints", 0),
        ])
    return code_table(["#", "Team", "Elims", "Total"], rows)


@dataclass
class AutoPollConfig:
    email: str
    api_url: str
    poll_seconds: int
    match_number: int
    map_name: str
    mock_mode: bool = False


class AutoPollRunner:
    def __init__(self) -> None:
        self.task: asyncio.Task[None] | None = None
        self.config: AutoPollConfig | None = None
        self.tracker = MatchTracker()
        self.mock = MockDataGenerator()
        self.last_results: list[dict] = []
        self.last_status = "Idle."
        self.last_error = ""
        self.last_saved_match: int | None = None
        self.waiting_for_new_match = False

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    async def start(self, config: AutoPollConfig, channel: Any | None = None) -> str:
        await self.stop()
        self.config = config
        self.tracker = MatchTracker()
        self.mock = MockDataGenerator()
        self.last_results = []
        self.last_error = ""
        self.last_saved_match = None
        self.waiting_for_new_match = False
        self.last_status = f"Starting live result auto-save for match {config.match_number}."
        self.task = asyncio.create_task(self._loop(channel), name="ec-discord-auto-poll")
        return self.status_text()

    async def stop(self) -> str:
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None
        self.last_status = "Auto-poll stopped."
        return self.status_text()

    async def poll_once(self) -> list[dict]:
        if not self.config:
            raise RuntimeError("Auto-poll is not configured.")
        em = manager_for(self.config.email)
        if self.config.mock_mode:
            snap = self.mock.fetch()
            source = "Sample live feed"
        else:
            payload = await asyncio.to_thread(fetch_json, self.config.api_url)
            snap = parse_snapshot(payload)
            source = "Live result feed"

        self.tracker.update(snap.team_states())
        self.last_results = self.tracker.build_results(
            em.event.get("pointSystem", DEFAULT_POINT_SYSTEM),
            em.team_name_overrides(),
        )
        self.last_status = (
            f"{source}: {self.tracker.alive_team_count} team(s) alive, "
            f"{len(self.last_results)} team(s) tracked."
        )
        self.last_error = ""
        return self.last_results

    def status_text(self) -> str:
        if not self.config:
            return self.last_status
        state = "running" if self.running else "stopped"
        return (
            f"Auto-poll {state}. Match {self.config.match_number}, {self.config.map_name}, "
            f"every {self.config.poll_seconds}s. {self.last_status}"
        )

    async def _loop(self, channel: Any | None) -> None:
        assert self.config is not None
        while True:
            try:
                await self.poll_once()
                if self.tracker.is_match_over and self.last_results and not self.waiting_for_new_match:
                    await self._save_current_match(channel)
                    self.waiting_for_new_match = True
                elif self.waiting_for_new_match and self.tracker.alive_team_count > 1:
                    self.tracker = MatchTracker()
                    self.last_results = []
                    self.waiting_for_new_match = False
                    self.last_status = f"Detected next match data. Tracking match {self.config.match_number}."
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - visible in Discord status
                self.last_error = str(exc)
                self.last_status = f"Auto-poll error: {exc}"
            await asyncio.sleep(max(1, self.config.poll_seconds))

    async def _save_current_match(self, channel: Any | None) -> None:
        assert self.config is not None
        saved_match = self.config.match_number
        em = manager_for(self.config.email)
        em.save_match_result(saved_match, self.config.map_name, self.last_results)
        save_exports(em)
        self.last_saved_match = saved_match
        self.last_status = f"Saved match {saved_match}."
        message = f"Saved match {saved_match} from live result feed. Sending result table now."
        self.config.match_number = em.next_match_number()

        if channel is not None:
            path = discord_match_table_path(em, saved_match)
            if path is not None and path.exists():
                try:
                    import discord

                    await channel.send(
                        content=match_result_caption(em, saved_match),
                        file=discord.File(str(path), filename=match_table_filename(saved_match)),
                    )
                    return
                except Exception as exc:  # noqa: BLE001 - fall back to text if Discord rejects the file
                    self.last_error = str(exc)
                    message += "\n" + format_results(em, saved_match, limit=8)
            for chunk in chunk_message(message):
                await channel.send(chunk)

def fetch_json(url: str) -> dict:
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Live result feed returned JSON, but not an object.")
    return payload


def default_auto_config(
    api_url: str = "",
    poll_seconds: int = DEFAULT_POLL_SECONDS,
    map_name: str = "Erangel",
    match_number: int = 0,
) -> AutoPollConfig:
    email = configured_email()
    em = manager_for(email)
    chosen_match = match_number if int(match_number or 0) > 0 else em.next_match_number()
    return AutoPollConfig(
        email=email,
        api_url=api_url or os.environ.get("OBSERVER_API_URL", DEFAULT_API_URL),
        poll_seconds=safe_int(
            poll_seconds or os.environ.get("OBSERVER_POLL_SECONDS"),
            DEFAULT_POLL_SECONDS,
            1,
            60,
        ),
        match_number=safe_int(chosen_match, em.next_match_number(), 1, 99),
        map_name=map_name or os.environ.get("OBSERVER_MAP", "Erangel"),
        mock_mode=os.environ.get("OBSERVER_MOCK_MODE", "").strip().lower()
        in {"1", "true", "yes", "on"},
    )


def create_bot():
    import discord
    from discord import app_commands
    from discord.ext import commands

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix=commands.when_mentioned_or("!"), intents=intents)
    runner = AutoPollRunner()

    async def send_text(destination: Any, text: str) -> None:
        for chunk in chunk_message(text):
            await destination.send(chunk)

    async def send_file(destination: Any, path: Path | None, content: str, missing: str) -> None:
        if path is None or not path.exists():
            await send_text(destination, missing)
            return
        await destination.send(content=content, file=discord.File(str(path)))

    async def reply_file(interaction: discord.Interaction, path: Path | None, content: str, missing: str) -> None:
        if path is None or not path.exists():
            await interaction.response.send_message(missing)
            return
        await interaction.response.send_message(content=content, file=discord.File(str(path)))

    async def send_table_file(
        destination: Any,
        path: Path | None,
        content: str,
        missing: str,
        filename: str | None = None,
    ) -> None:
        if path is None or not path.exists():
            await send_text(destination, missing)
            return
        await destination.send(content=content, file=discord.File(str(path), filename=filename or path.name))

    async def reply_table_file(
        interaction: discord.Interaction,
        path: Path | None,
        content: str,
        missing: str,
        filename: str | None = None,
    ) -> None:
        if path is None or not path.exists():
            await interaction.response.send_message(missing)
            return
        await interaction.response.send_message(
            content=content,
            file=discord.File(str(path), filename=filename or path.name),
        )

    async def send_match_result_table(
        destination: Any,
        current: EventManager | None,
        match: int | None = None,
    ) -> None:
        number = match or latest_match_number(current)
        await send_table_file(
            destination,
            discord_match_table_path(current, number),
            match_result_caption(current, number),
            format_results(current, number),
            match_table_filename(number),
        )

    async def reply_match_result_table(
        interaction: discord.Interaction,
        current: EventManager | None,
        match: int | None = None,
    ) -> None:
        number = match or latest_match_number(current)
        await reply_table_file(
            interaction,
            discord_match_table_path(current, number),
            match_result_caption(current, number),
            format_results(current, number),
            match_table_filename(number),
        )

    async def send_overall_standings_table(destination: Any, current: EventManager | None, top: int = 16) -> None:
        chosen_top = safe_int(top, 16, 1, 50)
        await send_table_file(
            destination,
            discord_overall_table_path(current, chosen_top),
            overall_standings_caption(current),
            format_standings(current, chosen_top),
            f"overall_top_{chosen_top:02d}_table.png",
        )

    async def reply_overall_standings_table(
        interaction: discord.Interaction,
        current: EventManager | None,
        top: int = 16,
    ) -> None:
        chosen_top = safe_int(top, 16, 1, 50)
        await reply_table_file(
            interaction,
            discord_overall_table_path(current, chosen_top),
            overall_standings_caption(current),
            format_standings(current, chosen_top),
            f"overall_top_{chosen_top:02d}_table.png",
        )

    async def send_players_table(destination: Any, current: EventManager | None, top: int = 10) -> None:
        chosen_top = safe_int(top, 10, 1, 50)
        event_name = current.event.get("eventName", "PUBGM Event") if current else "PUBGM Event"
        await send_table_file(
            destination,
            discord_players_table_path(current, chosen_top),
            f"**{event_name}**\nTop {chosen_top} Players",
            format_players(current, chosen_top),
            f"top_players_{chosen_top:02d}_table.png",
        )

    async def reply_players_table(
        interaction: discord.Interaction,
        current: EventManager | None,
        top: int = 10,
    ) -> None:
        chosen_top = safe_int(top, 10, 1, 50)
        event_name = current.event.get("eventName", "PUBGM Event") if current else "PUBGM Event"
        await reply_table_file(
            interaction,
            discord_players_table_path(current, chosen_top),
            f"**{event_name}**\nTop {chosen_top} Players",
            format_players(current, chosen_top),
            f"top_players_{chosen_top:02d}_table.png",
        )

    async def send_matches_table(destination: Any, current: EventManager | None) -> None:
        event_name = current.event.get("eventName", "PUBGM Event") if current else "PUBGM Event"
        await send_table_file(
            destination,
            discord_matches_table_path(current),
            f"**{event_name}**\nSaved Matches",
            format_matches(current),
            "saved_matches_table.png",
        )

    async def reply_matches_table(interaction: discord.Interaction, current: EventManager | None) -> None:
        event_name = current.event.get("eventName", "PUBGM Event") if current else "PUBGM Event"
        await reply_table_file(
            interaction,
            discord_matches_table_path(current),
            f"**{event_name}**\nSaved Matches",
            format_matches(current),
            "saved_matches_table.png",
        )

    async def send_event_table(destination: Any, current: EventManager | None) -> None:
        event_name = current.event.get("eventName", "PUBGM Event") if current else "PUBGM Event"
        await send_table_file(
            destination,
            discord_event_table_path(current),
            f"**{event_name}**\nEvent Details",
            format_event(current),
            "event_details_table.png",
        )

    async def reply_event_table(interaction: discord.Interaction, current: EventManager | None) -> None:
        event_name = current.event.get("eventName", "PUBGM Event") if current else "PUBGM Event"
        await reply_table_file(
            interaction,
            discord_event_table_path(current),
            f"**{event_name}**\nEvent Details",
            format_event(current),
            "event_details_table.png",
        )

    async def send_live_results_table(destination: Any, current: EventManager | None, results: list[dict]) -> None:
        await send_table_file(
            destination,
            discord_live_table_path(current, results),
            "Live result check complete.",
            "Live result check complete. No live result rows were returned.",
            "live_result_check_table.png",
        )

    async def send_match_result_sheet(
        destination: Any,
        current: EventManager | None,
        match: int | None = None,
    ) -> None:
        number = match or latest_match_number(current)
        path = match_image_path(current, number)
        if path is None or not path.exists():
            await send_text(destination, format_results(current, number))
            return
        await destination.send(
            content=match_result_caption(current, number),
            file=discord.File(str(path), filename=match_result_filename(number)),
        )

    async def reply_match_result_sheet(
        interaction: discord.Interaction,
        current: EventManager | None,
        match: int | None = None,
    ) -> None:
        number = match or latest_match_number(current)
        path = match_image_path(current, number)
        if path is None or not path.exists():
            await reply_interaction(interaction, format_results(current, number))
            return
        await interaction.response.send_message(
            content=match_result_caption(current, number),
            file=discord.File(str(path), filename=match_result_filename(number)),
        )

    async def send_overall_standings_sheet(destination: Any, current: EventManager | None) -> None:
        path = overall_image_path(current)
        if path is None or not path.exists():
            await send_text(destination, format_standings(current))
            return
        await destination.send(
            content=overall_standings_caption(current),
            file=discord.File(str(path), filename="overall_standings.png"),
        )

    async def reply_overall_standings_sheet(
        interaction: discord.Interaction,
        current: EventManager | None,
    ) -> None:
        path = overall_image_path(current)
        if path is None or not path.exists():
            await reply_interaction(interaction, format_standings(current))
            return
        await interaction.response.send_message(
            content=overall_standings_caption(current),
            file=discord.File(str(path), filename="overall_standings.png"),
        )

    async def reply_interaction(interaction: discord.Interaction, text: str) -> None:
        chunks = chunk_message(text)
        await interaction.response.send_message(chunks[0])
        for chunk in chunks[1:]:
            await interaction.followup.send(chunk)

    def can_manage_member(member: Any) -> bool:
        permissions = getattr(member, "guild_permissions", None)
        if permissions and getattr(permissions, "manage_guild", False):
            return True
        wanted = os.environ.get("DISCORD_ADMIN_ROLE", "").strip().lower()
        if not wanted:
            return False
        for role in getattr(member, "roles", []) or []:
            if str(getattr(role, "id", "")).lower() == wanted:
                return True
            if str(getattr(role, "name", "")).lower() == wanted:
                return True
        return False

    async def require_manager_for_context(ctx: commands.Context) -> bool:
        if can_manage_member(ctx.author):
            return True
        await ctx.reply("Only event managers can control live result automation.")
        return False

    async def require_manager_for_interaction(interaction: discord.Interaction) -> bool:
        if can_manage_member(interaction.user):
            return True
        await interaction.response.send_message(
            "Only event managers can control live result automation.",
            ephemeral=True,
        )
        return False

    def em() -> EventManager | None:
        email = configured_email()
        ref = active_event_ref(email)
        if not ref:
            return None
        return EventManager(ref["dataDir"])

    @bot.event
    async def on_ready() -> None:
        guild_id = os.environ.get("DISCORD_GUILD_ID", "").strip()
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
        else:
            await bot.tree.sync()

        channel_id = os.environ.get("DISCORD_ANNOUNCE_CHANNEL_ID", "").strip()
        auto = os.environ.get("DISCORD_AUTOPOLL", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if auto and channel_id and not runner.running:
            channel = bot.get_channel(int(channel_id))
            await runner.start(default_auto_config(), channel)
        print(f"Discord bot logged in as {bot.user}")

    @bot.command(name="results")
    async def results_cmd(ctx: commands.Context, match: int | None = None) -> None:
        await send_match_result_table(ctx, em(), match)

    @bot.command(name="standings")
    async def standings_cmd(ctx: commands.Context, top: int = 16) -> None:
        current = em()
        chosen_top = safe_int(top, 16, 1, 50)
        await send_overall_standings_table(ctx, current, chosen_top)

    @bot.command(name="matches")
    async def matches_cmd(ctx: commands.Context) -> None:
        await send_matches_table(ctx, em())

    @bot.command(name="players")
    async def players_cmd(ctx: commands.Context, top: int = 10) -> None:
        await send_players_table(ctx, em(), safe_int(top, 10, 1, 50))

    @bot.command(name="event")
    async def event_cmd(ctx: commands.Context) -> None:
        await send_event_table(ctx, em())

    @bot.command(name="teamss", aliases=["matchss", "resultss"])
    async def teamss_cmd(ctx: commands.Context, match: int | None = None) -> None:
        await send_match_result_sheet(ctx, em(), match)

    @bot.command(name="overallss", aliases=["standingss"])
    async def overallss_cmd(ctx: commands.Context) -> None:
        await send_overall_standings_sheet(ctx, em())

    @bot.command(name="playerdetails", aliases=["playerscsv", "playercsv"])
    async def playerdetails_cmd(ctx: commands.Context) -> None:
        await send_file(
            ctx,
            player_details_csv_path(em()),
            "Full player details CSV",
            "Please wait, player details are not available yet. Try again after the organizer posts the match result.",
        )

    @bot.command(name="autostart")
    async def autostart_cmd(
        ctx: commands.Context,
        live_link: str = "",
        poll_seconds: int = DEFAULT_POLL_SECONDS,
        map_name: str = "Erangel",
        match_number: int = 0,
    ) -> None:
        if not await require_manager_for_context(ctx):
            return
        if em() is None:
            await ctx.reply(PUBLIC_EVENT_NOT_READY)
            return
        config = default_auto_config(live_link, poll_seconds, map_name, match_number)
        await runner.start(config, ctx.channel)
        await ctx.reply(runner.status_text())

    @bot.command(name="autostop")
    async def autostop_cmd(ctx: commands.Context) -> None:
        if not await require_manager_for_context(ctx):
            return
        await runner.stop()
        await ctx.reply(runner.status_text())

    @bot.command(name="autostatus")
    async def autostatus_cmd(ctx: commands.Context) -> None:
        await ctx.reply(runner.status_text())

    @bot.command(name="pollonce")
    async def pollonce_cmd(ctx: commands.Context, live_link: str = "") -> None:
        if not await require_manager_for_context(ctx):
            return
        if em() is None:
            await ctx.reply(PUBLIC_EVENT_NOT_READY)
            return
        config = default_auto_config(live_link)
        if not runner.config:
            runner.config = config
        else:
            runner.config.api_url = config.api_url
        await runner.poll_once()
        await send_live_results_table(ctx, em(), runner.last_results)

    @bot.tree.command(name="results", description="Show latest or selected match results.")
    @app_commands.describe(match="Match number. Leave empty for latest.")
    async def results_slash(interaction: discord.Interaction, match: int | None = None) -> None:
        await reply_match_result_table(interaction, em(), match)

    @bot.tree.command(name="standings", description="Show overall standings.")
    @app_commands.describe(top="How many teams to show.")
    async def standings_slash(interaction: discord.Interaction, top: int = 16) -> None:
        current = em()
        chosen_top = safe_int(top, 16, 1, 50)
        await reply_overall_standings_table(interaction, current, chosen_top)

    @bot.tree.command(name="matches", description="List saved matches.")
    async def matches_slash(interaction: discord.Interaction) -> None:
        await reply_matches_table(interaction, em())

    @bot.tree.command(name="players", description="Show top players.")
    @app_commands.describe(top="How many players to show.")
    async def players_slash(interaction: discord.Interaction, top: int = 10) -> None:
        await reply_players_table(interaction, em(), safe_int(top, 10, 1, 50))

    @bot.tree.command(name="event", description="Show current event info.")
    async def event_slash(interaction: discord.Interaction) -> None:
        await reply_event_table(interaction, em())

    @bot.tree.command(name="teamss", description="Send the latest or selected match result image.")
    @app_commands.describe(match="Match number. Leave empty for latest.")
    async def teamss_slash(interaction: discord.Interaction, match: int | None = None) -> None:
        await reply_match_result_sheet(interaction, em(), match)

    @bot.tree.command(name="overallss", description="Send the overall standings image.")
    async def overallss_slash(interaction: discord.Interaction) -> None:
        await reply_overall_standings_sheet(interaction, em())

    @bot.tree.command(name="playerdetails", description="Send full player details as CSV.")
    async def playerdetails_slash(interaction: discord.Interaction) -> None:
        await reply_file(
            interaction,
            player_details_csv_path(em()),
            "Full player details CSV",
            "Please wait, player details are not available yet. Try again after the organizer posts the match result.",
        )

    @bot.tree.command(name="autostart", description="Start live result auto-save.")
    @app_commands.describe(
        live_link="Live result link.",
        poll_seconds="Seconds between polls.",
        map_name="Map name to save with the match.",
        match_number="Match number. Leave 0 for next match.",
        mock_mode="Use generated sample live data.",
    )
    async def autostart_slash(
        interaction: discord.Interaction,
        live_link: str = "",
        poll_seconds: int = DEFAULT_POLL_SECONDS,
        map_name: str = "Erangel",
        match_number: int = 0,
        mock_mode: bool = False,
    ) -> None:
        if not await require_manager_for_interaction(interaction):
            return
        if em() is None:
            await interaction.response.send_message(PUBLIC_EVENT_NOT_READY, ephemeral=True)
            return
        config = default_auto_config(live_link, poll_seconds, map_name, match_number)
        config.mock_mode = mock_mode
        await runner.start(config, interaction.channel)
        await interaction.response.send_message(runner.status_text())

    @bot.tree.command(name="autostop", description="Stop live result auto-save.")
    async def autostop_slash(interaction: discord.Interaction) -> None:
        if not await require_manager_for_interaction(interaction):
            return
        await runner.stop()
        await interaction.response.send_message(runner.status_text())

    @bot.tree.command(name="autostatus", description="Show live result automation status.")
    async def autostatus_slash(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(runner.status_text())

    return bot


def main() -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "Set DISCORD_BOT_TOKEN first. Example:\n"
            "  set DISCORD_BOT_TOKEN=your_token_here\n"
            "Then run: python discord_bot.py"
        )
    create_bot().run(token)


if __name__ == "__main__":
    main()

