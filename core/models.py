"""Data models for the PUBG Mobile observer API.

The observer endpoint commonly runs at
http://127.0.0.1:10086/gettotalplayerlist on the observer PC. Field names vary
between observer versions, so parsing is intentionally tolerant.
"""

from dataclasses import dataclass, field


# liveState 5 = dead in the observer API; knocked players still count as alive
DEAD_LIVE_STATE = 5


@dataclass
class Player:
    uId: str = ""
    playerName: str = ""
    teamId: int = 0
    teamName: str = ""
    health: float = 0.0
    liveState: int = 0
    killNum: int = 0
    damage: float = 0.0
    knockouts: int = 0
    rank: int = 0
    survivalTime: float = 0.0
    bHasDied: bool = False
    # extended stats (Player Stats sheet / OVERALL GD dump)
    headShotNum: int = 0
    assists: int = 0
    heal: float = 0.0
    rescueTimes: int = 0
    inDamage: float = 0.0
    maxKillDistance: float = 0.0
    killNumByGrenade: int = 0
    killNumInVehicle: int = 0
    gotAirDropNum: int = 0
    driveDistance: float = 0.0
    marchDistance: float = 0.0
    outsideBlueCircleTime: float = 0.0
    useSmokeGrenadeNum: int = 0
    useFragGrenadeNum: int = 0
    useBurnGrenadeNum: int = 0
    useFlashGrenadeNum: int = 0
    raw: dict = field(default_factory=dict)  # original API row for full GD export

    @property
    def is_alive(self) -> bool:
        return not self.bHasDied and self.liveState != DEAD_LIVE_STATE


@dataclass
class TeamInfo:
    teamId: int = 0
    teamName: str = ""
    killNum: int = 0
    liveMemberNum: int = 0
    rank: int = 0


@dataclass
class TeamState:
    """Combined per-team view built from players + team info for one poll."""
    teamId: int = 0
    teamName: str = ""
    kills: int = 0
    alive_count: int = 0
    api_rank: int = 0
    players: list = field(default_factory=list)


@dataclass
class Snapshot:
    players: list = field(default_factory=list)
    teams: list = field(default_factory=list)
    is_mock: bool = False

    def team_states(self) -> dict:
        """Return {teamId: TeamState} merging player data with team info."""
        states = {}
        for p in self.players:
            if p.teamId <= 0:
                continue
            st = states.setdefault(p.teamId, TeamState(teamId=p.teamId))
            st.players.append(p)
            st.kills += p.killNum
            if p.is_alive:
                st.alive_count += 1
            if not st.teamName and p.teamName:
                st.teamName = p.teamName
        # Team info list is authoritative for kills/alive when present
        for t in self.teams:
            if t.teamId <= 0:
                continue
            st = states.setdefault(t.teamId, TeamState(teamId=t.teamId))
            if t.teamName:
                st.teamName = t.teamName
            if t.killNum > 0 or not st.players:
                st.kills = max(st.kills, t.killNum)
            st.api_rank = t.rank
            # liveMemberNum can lag; trust it only if we have no player data
            if not st.players:
                st.alive_count = t.liveMemberNum
        for st in states.values():
            if not st.teamName:
                st.teamName = f"Team {st.teamId}"
        return states


def _get(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    return default


def _payload(data: dict) -> dict:
    if not isinstance(data, dict):
        return {}
    for key in ("data", "Data", "result", "Result", "payload", "Payload", "response", "Response"):
        child = data.get(key)
        if isinstance(child, dict):
            return child
    return data


def _list(d: dict, *keys) -> list:
    value = _get(d, *keys, default=[])
    return value if isinstance(value, list) else []


def _int(value, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _float(value, default: float = 0.0) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "dead"}
    return False


def parse_snapshot(data: dict) -> Snapshot:
    snap = Snapshot()
    payload = _payload(data)
    raw_players = _list(
        payload,
        "TotalPlayerList", "totalPlayerList",
        "PlayerInfoList", "playerInfoList",
        "PlayerList", "playerList",
        "players", "Players",
    )
    raw_teams = _list(
        payload,
        "TeamInfoList", "teamInfoList",
        "TeamList", "teamList",
        "teams", "Teams",
    )

    for rp in raw_players:
        if not isinstance(rp, dict):
            continue
        snap.players.append(Player(
            uId=str(_get(rp, "uId", "uid", "UID", "playerOpenId", "openId", default="")),
            playerName=str(_get(rp, "playerName", "name", "userName", "nickName", "nickname", default="")),
            teamId=_int(_get(rp, "teamId", "teamID", "team_id", "campId", "campID", default=0)),
            teamName=str(_get(rp, "teamName", "team", "team_name", "campName", default="")),
            health=_float(_get(rp, "health", "hp", default=0)),
            liveState=_int(_get(rp, "liveState", "live_state", "state", default=0)),
            killNum=_int(_get(rp, "killNum", "kills", "kill", "killCount", "eliminations", "elims", default=0)),
            damage=_float(_get(rp, "damage", "damageDealt", "totalDamage", default=0)),
            knockouts=_int(_get(rp, "knockouts", "knockout", "knockoutNum", "knockNum", default=0)),
            rank=_int(_get(rp, "rank", "teamRank", "placement", "place", default=0)),
            survivalTime=_float(_get(rp, "survivalTime", "surviveTime", "liveTime", default=0)),
            bHasDied=_bool(_get(rp, "bHasDied", "hasDied", "isDead", "dead", default=False)),
            headShotNum=_int(_get(rp, "headShotNum", "headshots", default=0)),
            assists=_int(_get(rp, "assists", "assist", "assistNum", default=0)),
            heal=_float(_get(rp, "heal", "heals", "healAmount", default=0)),
            rescueTimes=_int(_get(rp, "rescueTimes", "rescues", "revives", default=0)),
            inDamage=_float(_get(rp, "inDamage", "damageTaken", default=0)),
            maxKillDistance=_float(_get(rp, "maxKillDistance", default=0)),
            killNumByGrenade=_int(_get(rp, "killNumByGrenade", default=0)),
            killNumInVehicle=_int(_get(rp, "killNumInVehicle", default=0)),
            gotAirDropNum=_int(_get(rp, "gotAirDropNum", default=0)),
            driveDistance=_float(_get(rp, "driveDistance", default=0)),
            marchDistance=_float(_get(rp, "marchDistance", default=0)),
            outsideBlueCircleTime=_float(_get(rp, "outsideBlueCircleTime", default=0)),
            useSmokeGrenadeNum=_int(_get(rp, "useSmokeGrenadeNum", default=0)),
            useFragGrenadeNum=_int(_get(rp, "useFragGrenadeNum", default=0)),
            useBurnGrenadeNum=_int(_get(rp, "useBurnGrenadeNum", default=0)),
            useFlashGrenadeNum=_int(_get(rp, "useFlashGrenadeNum", default=0)),
            raw=dict(rp),
        ))

    for rt in raw_teams:
        if not isinstance(rt, dict):
            continue
        snap.teams.append(TeamInfo(
            teamId=_int(_get(rt, "teamId", "teamID", "team_id", "campId", "campID", default=0)),
            teamName=str(_get(rt, "teamName", "name", "team", "team_name", "campName", default="")),
            killNum=_int(_get(rt, "killNum", "kills", "kill", "killCount", "eliminations", "elims", default=0)),
            liveMemberNum=_int(_get(rt, "liveMemberNum", "aliveNum", "aliveCount", "liveMembers", default=0)),
            rank=_int(_get(rt, "rank", "teamRank", "placement", "place", default=0)),
        ))

    return snap
