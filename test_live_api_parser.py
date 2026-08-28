from core.models import parse_snapshot


def test_parse_snapshot_accepts_nested_lowercase_live_payload():
    snapshot = parse_snapshot({
        "data": {
            "totalPlayerList": [
                {
                    "uid": "p1",
                    "name": "EC Player",
                    "teamID": "7",
                    "team": "ESPORTS COUNTY",
                    "kills": "3",
                    "damageDealt": "450.5",
                    "liveState": 0,
                    "hasDied": "false",
                }
            ],
            "teamList": [
                {
                    "teamID": 7,
                    "name": "ESPORTS COUNTY",
                    "kills": 3,
                    "aliveNum": 4,
                    "teamRank": 1,
                }
            ],
        }
    })

    states = snapshot.team_states()

    assert list(states) == [7]
    assert states[7].teamName == "ESPORTS COUNTY"
    assert states[7].kills == 3
    assert states[7].alive_count == 1
    assert states[7].api_rank == 1
    assert states[7].players[0].playerName == "EC Player"


def test_parse_snapshot_understands_dead_string_flags():
    snapshot = parse_snapshot({
        "TotalPlayerList": [
            {"uId": "p1", "playerName": "A", "teamId": 1, "liveState": 0, "bHasDied": "true"},
            {"uId": "p2", "playerName": "B", "teamId": 1, "liveState": 5, "bHasDied": "false"},
        ]
    })

    state = snapshot.team_states()[1]

    assert state.alive_count == 0
