"""Discord-friendly PNG tables for result bot commands.

These are intentionally smaller and denser than the 1920x1080 broadcast
screenshots in result_graphic.py. Discord scales images in chat, so the table
needs clear columns, centered values, and predictable height.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

WIDTH = 1280
MARGIN = 48
TABLE_TOP = 158
HEAD_H = 54
ROW_H = 52
FOOTER_H = 70
MIN_HEIGHT = 520

BG_FROM = (6, 5, 4)
BG_TO = (20, 13, 9)
PANEL = (18, 15, 13)
ROW = (13, 12, 11)
ROW_ALT = (23, 19, 16)
ROW_TOP = (38, 27, 18)
GRID = (72, 50, 34)
ACCENT = (202, 125, 53)
ACCENT_LIGHT = (245, 188, 105)
HEADER_FILL = (222, 205, 181)
HEADER_TEXT = (12, 9, 7)
TEXT = (248, 243, 234)
MUTED = (188, 161, 134)
BLACK = (0, 0, 0)

FONT_PATHS = {
    "regular": [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ],
    "bold": [
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ],
}

Column = dict[str, Any]
RowData = dict[str, Any]


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    key = "bold" if bold else "regular"
    for raw in FONT_PATHS[key]:
        path = Path(raw)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    try:
        name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
        return ImageFont.truetype(name, size)
    except OSError:
        return ImageFont.load_default()


def _clean(value: Any, fallback: str = "-") -> str:
    text = " ".join(str(value or "").replace("\n", " ").split())
    return text or fallback


def _cell(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _clean(value)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> float:
    try:
        return draw.textlength(text, font=font)
    except Exception:  # noqa: BLE001 - Pillow fallback fonts can vary by host
        box = draw.textbbox((0, 0), text, font=font)
        return float(box[2] - box[0])


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    text = _clean(text)
    if _text_width(draw, text, font) <= max_width:
        return text
    suffix = "..."
    while text and _text_width(draw, text + suffix, font) > max_width:
        text = text[:-1]
    return text + suffix if text else suffix


def _gradient(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), BG_FROM)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(1, height - 1)
        colour = tuple(int(BG_FROM[i] + (BG_TO[i] - BG_FROM[i]) * t) for i in range(3))
        draw.line([(0, y), (width, y)], fill=colour)
    return image


def _column_widths(columns: list[Column], available: int) -> list[int]:
    requested = [int(col.get("width", 100)) for col in columns]
    total = sum(requested) or 1
    widths = [max(42, round(width * available / total)) for width in requested]
    widths[-1] += available - sum(widths)
    return widths


def _draw_logo(image: Image.Image, logo_path: str | Path | None, x: int, y: int, box: int) -> int:
    if not logo_path:
        return x
    path = Path(str(logo_path))
    if not path.exists():
        return x
    try:
        with Image.open(path) as source:
            logo = source.convert("RGBA")
    except OSError:
        return x

    scale = min(box / logo.width, box / logo.height, 1.0)
    logo = logo.resize(
        (max(1, round(logo.width * scale)), max(1, round(logo.height * scale))),
        Image.LANCZOS,
    )
    px = x
    py = y + (box - logo.height) // 2
    image.paste(logo, (px, py), logo)
    return x + box + 18


def _branding_logo(branding: Any | None) -> str:
    if not branding or not getattr(branding, "show_logo", True):
        return ""
    return str(getattr(branding, "logo_image", "") or "")


def _draw_table(
    draw: ImageDraw.ImageDraw,
    columns: list[Column],
    rows: list[RowData],
    left: int,
    top: int,
    width: int,
) -> int:
    widths = _column_widths(columns, width)
    header_font = _font(19, True)
    row_font = _font(22, False)
    row_bold = _font(22, True)

    draw.rounded_rectangle(
        [left, top, left + width, top + HEAD_H + ROW_H * max(1, len(rows))],
        radius=8,
        fill=PANEL,
        outline=GRID,
        width=1,
    )
    draw.rounded_rectangle(
        [left, top, left + width, top + HEAD_H],
        radius=8,
        fill=HEADER_FILL,
    )
    draw.rectangle([left, top + HEAD_H - 8, left + width, top + HEAD_H], fill=HEADER_FILL)

    x = left
    for col, col_w in zip(columns, widths, strict=True):
        label = _fit_text(draw, str(col.get("label", "")), header_font, col_w - 16).upper()
        draw.text((x + col_w / 2, top + HEAD_H / 2), label, font=header_font, fill=HEADER_TEXT, anchor="mm")
        if x > left:
            draw.line([(x, top), (x, top + HEAD_H + ROW_H * max(1, len(rows)))], fill=GRID, width=1)
        x += col_w

    if not rows:
        y = top + HEAD_H
        draw.rectangle([left, y, left + width, y + ROW_H], fill=ROW)
        draw.text((left + width / 2, y + ROW_H / 2), "No rows available yet", font=row_bold, fill=MUTED, anchor="mm")
        return y + ROW_H

    for row_index, row in enumerate(rows):
        y = top + HEAD_H + row_index * ROW_H
        fill = ROW_TOP if row_index == 0 else (ROW_ALT if row_index % 2 else ROW)
        draw.rectangle([left, y, left + width, y + ROW_H], fill=fill)
        draw.line([(left, y), (left + width, y)], fill=GRID, width=1)
        x = left
        for col, col_w in zip(columns, widths, strict=True):
            key = str(col.get("key", ""))
            value = _fit_text(draw, _cell(row.get(key, "")), row_font, col_w - 18)
            colour = ACCENT_LIGHT if col.get("highlight") else TEXT
            font = row_bold if col.get("bold") or col.get("highlight") else row_font
            draw.text((x + col_w / 2, y + ROW_H / 2), value, font=font, fill=colour, anchor="mm")
            x += col_w

    bottom = top + HEAD_H + len(rows) * ROW_H
    draw.line([(left, bottom), (left + width, bottom)], fill=GRID, width=1)
    return bottom


def render_table(
    title: str,
    subtitle: str,
    columns: list[Column],
    rows: list[RowData],
    out_path: str | Path,
    *,
    branding: Any | None = None,
    footer: str = "All rights reserved to ESPORTS COUNTY",
) -> Path:
    row_count = max(1, len(rows))
    height = max(MIN_HEIGHT, TABLE_TOP + HEAD_H + row_count * ROW_H + FOOTER_H)
    image = _gradient(WIDTH, height)
    draw = ImageDraw.Draw(image)

    draw.rectangle([0, 0, WIDTH, 8], fill=ACCENT)
    draw.rounded_rectangle([MARGIN - 16, 26, WIDTH - MARGIN + 16, height - 28], radius=10, fill=PANEL, outline=GRID)

    logo_right = _draw_logo(image, _branding_logo(branding), MARGIN, 34, 82)
    title_font = _font(34, True)
    subtitle_font = _font(21, False)
    small_font = _font(18, True)
    draw.text((logo_right, 48), _clean(title, "PUBGM RESULTS").upper(), font=title_font, fill=TEXT, anchor="lm")
    if subtitle:
        draw.text((logo_right, 88), _clean(subtitle), font=subtitle_font, fill=MUTED, anchor="lm")
    draw.rounded_rectangle([WIDTH - 282, 52, WIDTH - MARGIN, 91], radius=8, fill=(30, 23, 17), outline=ACCENT)
    draw.text((WIDTH - 165, 72), "ESPORTS COUNTY", font=small_font, fill=ACCENT_LIGHT, anchor="mm")

    table_left = MARGIN
    table_width = WIDTH - MARGIN * 2
    bottom = _draw_table(draw, columns, rows, table_left, TABLE_TOP, table_width)

    if footer:
        draw.text((WIDTH / 2, bottom + 34), _clean(footer), font=_font(17, False), fill=MUTED, anchor="mm")

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out, "PNG")
    return out


def _limited(items: list[dict], limit: int) -> list[dict]:
    limit = max(1, min(50, int(limit or 1)))
    return list(items[:limit])


def render_match_results_table(
    match: dict,
    out_path: str | Path,
    *,
    branding: Any | None = None,
    limit: int = 16,
) -> Path:
    rows = []
    for result in _limited(match.get("results") or [], limit):
        rows.append({
            "rank": result.get("placement", ""),
            "team": result.get("teamName", ""),
            "wwcd": 1 if result.get("wwcd") else 0,
            "elims": result.get("kills", 0),
            "place": result.get("placementPoints", 0),
            "total": result.get("totalPoints", 0),
        })
    number = match.get("matchNumber", "?")
    event_name = match.get("eventName") or "PUBGM Event"
    map_name = match.get("map") or "Unknown map"
    return render_table(
        f"Match {number} Standing",
        f"{event_name} | {map_name}",
        [
            {"key": "rank", "label": "Rank", "width": 90, "bold": True},
            {"key": "team", "label": "Team Name", "width": 350},
            {"key": "wwcd", "label": "WWCD", "width": 100},
            {"key": "elims", "label": "Eliminations", "width": 165},
            {"key": "place", "label": "Placement Points", "width": 230},
            {"key": "total", "label": "Total Points", "width": 185, "highlight": True},
        ],
        rows,
        out_path,
        branding=branding,
    )


def render_overall_table(
    standings: list[dict],
    event_name: str,
    matches_played: int,
    out_path: str | Path,
    *,
    branding: Any | None = None,
    limit: int = 16,
) -> Path:
    rows = []
    for row in _limited(standings, limit):
        rows.append({
            "rank": row.get("rank", ""),
            "team": row.get("teamName", ""),
            "wwcd": row.get("wwcd", 0),
            "matches": row.get("matches", 0),
            "elims": row.get("kills", 0),
            "place": row.get("placementPoints", 0),
            "total": row.get("totalPoints", 0),
        })
    return render_table(
        "Overall Standing",
        f"{event_name or 'PUBGM Event'} | After {matches_played} match{'es' if matches_played != 1 else ''}",
        [
            {"key": "rank", "label": "Rank", "width": 80, "bold": True},
            {"key": "team", "label": "Team Name", "width": 315},
            {"key": "wwcd", "label": "WWCD", "width": 90},
            {"key": "matches", "label": "Matches", "width": 110},
            {"key": "elims", "label": "Eliminations", "width": 150},
            {"key": "place", "label": "Placement Points", "width": 210},
            {"key": "total", "label": "Total Points", "width": 165, "highlight": True},
        ],
        rows,
        out_path,
        branding=branding,
    )


def render_players_table(
    players: list[dict],
    event_name: str,
    out_path: str | Path,
    *,
    branding: Any | None = None,
    limit: int = 10,
) -> Path:
    rows = []
    for player in _limited(players, limit):
        rows.append({
            "rank": player.get("rank", ""),
            "player": player.get("playerName", ""),
            "team": player.get("teamName", ""),
            "elims": player.get("kills", 0),
            "damage": player.get("damage", 0),
            "assists": player.get("assists", 0),
            "matches": player.get("matches", 0),
        })
    return render_table(
        "Top Players",
        event_name or "PUBGM Event",
        [
            {"key": "rank", "label": "Rank", "width": 80, "bold": True},
            {"key": "player", "label": "Player", "width": 300},
            {"key": "team", "label": "Team", "width": 300},
            {"key": "elims", "label": "Elims", "width": 110, "highlight": True},
            {"key": "damage", "label": "Damage", "width": 130},
            {"key": "assists", "label": "Assists", "width": 110},
            {"key": "matches", "label": "Matches", "width": 110},
        ],
        rows,
        out_path,
        branding=branding,
    )


def render_matches_table(
    matches: list[dict],
    event_name: str,
    out_path: str | Path,
    *,
    branding: Any | None = None,
    limit: int = 10,
) -> Path:
    rows = []
    for match in _limited(matches, limit):
        results = match.get("results") or []
        winner = results[0].get("teamName", "") if results else ""
        rows.append({
            "match": f"#{match.get('matchNumber', '')}",
            "map": match.get("map", ""),
            "winner": winner,
            "teams": len(results),
            "saved": _clean(str(match.get("finalizedAt", ""))[:10]),
        })
    return render_table(
        "Saved Matches",
        event_name or "PUBGM Event",
        [
            {"key": "match", "label": "Match", "width": 120, "bold": True},
            {"key": "map", "label": "Map", "width": 170},
            {"key": "winner", "label": "Winner", "width": 470, "highlight": True},
            {"key": "teams", "label": "Teams", "width": 130},
            {"key": "saved", "label": "Saved", "width": 230},
        ],
        rows,
        out_path,
        branding=branding,
    )


def render_event_table(
    event: dict,
    matches_played: int,
    next_match: int,
    out_path: str | Path,
    *,
    branding: Any | None = None,
) -> Path:
    rows = [
        {"field": "Event", "value": event.get("eventName") or "PUBGM Event"},
        {"field": "Stage", "value": event.get("stage") or "Not set"},
        {"field": "Teams", "value": len(event.get("teams") or [])},
        {"field": "Saved Matches", "value": f"{matches_played} / {event.get('totalMatches', '?')}"},
        {"field": "Next Match", "value": next_match},
    ]
    return render_table(
        "Event Details",
        event.get("eventName") or "PUBGM Event",
        [
            {"key": "field", "label": "Field", "width": 340, "bold": True},
            {"key": "value", "label": "Value", "width": 780, "highlight": True},
        ],
        rows,
        out_path,
        branding=branding,
    )


def render_live_results_table(
    results: list[dict],
    out_path: str | Path,
    *,
    branding: Any | None = None,
    limit: int = 16,
) -> Path:
    rows = []
    for result in _limited(results, limit):
        rows.append({
            "rank": result.get("placement", ""),
            "team": result.get("teamName", ""),
            "elims": result.get("kills", 0),
            "place": result.get("placementPoints", 0),
            "total": result.get("totalPoints", 0),
        })
    return render_table(
        "Live Result Check",
        "Current match feed",
        [
            {"key": "rank", "label": "Rank", "width": 90, "bold": True},
            {"key": "team", "label": "Team Name", "width": 450},
            {"key": "elims", "label": "Eliminations", "width": 170},
            {"key": "place", "label": "Placement Points", "width": 230},
            {"key": "total", "label": "Total Points", "width": 180, "highlight": True},
        ],
        rows,
        out_path,
        branding=branding,
    )
