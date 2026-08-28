"""The Claude vision fallback, exercised without touching the network.

What matters here is that whatever the model returns is normalised into
exactly the same card shape the local parser produces, and that a bad answer
degrades to something the operator can fix rather than something that
silently corrupts a match.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import ocr_vision
from core.ocr_pipeline import resolve_mode

FIXTURE = Path(__file__).parent / "fixtures" / "results" / "match_a_01.png"


def test_absent_key_keeps_everything_local(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ocr_vision.available() is False
    assert resolve_mode("hybrid") == "local"
    assert resolve_mode("vision") == "local"


def test_results_are_normalised_to_the_local_card_shape(monkeypatch):
    monkeypatch.setattr(ocr_vision, "_read", lambda *_: [
        {"rank": 3, "players": [
            {"name": "CNxGoRkHeY", "kills": 0},
            {"name": "  CNxSpartA  ", "kills": 2},
        ]},
    ])
    cards = ocr_vision.read_results_screenshot("ignored.png")
    assert cards == [{
        "rank": 3,
        "players": [
            {"name": "CNxGoRkHeY", "kills": 0},
            {"name": "CNxSpartA", "kills": 2},
        ],
    }]


@pytest.mark.parametrize("rank", [0, 26, -1, "seven", None, 99])
def test_out_of_range_ranks_become_none(monkeypatch, rank):
    """A rank outside 1..25 is a misread, not a real placement. Blanking it
    puts the card in front of the operator instead of quietly filing a team
    under a rank that cannot exist."""
    monkeypatch.setattr(ocr_vision, "_read", lambda *_: [
        {"rank": rank, "players": [{"name": "ZORO", "kills": 1}]},
    ])
    assert ocr_vision.read_results_screenshot("ignored.png")[0]["rank"] is None


def test_junk_rows_are_dropped_not_passed_through(monkeypatch):
    monkeypatch.setattr(ocr_vision, "_read", lambda *_: [
        {"rank": 1, "players": [{"name": "   ", "kills": 0}]},          # no name at all
        {"rank": 2, "players": []},                                      # no players
        {"rank": 4, "players": [{"name": "RUxDNL", "kills": -3}]},       # impossible count
    ])
    cards = ocr_vision.read_results_screenshot("ignored.png")
    assert [c["rank"] for c in cards] == [4]
    assert cards[0]["players"][0]["kills"] == 0


def test_never_more_than_a_full_squad(monkeypatch):
    monkeypatch.setattr(ocr_vision, "_read", lambda *_: [
        {"rank": 5, "players": [{"name": f"P{i}", "kills": 0} for i in range(7)]},
    ])
    assert len(ocr_vision.read_results_screenshot("ignored.png")[0]["players"]) == 4


def test_roster_cards_are_plain_string_players(monkeypatch):
    monkeypatch.setattr(ocr_vision, "_read", lambda *_: [
        {"slot": 18, "players": ["TRGxToxicBoiii", " TRGxSABRIN ", ""]},
        {"slot": 44, "players": ["Ghost"]},
    ])
    cards = ocr_vision.read_roster_screenshot("ignored.png")
    assert cards[0] == {"slot": 18, "players": ["TRGxToxicBoiii", "TRGxSABRIN"]}
    assert cards[1]["slot"] is None          # 44 is outside the lobby's slot range


@pytest.mark.slow
def test_image_encoding_stays_within_the_vision_size_limit():
    """Screenshots are sent as captured when they already fit, and downscaled
    when they do not — an oversized image is resampled server-side anyway and
    the extra pixels are billed."""
    from PIL import Image

    data, media_type = ocr_vision._encode_image(FIXTURE)
    assert media_type == "image/png"
    assert data and isinstance(data, str)

    with Image.open(FIXTURE) as im:
        assert max(im.size) <= ocr_vision.MAX_EDGE, "fixture should not need downscaling"
