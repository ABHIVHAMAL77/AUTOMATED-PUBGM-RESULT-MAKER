"""Event data: teams, point system, saved match results, overall standings.

All data lives under the app's data/ folder:
    data/event.json               event name, teams, point system
    data/results/match_01.json    finalized match results
    data/exports/                 rendered PNG graphics
"""

import json
import re
from datetime import datetime
from pathlib import Path

from .scoring import DEFAULT_POINT_SYSTEM

#: Look of the exported PNGs. `template` is a key from core/graphic_themes.py,
#: or "custom" to use the uploaded background. Filenames are relative to the
#: event's own branding/ folder so an event stays self-contained.
DEFAULT_GRAPHICS = {
    "template": "midnight-gold",
    "accent": "",
    "text": "",
    "title": "",
    "background": "",
    "logo": "",
    "logoPosition": "top-right",
    "showLogo": True,
    "scrim": None,
    "layout": "",
}

DEFAULT_EVENT = {
    "eventName": "My PUBGM Event",
    "stage": "",
    "totalMatches": 6,  # tournaments can run up to 30+ matches
    "pointSystem": DEFAULT_POINT_SYSTEM,
    "teams": [],  # [{"teamId": 1, "teamName": "Alpha Esports", "shortName": "ALPHA"}]
    "graphics": DEFAULT_GRAPHICS,
}


def default_graphics() -> dict:
    """A fresh copy — the module-level dict must never be handed out, or one
    event's template change would edit every other event's defaults."""
    return dict(DEFAULT_GRAPHICS)


class EventManager:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.results_dir = self.data_dir / "results"
        self.exports_dir = self.data_dir / "exports"
        self.event_file = self.data_dir / "event.json"
        for d in (self.data_dir, self.results_dir, self.exports_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.event = self._load_event()

    # ---- event -----------------------------------------------------------
    def _load_event(self) -> dict:
        if self.event_file.exists():
            try:
                data = json.loads(self.event_file.read_text(encoding="utf-8"))
                # Deep-copy the defaults in: handing out the module-level dict
                # would let one event's edits mutate every other event's
                # defaults for the life of the process.
                for key, val in DEFAULT_EVENT.items():
                    data.setdefault(key, json.loads(json.dumps(val)))
                # events saved before the graphics block existed only get the
                # keys they are missing, not a reset of the ones they have
                graphics = data.get("graphics")
                if isinstance(graphics, dict):
                    for key, val in DEFAULT_GRAPHICS.items():
                        graphics.setdefault(key, val)
                else:
                    data["graphics"] = default_graphics()
                return data
            except (json.JSONDecodeError, OSError):
                pass
        return json.loads(json.dumps(DEFAULT_EVENT))

    def save_event(self):
        self.event_file.write_text(
            json.dumps(self.event, indent=2, ensure_ascii=False), encoding="utf-8")

    # ---- result graphics -------------------------------------------------
    @property
    def branding_dir(self) -> Path:
        """Where this event's uploaded background and logo live.

        Kept inside the event folder so an event is self-contained: copy the
        folder and the artwork travels with it.
        """
        path = self.data_dir / "branding"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def branding(self):
        """The event's graphic template and artwork, ready to render with.

        Both the desktop app and the web app call this, so a template chosen
        in one is the template the other exports with.
        """
        from .graphic_themes import Branding

        directory = self.branding_dir
        return Branding.from_event(
            self.event, resolve=lambda name: directory / Path(str(name)).name)

    def team_name_overrides(self) -> dict:
        """teamId -> configured display name (falls back to API names if empty)."""
        return {
            int(t["teamId"]): t.get("teamName", "")
            for t in self.event.get("teams", [])
            if t.get("teamName")
        }

    # ---- match results ---------------------------------------------------
    def _match_path(self, number: int) -> Path:
        return self.results_dir / f"match_{number:02d}.json"

    def save_match_result(self, match_number: int, map_name: str, results: list) -> Path:
        payload = {
            "matchNumber": match_number,
            "map": map_name,
            "eventName": self.event.get("eventName", ""),
            "finalizedAt": datetime.now().isoformat(timespec="seconds"),
            "results": results,
        }
        path = self._match_path(match_number)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def list_match_numbers(self) -> list:
        numbers = []
        for f in sorted(self.results_dir.glob("match_*.json")):
            m = re.match(r"match_(\d+)\.json", f.name)
            if m:
                numbers.append(int(m.group(1)))
        return numbers

    def load_match(self, number: int) -> dict | None:
        path = self._match_path(number)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def delete_match(self, number: int):
        path = self._match_path(number)
        if path.exists():
            path.unlink()

    def next_match_number(self) -> int:
        nums = self.list_match_numbers()
        return (max(nums) + 1) if nums else 1

    # ---- overall standings -------------------------------------------------
    def overall_standings(self) -> list:
        """Aggregate all saved matches into overall standings.

        Tiebreakers (standard PUBGM): total points, WWCD count,
        placement points, total kills, best single-match placement.
        """
        agg = {}
        for num in self.list_match_numbers():
            match = self.load_match(num)
            if not match:
                continue
            for r in match.get("results", []):
                tid = r["teamId"]
                a = agg.setdefault(tid, {
                    "teamId": tid,
                    "teamName": r["teamName"],
                    "matches": 0,
                    "kills": 0,
                    "placementPoints": 0,
                    "killPoints": 0,
                    "totalPoints": 0,
                    "wwcd": 0,
                    "bestPlacement": 99,
                })
                a["teamName"] = r["teamName"]  # keep most recent name
                a["matches"] += 1
                a["kills"] += r["kills"]
                a["placementPoints"] += r["placementPoints"]
                a["killPoints"] += r["killPoints"]
                a["totalPoints"] += r["totalPoints"]
                a["wwcd"] += 1 if r.get("wwcd") else 0
                a["bestPlacement"] = min(a["bestPlacement"], r["placement"])

        standings = sorted(agg.values(), key=lambda a: (
            -a["totalPoints"], -a["wwcd"], -a["placementPoints"],
            -a["kills"], a["bestPlacement"],
        ))
        for i, a in enumerate(standings, start=1):
            a["rank"] = i
        return standings

    # ---- player stats ------------------------------------------------------
    def player_stats(self) -> list:
        """Aggregate per-player stats across all saved matches.

        Same columns as the 'Player Stats' sheet: elims, damage, headshots,
        assists, knockouts, damage received, survival time, heal, rescues,
        longest elimination, plus an MVP rating (each player's share of total
        lobby contribution: elims*2 + knockouts + assists*0.75 + damage/100
        + rescues*0.5).
        """
        agg = {}
        for num in self.list_match_numbers():
            match = self.load_match(num)
            if not match:
                continue
            for r in match.get("results", []):
                for p in r.get("players", []):
                    key = p.get("uId") or p.get("playerName")
                    if not key:
                        continue
                    a = agg.setdefault(key, {
                        "uId": p.get("uId", ""),
                        "playerName": p.get("playerName", ""),
                        "teamName": r["teamName"],
                        "matches": 0, "kills": 0, "damage": 0.0, "headshots": 0,
                        "assists": 0, "knockouts": 0, "damageReceived": 0.0,
                        "survivalTime": 0.0, "heal": 0.0, "rescues": 0,
                        "longestKill": 0.0, "grenadeKills": 0,
                    })
                    a["playerName"] = p.get("playerName") or a["playerName"]
                    a["teamName"] = r["teamName"]
                    a["matches"] += 1
                    a["kills"] += p.get("kills", 0)
                    a["damage"] += p.get("damage", 0)
                    a["headshots"] += p.get("headshots", 0)
                    a["assists"] += p.get("assists", 0)
                    a["knockouts"] += p.get("knockouts", 0)
                    a["damageReceived"] += p.get("damageReceived", 0)
                    a["survivalTime"] += p.get("survivalTime", 0)
                    a["heal"] += p.get("heal", 0)
                    a["rescues"] += p.get("rescues", 0)
                    a["longestKill"] = max(a["longestKill"], p.get("longestKill", 0))
                    a["grenadeKills"] += p.get("grenadeKills", 0)

        for a in agg.values():
            a["contribution"] = (a["kills"] * 2 + a["knockouts"] + a["assists"] * 0.75
                                 + a["damage"] / 100 + a["rescues"] * 0.5)
        total_contribution = sum(a["contribution"] for a in agg.values()) or 1.0
        stats = sorted(agg.values(), key=lambda a: (
            -a["kills"], -a["damage"], -a["knockouts"]))
        for i, a in enumerate(stats, start=1):
            a["rank"] = i
            a["mvpRating"] = round(a["contribution"] / total_contribution, 6)
            a["damage"] = round(a["damage"], 1)
            a["damageReceived"] = round(a["damageReceived"], 1)
            a["survivalTime"] = round(a["survivalTime"], 1)
            a["heal"] = round(a["heal"], 1)
            a["contribution"] = round(a["contribution"], 2)
        return stats
