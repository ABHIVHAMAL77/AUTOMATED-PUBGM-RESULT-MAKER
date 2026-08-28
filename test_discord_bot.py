import tempfile
from pathlib import Path

from core.event_manager import EventManager
from discord_bot import format_matches, format_players, format_results, format_standings


def make_event() -> EventManager:
    em = EventManager(Path(tempfile.mkdtemp(prefix="ec_bot_test_")))
    em.event["eventName"] = "EC Test Event"
    em.event["teams"] = [
        {"teamId": 1, "teamName": "Alpha Esports", "shortName": "ALP", "players": ["ALP One"]},
        {"teamId": 2, "teamName": "Bravo Gaming", "shortName": "BRV", "players": ["BRV Two"]},
    ]
    em.save_event()
    em.save_match_result(
        1,
        "Erangel",
        [
            {
                "teamId": 1,
                "teamName": "Alpha Esports",
                "placement": 1,
                "kills": 8,
                "placementPoints": 10,
                "killPoints": 8,
                "totalPoints": 18,
                "wwcd": True,
                "players": [{"playerName": "ALP One", "uId": "", "kills": 8}],
            },
            {
                "teamId": 2,
                "teamName": "Bravo Gaming",
                "placement": 2,
                "kills": 3,
                "placementPoints": 6,
                "killPoints": 3,
                "totalPoints": 9,
                "wwcd": False,
                "players": [{"playerName": "BRV Two", "uId": "", "kills": 3}],
            },
        ],
    )
    return em


def test_format_results_latest_match():
    text = format_results(make_event())

    assert "Match 1 Results" in text
    assert "Alpha Esports" in text
    assert "18" in text


def test_format_standings_and_matches():
    em = make_event()

    standings = format_standings(em)
    matches = format_matches(em)

    assert "Overall Standings" in standings
    assert "Alpha Esports" in standings
    assert "Saved Matches" in matches
    assert "Erangel" in matches


def test_format_players():
    text = format_players(make_event())

    assert "Top Players" in text
    assert "ALP One" in text
