"""Visual templates for the exported result graphics.

Ten built-in looks plus a custom slot where the operator supplies their own
background image and logo. A template is pure data — palette, background
treatment, row treatment, column count — and `core/result_graphic.py` is the
one renderer that reads it. Adding an eleventh look means adding an entry
here, not another render function.

The templates deliberately differ in *layout* as well as colour: one- versus
two-column, card rows versus striped rows versus outlined rows, rounded
versus square, light versus dark. Ten palettes over one layout would all read
as the same graphic tinted differently, which is not a choice worth offering.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

RGB = tuple[int, int, int]
RGBA = tuple[int, int, int, int]

# Background treatments
VERTICAL = "vertical"      # top-to-bottom gradient
DIAGONAL = "diagonal"      # corner-to-corner gradient
RADIAL = "radial"          # bright centre falling off to the edges
SOLID = "solid"            # flat fill

# Row treatments
CARD = "card"              # filled rounded block per team
STRIPED = "striped"        # alternating fills, no gaps
OUTLINE = "outline"        # transparent with a drawn border
GLOW = "glow"              # filled with a coloured halo behind it
MINIMAL = "minimal"        # a hairline rule under each row, nothing else

# Rank badge treatments
BLOCK = "block"            # vertical accent bar beside the number
CIRCLE = "circle"          # number inside a filled disc
PLAIN = "plain"            # just the number
CHEVRON = "chevron"        # number on an angled tab


def hex_to_rgb(value: str, fallback: RGB = (255, 255, 255)) -> RGB:
    """'#e8be52' -> (232, 190, 82). Bad input returns the fallback rather than
    raising, because these values can come from a user colour field."""
    text = str(value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        return fallback
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except ValueError:
        return fallback


def rgb_to_hex(colour: RGB) -> str:
    return "#{:02x}{:02x}{:02x}".format(*colour[:3])


def _mix(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _luma(colour: RGB) -> float:
    """Perceived brightness, for deciding whether a palette is light or dark."""
    r, g, b = colour[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    blurb: str

    # background
    bg_style: str = VERTICAL
    bg_from: RGB = (12, 16, 28)
    bg_to: RGB = (24, 32, 54)
    #: darkening laid over a custom background image so text stays readable
    image_scrim: int = 130

    # type
    title: RGB = (240, 242, 248)
    subtitle: RGB = (232, 190, 82)
    text: RGB = (240, 242, 248)
    muted: RGB = (150, 158, 175)
    accent: RGB = (232, 190, 82)
    bold_fonts: tuple = ("bahnschrift.ttf", "arialbd.ttf", "arial.ttf")
    body_fonts: tuple = ("bahnschrift.ttf", "arial.ttf")

    # rows
    row_style: str = CARD
    row_fill: RGBA = (255, 255, 255, 18)
    row_fill_alt: RGBA = (255, 255, 255, 10)
    top1_fill: RGBA = (232, 190, 82, 60)
    top3_fill: RGBA = (255, 255, 255, 36)
    radius: int = 8
    columns: int = 2
    row_gap: int = 8
    rank_style: str = BLOCK
    #: names rendered in caps — reads louder on stream, worse for long names
    caps_names: bool = False
    #: draws the rule under the header block
    header_rule: bool = True
    #: set by over_artwork(); tells the renderer text is sitting on a photo
    over_image: bool = False

    def over_artwork(self) -> Theme:
        """A copy safe to draw over an uploaded background.

        Templates set row fills as low as 6% alpha, which reads beautifully on
        a flat gradient and becomes unreadable the moment there is a photograph
        behind it — busy artwork shows straight through the row and collides
        with the text. Over a custom background every row therefore gets an
        opaque plate. The operator picked the picture to be *behind* the
        standings, not through them.
        """
        floor = 200
        base = self.bg_from if _luma(self.bg_from) < 128 else (255, 255, 255)

        def plate(colour: RGBA, minimum: int) -> RGBA:
            if colour[3] >= minimum:
                return colour
            # keep the template's tint, just make it cover
            tint = _mix(base, colour[:3], colour[3] / 255) if colour[3] else base
            return (*tint, minimum)

        return replace(
            self,
            row_fill=plate(self.row_fill, floor),
            row_fill_alt=plate(self.row_fill_alt, floor),
            top1_fill=plate(self.top1_fill, 225),
            top3_fill=plate(self.top3_fill, 210),
            # MINIMAL draws no plate at all by design, so it has to become a
            # style that does once there is artwork underneath
            row_style=STRIPED if self.row_style == MINIMAL else self.row_style,
            over_image=True,
        )

    def override(self, *, accent: str = "", text: str = "", title: str = "") -> Theme:
        """A copy with the operator's colour choices applied on top."""
        changes: dict = {}
        if accent:
            changes["accent"] = hex_to_rgb(accent, self.accent)
            changes["subtitle"] = changes["accent"]
            changes["top1_fill"] = (*changes["accent"], self.top1_fill[3])
        if text:
            changes["text"] = hex_to_rgb(text, self.text)
        if title:
            changes["title"] = hex_to_rgb(title, self.title)
        return replace(self, **changes) if changes else self

    def as_dict(self) -> dict:
        """The shape the template picker renders."""
        return {
            "key": self.key,
            "name": self.name,
            "blurb": self.blurb,
            "columns": self.columns,
            "swatch": [rgb_to_hex(c) for c in (self.bg_from, self.bg_to, self.accent, self.text)],
        }


THEMES: tuple[Theme, ...] = (
    Theme(
        key="midnight-gold",
        name="Midnight Gold",
        blurb="The classic broadcast look — deep navy with gold accents and rounded team cards.",
        bg_style=VERTICAL,
        bg_from=(12, 16, 28), bg_to=(24, 32, 54),
        accent=(232, 190, 82), subtitle=(232, 190, 82),
        row_style=CARD, radius=8, columns=2, rank_style=BLOCK,
    ),
    Theme(
        key="neon-circuit",
        name="Neon Circuit",
        blurb="Near-black with cyan and magenta glow. Built to pop against a dark stream overlay.",
        bg_style=RADIAL,
        bg_from=(16, 10, 34), bg_to=(4, 4, 10),
        title=(236, 240, 255), accent=(64, 232, 238), subtitle=(255, 92, 190),
        text=(226, 234, 248), muted=(122, 132, 168),
        row_style=GLOW, row_fill=(64, 232, 238, 26), row_fill_alt=(64, 232, 238, 26),
        top1_fill=(255, 92, 190, 62), top3_fill=(64, 232, 238, 42),
        radius=6, columns=2, rank_style=CIRCLE,
    ),
    Theme(
        key="crimson-elite",
        name="Crimson Elite",
        blurb="Deep red on black, one wide column with heavy outlined rows. Reads well on a big screen.",
        bg_style=DIAGONAL,
        bg_from=(44, 8, 12), bg_to=(8, 4, 6),
        title=(255, 244, 240), accent=(226, 62, 62), subtitle=(226, 62, 62),
        text=(246, 238, 236), muted=(158, 122, 122),
        row_style=OUTLINE, row_fill=(226, 62, 62, 16), row_fill_alt=(226, 62, 62, 10),
        top1_fill=(226, 62, 62, 70), top3_fill=(226, 62, 62, 34),
        radius=4, columns=1, row_gap=10, rank_style=CHEVRON, caps_names=True,
    ),
    Theme(
        key="arctic",
        name="Arctic",
        blurb="Light template — white background, ice-blue accents, striped rows. For print and light decks.",
        bg_style=VERTICAL,
        bg_from=(248, 250, 253), bg_to=(226, 236, 246),
        image_scrim=90,
        title=(16, 28, 44), subtitle=(28, 122, 190), text=(22, 34, 50),
        muted=(108, 128, 150), accent=(28, 122, 190),
        row_style=STRIPED, row_fill=(28, 122, 190, 20), row_fill_alt=(16, 28, 44, 10),
        top1_fill=(28, 122, 190, 64), top3_fill=(28, 122, 190, 34),
        radius=0, columns=2, row_gap=0, rank_style=PLAIN,
    ),
    Theme(
        key="carbon",
        name="Carbon Mono",
        blurb="Greyscale and minimal — hairline rules, no fills. Lets team logos and names do the talking.",
        bg_style=SOLID,
        bg_from=(18, 18, 20), bg_to=(18, 18, 20),
        title=(244, 244, 246), subtitle=(168, 168, 176), text=(232, 232, 238),
        muted=(124, 124, 134), accent=(214, 214, 222),
        row_style=MINIMAL, row_fill=(255, 255, 255, 0), row_fill_alt=(255, 255, 255, 0),
        top1_fill=(255, 255, 255, 22), top3_fill=(255, 255, 255, 10),
        radius=0, columns=2, row_gap=2, rank_style=PLAIN,
    ),
    Theme(
        key="sunset-arena",
        name="Sunset Arena",
        blurb="Warm orange into violet with soft cards. Friendly look for community cups.",
        bg_style=DIAGONAL,
        bg_from=(58, 22, 78), bg_to=(198, 84, 46),
        title=(255, 248, 240), subtitle=(255, 206, 122), text=(255, 246, 238),
        muted=(216, 178, 168), accent=(255, 206, 122),
        row_style=CARD, row_fill=(0, 0, 0, 62), row_fill_alt=(0, 0, 0, 48),
        top1_fill=(255, 206, 122, 74), top3_fill=(0, 0, 0, 86),
        radius=14, columns=2, row_gap=10, rank_style=CIRCLE,
    ),
    Theme(
        key="jungle-ops",
        name="Jungle Ops",
        blurb="Military olive, hard square edges, caps throughout. Tactical scrim energy.",
        bg_style=VERTICAL,
        bg_from=(26, 34, 24), bg_to=(12, 16, 12),
        title=(232, 238, 220), subtitle=(164, 200, 96), text=(224, 232, 210),
        muted=(132, 148, 116), accent=(164, 200, 96),
        row_style=OUTLINE, row_fill=(164, 200, 96, 14), row_fill_alt=(164, 200, 96, 8),
        top1_fill=(164, 200, 96, 58), top3_fill=(164, 200, 96, 30),
        radius=0, columns=2, row_gap=6, rank_style=BLOCK, caps_names=True,
    ),
    Theme(
        key="royal",
        name="Royal Purple",
        blurb="Violet and gold with a strong podium highlight. Finals-day look.",
        bg_style=RADIAL,
        bg_from=(58, 30, 108), bg_to=(14, 8, 30),
        title=(248, 244, 255), subtitle=(238, 198, 108), text=(240, 236, 250),
        muted=(154, 142, 186), accent=(238, 198, 108),
        row_style=CARD, row_fill=(255, 255, 255, 16), row_fill_alt=(255, 255, 255, 10),
        top1_fill=(238, 198, 108, 82), top3_fill=(238, 198, 108, 40),
        radius=10, columns=2, rank_style=CIRCLE,
    ),
    Theme(
        key="broadcast",
        name="Broadcast Clean",
        blurb="Flat slate, one column, oversized rows. The most legible option on a small stream window.",
        bg_style=SOLID,
        bg_from=(22, 27, 36), bg_to=(22, 27, 36),
        title=(244, 247, 252), subtitle=(120, 200, 255), text=(238, 242, 248),
        muted=(138, 152, 172), accent=(120, 200, 255),
        row_style=STRIPED, row_fill=(255, 255, 255, 14), row_fill_alt=(255, 255, 255, 6),
        top1_fill=(120, 200, 255, 52), top3_fill=(120, 200, 255, 26),
        radius=0, columns=1, row_gap=0, rank_style=BLOCK,
    ),
    Theme(
        key="championship",
        name="Championship Gold",
        blurb="Black and heavy gold, single column, big rank numerals. Save it for the trophy shot.",
        bg_style=RADIAL,
        bg_from=(46, 36, 8), bg_to=(6, 5, 3),
        title=(255, 248, 226), subtitle=(246, 202, 92), text=(250, 244, 228),
        muted=(160, 142, 96), accent=(246, 202, 92),
        row_style=GLOW, row_fill=(246, 202, 92, 20), row_fill_alt=(246, 202, 92, 20),
        top1_fill=(246, 202, 92, 96), top3_fill=(246, 202, 92, 48),
        radius=6, columns=1, row_gap=10, rank_style=CHEVRON, caps_names=True,
    ),
)

BY_KEY = {theme.key: theme for theme in THEMES}
DEFAULT_KEY = THEMES[0].key

#: `template: "custom"` means "use my uploaded background". The layout still
#: comes from a real template so the table always lands somewhere sensible.
CUSTOM_KEY = "custom"
CUSTOM_BASE_KEY = "broadcast"


@dataclass
class Branding:
    """Everything the operator can change on top of a template."""

    template: str = DEFAULT_KEY
    accent: str = ""
    text: str = ""
    title: str = ""
    #: absolute paths, resolved by the caller from its own storage
    background_image: str = ""
    logo_image: str = ""
    logo_position: str = "top-right"
    show_logo: bool = True
    #: 0-255 darkening over a custom background; None uses the template default
    scrim: int | None = None
    layout: str = ""          # "", "1" or "2" — overrides the template's columns
    notes: list = field(default_factory=list)

    @classmethod
    def from_event(cls, event: dict, resolve=None) -> Branding:
        """Read the `graphics` block out of an event.json.

        `resolve` turns a stored filename into an absolute path; it is supplied
        by the caller because the desktop app and each web tenant keep their
        uploads in different places.
        """
        raw = (event or {}).get("graphics") or {}
        resolve = resolve or (lambda name: name)
        background = raw.get("background") or ""
        logo = raw.get("logo") or ""
        return cls(
            template=raw.get("template") or DEFAULT_KEY,
            accent=raw.get("accent") or "",
            text=raw.get("text") or "",
            title=raw.get("title") or "",
            background_image=str(resolve(background)) if background else "",
            logo_image=str(resolve(logo)) if logo else "",
            logo_position=raw.get("logoPosition") or "top-right",
            show_logo=bool(raw.get("showLogo", True)),
            scrim=raw.get("scrim"),
            layout=str(raw.get("layout") or ""),
        )

    def has_artwork(self) -> bool:
        return bool(self.background_image)

    def resolved_theme(self) -> Theme:
        """The template to render with, after custom-mode and colour overrides."""
        key = self.template if self.template in BY_KEY else (
            CUSTOM_BASE_KEY if self.template == CUSTOM_KEY else DEFAULT_KEY
        )
        theme = BY_KEY[key]
        if self.has_artwork():
            theme = theme.over_artwork()
        theme = theme.override(accent=self.accent, text=self.text, title=self.title)
        if self.layout in ("1", "2"):
            theme = replace(theme, columns=int(self.layout))
        if self.scrim is not None:
            theme = replace(theme, image_scrim=max(0, min(255, int(self.scrim))))
        return theme


def catalogue() -> list:
    """Template metadata for the picker, custom slot last."""
    return [theme.as_dict() for theme in THEMES] + [{
        "key": CUSTOM_KEY,
        "name": "Custom",
        "blurb": "Your own background image and logo. The standings table is drawn on top.",
        "columns": BY_KEY[CUSTOM_BASE_KEY].columns,
        "swatch": ["#1a1a1a", "#333333", "#e8be52", "#f2f2f2"],
    }]
