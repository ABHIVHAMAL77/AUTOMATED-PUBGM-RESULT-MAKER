from __future__ import annotations

from PIL import Image

from core import discord_tables
from core.graphic_themes import Branding


def test_match_table_renders_png(tmp_path):
    match = {
        "matchNumber": 1,
        "map": "Erangel",
        "eventName": "EC Scrims",
        "results": [
            {
                "placement": i,
                "teamName": f"Team {i}",
                "wwcd": i == 1,
                "kills": max(0, 18 - i),
                "placementPoints": max(0, 11 - i),
                "totalPoints": max(0, 29 - i * 2),
            }
            for i in range(1, 17)
        ],
    }

    out = discord_tables.render_match_results_table(
        match,
        tmp_path / "match_table.png",
        branding=Branding(),
    )

    with Image.open(out) as image:
        assert image.format == "PNG"
        assert image.width == discord_tables.WIDTH
        assert image.height >= 1000


def test_players_table_handles_long_names(tmp_path):
    players = [
        {
            "rank": i,
            "playerName": f"VERY-LONG-PLAYER-NAME-{i}-WITH-TAG",
            "teamName": "TRAINED TO KILL INTERNATIONAL",
            "kills": 20 - i,
            "damage": 1234.5 + i,
            "assists": i % 4,
            "matches": 3,
        }
        for i in range(1, 11)
    ]

    out = discord_tables.render_players_table(
        players,
        "EC Scrims",
        tmp_path / "players_table.png",
        branding=Branding(),
    )

    with Image.open(out) as image:
        assert image.size[0] == discord_tables.WIDTH
        assert image.size[1] >= discord_tables.MIN_HEIGHT
