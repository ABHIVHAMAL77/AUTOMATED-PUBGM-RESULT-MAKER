"""Tracks a live match across API polls and determines final placements.

Placement logic:
- While polling, the tracker records the order in which teams are eliminated
  (alive count reaches 0). If a team comes back (Rondo recall), it is removed
  from the elimination order again.
- At finalize time, teams still alive are ranked first (by API rank when the
  observer provides it, otherwise by kills), then eliminated teams follow in
  reverse elimination order (last team to die = best placement among dead).
"""

from .scoring import build_team_result


class MatchTracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.elimination_order = []   # teamIds, first eliminated first
        self.latest_states = {}       # teamId -> TeamState (last known)
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

    def build_results(self, point_system: dict, name_overrides: dict = None) -> list:
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

        results = []
        for placement, st in enumerate(ordered, start=1):
            display = name_overrides.get(st.teamId, "")
            results.append(build_team_result(st, placement, point_system, display))
        return results
