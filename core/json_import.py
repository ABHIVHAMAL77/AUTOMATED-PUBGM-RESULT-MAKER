"""Import already-saved match JSON into the manual review flow."""

from __future__ import annotations

from core.models import parse_snapshot
from core.scoring import build_team_result, placement_points

RESULT_KEYS = ("results", "Results", "matchResults", "MatchResults")
TEAM_KEYS = ("teams", "Teams", "rows", "Rows")
PLAYER_LIST_KEYS = (
    "TotalPlayerList", "totalPlayerList",
    "PlayerInfoList", "playerInfoList",
    "PlayerList", "playerList",
    "players", "Players",
)
TEAM_LIST_KEYS = ("TeamInfoList", "teamInfoList", "TeamList", "teamList")


def import_match_json(data, point_system: dict, name_overrides: dict | None = None) -> dict:
    """Return review rows parsed from a saved result or observer JSON file."""
    name_overrides = name_overrides or {}
    payload = _payload(data)
    results, source = _extract_results(payload, point_system, name_overrides)
    if not results:
        raise ValueError(
            "No match result rows were found in this JSON. Upload a saved match JSON, "
            "a team-results JSON, or a final observer JSON with placement ranks."
        )

    rows = [_row_from_result(result) for result in results]
    rows.sort(key=lambda row: (not bool(row["rank"]), int(row["rank"] or 999)))
    problems = _problems(rows)
    return {
        "rows": rows,
        "cards": [],
        "errors": [],
        "problems": problems,
        "engineUsed": "json",
        "escalatedCards": 0,
        "source": source,
        "matchNumber": _int(_get(payload, "matchNumber", "match", "matchNo", "match_no")),
        "map": str(_get(payload, "map", "mapName", "Map", default="") or ""),
    }


def result_from_manual_payload(entry, point_system: dict) -> dict:
    """Build a saved-match result while preserving imported API/player details."""
    rank = int(entry.rank)
    slot = int(entry.slot)
    team_name = entry.teamName.strip() or f"Team {slot}"
    kills = int(entry.kills or 0)
    pp = placement_points(rank, point_system)
    kp = kills * int(point_system.get("killPoint", 1))

    raw = entry.rawResult if isinstance(entry.rawResult, dict) else None
    result = dict(raw or {})
    result.update({
        "teamId": slot,
        "teamName": team_name,
        "placement": rank,
        "kills": kills,
        "placementPoints": pp,
        "killPoints": kp,
        "totalPoints": pp + kp,
        "wwcd": rank == 1,
    })
    result["players"] = _players_for_save(entry.players, raw)
    return result


def _extract_results(payload, point_system: dict, name_overrides: dict) -> tuple[list, str]:
    if isinstance(payload, list):
        return [_normalise_result(item, point_system) for item in payload if isinstance(item, dict)], "rows"
    if not isinstance(payload, dict):
        return [], "unknown"

    for key in RESULT_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return [_normalise_result(item, point_system) for item in value if isinstance(item, dict)], "results"

    for key in TEAM_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return [_normalise_result(item, point_system) for item in value if isinstance(item, dict)], "teams"

    if _has_any_list(payload, PLAYER_LIST_KEYS) or _has_any_list(payload, TEAM_LIST_KEYS):
        return _results_from_observer(payload, point_system, name_overrides), "observer"

    return [], "unknown"


def _results_from_observer(payload: dict, point_system: dict, name_overrides: dict) -> list:
    snap = parse_snapshot(payload)
    states = snap.team_states()
    if not states:
        return []

    for state in states.values():
        if state.api_rank:
            continue
        ranks = [int(player.rank) for player in state.players if int(player.rank or 0) > 0]
        if ranks:
            state.api_rank = min(ranks)

    if not any(state.api_rank > 0 for state in states.values()):
        raise ValueError(
            "This looks like live observer JSON, but it has no final placement ranks. "
            "Use a JSON saved after the match finished, or save from Live API while polling."
        )

    ordered = sorted(states.values(), key=lambda state: (state.api_rank or 999, -state.kills))
    return [
        build_team_result(state, state.api_rank or placement, point_system, name_overrides.get(state.teamId, ""))
        for placement, state in enumerate(ordered, start=1)
    ]


def _normalise_result(item: dict, point_system: dict) -> dict:
    rank = _int(_get(item, "placement", "rank", "place", "teamRank"))
    slot = _int(_get(item, "teamId", "slot", "teamID", "team_id", "campId"))
    players = _players_from_result(item)
    kills = _int(
        _get(item, "kills", "killNum", "killCount", "eliminations", "elims"),
        default=sum(player["kills"] for player in players),
    )
    team_name = str(
        _get(item, "teamName", "name", "team", "team_name", "shortName", default="") or ""
    ).strip()
    if not team_name and slot:
        team_name = f"Team {slot}"

    pp = placement_points(rank, point_system) if rank else _int(item.get("placementPoints"))
    kp = kills * int(point_system.get("killPoint", 1))
    result = dict(item)
    result.update({
        "teamId": slot,
        "teamName": team_name,
        "placement": rank,
        "kills": kills,
        "placementPoints": pp,
        "killPoints": kp,
        "totalPoints": pp + kp,
        "wwcd": rank == 1,
        "players": _normalised_raw_players(item, players),
    })
    return result


def _row_from_result(result: dict) -> dict:
    rank = _int(_get(result, "placement", "rank", "place", "teamRank"))
    slot = _int(_get(result, "teamId", "slot", "teamID", "team_id", "campId"))
    players = _players_from_result(result)
    kills = _int(
        _get(result, "kills", "killNum", "killCount", "eliminations", "elims"),
        default=sum(player["kills"] for player in players),
    )
    return {
        "rank": rank or "",
        "slot": slot or "",
        "teamName": str(_get(result, "teamName", "name", "team", "team_name", default="") or ""),
        "kills": kills,
        "matchScore": 1.0,
        "players": players,
        "confidence": 1.0,
        "confidenceReasons": ["Imported from JSON. Check the row before saving."],
        "needsReview": not rank or not slot,
        "source": "json",
        "sourceOrder": rank or 999,
        "rawResult": result,
    }


def _players_from_result(item: dict) -> list:
    raw_players = _get(
        item,
        "players", "Players", "playerStats", "PlayerStats", "members", "Members",
        default=[],
    )
    if not isinstance(raw_players, list):
        return []
    players = []
    for player in raw_players:
        if isinstance(player, str):
            name = player.strip()
            kills = 0
        elif isinstance(player, dict):
            name = str(_get(
                player,
                "playerName", "name", "userName", "nickName", "nickname",
                default="",
            ) or "").strip()
            kills = _int(_get(player, "kills", "killNum", "kill", "eliminations", "elims"))
        else:
            continue
        if name:
            players.append({"name": name, "kills": kills})
    return players


def _normalised_raw_players(item: dict, ui_players: list) -> list:
    raw_players = _get(item, "players", "Players", "playerStats", "PlayerStats", default=[])
    raw_players = raw_players if isinstance(raw_players, list) else []
    out = []
    for index, player in enumerate(ui_players):
        raw = raw_players[index] if index < len(raw_players) and isinstance(raw_players[index], dict) else {}
        saved = dict(raw)
        saved.setdefault("uId", str(_get(raw, "uId", "uid", "playerOpenId", default="") or ""))
        saved.update({
            "playerName": player["name"],
            "kills": int(player["kills"]),
            "damage": _float(_get(saved, "damage", "damageDealt", "totalDamage")),
            "knockouts": _int(_get(saved, "knockouts", "knockout", "knockoutNum", "knockNum")),
            "headshots": _int(_get(saved, "headshots", "headShotNum")),
            "assists": _int(_get(saved, "assists", "assist", "assistNum")),
            "damageReceived": _float(_get(saved, "damageReceived", "inDamage", "damageTaken")),
            "survivalTime": _float(_get(saved, "survivalTime", "surviveTime", "liveTime")),
            "heal": _float(_get(saved, "heal", "heals", "healAmount")),
            "rescues": _int(_get(saved, "rescues", "rescueTimes", "revives")),
            "longestKill": _float(_get(saved, "longestKill", "maxKillDistance")),
            "grenadeKills": _int(_get(saved, "grenadeKills", "killNumByGrenade")),
            "raw": dict(raw),
        })
        out.append(saved)
    return out


def _players_for_save(players, raw_result: dict | None) -> list:
    raw_players = []
    if isinstance(raw_result, dict) and isinstance(raw_result.get("players"), list):
        raw_players = raw_result["players"]

    out = []
    for index, player in enumerate(players or []):
        name = str(getattr(player, "name", "") or "").strip()
        if not name:
            continue
        raw = raw_players[index] if index < len(raw_players) and isinstance(raw_players[index], dict) else {}
        saved = dict(raw)
        saved.setdefault("uId", str(_get(raw, "uId", "uid", "playerOpenId", default="") or ""))
        saved.update({
            "playerName": name,
            "kills": int(getattr(player, "kills", 0) or 0),
            "damage": _float(_get(saved, "damage", "damageDealt", "totalDamage")),
            "knockouts": _int(_get(saved, "knockouts", "knockout", "knockoutNum", "knockNum")),
            "headshots": _int(_get(saved, "headshots", "headShotNum")),
            "assists": _int(_get(saved, "assists", "assist", "assistNum")),
            "damageReceived": _float(_get(saved, "damageReceived", "inDamage", "damageTaken")),
            "survivalTime": _float(_get(saved, "survivalTime", "surviveTime", "liveTime")),
            "heal": _float(_get(saved, "heal", "heals", "healAmount")),
            "rescues": _int(_get(saved, "rescues", "rescueTimes", "revives")),
            "longestKill": _float(_get(saved, "longestKill", "maxKillDistance")),
            "grenadeKills": _int(_get(saved, "grenadeKills", "killNumByGrenade")),
            "raw": dict(raw.get("raw") if isinstance(raw.get("raw"), dict) else raw),
        })
        out.append(saved)
    return out


def _payload(data):
    if not isinstance(data, dict):
        return data
    for key in ("data", "Data", "result", "Result", "payload", "Payload", "response", "Response"):
        value = data.get(key)
        if isinstance(value, (dict, list)):
            return value
    return data


def _get(d, *keys, default=None):
    for key in keys:
        if isinstance(d, dict) and key in d and d[key] is not None:
            return d[key]
    return default


def _has_any_list(d: dict, keys: tuple[str, ...]) -> bool:
    return any(isinstance(d.get(key), list) for key in keys)


def _int(value, default: int = 0) -> int:
    try:
        return int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default


def _float(value, default: float = 0.0) -> float:
    try:
        return float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default


def _problems(rows: list) -> list:
    problems = []
    if any(not row["rank"] for row in rows):
        problems.append("Some imported rows need a rank.")
    if any(not row["slot"] for row in rows):
        problems.append("Some imported rows need a slot/team number.")

    ranks = [int(row["rank"]) for row in rows if row["rank"]]
    slots = [int(row["slot"]) for row in rows if row["slot"]]
    for label, values in (("rank", ranks), ("slot", slots)):
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            problems.append(
                f"Duplicate {label}(s) in JSON: " + ", ".join(str(value) for value in duplicates)
            )
    return problems
