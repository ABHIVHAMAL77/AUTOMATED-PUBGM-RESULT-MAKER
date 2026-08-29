from core.ocr_results import _repair_right_rank_sequence, match_cards_to_roster


def test_right_rank_sequence_repairs_clipped_two_digit_rank():
    cards = [
        {"rank": 9, "players": [{"name": "A", "kills": 1}], "_sortY": 100},
        {"rank": 10, "players": [{"name": "B", "kills": 1}], "_sortY": 220},
        {"rank": 1, "players": [{"name": "C", "kills": 1}], "_sortY": 340},
    ]

    _repair_right_rank_sequence(cards)

    assert [card["rank"] for card in cards] == [9, 10, 11]
    assert cards[2]["rankInferred"] is True


def test_roster_repair_restores_missing_and_symbol_names():
    cards = [{
        "rank": 9,
        "players": [
            {"name": "JHOLAaGANG", "kills": 3},
            {"name": "HEX2|19Crime", "kills": 1},
            {"name": "justBeatless", "kills": 0},
            {"name": "", "kills": 2, "missingName": True},
        ],
    }]
    teams = [{
        "teamId": 9,
        "teamName": "Rank 9",
        "players": ["JHOLAaGANG", "HEX² | 19Crime", "justBeatless", "चिनी बा"],
    }]

    match_cards_to_roster(cards, teams)

    names = [player["name"] for player in cards[0]["players"]]
    assert names == ["JHOLAaGANG", "HEX² | 19Crime", "justBeatless", "चिनी बा"]
    assert cards[0]["players"][3]["kills"] == 2
    assert "missingName" not in cards[0]["players"][3]
