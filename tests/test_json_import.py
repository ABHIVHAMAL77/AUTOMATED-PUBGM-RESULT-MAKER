from types import SimpleNamespace

import pytest

from core.json_import import import_match_json, result_from_manual_payload

POINTS = {"placementPoints": [10, 6, 5, 4, 3, 2, 1, 1], "killPoint": 1}


def test_import_saved_match_json_returns_review_rows_and_match_defaults():
    imported = import_match_json(
        {
            "matchNumber": 1,
            "map": "Erangel",
            "results": [
                {
                    "teamId": 7,
                    "teamName": "ESPORTS COUNTY",
                    "placement": 1,
                    "kills": 6,
                    "players": [
                        {"playerName": "EC Abhiv", "kills": 4, "damage": 640.5},
                        {"playerName": "EC Carry", "kills": 2, "assists": 1},
                    ],
                }
            ],
        },
        POINTS,
    )

    assert imported["matchNumber"] == 1
    assert imported["map"] == "Erangel"
    assert imported["engineUsed"] == "json"
    row = imported["rows"][0]
    assert row["rank"] == 1
    assert row["slot"] == 7
    assert row["teamName"] == "ESPORTS COUNTY"
    assert row["players"] == [
        {"name": "EC Abhiv", "kills": 4},
        {"name": "EC Carry", "kills": 2},
    ]
    assert row["rawResult"]["players"][0]["damage"] == 640.5


def test_import_simple_team_rows_are_supported():
    imported = import_match_json(
        {
            "teams": [
                {
                    "rank": "2",
                    "slot": "12",
                    "teamName": "Team Twelve",
                    "players": ["P1", {"name": "P2", "kills": "3"}],
                }
            ],
        },
        POINTS,
    )

    row = imported["rows"][0]
    assert row["rank"] == 2
    assert row["slot"] == 12
    assert row["kills"] == 3
    assert row["players"] == [{"name": "P1", "kills": 0}, {"name": "P2", "kills": 3}]


def test_import_observer_json_with_final_ranks():
    imported = import_match_json(
        {
            "playerInfoList": [
                {
                    "uId": "a",
                    "playerName": "A",
                    "teamId": 1,
                    "teamName": "One",
                    "rank": 2,
                    "killNum": 1,
                    "damage": 120,
                },
                {
                    "uId": "b",
                    "playerName": "B",
                    "teamId": 2,
                    "teamName": "Two",
                    "rank": 1,
                    "killNum": 4,
                    "damage": 500,
                },
            ]
        },
        POINTS,
    )

    assert [row["slot"] for row in imported["rows"]] == [2, 1]
    assert imported["rows"][0]["rank"] == 1
    assert imported["rows"][0]["players"][0] == {"name": "B", "kills": 4}


def test_import_observer_json_uses_slot_list_name_over_feed_name():
    imported = import_match_json(
        {
            "playerInfoList": [
                {
                    "uId": "a",
                    "playerName": "A",
                    "teamId": 11,
                    "teamName": "PAKISTAN",
                    "rank": 1,
                    "killNum": 5,
                },
            ]
        },
        POINTS,
        {11: "DRS GAMING"},
    )

    row = imported["rows"][0]
    assert row["slot"] == 11
    assert row["teamName"] == "DRS GAMING"


def test_import_observer_json_uses_roster_override_for_generic_feed_name():
    imported = import_match_json(
        {
            "playerInfoList": [
                {
                    "uId": "a",
                    "playerName": "A",
                    "teamId": 11,
                    "teamName": "Team11",
                    "rank": 1,
                    "killNum": 5,
                },
            ]
        },
        POINTS,
        {11: "DRS GAMING"},
    )

    assert imported["rows"][0]["teamName"] == "DRS GAMING"


def test_import_saved_result_json_uses_slot_list_name_when_available():
    imported = import_match_json(
        {
            "results": [{"teamId": 11, "teamName": "PAKISTAN", "placement": 1, "kills": 5}],
        },
        POINTS,
        {11: "DRS GAMING"},
    )

    assert imported["rows"][0]["teamName"] == "DRS GAMING"


def test_import_observer_json_matches_saved_roster_players_before_feed_slot():
    imported = import_match_json(
        {
            "playerInfoList": [
                {
                    "uId": "sdmz1",
                    "playerName": "SdmzNAAIM",
                    "teamId": 16,
                    "teamName": "JORDAN",
                    "rank": 2,
                    "killNum": 1,
                },
                {
                    "uId": "sdmz2",
                    "playerName": "SdmzAMAAN24",
                    "teamId": 16,
                    "teamName": "JORDAN",
                    "rank": 2,
                    "killNum": 1,
                },
            ]
        },
        POINTS,
        {7: "LNN SDMZ", 16: "1HITxUF"},
        [
            {"teamId": 7, "teamName": "LNN SDMZ", "players": ["SdmzNAAIM", "SdmzAMAAN24"]},
            {"teamId": 16, "teamName": "1HITxUF", "players": ["1HITxScoutUF", "1HITxAdiosUF"]},
        ],
    )

    row = imported["rows"][0]
    assert row["rank"] == 2
    assert row["slot"] == 7
    assert row["teamName"] == "LNN SDMZ"
    assert row["rawResult"]["placementPoints"] == 6
    assert row["rawResult"]["totalPoints"] == 8


def test_import_live_observer_json_without_ranks_explains_the_problem():
    with pytest.raises(ValueError, match="no final placement ranks"):
        import_match_json(
            {
                "playerInfoList": [
                    {"playerName": "A", "teamId": 1, "teamName": "One", "rank": 0, "killNum": 1},
                    {"playerName": "B", "teamId": 2, "teamName": "Two", "rank": 0, "killNum": 2},
                ]
            },
            POINTS,
        )


def test_manual_save_preserves_imported_player_details():
    entry = SimpleNamespace(
        rank=1,
        slot=7,
        teamName="ESPORTS COUNTY",
        kills=4,
        players=[SimpleNamespace(name="EC Abhiv", kills=4)],
        rawResult={
            "teamId": 7,
            "teamName": "Old Name",
            "placement": 3,
            "players": [{"playerName": "EC Abhiv", "kills": 4, "damage": 777, "headshots": 2}],
        },
    )

    result = result_from_manual_payload(entry, POINTS)

    assert result["placement"] == 1
    assert result["totalPoints"] == 14
    assert result["players"][0]["damage"] == 777
    assert result["players"][0]["headshots"] == 2
