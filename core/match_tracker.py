"""Tracks a live match across API polls and determines final placements.

Placement logic:
- While polling, the tracker records the order in which teams are eliminated
  (alive count reaches 0). If a team comes back (Rondo recall), it is removed
  from the elimination order again.
- At finalize time, teams still alive are ranked first (by API rank when the
  observer provides it, otherwise by kills), then eliminated teams follow in
  reverse elimination order (last team to die = best placement among dead).
"""

from .ocr_results import match_cards_to_roster
from .scoring import build_team_result


class MatchTracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.elimination_order = []  # teamIds, first eliminated first
        self.latest_states = {}  # teamId -> TeamState (last known)
        self.seen_any_data = False

    def update(self, team_states: dict):
        """Feed one poll's {teamId: TeamState}."""
        if not team_states:
            return
        self.seen_any_data = True
        for tid, st in team_states.items():
            prev = self.latest_states.get(tid)
            was_alive = prev.alive_count > 0 if prev else True
            self.latest_states[tid] = st
            if was_alive and st.alive_count == 0 and tid not in self.elimination_order:
                self.elimination_order.append(tid)
            elif st.alive_count > 0 and tid in self.elimination_order:
                # Team recalled/revived (Rondo) — no longer eliminated
                self.elimination_order.remove(tid)

    @property
    def alive_team_count(self) -> int:
        return sum(1 for st in self.latest_states.values() if st.alive_count > 0)

    @property
    def is_match_over(self) -> bool:
        return self.seen_any_data and len(self.latest_states) > 1 and self.alive_team_count <= 1

    def build_results(
        self,
        point_system: dict,
        name_overrides: dict = None,
        teams: list | None = None,
    ) -> list:
        """Return final per-team result dicts sorted by placement."""
        name_overrides = name_overrides or {}
        alive = [st for st in self.latest_states.values() if st.alive_count > 0]
        # Prefer the observer's own rank when it reports one for alive teams
        alive.sort(key=lambda st: (st.api_rank if st.api_rank > 0 else 999, -st.kills))
        dead_ids = [tid for tid in reversed(self.elimination_order) if tid in self.latest_states]

        ordered = alive + [self.latest_states[tid] for tid in dead_ids]
        # Safety: include any team that never registered as eliminated or alive
        seen = {st.teamId for st in ordered}
        ordered += [st for st in self.latest_states.values() if st.teamId not in seen]

        roster_matches = _match_states_to_roster(ordered, teams or [])
        results = []
        for placement, st in enumerate(ordered, start=1):
            display = name_overrides.get(st.teamId, "")
            result = build_team_result(st, placement, point_system, display)
            matched = roster_matches.get(st.teamId)
            if matched:
                result["teamId"] = int(matched["slot"])
                result["teamName"] = str(matched["teamName"])
                result["matchScore"] = matched.get("matchScore", 0)
                _apply_matched_player_names(result, matched.get("players") or [])
            results.append(result)
        return results


def _match_states_to_roster(states: list, teams: list) -> dict:
    if not any(team.get("players") for team in teams if isinstance(team, dict)):
        return {}

    cards = []
    for index, state in enumerate(states, start=1):
        cards.append(
            {
                "rank": index,
                "players": [
                    {"name": player.playerName, "kills": player.killNum}
                    for player in state.players
                    if player.playerName
                ],
            }
        )
    match_cards_to_roster(cards, teams)
    return {
        state.teamId: card
        for state, card in zip(states, cards, strict=True)
        if card.get("slot") and card.get("teamName")
    }


def _apply_matched_player_names(result: dict, matched_players: list) -> None:
    saved_players = result.get("players") or []
    if len(saved_players) != len(matched_players):
        return
    for saved, matched in zip(saved_players, matched_players, strict=True):
        name = str(matched.get("name") or "").strip()
        if name:
            saved["playerName"] = name
