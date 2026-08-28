"""Result-graphic templates: every look renders, and nothing falls off the page.

The failure this guards against is subtle — a template that renders fine with
twelve teams and silently pushes rows past the bottom of the canvas with
twenty-five, or draws 30px text into a 28px row. Neither raises; both produce a
graphic that goes out on stream broken.
"""

from __future__ import annotations

import pytest
from PIL import Image

from core import result_graphic
from core.graphic_themes import (
    BY_KEY,
    CUSTOM_KEY,
    THEMES,
    Branding,
    catalogue,
    hex_to_rgb,
)

CANVAS = (result_graphic.W, result_graphic.H)
LOBBY_SIZES = [1, 2, 8, 12, 16, 20, 25, 32]


def standings(count: int) -> list:
    return [{
        "rank": i,
        "teamName": f"Team Number {i}",
        "wwcd": 1 if i == 1 else 0,
        "kills": max(0, 30 - i),
        "placementPoints": max(0, count - i),
        "totalPoints": max(0, count - i) + max(0, 30 - i),
        "bestPlacement": i,
    } for i in range(1, count + 1)]


def test_catalogue_offers_ten_templates_plus_custom():
    entries = catalogue()
    assert len(entries) == 11
    assert entries[-1]["key"] == CUSTOM_KEY
    assert len({entry["key"] for entry in entries}) == 11


def test_templates_are_visually_distinct():
    """Ten palettes over one layout would be ten of the same graphic."""
    looks = {(t.bg_style, t.row_style, t.columns, t.rank_style) for t in THEMES}
    assert len(looks) >= 8, "templates have collapsed into near-duplicates"
    assert {t.columns for t in THEMES} == {1, 2}, "both column layouts should be offered"
    # at least one light template, for print and light decks
    assert any(sum(t.bg_from) > 500 for t in THEMES)


@pytest.mark.parametrize("key", sorted(BY_KEY))
def test_every_template_renders_at_full_size(key, tmp_path):
    out = result_graphic.render_overall_standings(
        standings(16), "Test Event", 6, tmp_path / f"{key}.png", Branding(template=key))
    with Image.open(out) as image:
        assert image.size == CANVAS


@pytest.mark.parametrize("count", LOBBY_SIZES)
def test_no_layout_overflows_the_canvas(count):
    """A 25-team single-column board used to run 110px past the bottom."""
    for theme in THEMES:
        rects = result_graphic._layout(theme, count)
        assert len(rects) == count
        bottom = max(y + h for _, y, _, h in rects)
        assert bottom <= result_graphic.H, f"{theme.key} with {count} teams runs off the canvas"
        assert min(x for x, _, _, _ in rects) >= 0


@pytest.mark.parametrize("count", LOBBY_SIZES)
def test_text_always_fits_its_row(count):
    """Font sizes are derived from row height; fixed sizes overlapped rows."""
    for theme in THEMES:
        row_h = result_graphic._layout(theme, count)[0][3]
        sizes = result_graphic._type_scale(row_h)
        assert sizes["name"] < row_h, f"{theme.key}: {sizes['name']}px text in a {row_h}px row"
        assert sizes["rank"] <= row_h


def test_big_lobby_switches_one_column_to_two():
    """Legibility beats the chosen layout: a one-column template cannot show
    25 teams without rows too short to read, so it becomes two columns."""
    single = next(t for t in THEMES if t.columns == 1)
    small = result_graphic._layout(single, 8)
    large = result_graphic._layout(single, 25)
    assert len({x for x, _, _, _ in small}) == 1
    assert len({x for x, _, _, _ in large}) == 2


def test_unknown_template_falls_back_rather_than_raising():
    """A template key from an older event file must not break exports."""
    theme = Branding(template="a-template-that-was-removed").resolved_theme()
    assert theme.key in BY_KEY


# --------------------------------------------------------------- custom mode

@pytest.fixture
def artwork(tmp_path):
    background = tmp_path / "bg.png"
    Image.new("RGB", (2560, 1440), (200, 120, 40)).save(background)
    logo = tmp_path / "logo.png"
    Image.new("RGBA", (400, 400), (255, 255, 255, 255)).save(logo)
    return background, logo


def test_custom_background_and_logo_are_composited(artwork, tmp_path):
    background, logo = artwork
    branding = Branding(template=CUSTOM_KEY, background_image=str(background),
                        logo_image=str(logo), logo_position="top-left")
    out = result_graphic.render_overall_standings(
        standings(16), "Branded Cup", 6, tmp_path / "custom.png", branding)

    with Image.open(out) as image:
        assert image.size == CANVAS
        # the logo lands in the corner it was asked for
        assert image.convert("RGB").getpixel((110, 110)) == (255, 255, 255)


def test_rows_become_opaque_over_artwork(artwork):
    """Low-alpha row fills are unreadable on a photograph, so every template
    gets solid plates once there is a background image behind it."""
    background, _ = artwork
    for theme in THEMES:
        plain = Branding(template=theme.key).resolved_theme()
        over = Branding(template=theme.key,
                        background_image=str(background)).resolved_theme()
        assert over.over_image is True
        assert over.row_fill[3] >= 200, f"{theme.key} rows stay see-through over artwork"
        assert over.row_fill[3] >= plain.row_fill[3]


def test_missing_artwork_file_does_not_break_the_export(tmp_path):
    """Artwork deleted from disk behind the app's back falls back to the
    template's own background instead of failing the export."""
    branding = Branding(template=CUSTOM_KEY,
                        background_image=str(tmp_path / "gone.png"),
                        logo_image=str(tmp_path / "also-gone.png"))
    out = result_graphic.render_overall_standings(
        standings(8), "Test", 1, tmp_path / "out.png", branding)
    with Image.open(out) as image:
        assert image.size == CANVAS


def test_colour_overrides_apply_and_bad_values_are_ignored():
    base = Branding(template="midnight-gold").resolved_theme()
    good = Branding(template="midnight-gold", accent="#39ff88").resolved_theme()
    assert good.accent == (0x39, 0xFF, 0x88)
    assert good.subtitle == good.accent

    junk = Branding(template="midnight-gold", accent="not-a-colour").resolved_theme()
    assert junk.accent == base.accent


def test_layout_override_beats_the_template():
    forced = Branding(template="midnight-gold", layout="1").resolved_theme()
    assert forced.columns == 1


@pytest.mark.parametrize("value,expected", [
    ("#e8be52", (232, 190, 82)),
    ("e8be52", (232, 190, 82)),
    ("#abc", (0xAA, 0xBB, 0xCC)),
    ("", (1, 2, 3)),
    ("#zzzzzz", (1, 2, 3)),
    (None, (1, 2, 3)),
])
def test_hex_parsing(value, expected):
    assert hex_to_rgb(value, fallback=(1, 2, 3)) == expected


def test_preview_is_small_and_needs_no_results(tmp_path):
    """The picker previews templates before the event has a single match."""
    out = result_graphic.render_preview(Branding(), tmp_path / "preview.png", width=320)
    with Image.open(out) as image:
        assert image.size == (320, 180)
    assert not list(tmp_path.glob("*.full.png")), "full-size render left behind"


def test_match_graphic_renders_with_a_template(tmp_path):
    match = {
        "matchNumber": 3, "map": "Erangel", "eventName": "Test Cup",
        "finalizedAt": "2026-07-28T10:00:00Z",
        "results": [{
            "placement": i, "teamName": f"Team {i}", "kills": 10 - i,
            "placementPoints": 12 - i, "totalPoints": 22 - 2 * i, "wwcd": i == 1,
        } for i in range(1, 17)],
    }
    out = result_graphic.render_match_results(
        match, tmp_path / "match.png", Branding(template="championship"))
    with Image.open(out) as image:
        assert image.size == CANVAS
