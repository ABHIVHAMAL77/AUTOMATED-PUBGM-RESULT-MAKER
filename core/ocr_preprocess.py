"""Image work that happens before and around the OCR call.

Two jobs.

**Bleed-through rejection.** The Observe-lobby screen is a dark, semi-transparent
panel laid over the live match, so the game world shows through: distant player
tags, the minimap legend, the timer, and whatever team list was on screen a
moment ago. RapidOCR reads that ghost text happily and confidently — scores of
0.9+ — and it used to land in the card grid as extra teams and, worse, as extra
player rows inside real cards, which is what wrecked slot assignment.

The engine's own score cannot tell the two apart. Local contrast can, decisively:
on a real card the glyphs are near-white on a near-black panel (contrast 200+,
70+ even for a dimmed row), while bleed-through is grey-on-grey (under 30).

**Scaling.** RapidOCR's detector wants text roughly 20-40px tall. Phone captures
downscaled for upload fall under that, and small text is where the digit
confusions (0/O, 1/l) come from. `prepare` upsamples anything too small and
stretches contrast, and reports the scale so boxes map back to original pixels.
"""

from __future__ import annotations

from io import BytesIO

# glyph-vs-background separation below this is bleed-through, not card text
MIN_TEXT_CONTRAST = 40

# target height for the shortest text we care about
TARGET_TEXT_HEIGHT = 26


def to_gray(image):
    """Grayscale view of a PIL image, cached on the image object."""
    cached = getattr(image, "_ec_gray", None)
    if cached is None:
        cached = image.convert("L")
        try:
            image._ec_gray = cached
        except AttributeError:                          # pragma: no cover - exotic image types
            pass
    return cached


def box_contrast(gray, box) -> float:
    """Spread between the glyph pixels and the background inside one OCR box.

    Percentiles rather than min/max so a single hot pixel or a JPEG artefact
    does not make grey text look like white text.
    """
    x0 = max(0, int(box.x0))
    y0 = max(0, int(box.y0))
    x1 = min(gray.width, max(x0 + 2, int(box.x1)))
    y1 = min(gray.height, max(y0 + 2, int(box.y1)))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    data = sorted(gray.crop((x0, y0, x1, y1)).getdata())
    if not data:
        return 0.0
    lo = data[int(len(data) * 0.10)]
    hi = data[int(len(data) * 0.90)]
    return float(hi - lo)


def drop_bleed_through(boxes, image, min_contrast: float = MIN_TEXT_CONTRAST) -> list:
    """Remove boxes whose text is too low-contrast to be on a UI panel.

    Returns the surviving boxes with `.contrast` recorded, so downstream code
    (and the confidence model) can weigh a dim-but-real row differently from a
    crisp one.
    """
    gray = to_gray(image)
    kept = []
    for box in boxes:
        contrast = box_contrast(gray, box)
        box.contrast = contrast
        if contrast >= min_contrast:
            kept.append(box)
    return kept


def prepare(image, min_text_height: float | None = None) -> tuple[bytes, float]:
    """Encode `image` for the OCR engine, upscaled if its text is small.

    Returns (png_bytes, scale). Divide box coordinates by `scale` to get back
    to the original image's pixel space.
    """
    from PIL import ImageOps

    scale = 1.0
    if min_text_height and min_text_height > 0:
        scale = max(1.0, TARGET_TEXT_HEIGHT / min_text_height)
        scale = min(scale, 3.0)          # beyond 3x the engine gets slower, not better

    work = image
    if scale > 1.05:
        work = image.resize((int(image.width * scale), int(image.height * scale)))

    work = ImageOps.autocontrast(work.convert("L"), cutoff=1)
    buf = BytesIO()
    work.save(buf, "PNG")
    return buf.getvalue(), scale


def zoom_crop(image, region, target_height: int = 240) -> bytes | None:
    """Grayscale, contrast-stretched, upscaled crop for a second OCR pass over
    a small region (a slot number, a rank digit). None if the region is empty.
    """
    from PIL import ImageOps

    x0, y0, x1, y1 = (int(max(0, v)) for v in region)
    x1 = min(x1, image.width)
    y1 = min(y1, image.height)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None

    crop = image.crop((x0, y0, x1, y1)).convert("L")
    crop = ImageOps.autocontrast(crop, cutoff=2)
    scale = max(2, int(target_height / max(1, crop.height)))
    crop = crop.resize((crop.width * scale, crop.height * scale))
    buf = BytesIO()
    crop.save(buf, "PNG")
    return buf.getvalue()


def brightness_profile(image, x0: int, x1: int) -> list:
    """Mean luminance per scanline of a vertical strip — used to find the
    boundaries of the gold result cards."""
    gray = to_gray(image)
    x0 = max(0, int(x0))
    x1 = min(gray.width, max(x0 + 1, int(x1)))
    strip = gray.crop((x0, 0, x1, gray.height))
    width = x1 - x0
    px = list(strip.getdata())
    return [sum(px[y * width:(y + 1) * width]) / width for y in range(gray.height)]


def panel_grid(image, min_span: int = 60) -> tuple[list, list]:
    """Find the card panels on the Observe-lobby screen.

    The panels are translucent dark rectangles over a bright game world, laid
    out in a rigid grid. Locating them from their own pixels beats inferring
    them from where text happens to sit: clustering name boxes by their left
    edge splits a card whose IGNs are indented differently, and merges two
    cards in neighbouring columns whose names line up.

    The measure is the 25th-percentile brightness of each column and row, not
    the mean or the median. A percentile that low samples the panel's
    *background* and ignores the text drawn on it, so a column full of bright
    IGNs still reads as dark — which is the whole point, and is what a mean
    profile gets wrong. The dark/bright split is then Otsu's, so the same code
    works on a washed-out capture and a dim one.

    Returns (column_spans, row_spans) as [(start, end), ...] in image pixels.
    Either may be empty when the screen does not look like this layout, and
    the caller should then fall back to text clustering.
    """
    gray = to_gray(image)
    width, height = gray.size
    px = gray.load()

    # skip the header strip and the bottom status bar
    y_lo, y_hi = int(height * 0.12), int(height * 0.96)
    x_lo, x_hi = int(width * 0.10), int(width * 0.86)
    if y_hi - y_lo < 40 or x_hi - x_lo < 40:
        return [], []

    ys = list(range(y_lo, y_hi, 3))
    col_profile = [_percentile([px[x, y] for y in ys], 0.25)
                   for x in range(0, width, 4)]
    columns = _fit_grid(_dark_spans(col_profile, 4, min_span + 20), width)
    if not columns:
        return [], []

    # Sample rows only *inside* the columns just found. Measured across the
    # full width, the bright gaps between columns drown the signal and the row
    # boundaries land tens of pixels off.
    xs = [x for lo, hi in columns
          for x in range(int(lo) + 8, int(min(hi, x_hi)) - 8, 4)]
    if not xs:
        xs = list(range(x_lo, x_hi, 4))
    row_profile = [_percentile([px[x, y] for x in xs], 0.25)
                   for y in range(0, height, 3)]
    rows = _fit_grid(_dark_spans(row_profile, 3, min_span), height)
    return columns, rows


def _fit_grid(spans: list, limit: int) -> list:
    """Turn noisy dark-runs into the regular grid they are samples of.

    A raw profile gives ragged answers: one panel splits in two where a bright
    icon crosses it, another is clipped short, a third is missing entirely
    because the card behind it happens to be pale. But the real layout is a
    uniform grid, so fitting pitch and cell size to the runs that *are* clean
    and regenerating the rest recovers the panels the profile lost.
    """
    if len(spans) < 2:
        return spans

    spans = _merge_close(spans)
    lengths = sorted(hi - lo for lo, hi in spans)
    typical = lengths[len(lengths) // 2]

    solid = [(lo, hi) for lo, hi in spans if (hi - lo) >= typical * 0.75]
    if len(solid) < 2:
        return spans

    starts = [lo for lo, _ in solid]
    gaps = sorted(b - a for a, b in zip(starts, starts[1:], strict=False))
    pitch = gaps[len(gaps) // 2]
    size = max(typical, max(hi - lo for lo, hi in solid))
    if pitch <= 0 or pitch < size * 0.8:
        return spans

    # Lay the pitch across the whole axis and keep every cell that fits, even
    # where the profile saw nothing. A panel sitting over a bright patch of
    # the game world is too pale to detect but is still there — that is
    # exactly the row this used to lose. Over-generating is safe: a cell with
    # no text in it produces no card.
    anchor = starts[0]
    positions = []
    position = anchor - pitch * (anchor // pitch)
    while position < limit:
        positions.append(position)
        position += pitch

    cells = [(int(pos), int(min(limit, pos + size))) for pos in positions
             if min(limit, pos + size) - pos >= size * 0.6]
    return cells or spans


def _merge_close(spans: list) -> list:
    """Join runs split by a bright detail crossing the panel.

    The tolerance has to stay well under the real gap between two panels,
    which is small next to the panels themselves — merging too eagerly fuses
    the entire grid into one cell.
    """
    if not spans:
        return spans
    lengths = sorted(hi - lo for lo, hi in spans)
    tolerance = max(6, lengths[len(lengths) // 2] * 0.04)
    out = [list(spans[0])]
    for lo, hi in spans[1:]:
        if lo - out[-1][1] <= tolerance:
            out[-1][1] = hi
        else:
            out.append([lo, hi])
    return [(lo, hi) for lo, hi in out]


def _percentile(values: list, q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return float(ordered[min(len(ordered) - 1, int(len(ordered) * q))])


def _dark_spans(profile: list, step: int, min_length: int) -> list:
    """Runs of the profile that sit on the dark side of the Otsu split."""
    threshold = otsu_threshold(profile)
    out, start = [], None
    for i, value in enumerate(profile):
        if value < threshold and start is None:
            start = i
        elif value >= threshold and start is not None:
            if (i - start) * step >= min_length:
                out.append((start * step, i * step))
            start = None
    if start is not None and (len(profile) - start) * step >= min_length:
        out.append((start * step, len(profile) * step))
    return out


def otsu_threshold(values: list) -> float:
    """Split a 1-D profile into dark and bright classes.

    The card detector used to threshold at a fixed 45% of the dynamic range,
    which assumes every capture has the same gamma. Otsu finds the split that
    actually separates the two populations in *this* image, so a dim capture
    and a bright one both work.

    The returned cut is the midpoint between the two class *means*, not Otsu's
    own boundary. When one class dominates — a screen that is mostly dark
    panel — Otsu's boundary sits flush against it, and pixel noise of a
    point or two then flickers across the line and shreds a solid run into
    fragments. Halfway between the means leaves room for that noise.
    """
    if not values:
        return 0.0
    lo, hi = min(values), max(values)
    if hi - lo < 1e-6:
        return lo

    bins = 64
    hist = [0] * bins
    for v in values:
        idx = int((v - lo) / (hi - lo) * (bins - 1))
        hist[idx] += 1

    total = len(values)
    sum_all = sum(i * h for i, h in enumerate(hist))
    sum_b = 0.0
    weight_b = 0
    best_var = -1.0
    best_means = (0.0, float(bins))
    for i in range(bins):
        weight_b += hist[i]
        if weight_b == 0:
            continue
        weight_f = total - weight_b
        if weight_f == 0:
            break
        sum_b += i * hist[i]
        mean_b = sum_b / weight_b
        mean_f = (sum_all - sum_b) / weight_f
        var = weight_b * weight_f * (mean_b - mean_f) ** 2
        if var > best_var:
            best_var = var
            best_means = (mean_b, mean_f)

    midpoint = (best_means[0] + best_means[1]) / 2
    return lo + (midpoint + 0.5) / bins * (hi - lo)
