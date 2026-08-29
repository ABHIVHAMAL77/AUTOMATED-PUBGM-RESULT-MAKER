from core.match_tracker import MatchTracker
from core.models import Player, TeamState

POINTS = {"placementPoints": [10, 6, 5, 4, 3, 2, 1, 1], "killPoint": 1}


def test_live_results_match_saved_roster_players_before_feed_slot():
    tracker = MatchTracker()
    tracker.latest_states = {
        11: TeamState(
            teamId=11,
            teamName="PAKISTAN",
            kills=13,
            alive_count=0,
            players=[
                Player(playerName="DRSxAsg", teamId=11, teamName="PAKISTAN", killNum=4),
                Player(playerName="DRSxKillerYT", teamId=11, teamName="PAKISTAN", killNum=3),
            ],
        ),
        16: TeamState(
            teamId=16,
            teamName="JORDAN",
            kills=2,
            alive_count=0,
            players=[
                Player(playerName="SdmzNAAIM", teamId=16, teamName="JORDAN", killNum=1),
                Player(playerName="SdmzAMAAN24", teamId=16, teamName="JORDAN", killNum=1),
            ],
        ),
    }
    tracker.elimination_order = [16, 11]
    tracker.seen_any_data = True

    results = tracker.build_results(
        POINTS,
        {7: "LNN SDMZ", 11: "DRS GAMING", 16: "1HITxUF"},
        [
            {"teamId": 7, "teamName": "LNN SDMZ", "players": ["SdmzNAAIM", "SdmzAMAAN24"]},
            {"teamId": 11, "teamName": "DRS GAMING", "players": ["DRSxAsg", "DRSxKillerYT"]},
            {"teamId": 16, "teamName": "1HITxUF", "players": ["1HITxScoutUF", "1HITxAdiosUF"]},
        ],
    )

    sdmz = next(row for row in results if row["teamName"] == "LNN SDMZ")
    assert sdmz["teamId"] == 7
    assert sdmz["kills"] == 2
    assert sdmz["placementPoints"] == 6
    assert sdmz["totalPoints"] == 8
