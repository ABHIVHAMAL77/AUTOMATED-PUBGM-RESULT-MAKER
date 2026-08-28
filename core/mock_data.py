"""Mock match simulator so the app can be tested without the observer API.

Each call to fetch() advances a fake match: kills accumulate, teams get
eliminated one by one, and eventually a single team remains (match end).
"""

import random

from .models import Snapshot, Player, TeamInfo

TEAM_NAMES = [
    "Alpha Esports", "Bravo Kings", "Crimson Wolves", "Delta Force",
    "Eclipse Gaming", "Falcon Rise", "Ghost Reapers", "Hydra Official",
    "Inferno Squad", "Jade Vipers", "Kraken Unit", "Lunar Titans",
    "Midnight Owls", "Nova Strike", "Omega Legion", "Phantom Core",
]


class MockDataGenerator:
    def __init__(self, team_count: int = 16):
        self.team_count = min(team_count, len(TEAM_NAMES))
        self.tick = 0
        self.reset()

    def reset(self):
        self.tick = 0
        self._players = []
        for tid in range(1, self.team_count + 1):
            for slot in range(1, 5):
                self._players.append(Player(
                    uId=str(5202920000 + tid * 10 + slot),
                    playerName=f"{TEAM_NAMES[tid - 1].split()[0].upper()}_P{slot}",
                    teamId=tid,
                    teamName=TEAM_NAMES[tid - 1],
                    health=100.0,
                    liveState=0,
                ))
        # Pre-decide the elimination order of teams for this simulated match
        order = list(range(1, self.team_count + 1))
        random.shuffle(order)
        self._elim_order = order  # last entry wins

    def fetch(self) -> Snapshot:
        self.tick += 1
        alive_teams = {p.teamId for p in self._players if p.is_alive}

        # Every few ticks, eliminate the next team (until one remains)
        if self.tick > 4 and self.tick % 3 == 0 and len(alive_teams) > 1:
            for tid in self._elim_order:
                if tid in alive_teams and len(alive_teams) > 1:
                    for p in self._players:
                        if p.teamId == tid and p.is_alive:
                            p.bHasDied = True
                            p.liveState = 5
                            p.health = 0
                    alive_teams.discard(tid)
                    break

        # Random kills and knocks among alive players
        alive_players = [p for p in self._players if p.is_alive]
        for _ in range(random.randint(0, 3)):
            if not alive_players:
                break
            p = random.choice(alive_players)
            p.killNum += 1
            p.damage += random.randint(80, 220)
            p.knockouts += 1
            if random.random() < 0.3:
                p.headShotNum += 1
            p.maxKillDistance = max(p.maxKillDistance, random.randint(5, 400))
            teammates = [q for q in alive_players if q.teamId == p.teamId and q is not p]
            if teammates and random.random() < 0.4:
                random.choice(teammates).assists += 1

        # Passive stats for everyone still alive
        for p in alive_players:
            p.survivalTime += 2
            if random.random() < 0.2:
                p.heal += random.randint(20, 75)
            if random.random() < 0.15:
                p.inDamage += random.randint(10, 90)
            if random.random() < 0.05:
                p.rescueTimes += 1

        # Occasionally kill a single player from an alive squad
        if alive_players and random.random() < 0.35:
            victim = random.choice(alive_players)
            squad_alive = [q for q in alive_players if q.teamId == victim.teamId]
            if len(squad_alive) > 1 or len(alive_teams) == 1:
                victim.bHasDied = True
                victim.liveState = 5
                victim.health = 0

        snap = Snapshot(is_mock=True)
        snap.players = [Player(**vars(p)) for p in self._players]
        team_ids = sorted({p.teamId for p in self._players})
        for tid in team_ids:
            members = [p for p in self._players if p.teamId == tid]
            snap.teams.append(TeamInfo(
                teamId=tid,
                teamName=members[0].teamName,
                killNum=sum(p.killNum for p in members),
                liveMemberNum=sum(1 for p in members if p.is_alive),
            ))
        return snap
