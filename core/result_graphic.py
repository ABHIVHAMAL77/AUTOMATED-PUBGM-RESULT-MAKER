"""Renders broadcast MATCH RESULTS and OVERALL STANDINGS graphics.

Output is a 1920x1080 PNG. The look comes entirely from a `Theme` in
`core/graphic_themes.py` — palette, background treatment, row treatment and
column count — so there is one renderer rather than one per design, and a
custom background image drops into the same path as a built-in template.

    render_match_results(match, out_path, branding=...)
    render_overall_standings(standings, name, matches, out_path, branding=...)

`branding` is optional everywhere; omitting it renders the default template,
which is what the older call sites did.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .graphic_themes import (
    BLOCK,
    CHEVRON,
    CIRCLE,
    DIAGONAL,
    GLOW,
    MINIMAL,
    OUTLINE,
    RADIAL,
    SOLID,
    STRIPED,
    Branding,
    Theme,
)

W, H = 1920, 1080

FONT_DIR = Path("C:/Windows/Fonts")

# Kept for callers that imported these before the template system existed.
GOLD = (232, 190, 82)
WHITE = (240, 242, 248)
GREY = (150, 158, 175)


def _font(candidates, size):
    for name in candidates:
        path = FONT_DIR / name
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default(size)


# ---------------------------------------------------------------- background

def _background(theme: Theme, branding: Branding | None) -> Image.Image:
    image = _custom_background(theme, branding) if branding else None
    return image or _generated_background(theme)


def _custom_background(theme: Theme, branding: Branding) -> Image.Image | None:
    """The operator's uploaded artwork, cropped to fill and dimmed enough that
    white text stays readable on top of it."""
    path = branding.background_image
    if not path or not Path(path).exists():
        return None
    try:
        with Image.open(path) as source:
            art = source.convert("RGB")
            art = _cover(art, W, H)
    except OSError:
        return None

    scrim = max(0, min(255, theme.image_scrim))
    if scrim:
        # A flat wash rather than a gradient: a gradient looks deliberate on a
        # designed background and accidental on a photograph.
        veil = Image.new("RGB", (W, H), theme.bg_to)
        art = Image.blend(art, veil, scrim / 255)
    return art


def _cover(image: Image.Image, width: int, height: int) -> Image.Image:
    """Scale to fill the frame and centre-crop the overflow, like CSS `cover`.
    Letterboxing would leave bars that look like a mistake."""
    scale = max(width / image.width, height / image.height)
    resized = image.resize((max(1, round(image.width * scale)),
                            max(1, round(image.height * scale))), Image.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _generated_background(theme: Theme) -> Image.Image:
    if theme.bg_style == SOLID:
        return Image.new("RGB", (W, H), theme.bg_from)

    if theme.bg_style == RADIAL:
        # Built small and upscaled — a per-pixel radial at 1920x1080 is slow
        # enough to notice, and the result is a smooth gradient either way.
        small = Image.new("RGB", (160, 90))
        pixels = small.load()
        cx, cy = 80, 38
        longest = (cx ** 2 + cy ** 2) ** 0.5
        for y in range(90):
            for x in range(160):
                t = min(1.0, ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / longest)
                pixels[x, y] = tuple(
                    int(theme.bg_from[i] + (theme.bg_to[i] - theme.bg_from[i]) * t)
                    for i in range(3)
                )
        return small.resize((W, H), Image.BICUBIC)

    if theme.bg_style == DIAGONAL:
        small = Image.new("RGB", (160, 90))
        pixels = small.load()
        for y in range(90):
            for x in range(160):
                t = (x / 160 + y / 90) / 2
                pixels[x, y] = tuple(
                    int(theme.bg_from[i] + (theme.bg_to[i] - theme.bg_from[i]) * t)
                    for i in range(3)
                )
        return small.resize((W, H), Image.BICUBIC)

    image = Image.new("RGB", (W, H))
    for y in range(H):
        t = y / H
        image.paste(
            tuple(int(theme.bg_from[i] + (theme.bg_to[i] - theme.bg_from[i]) * t)
                  for i in range(3)),
            (0, y, W, y + 1),
        )
    return image


def _paste_logo(image: Image.Image, branding: Branding | None) -> None:
    if not branding or not branding.show_logo:
        return
    path = branding.logo_image
    if not path or not Path(path).exists():
        return
    try:
        with Image.open(path) as source:
            logo = source.convert("RGBA")
    except OSError:
        return

    box = 150
    scale = min(box / logo.width, box / logo.height, 1.0)
    logo = logo.resize((max(1, round(logo.width * scale)),
                        max(1, round(logo.height * scale))), Image.LANCZOS)

    margin = 48
    positions = {
        "top-left": (margin, margin),
        "top-right": (W - logo.width - margin, margin),
        "bottom-left": (margin, H - logo.height - margin),
        "bottom-right": (W - logo.width - margin, H - logo.height - margin),
    }
    image.paste(logo, positions.get(branding.logo_position, positions["top-right"]), logo)


# -------------------------------------------------------------------- header

def _draw_header(draw, theme: Theme, title: str, subtitle: str, right_text: str = ""):
    f_title = _font(theme.bold_fonts, 74)
    f_sub = _font(theme.body_fonts, 34)
    draw.text((W // 2, 70), title.upper(), font=f_title, fill=theme.title, anchor="mm")
    draw.text((W // 2, 138), subtitle.upper(), font=f_sub, fill=theme.subtitle, anchor="mm")
    if right_text:
        draw.text((W - 60, 60), right_text.upper(), font=_font(theme.body_fonts, 26),
                  fill=theme.muted, anchor="rm")
    if theme.header_rule:
        draw.rectangle([W // 2 - 260, 170, W // 2 + 260, 174], fill=theme.accent)


# --------------------------------------------------------------------- table

TOP_EDGE, BOTTOM_EDGE = 250, H - 70

#: Below this a row cannot hold legible text at 1080p. A one-column template
#: that would need shorter rows is switched to two columns instead — a graphic
#: nobody can read on stream is worse than one that ignores the chosen layout.
MIN_LEGIBLE_ROW = 42


def _row_height(theme: Theme, count: int, columns: int) -> int:
    per_col = -(-count // columns)
    available = BOTTOM_EDGE - TOP_EDGE
    ceiling = 72 if columns == 1 else 66
    return min(ceiling, available // per_col - theme.row_gap)


def _layout(theme: Theme, count: int):
    """(x, y, w, h) per row, sized so the table always fits the canvas."""
    count = max(1, count)
    columns = max(1, min(2, theme.columns))
    if columns == 1 and _row_height(theme, count, 1) < MIN_LEGIBLE_ROW:
        columns = 2

    per_col = -(-count // columns)
    col_w, gap_x = (860, 60) if columns == 2 else (1180, 0)
    total_w = col_w * columns + gap_x * (columns - 1)
    x0 = (W - total_w) // 2

    # Clamped, but never below what actually fits: the old code floored the
    # height at 28px without re-checking, so a 25-team single column ran off
    # the bottom of the image.
    available = BOTTOM_EDGE - TOP_EDGE
    row_h = max(20, min(_row_height(theme, count, columns),
                        available // per_col - theme.row_gap))
    spacing = row_h + theme.row_gap

    used = per_col * spacing - theme.row_gap
    top = TOP_EDGE + max(0, (available - used) // 2)

    rects = []
    for i in range(count):
        col, row = divmod(i, per_col)
        rects.append((x0 + col * (col_w + gap_x), top + row * spacing, col_w, row_h))
    return rects


def _type_scale(row_h: int) -> dict:
    """Font sizes derived from the row height.

    Fixed sizes meant a 20-team single-column board drew 30px text into 28px
    rows, so the names collided with the row above and below.
    """
    def fit(ratio: float, lo: int, hi: int) -> int:
        return max(lo, min(hi, round(row_h * ratio)))

    return {
        "rank": fit(0.50, 14, 32),
        "name": fit(0.46, 13, 30),
        "value": fit(0.44, 13, 30),
        "header": fit(0.30, 11, 20),
    }


def _row_fill(theme: Theme, rank: int, index: int):
    if rank == 1:
        return theme.top1_fill
    if rank <= 3:
        return theme.top3_fill
    return theme.row_fill if index % 2 == 0 else theme.row_fill_alt


def _draw_row_shape(od, theme: Theme, box, rank: int, index: int, glow_draw):
    x, y, w, h = box
    rect = [x, y, x + w, y + h]
    fill = _row_fill(theme, rank, index)

    if theme.row_style == MINIMAL:
        if rank <= 3:
            od.rounded_rectangle(rect, radius=theme.radius, fill=fill)
        # A 1px rule at low alpha vanished on export and the board read as an
        # empty canvas. Two pixels at full weight is still minimal but visible.
        od.rectangle([x, y + h, x + w, y + h + 2], fill=(*theme.muted, 150))
        if rank == 1:
            od.rectangle([x, y, x + 3, y + h], fill=theme.accent)
        return

    if theme.row_style == STRIPED:
        od.rectangle(rect, fill=fill)
        if rank == 1:
            od.rectangle([x, y, x + 6, y + h], fill=theme.accent)
        return

    if theme.row_style == OUTLINE:
        od.rounded_rectangle(rect, radius=theme.radius, fill=fill,
                             outline=(*theme.accent, 150 if rank <= 3 else 70), width=2)
        return

    if theme.row_style == GLOW:
        # The halo is drawn on its own layer and blurred, so the row sits in a
        # pool of colour instead of getting a hard second border.
        glow_draw.rounded_rectangle([x - 6, y - 6, x + w + 6, y + h + 6],
                                    radius=theme.radius + 6,
                                    fill=(*theme.accent, 90 if rank <= 3 else 34))
        od.rounded_rectangle(rect, radius=theme.radius, fill=fill)
        return

    od.rounded_rectangle(rect, radius=theme.radius, fill=fill)
    if rank == 1:
        od.rounded_rectangle(rect, radius=theme.radius, outline=theme.accent, width=2)


def _draw_rank(od, theme: Theme, box, rank: int, font):
    x, y, w, h = box
    cy = y + h // 2
    colour = theme.accent if rank <= 3 else theme.text

    if theme.rank_style == CIRCLE:
        r = min(22, h // 2 - 4)
        od.ellipse([x + 16, cy - r, x + 16 + 2 * r, cy + r],
                   fill=(*theme.accent, 210) if rank <= 3 else (*theme.muted, 70))
        od.text((x + 16 + r, cy), str(rank), font=font,
                fill=theme.bg_from if rank <= 3 else theme.text, anchor="mm")
        return x + 16 + 2 * r + 18

    if theme.rank_style == CHEVRON:
        tab_w = 84
        od.polygon([(x, y), (x + tab_w, y), (x + tab_w - 18, y + h), (x, y + h)],
                   fill=(*theme.accent, 200) if rank <= 3 else (*theme.muted, 60))
        od.text((x + tab_w // 2 - 6, cy), str(rank), font=font,
                fill=theme.bg_from if rank <= 3 else theme.text, anchor="mm")
        return x + tab_w + 16

    if theme.rank_style == BLOCK:
        od.rectangle([x, y + 6, x + 4, y + h - 6],
                     fill=theme.accent if rank <= 3 else theme.muted)

    od.text((x + 58, cy), f"#{rank}", font=font, fill=colour, anchor="mm")
    return x + 110


def _draw_table(image, theme: Theme, rows, columns, col_headers=True):
    """rows: dicts with 'rank', 'name' and one key per column.
    columns: (key, header, width) drawn right-aligned from the row's end."""
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)

    rects = _layout(theme, len(rows))
    sizes = _type_scale(rects[0][3])
    f_rank = _font(theme.bold_fonts, sizes["rank"])
    f_name = _font(theme.bold_fonts, sizes["name"])
    f_val = _font(theme.body_fonts, sizes["value"])
    f_head = _font(theme.body_fonts, sizes["header"])

    if col_headers and theme.over_image:
        # Column labels are small, thin text and they sit above the row plates,
        # i.e. directly on the operator's artwork. Give them their own strip.
        head_h = sizes["header"] + 14
        for x, _, w, _ in {(x, 0, w, 0) for x, _, w, _ in rects}:
            od.rounded_rectangle(
                [x, rects[0][1] - head_h - 6, x + w, rects[0][1] - 4],
                radius=theme.radius,
                fill=(*(theme.bg_from if theme.row_fill[3] > 120 else theme.bg_to), 170),
            )

    headers_drawn = set()
    for index, (row, box) in enumerate(zip(rows, rects, strict=True)):
        rank = int(row["rank"])
        _draw_row_shape(od, theme, box, rank, index, glow_draw)

        x, y, w, h = box
        cy = y + h // 2
        name_x = _draw_rank(od, theme, box, rank, f_rank)

        name = str(row["name"])
        if theme.caps_names:
            name = name.upper()
        max_name_w = (x + w - 24) - name_x - sum(cw for _, _, cw in columns) - 16
        while name and od.textlength(name, font=f_name) > max_name_w:
            name = name[:-1]
        od.text((name_x, cy), name, font=f_name, fill=theme.text, anchor="lm")

        cx = x + w - 24
        for key, header, cw in reversed(columns):
            od.text((cx, cy), str(row[key]), font=f_val,
                    fill=theme.accent if key == "total" else theme.text, anchor="rm")
            if col_headers and (x, cx) not in headers_drawn:
                od.text((cx, rects[0][1] - 18), header, font=f_head,
                        fill=theme.muted, anchor="rm")
                headers_drawn.add((x, cx))
            cx -= cw

    if theme.row_style == GLOW:
        image.paste(Image.alpha_composite(
            image.convert("RGBA"), glow.filter(ImageFilter.GaussianBlur(12))).convert("RGB"),
            (0, 0))
    image.paste(overlay, (0, 0), overlay)


# ------------------------------------------------------------------ renderers

def _render(branding: Branding | None, title: str, subtitle: str, right_text: str,
            rows: list, columns: list, out_path) -> Path:
    theme = branding.resolved_theme() if branding else Branding().resolved_theme()
    image = _background(theme, branding)
    _draw_header(ImageDraw.Draw(image), theme, title, subtitle, right_text)
    if rows:
        _draw_table(image, theme, rows, columns)
    _paste_logo(image, branding)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, "PNG")
    return out_path


def render_match_results(match: dict, out_path, branding: Branding | None = None) -> Path:
    subtitle = f"Match {match.get('matchNumber', '?')} Results"
    if match.get("map"):
        subtitle += f"  •  {match['map']}"

    rows = [{
        "rank": result["placement"],
        "name": ("WWCD  " if result.get("wwcd") else "") + result["teamName"],
        "place": result["placementPoints"],
        "elims": result["kills"],
        "total": result["totalPoints"],
    } for result in match.get("results", [])]

    return _render(
        branding,
        match.get("eventName") or "PUBGM Event",
        subtitle,
        str(match.get("finalizedAt", ""))[:10],
        rows,
        [("place", "PLACE", 110), ("elims", "ELIMS", 110), ("total", "TOTAL", 130)],
        out_path,
    )


def render_overall_standings(standings: list, event_name: str, matches_played: int,
                             out_path, branding: Branding | None = None) -> Path:
    plural = "es" if matches_played != 1 else ""
    rows = [{
        "rank": team["rank"],
        "name": team["teamName"],
        "wwcd": team["wwcd"],
        "place": team["placementPoints"],
        "elims": team["kills"],
        "total": team["totalPoints"],
    } for team in standings]

    return _render(
        branding,
        event_name or "PUBGM Event",
        f"Overall Standings  •  After {matches_played} Match{plural}",
        "",
        rows,
        [("wwcd", "WWCD", 110), ("place", "PLACE", 110),
         ("elims", "ELIMS", 110), ("total", "TOTAL", 130)],
        out_path,
    )


# ------------------------------------------------------------------- preview

SAMPLE_TEAMS = [
    ("Hiix", 3, 9, 1), ("4M Esports", 2, 4, 2), ("CNx", 1, 2, 3), ("Ucan Gaming", 0, 3, 4),
    ("LovesU", 0, 3, 5), ("Zero GUP", 2, 6, 6), ("Shrijan XI", 0, 0, 7), ("RUx", 1, 6, 8),
    ("Jhola Gang", 0, 4, 9), ("TRGx", 0, 1, 10), ("EG Paradise", 0, 0, 11), ("PS Squad", 0, 2, 12),
]


def render_preview(branding: Branding | None, out_path, width: int = 640) -> Path:
    """A downscaled sample graphic for the template picker.

    Rendered with placeholder teams so a template can be previewed before the
    event has any results, and shrunk so a dozen previews are cheap to send.
    """
    standings = []
    for rank, (name, wwcd, kills, place) in enumerate(SAMPLE_TEAMS, start=1):
        placement_points = max(0, 11 - rank)
        standings.append({
            "rank": rank, "teamName": name, "wwcd": wwcd, "kills": kills,
            "placementPoints": placement_points, "totalPoints": placement_points + kills,
            "bestPlacement": place,
        })

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    full = out_path.with_suffix(".full.png")
    render_overall_standings(standings, "Your Event Name", 6, full, branding)
    with Image.open(full) as image:
        image.resize((width, round(width * H / W)), Image.LANCZOS).save(out_path, "PNG")
    full.unlink(missing_ok=True)
    return out_path
