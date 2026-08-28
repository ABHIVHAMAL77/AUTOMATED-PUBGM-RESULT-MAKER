"""Point calculation for PUBG Mobile esports matches.

Default point system (same as the broadcast engine's current_event.json):
1st=10, 2nd=6, 3rd=5, 4th=4, 5th=3, 6th=2, 7th=1, 8th=1, 9th+=0,
plus 1 point per kill.
"""

DEFAULT_POINT_SYSTEM = {
    "placementPoints": [10, 6, 5, 4, 3, 2, 1, 1],
    "killPoint": 1,
}


def placement_points(placement: int, point_system: dict) -> int:
    table = point_system.get("placementPoints", DEFAULT_POINT_SYSTEM["placementPoints"])
    if 1 <= placement <= len(table):
        return int(table[placement - 1])
    return 0


def build_team_result(team_state, placement: int, point_system: dict, display_name: str = "") -> dict:
    pp = placement_points(placement, point_system)
    kp = team_state.kills * int(point_system.get("killPoint", 1))
    return {
        "teamId": team_state.teamId,
        "teamName": display_name or team_state.teamName,
        "placement": placement,
        "kills": team_state.kills,
        "placementPoints": pp,
        "killPoints": kp,
        "totalPoints": pp + kp,
        "wwcd": placement == 1,
        "players": [
            {
                "playerName": p.playerName,
                "uId": p.uId,
                "kills": p.killNum,
                "damage": round(p.damage, 1),
                "knockouts": p.knockouts,
                "headshots": p.headShotNum,
                "assists": p.assists,
                "damageReceived": round(p.inDamage, 1),
                "survivalTime": round(p.survivalTime, 1),
                "heal": round(p.heal, 1),
                "rescues": p.rescueTimes,
                "longestKill": round(p.maxKillDistance, 1),
                "grenadeKills": p.killNumByGrenade,
                "raw": p.raw,
            }
            for p in team_state.players
        ],
    }
