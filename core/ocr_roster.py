"""OCR for the in-game team/slot list screenshots (Observe lobby view).

The screenshot shows team cards in a 3-column grid. Each card has:
  - a big colored slot number at the top-left (e.g. 15, 05)
  - up to 4 player IGNs, one per row
  - "/0 Eliminations" text on the right of every row (noise for us)

parse_slot_screenshot() returns [{"slot": int|None, "players": [str, ...]}].
Slot may be None when the number could not be read — the UI lets the
operator fix it by hand.

Strategy: player names OCR very reliably, so cards are located by clustering
name boxes into columns and splitting on row-pitch gaps. The big colored slot
digits are less reliable full-frame, so every card's slot number is confirmed
with a second, zoomed-in OCR pass over just the slot-number region.

Before any of that, low-contrast boxes are discarded. This screen is a
translucent panel over the live match, and the game world bleeding through it
OCRs at high confidence — see core/ocr_preprocess.drop_bleed_through.

Engine: RapidOCR (PP-OCR models via onnxruntime) — pure pip install, works
offline. Player IGNs with rare Unicode symbols may come out slightly wrong;
that is fine because the results matching step uses fuzzy comparison, the
roster table is editable, and the Claude vision pass can re-read the hard ones.
"""

import re
import statistics
from dataclasses import dataclass, field

from .ocr_preprocess import TARGET_TEXT_HEIGHT, drop_bleed_through, prepare, zoom_crop

_ENGINE = None

# Boxes below this are noise. Kept low deliberately: dropping a weak box early
# is how clipped rank digits used to disappear, and the contrast gate plus the
# 1..25 range check downstream are far better filters than the raw score.
MIN_BOX_SCORE = 0.2

# text that is UI noise, never a player name
NOISE_RE = re.compile(
    r"elimination|remaining|^team$|^stage|^change$|^smooth|^pubg|mobile|ranked",
    re.IGNORECASE)
# the "/0" kill counters (OCR reads them as /0, 10, l0, /O, 0 ...)
KILL_COUNTER_RE = re.compile(r"^[/\\|(\[{1lI]?\s*[0OoQD]{1,2}$")
DIGIT_FIX = str.maketrans({"O": "0", "o": "0", "Q": "0", "D": "0",
                           "l": "1", "I": "1", "|": "1", "B": "8", "S": "5"})


@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    score: float
    # glyph-vs-background separation, filled in by drop_bleed_through
    contrast: float = 0.0

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def h(self):
        return self.y1 - self.y0

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2


@dataclass
class Card:
    column: int
    top: float
    name_x0: float
    slot: int | None = None
    players: list = field(default_factory=list)


def _get_engine():
    global _ENGINE
    if _ENGINE is None:
        from rapidocr_onnxruntime import RapidOCR
        _ENGINE = RapidOCR()
    return _ENGINE


def warm_up() -> None:
    """Load the ONNX models now rather than on the first upload.

    Model load is several seconds; paying it during a request makes the first
    OCR of a session look broken. The web app calls this at startup.
    """
    try:
        _get_engine()
    except Exception:                                   # noqa: BLE001 - never block startup
        pass


def _run_ocr(source, min_score: float = MIN_BOX_SCORE, scale: float = 1.0) -> list:
    result, _ = _get_engine()(source)
    boxes = []
    for pts, text, score in result or []:
        text = (text or "").strip()
        if not text or float(score) < min_score:
            continue
        xs = [p[0] / scale for p in pts]
        ys = [p[1] / scale for p in pts]
        boxes.append(Box(min(xs), min(ys), max(xs), max(ys), text, float(score)))
    return boxes


def _iou(a, b) -> float:
    ix0, iy0 = max(a.x0, b.x0), max(a.y0, b.y0)
    ix1, iy1 = min(a.x1, b.x1), min(a.y1, b.y1)
    if ix1 <= ix0 or iy1 <= iy0:
        return 0.0
    inter = (ix1 - ix0) * (iy1 - iy0)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


def merge_boxes(*box_lists, iou_threshold: float = 0.45) -> list:
    """Combine boxes from several OCR passes, keeping the best read of each.

    Two passes over the same screenshot disagree in useful ways: the full-frame
    pass has the layout right, the zoomed half-frame pass reads small glyphs
    better. Where they overlap, the higher-scoring read wins.
    """
    merged = []
    for boxes in box_lists:
        for box in boxes:
            for i, kept in enumerate(merged):
                if _iou(box, kept) >= iou_threshold:
                    if box.score > kept.score:
                        merged[i] = box
                    break
            else:
                merged.append(box)
    return merged


def ocr_image(image, halves: bool = True) -> list:
    """OCR one PIL image thoroughly.

    Pass 1 is the full frame, which gets the layout right. Pass 2 splits the
    frame in half and re-reads each half upscaled, which recovers small or
    faint glyphs the full-frame detector rounds off — the digit confusions and
    the clipped rank numbers came from there.
    """
    full = _run_ocr(_encode(image))
    if not halves:
        return full

    med_h = statistics.median([b.h for b in full]) if full else 0
    if med_h and med_h >= TARGET_TEXT_HEIGHT:
        # text is already large enough that a zoom pass buys nothing
        return full

    extra = []
    mid = image.width // 2
    for x0, x1 in ((0, mid), (mid, image.width)):
        crop = image.crop((x0, 0, x1, image.height))
        payload, scale = prepare(crop, min_text_height=med_h or None)
        for box in _run_ocr(payload, scale=scale):
            box.x0 += x0
            box.x1 += x0
            extra.append(box)
    return merge_boxes(full, extra)


def _encode(image) -> bytes:
    from io import BytesIO
    buf = BytesIO()
    image.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def ocr_boxes(image_path) -> tuple[list, int, int]:
    """Full-frame OCR pass; returns (boxes, width, height)."""
    from PIL import Image
    with Image.open(image_path) as im:
        width, height = im.size
    return _run_ocr(str(image_path)), width, height


def _as_slot_number(text: str) -> int | None:
    cleaned = re.sub(r"\D", "", text.replace(" ", "").translate(DIGIT_FIX))
    if cleaned and len(cleaned) <= 2:
        n = int(cleaned)
        if 1 <= n <= 25:
            return n
    return None


def _ocr_slot_crop(im, region) -> int | None:
    """Zoomed-in second OCR pass over one card's slot-number area."""
    return _ocr_slot_crop_scored(im, region)[0]


def _ocr_slot_crop_scored(im, region) -> tuple[int | None, float]:
    """As _ocr_slot_crop but also returns the engine's confidence, so a caller
    can decide whether the zoom pass is more trustworthy than what the
    full-frame pass thought it saw."""
    payload = zoom_crop(im, region)
    if payload is None:
        return None, 0.0

    candidates = []
    for b in _run_ocr(payload):
        n = _as_slot_number(b.text)
        if n is None:
            continue
        digits = len(re.sub(r"\D", "", b.text.translate(DIGIT_FIX)))
        candidates.append((b.score, n, b.x0, digits))

    if not candidates:
        return None, 0.0

    joined = _join_split_digits(candidates)
    if joined is not None:
        return joined

    # PUBGM zero-pads slot numbers ("05", "18"), so a two-digit read beats a
    # one-digit read even when the engine likes the shorter one better: a lone
    # digit here is nearly always half of a number whose other half was lost
    # in the thin stroke of a "1" or a colour the detector washed out.
    two_digit = [c for c in candidates if c[3] == 2]
    score, n, _, _ = max(two_digit or candidates)
    return n, score


def _join_split_digits(candidates: list) -> tuple[int, float] | None:
    """Two single-digit boxes side by side are one two-digit slot number."""
    singles = sorted((c for c in candidates if c[3] == 1), key=lambda c: c[2])
    if len(singles) != 2 or len(candidates) != 2:
        return None
    n = singles[0][1] * 10 + singles[1][1]
    if not 1 <= n <= 25:
        return None
    return n, min(singles[0][0], singles[1][0])


def parse_slot_screenshot(image_path) -> list:
    from PIL import Image

    im = Image.open(image_path).convert("RGB")
    height = im.size[1]
    boxes = ocr_image(im)

    # 1. drop the live match bleeding through the translucent panel, then the
    #    header zone (compass strip, "Remaining 67 Team 17") and UI noise
    boxes = drop_bleed_through(boxes, im)
    boxes = [b for b in boxes
             if b.cy > height * 0.12
             and not NOISE_RE.search(b.text)
             and not KILL_COUNTER_RE.fullmatch(b.text.replace(" ", ""))]
    if not boxes:
        return []

    # 2. prefer the real panel rectangles; fall back to clustering text when
    #    the screen does not have the expected grid
    cards = _cards_from_panels(im, boxes)
    if cards:
        return cards
    return _cards_from_text_clusters(im, boxes)


def _cards_from_panels(im, boxes) -> list:
    """Assign text to the detected panel rectangles, one card per panel."""
    from .ocr_preprocess import panel_grid

    columns, rows = panel_grid(im)
    if len(columns) < 2 or len(rows) < 2:
        return []

    cells = {}
    for box in boxes:
        col = _span_index(columns, box.cx)
        row = _span_index(rows, box.cy)
        if col is None or row is None:
            continue
        cells.setdefault((row, col), []).append(box)
    if not cells:
        return []

    out = []
    for (row, col), cell_boxes in sorted(cells.items()):
        card = _card_from_cell(im, cell_boxes, columns[col], rows[row])
        if card:
            out.append(card)
    out.sort(key=lambda c: (c["slot"] is None, c["slot"] if c["slot"] is not None else 99))
    return out


def _span_index(spans, value) -> int | None:
    for i, (lo, hi) in enumerate(spans):
        if lo <= value <= hi:
            return i
    return None


def _card_from_cell(im, boxes, col_span, row_span) -> dict | None:
    """One panel -> {"slot", "players"}.

    The slot number sits alone in the panel's top-left corner, printed larger
    and in the team's colour. Reading it from a zoomed crop of that corner is
    much more reliable than picking a numeric box out of the full-frame pass,
    which is where the old code kept attaching the wrong number to a card.
    """
    x0, x1 = col_span
    y0, y1 = row_span
    number_right = x0 + (x1 - x0) * 0.17

    slot, slot_score = _ocr_slot_crop_scored(
        im, (x0 + 2, y0 + 2, number_right, y0 + (y1 - y0) * 0.34))

    names = []
    for box in sorted(boxes, key=lambda b: b.y0):
        text = box.text.strip()
        if not text:
            continue
        # the slot number itself, and the "/0 Eliminations" column
        if box.x1 <= number_right and _as_slot_number(text) is not None:
            if slot is None:
                slot = _as_slot_number(text)
            continue
        if KILL_COUNTER_RE.fullmatch(text.replace(" ", "")):
            continue

        # a slot number glued onto the first player name ("15 Wz Lynx")
        m = re.match(r"^(\d{1,2})\s+(.{2,})$", text)
        if m and not names and _as_slot_number(m.group(1)) is not None:
            if slot is None or slot_score < 0.6:
                slot = _as_slot_number(m.group(1))
            text = m.group(2)
        if len(text.replace(" ", "")) >= 2:
            names.append(text)

    if not names:
        return None
    return {"slot": slot, "players": names[:4]}


def _cards_from_text_clusters(im, boxes) -> list:
    """Original strategy: cluster name boxes into columns by their left edge
    and split each column on row-pitch gaps. Used when panel detection finds
    no grid — a different resolution, aspect ratio, or UI skin."""
    width = im.size[0]

    # 2. split into name boxes and standalone slot-number boxes
    slot_candidates = []   # (Box, number)
    name_boxes = []
    for b in boxes:
        n = _as_slot_number(b.text)
        if n is not None and re.fullmatch(r"[\dOoQDlI|BS ]{1,3}",
                                          b.text.replace(" ", "")):
            slot_candidates.append((b, n))
        elif len(b.text.replace(" ", "")) >= 2:
            name_boxes.append(b)
    if not name_boxes:
        return []

    med_h = statistics.median(b.h for b in name_boxes)

    # 3. cluster name boxes into columns by left edge
    name_boxes.sort(key=lambda b: b.x0)
    columns = []  # [x0_ref, [boxes]]
    tol = width * 0.04
    for b in name_boxes:
        for col in columns:
            if abs(col[0] - b.x0) < tol:
                col[1].append(b)
                break
        else:
            columns.append([b.x0, [b]])
    columns.sort(key=lambda c: c[0])

    # 4. split each column into cards on row-pitch gaps
    cards = []
    for col_idx, (col_x0, col_boxes) in enumerate(columns):
        col_boxes.sort(key=lambda b: b.y0)
        pitches = [b2.y0 - b1.y0 for b1, b2 in zip(col_boxes, col_boxes[1:], strict=False)]
        row_pitch = statistics.median(pitches) if pitches else med_h * 2
        threshold = row_pitch * 1.55
        current = None
        prev = None
        for b in col_boxes:
            if current is None or (b.y0 - prev.y0) > threshold:
                current = Card(column=col_idx, top=b.y0, name_x0=col_x0)
                cards.append(current)
            # a slot number glued onto the first player name ("15 Wz Lynx")
            m = re.match(r"^(\d{1,2})\s+(.{2,})$", b.text)
            if m and not current.players and current.slot is None \
                    and _as_slot_number(m.group(1)) is not None:
                current.slot = _as_slot_number(m.group(1))
                current.players.append(m.group(2))
            else:
                current.players.append(b.text)
            prev = b

    # 5. attach standalone slot-number boxes (left of names, on the top row)
    for sb, n in slot_candidates:
        best, best_d = None, None
        for card in cards:
            if card.slot is not None:
                continue
            if sb.x1 > card.name_x0 + tol or sb.x0 < card.name_x0 - width * 0.08:
                continue
            d = abs(card.top - sb.y0)
            if d < med_h * 2 and (best_d is None or d < best_d):
                best, best_d = card, d
        if best is not None:
            best.slot = n

    # 6. zoomed-in retry for cards still missing a slot number
    for card in cards:
        if card.slot is not None:
            continue
        card.slot = _ocr_slot_crop(im, (
            card.name_x0 - width * 0.055, card.top - med_h * 0.8,
            card.name_x0 - 2, card.top + med_h * 1.6,
        ))

    # 7. build output, max 4 players per card
    out = []
    for card in cards:
        players = [p.strip() for p in card.players if p.strip()][:4]
        if not players:
            continue
        out.append({"slot": card.slot, "players": players})
    out.sort(key=lambda c: (c["slot"] is None, c["slot"] if c["slot"] is not None else 99))
    return out


def suggest_tag(players: list) -> str:
    """Guess the team tag from a common prefix of the player IGNs.

    'Wz Lynx', 'Wz Kúkú' -> 'Wz';  'SC-MSTRhyunn', 'SC-RAMBO' -> 'SC'
    """
    if len(players) < 2:
        return ""
    cleaned = [p.strip() for p in players if p.strip()]
    if len(cleaned) < 2:
        return ""
    prefix = cleaned[0]
    for p in cleaned[1:]:
        while prefix and not p.startswith(prefix):
            prefix = prefix[:-1]
    prefix = prefix.strip(" -·×.『』[]_")
    return prefix if len(prefix) >= 2 else ""
