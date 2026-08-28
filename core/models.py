"""Data models for the PUBG Mobile observer API.

The observer API at http://127.0.0.1:10086/gettotalplayerlist returns JSON
with player and team lists. Field names vary between observer versions, so
parsing is tolerant: both "TotalPlayerList" / "playerInfoList" and
"TeamInfoList" / "teamInfoList" are handled, and every field is optional.
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
        if k in d and d[k] is not None:
            return d[k]
    return default


def parse_snapshot(data: dict) -> Snapshot:
    snap = Snapshot()
    raw_players = _get(data, "TotalPlayerList", "playerInfoList", default=[]) or []
    raw_teams = _get(data, "TeamInfoList", "teamInfoList", default=[]) or []

    for rp in raw_players:
        try:
            snap.players.append(Player(
                uId=str(_get(rp, "uId", "uid", default="")),
                playerName=str(_get(rp, "playerName", "name", default="")),
                teamId=int(_get(rp, "teamId", default=0) or 0),
                teamName=str(_get(rp, "teamName", default="")),
                health=float(_get(rp, "health", default=0) or 0),
                liveState=int(_get(rp, "liveState", default=0) or 0),
                killNum=int(_get(rp, "killNum", default=0) or 0),
                damage=float(_get(rp, "damage", default=0) or 0),
                knockouts=int(_get(rp, "knockouts", default=0) or 0),
                rank=int(_get(rp, "rank", default=0) or 0),
                survivalTime=float(_get(rp, "survivalTime", default=0) or 0),
                bHasDied=bool(_get(rp, "bHasDied", default=False)),
                headShotNum=int(_get(rp, "headShotNum", default=0) or 0),
                assists=int(_get(rp, "assists", default=0) or 0),
                heal=float(_get(rp, "heal", default=0) or 0),
                rescueTimes=int(_get(rp, "rescueTimes", default=0) or 0),
                inDamage=float(_get(rp, "inDamage", default=0) or 0),
                maxKillDistance=float(_get(rp, "maxKillDistance", default=0) or 0),
                killNumByGrenade=int(_get(rp, "killNumByGrenade", default=0) or 0),
                killNumInVehicle=int(_get(rp, "killNumInVehicle", default=0) or 0),
                gotAirDropNum=int(_get(rp, "gotAirDropNum", default=0) or 0),
                driveDistance=float(_get(rp, "driveDistance", default=0) or 0),
                marchDistance=float(_get(rp, "marchDistance", default=0) or 0),
                outsideBlueCircleTime=float(_get(rp, "outsideBlueCircleTime", default=0) or 0),
                useSmokeGrenadeNum=int(_get(rp, "useSmokeGrenadeNum", default=0) or 0),
                useFragGrenadeNum=int(_get(rp, "useFragGrenadeNum", default=0) or 0),
                useBurnGrenadeNum=int(_get(rp, "useBurnGrenadeNum", default=0) or 0),
                useFlashGrenadeNum=int(_get(rp, "useFlashGrenadeNum", default=0) or 0),
                raw=dict(rp),
            ))
        except (TypeError, ValueError):
            continue

    for rt in raw_teams:
        try:
            snap.teams.append(TeamInfo(
                teamId=int(_get(rt, "teamId", default=0) or 0),
                teamName=str(_get(rt, "teamName", default="")),
                killNum=int(_get(rt, "killNum", default=0) or 0),
                liveMemberNum=int(_get(rt, "liveMemberNum", default=0) or 0),
                rank=int(_get(rt, "rank", default=0) or 0),
            ))
        except (TypeError, ValueError):
            continue

    return snap
