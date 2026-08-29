"""OCR for post-match rankings screenshots.

Layout of the game's match-results screen:
  - LEFT panel (fixed on every screenshot): the #1 team (crown icon, no
    number) and the #2 team, players listed with "N elimination(s)".
  - RIGHT column (scrolls): gold cards with a big white rank number and up
    to 4 player rows. Cards at the top/bottom edge can be cut off — the
    same card usually appears complete in the neighbouring screenshot.

Pipeline:
  parse_results_screenshot(path)  -> cards for one image
  merge_result_cards(cards_lists) -> de-duplicated cards across screenshots
  match_cards_to_roster(cards, teams) -> attach slot/team via fuzzy matching

A card is {"rank": int|None, "players": [{"name": str, "kills": int}]}.
Rank is None when the number was cut off or unreadable — the operator can
fix it in the UI table.
"""

import re
import statistics
import unicodedata
from difflib import SequenceMatcher

from .ocr_preprocess import brightness_profile, otsu_threshold
from .ocr_roster import (
    DIGIT_FIX,
    _as_slot_number,
    _ocr_slot_crop,
    _ocr_slot_crop_scored,
    _run_ocr,
    ocr_image,
)

NOISE_RE = re.compile(r"^continue$|^pubg$|mobile|^stage|^change$", re.IGNORECASE)

ELIM_WORD = r"(?:e?l[i1l]m(?:ination)?s?|elims?|\bkills?\b)"
ELIM_RE = re.compile(rf"([0-9OoQDlI|]{{0,2}})\s*{ELIM_WORD}", re.IGNORECASE)
ELIM_AFTER_RE = re.compile(rf"{ELIM_WORD}\s*([0-9OoQDlI|]{{1,2}})", re.IGNORECASE)
NAME_NOISE_RE = re.compile(rf"{ELIM_WORD}|^\W*$", re.IGNORECASE)

SYMBOL_REPLACEMENTS = {
    0x00D7: "x",
    0x2715: "x",
    0x2716: "x",
    0x2573: "x",
    0x4E28: "i",
    0xFF5C: "i",
    0x2160: "i",
    0x0131: "i",
    0x0130: "i",
}
RELAXED_NAME_TRANS = str.maketrans({
    "0": "o", "o": "o",
    "1": "i", "l": "i", "i": "i", "|": "i",
    "5": "s", "8": "b", "2": "z", "6": "g",
})


def _ascii_text(text: str) -> str:
    text = "".join(SYMBOL_REPLACEMENTS.get(ord(ch), ch) for ch in str(text or ""))
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii")


def _elim_count(text: str) -> int | None:
    """Robust elimination counter for labels like '4 eliminations',
    'eliminations 4', '4 elims', or a label without a readable count."""
    t = _ascii_text(text).strip()
    m = ELIM_RE.search(t) or ELIM_AFTER_RE.search(t)
    if not m:
        return -1 if re.search(ELIM_WORD, t, re.IGNORECASE) else None
    digits = re.sub(r"\D", "", (m.group(1) or "").translate(DIGIT_FIX))
    return int(digits) if digits else -1


def _norm(name: str) -> str:
    text = _ascii_text(name).lower()
    text = re.sub(ELIM_WORD, "", text, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9|]", "", text)


def _display_name(name: str) -> str:
    text = _ascii_text(name)
    text = re.sub(rf"\b[0-9OoQDlI|]{{0,2}}\s*{ELIM_WORD}.*$", "",
                  text, flags=re.IGNORECASE)
    text = re.sub(rf"\b{ELIM_WORD}\s*[0-9OoQDlI|]{{0,2}}.*$", "",
                  text, flags=re.IGNORECASE)
    return text.strip(" -_.|[](){}")


def _looks_like_name(text: str) -> bool:
    compact = _norm(text)
    return len(compact) >= 2 and not compact.isdigit() and not NAME_NOISE_RE.search(_ascii_text(text))


def _parse_inline_player_row(text: str) -> tuple[str, int] | None:
    """Handle OCR boxes like 'PlayerName 4 eliminations'."""
    t = _ascii_text(text).strip()
    m = re.match(rf"(.+?)\s+([0-9OoQDlI|]{{0,2}})\s*{ELIM_WORD}\b", t,
                 re.IGNORECASE)
    if not m:
        m = re.match(rf"(.+?)\s+{ELIM_WORD}\s*([0-9OoQDlI|]{{0,2}})\b", t,
                     re.IGNORECASE)
    if not m:
        return None
    name = _display_name(m.group(1))
    if not _looks_like_name(name):
        return None
    digits = re.sub(r"\D", "", (m.group(2) or "").translate(DIGIT_FIX))
    return name, int(digits) if digits else 0


def _refine_name_from_crop(im, parts: list, original: str) -> str:
    """Re-read a player-name crop when the full-frame pass looks doubtful."""
    original = _display_name(original)
    if not parts:
        return original

    current_score = min((float(getattr(p, "score", 0.0)) for p in parts), default=0.0)
    if current_score >= 0.76 and len(_norm(original)) >= 3:
        return original

    pad_x = 32
    x0 = max(0, int(min(p.x0 for p in parts) - pad_x))
    y0 = max(0, int(min(p.y0 for p in parts) - 6))
    x1 = min(im.width, int(max(p.x1 for p in parts) + pad_x))
    y1 = min(im.height, int(max(p.y1 for p in parts) + 6))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return original

    crop = im.crop((x0, y0, x1, y1))
    variants = [crop]
    if current_score < 0.55:
        try:
            from PIL import ImageEnhance, ImageOps
            gray = ImageOps.autocontrast(crop.convert("L"), cutoff=1)
            variants.extend([
                gray,
                ImageEnhance.Sharpness(gray).enhance(2.4),
            ])
        except Exception:                              # noqa: BLE001 - raw crop still works
            pass

    candidates = []
    for variant in variants:
        try:
            read = _run_ocr(variant, min_score=0.35)
        except Exception:                              # noqa: BLE001 - never fail a screenshot for a retry
            continue
        if not read:
            continue
        read = sorted(read, key=lambda b: (b.y0, b.x0))
        med_y = statistics.median([b.cy for b in read])
        line = [b for b in read if abs(b.cy - med_y) <= max(8, crop.height * 0.35)]
        text = _display_name(" ".join(b.text for b in line))
        if not _looks_like_name(text):
            continue
        score = max(float(b.score) for b in line)
        candidates.append((score, len(_norm(text)), text))

    if not candidates:
        return original
    best_score, _, best_text = max(candidates, key=lambda item: (item[0], item[1]))
    if best_score >= 0.82 and best_score >= current_score + 0.12:
        return best_text
    if best_score >= 0.94 and _name_similarity(best_text, original) < 0.55:
        return best_text
    return original


def _name_variants(name: str) -> set:
    base = _norm(name)
    if not base:
        return set()
    variants = {base, base.translate(RELAXED_NAME_TRANS)}
    variants.add(re.sub(r"(.)\1{2,}", r"\1\1", base))
    if len(base) >= 6:
        variants.add(re.sub(r"^([a-z0-9]{2,5})i([a-z0-9]{3,})$", r"\1\2", base))
    return {v for v in variants if v}


def _bigrams(text: str) -> set:
    if len(text) < 2:
        return {text} if text else set()
    return {text[i:i + 2] for i in range(len(text) - 1)}


def _name_similarity(left: str, right: str) -> float:
    best = 0.0
    for a in _name_variants(left):
        for b in _name_variants(right):
            if not a or not b:
                continue
            score = SequenceMatcher(None, a, b).ratio()
            short, long = (a, b) if len(a) <= len(b) else (b, a)
            if len(short) >= 3 and short in long:
                score = max(score, min(0.98, 0.72 + (len(short) / len(long)) * 0.24))
            ag, bg = _bigrams(a), _bigrams(b)
            if ag and bg:
                dice = (2 * len(ag & bg)) / (len(ag) + len(bg))
                score = max(score, dice * 0.95)
            best = max(best, score)
    return best


def parse_results_screenshot(image_path) -> list:
    from PIL import Image

    im = Image.open(image_path).convert("RGB")
    width = im.size[0]
    boxes = [b for b in ocr_image(im) if not NOISE_RE.search(b.text)]
    if not boxes:
        return []

    divider = width * 0.53
    cards = []
    for region_boxes, is_left in (
        ([b for b in boxes if b.cx < divider], True),
        ([b for b in boxes if b.cx >= divider], False),
    ):
        cards.extend(_parse_region(im, region_boxes, width, is_left))
    return cards


def _parse_region(im, boxes, width, is_left) -> list:
    if not boxes:
        return []

    inline_rows = []
    inline_box_ids = set()
    for b in boxes:
        parsed = _parse_inline_player_row(b.text)
        if parsed is None:
            continue
        name, kills = parsed
        name = _refine_name_from_crop(im, [b], name)
        inline_rows.append({"name": name, "kills": kills, "cy": b.cy,
                            "y0": b.y0, "x0": b.x0})
        inline_box_ids.add(id(b))
    boxes = [b for b in boxes if id(b) not in inline_box_ids]

    # classify boxes: elimination labels, big rank numbers, names, counts
    elim_boxes = []       # (box, count or -1)
    other = []
    for b in boxes:
        c = _elim_count(b.text)
        if c is not None:
            elim_boxes.append((b, c))
        else:
            other.append(b)

    med_h = statistics.median([b.h for b, _ in elim_boxes] or [b.h for b in other] or [18])

    rank_boxes = []       # (box, number)
    name_boxes = []
    count_boxes = []      # standalone digits (an elim count in its own box)
    for b in other:
        stripped = b.text.replace(" ", "")
        n = _as_slot_number(b.text)
        if n is not None and re.fullmatch(r"[\dOoQDlI|BS]{1,2}", stripped):
            if b.h >= med_h * 1.35:
                rank_boxes.append((b, n))
            else:
                count_boxes.append(b)
        elif len(stripped) >= 2 and _looks_like_name(b.text):
            name_boxes.append(b)

    # build player rows: each elimination label pairs with name boxes on its
    # line (left of it) and, if the count was separate, the nearest digit box
    rows = list(inline_rows)
    used_names = set()
    used_counts = set()
    for eb, count in sorted(elim_boxes, key=lambda e: e[0].cy):
        if count == -1:
            best, best_d = None, None
            for cb in count_boxes:
                if id(cb) in used_counts:
                    continue
                if cb.x1 <= eb.x0 + med_h and abs(cb.cy - eb.cy) < med_h * 0.9:
                    d = eb.x0 - cb.x1
                    if 0 <= d < med_h * 4 and (best_d is None or d < best_d):
                        best, best_d = cb, d
            if best is not None:
                count = _as_slot_number(best.text) or 0
                used_counts.add(id(best))
            else:
                count = 0
        parts = []
        for nb in name_boxes:
            if id(nb) in used_names:
                continue
            if nb.x1 <= eb.x0 and abs(nb.cy - eb.cy) < med_h * 0.9:
                parts.append(nb)
        if not parts:
            if count > 0:
                rows.append({"name": "", "kills": max(0, count),
                             "cy": eb.cy, "y0": eb.y0, "x0": eb.x0,
                             "missingName": True})
            continue
        for nb in parts:
            used_names.add(id(nb))
        parts.sort(key=lambda b: b.x0)
        name = _display_name(" ".join(p.text for p in parts))
        name = _refine_name_from_crop(im, parts, name)
        if not _looks_like_name(name):
            continue
        rows.append({"name": name, "kills": max(0, count),
                     "cy": eb.cy, "y0": min(p.y0 for p in parts),
                     "x0": min(p.x0 for p in parts)})

    # Fallback for screenshots where OCR reads the kill count as a standalone
    # number but misses/drops the word "eliminations".
    for cb in count_boxes:
        if id(cb) in used_counts:
            continue
        parts = []
        for nb in name_boxes:
            if id(nb) in used_names:
                continue
            if nb.x1 <= cb.x0 + med_h and abs(nb.cy - cb.cy) < med_h * 0.95:
                parts.append(nb)
        if not parts:
            continue
        parts.sort(key=lambda b: b.x0)
        name = _display_name(" ".join(p.text for p in parts))
        name = _refine_name_from_crop(im, parts, name)
        if not _looks_like_name(name):
            continue
        for nb in parts:
            used_names.add(id(nb))
        rows.append({"name": name, "kills": _as_slot_number(cb.text) or 0,
                     "cy": cb.cy, "y0": min(p.y0 for p in parts),
                     "x0": min(p.x0 for p in parts)})
    if not rows:
        return []

    rows.sort(key=lambda r: r["cy"])
    pitches = [r2["cy"] - r1["cy"] for r1, r2 in zip(rows, rows[1:], strict=False)]
    small = [p for p in pitches if p < med_h * 3.2]
    pitch = statistics.median(small) if small else med_h * 2

    if is_left:
        return _cards_left(rows, rank_boxes, pitch)
    return _cards_right(im, rows, rank_boxes, pitch, med_h, width)


def _cards_left(rows, rank_boxes, pitch) -> list:
    """Left panel: split on gaps; topmost card is #1 (crown), next is #2.

    This panel holds exactly two cards — the winner and the runner-up — and
    never scrolls. Splitting purely on row gaps does not know that, so on a
    blurry or downscaled capture an uneven gap inside one team's rows breaks it
    into a third card, which then picks up a rank from the column beside it and
    collides with a real one. Folding the extras back into the nearest card
    keeps the split from turning into a wrong result.
    """
    cards = _cards_from_row_gaps(rows, rank_boxes, pitch, default_rank_start=1)
    if len(cards) <= 2:
        return cards

    first, second = cards[0], cards[1]
    for extra in cards[2:]:
        target = second if len(second["players"]) <= len(first["players"]) else first
        room = 4 - len(target["players"])
        if room > 0:
            target["players"].extend(extra["players"][:room])
    first["rank"], second["rank"] = 1, 2
    return [first, second]


def _cards_from_row_gaps(rows, rank_boxes, pitch, default_rank_start=None) -> list:
    groups = []
    current = None
    prev = None
    for r in rows:
        if current is None or (r["cy"] - prev["cy"]) > pitch * 1.6:
            current = []
            groups.append(current)
        current.append(r)
        prev = r
    cards = []
    for i, g in enumerate(groups):
        rank = None
        for rb, n in rank_boxes:
            if g[0]["cy"] - pitch <= rb.cy <= g[-1]["cy"] + pitch:
                rank = n
                break
        if rank is None and default_rank_start is not None:
            rank = default_rank_start + i
        cards.append(_make_card(rank, g))
    return cards


def _cards_right(im, rows, rank_boxes, pitch, med_h, width) -> list:
    """Right column: the gold cards sit on a dark background, so card
    boundaries come from the brightness profile of the strip left of the
    player names (where the big rank number lives). Rows are assigned to
    their card span; the rank is a detected number box inside the span or,
    failing that, a zoomed OCR pass over the span's number strip."""
    name_x0 = min(r["x0"] for r in rows)
    x0 = max(0, int(name_x0 - width * 0.075))
    x1 = max(x0 + 2, int(name_x0 - 4))
    profile = brightness_profile(im, x0, x1)
    # The split between "gold card" and "dark gap" used to be a fixed 45% of
    # the dynamic range, which assumes every phone renders the gold at the same
    # brightness. Deriving it from this image's own two populations means a
    # dim capture and a bright one both find the same card edges.
    threshold = otsu_threshold(profile)

    spans = []
    start = None
    for y, v in enumerate(profile):
        if v >= threshold and start is None:
            start = y
        elif v < threshold and start is not None:
            if y - start >= pitch * 0.9:
                spans.append((start, y))
            start = None
    if start is not None and im.height - start >= pitch * 0.9:
        spans.append((start, im.height))

    pad = pitch * 0.35
    span_rows = [[] for _ in spans]
    orphans = []
    for r in rows:
        for i, (s0, s1) in enumerate(spans):
            if s0 - pad <= r["cy"] <= s1 + pad:
                span_rows[i].append(r)
                break
        else:
            orphans.append(r)

    cards = []
    for (s0, s1), grp in zip(spans, span_rows, strict=True):
        if not grp:
            continue
        rank = None
        for rb, n in rank_boxes:
            if s0 - pad <= rb.cy <= s1 + pad:
                rank = n
                break
        rank = _confirm_rank(im, rank, (x0, s0 + 1, name_x0 - 2, s1 - 1))
        card = _make_card(rank, grp)
        card["_sortY"] = sum(r["cy"] for r in grp) / len(grp)
        cards.append(card)

    # rows outside every span: cut-off cards at the very edge
    groups = []
    current = None
    prev = None
    for r in orphans:
        if current is None or (r["cy"] - prev["cy"]) > pitch * 1.6:
            current = []
            groups.append(current)
        current.append(r)
        prev = r
    for g in groups:
        rank = _ocr_slot_crop(im, (
            x0, g[0]["cy"] - pitch, name_x0 - 2, g[-1]["cy"] + pitch))
        edge_cut = g[0]["cy"] < pitch * 1.5 or g[-1]["cy"] > im.height - pitch * 1.1
        if rank is None and len(g) <= 1 and edge_cut:
            continue
        card = _make_card(rank, g)
        card["_sortY"] = sum(r["cy"] for r in g) / len(g)
        cards.append(card)

    cards = _repair_right_rank_sequence(cards)

    fallback = _cards_from_row_gaps(rows, rank_boxes, pitch, default_rank_start=None)
    if len(fallback) > len(cards):
        cards = _dedupe_cards(cards + fallback)
        cards = _repair_right_rank_sequence(cards)
    return _strip_internal_keys(cards)


def _confirm_rank(im, rank, region):
    """Second look at a card's rank number.

    The big rank digits are the least reliable thing on the screen: they are
    wide-tracked, so "11" and "18" arrive as a lone "1" when the full-frame
    detector clips the second glyph, and a card that lands on rank 1 collides
    with the actual winner and disappears in the merge. A zoomed re-read of
    just the number strip settles it, and a two-digit answer beats a one-digit
    one — losing a digit is the common failure, inventing one is not.
    """
    zoomed, _ = _ocr_slot_crop_scored(im, region)
    if zoomed is None:
        return rank
    if rank is None:
        return zoomed
    if zoomed >= 10 and rank < 10 and zoomed % 10 == rank:
        # the full-frame read is the tail of the zoomed one: "1" out of "11"
        return zoomed
    return rank


def _repair_right_rank_sequence(cards: list) -> list:
    """Use right-column order to fix clipped ranks such as 11 -> 1.

    The right side is a scrolling placement list. Visible cards are consecutive,
    so a lone 1 after ranks 9 and 10 is far more likely to be 11 than another
    first-place card.
    """
    if len(cards) < 2:
        return cards

    ordered = sorted(enumerate(cards), key=lambda item: item[1].get("_sortY", item[0]))

    def rank_of(card):
        try:
            value = card.get("rank")
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    ranks = [rank_of(card) for _, card in ordered]
    starts = {rank - idx for idx, rank in enumerate(ranks)
              if rank is not None and 3 <= rank <= 25}
    if not starts:
        return cards

    def score_start(start: int) -> tuple[int, int]:
        good = 0
        bad = 0
        for idx, rank in enumerate(ranks):
            expected = start + idx
            if not 3 <= expected <= 25:
                bad += 2
                continue
            if rank is None or rank <= 2:
                continue
            if rank == expected:
                good += 1
            elif expected >= 10 and expected % 10 == rank:
                continue
            else:
                bad += 1
        return good, -bad

    start = max(starts, key=score_start)
    good, negative_bad = score_start(start)
    if good < 1 or -negative_bad > good:
        return cards

    for idx, (_, card) in enumerate(ordered):
        expected = start + idx
        if not 3 <= expected <= 25:
            continue
        rank = rank_of(card)
        previous = ranks[idx - 1] if idx else None
        suspect = (
            rank is None
            or rank <= 2
            or (expected >= 10 and rank < 10 and expected % 10 == rank)
            or (previous is not None and rank is not None and rank <= previous)
        )
        if suspect and rank != expected:
            card["rank"] = expected
            card["rankInferred"] = True
    return cards


def _strip_internal_keys(cards: list) -> list:
    for card in cards:
        for key in list(card):
            if key.startswith("_"):
                card.pop(key, None)
    return cards


def _dedupe_cards(cards: list) -> list:
    by_rank = {}
    unknown = []
    for card in cards:
        rank = card.get("rank")
        if rank is None:
            unknown.append(card)
            continue
        cur = by_rank.get(rank)
        if cur is None or _card_score(card) > _card_score(cur):
            by_rank[rank] = card
    out = [by_rank[r] for r in sorted(by_rank)]
    for card in unknown:
        if not any(_cards_similarity(card, known) >= 0.82 for known in out):
            out.append(card)
    return out


def _make_card(rank, rows) -> dict:
    rows = sorted(rows, key=lambda r: r["cy"])[:4]
    players = []
    for row in rows:
        player = {"name": _display_name(row["name"]), "kills": row["kills"]}
        if row.get("missingName"):
            player["missingName"] = True
        players.append(player)
    return {"rank": rank, "players": players}


def merge_result_cards(cards_lists: list) -> list:
    """Merge cards from several screenshots. Same rank -> keep the version
    with the most players (edge-cut duplicates lose). Rank-less cards are
    matched to known cards by player-name overlap, else kept for manual fix."""
    by_rank = {}
    unknown = []
    for cards in cards_lists:
        for c in cards:
            if c["rank"] is None:
                unknown.append(c)
                continue
            cur = by_rank.get(c["rank"])
            if cur is None:
                by_rank[c["rank"]] = c
                continue
            if _cards_similarity(c, cur) < 0.6:
                # Two different teams both read as this rank — one of the two
                # numbers was misread. Dropping the loser deletes a team from
                # the match entirely; keeping it rank-less puts it in front of
                # the operator with an empty rank box to fill in.
                loser = c if _card_score(c) <= _card_score(cur) else cur
                winner = cur if loser is c else c
                by_rank[c["rank"]] = winner
                loser = dict(loser, rank=None)
                unknown.append(loser)
            elif _card_score(c) > _card_score(cur):
                by_rank[c["rank"]] = c

    still_unknown = []
    for u in unknown:
        merged = False
        for c in by_rank.values():
            if _cards_similarity(u, c) >= 0.82:
                if _card_score(u) > _card_score(c):
                    u["rank"] = c["rank"]
                    by_rank[c["rank"]] = u
                merged = True
                break
        if not merged:
            still_unknown.append(u)

    out = [by_rank[r] for r in sorted(by_rank)] + still_unknown
    return out


def _card_score(card) -> tuple:
    return (len(card["players"]), sum(p["kills"] for p in card["players"]))


def _cards_similarity(left: dict, right: dict) -> float:
    left_names = [p.get("name", "") for p in left.get("players", []) if p.get("name")]
    right_names = [p.get("name", "") for p in right.get("players", []) if p.get("name")]
    if not left_names or not right_names:
        return 0.0
    scores = []
    for name in left_names:
        scores.append(max((_name_similarity(name, other) for other in right_names), default=0.0))
    return sum(scores) / len(scores)


def _team_match_score(names: list, roster: list) -> float:
    if not names or not roster:
        return 0.0
    pairs = []
    for ni, name in enumerate(names):
        for ri, roster_name in enumerate(roster):
            pairs.append((_name_similarity(name, roster_name), ni, ri))
    pairs.sort(reverse=True)
    used_names, used_roster = set(), set()
    total = 0.0
    matched = 0
    for score, ni, ri in pairs:
        if ni in used_names or ri in used_roster:
            continue
        used_names.add(ni)
        used_roster.add(ri)
        total += score
        matched += 1
    if not matched:
        return 0.0
    # Average by OCR names so incomplete game cards can still match, but do not
    # let one strong player on a four-player team look like a perfect match.
    score = total / len(names)
    if len(names) == 1:
        score *= 0.92
    return score


def _repair_card_players_from_roster(card: dict, roster: list) -> None:
    """Use a matched roster to restore player spellings and missing names."""
    players = card.get("players") or []
    roster = [str(name) for name in roster if str(name).strip()]
    if not players or not roster:
        return

    pairs = []
    for pi, player in enumerate(players):
        name = _display_name(player.get("name", ""))
        if not name:
            continue
        for ri, roster_name in enumerate(roster):
            pairs.append((_name_similarity(name, roster_name), pi, ri))
    pairs.sort(reverse=True)

    used_players = set()
    used_roster = set()

    def set_name(pi: int, roster_name: str) -> None:
        old = players[pi].get("name", "")
        if old != roster_name:
            players[pi].setdefault("ocrName", old)
            players[pi]["nameRepaired"] = True
        players[pi]["name"] = roster_name
        players[pi].pop("missingName", None)

    for score, pi, ri in pairs:
        if pi in used_players or ri in used_roster or score < 0.72:
            continue
        set_name(pi, roster[ri])
        used_players.add(pi)
        used_roster.add(ri)

    remaining_players = [idx for idx in range(len(players)) if idx not in used_players]
    remaining_roster = [idx for idx in range(len(roster)) if idx not in used_roster]
    if (remaining_players and len(remaining_players) == len(remaining_roster)
            and len(used_players) >= 2):
        for pi, ri in zip(remaining_players, remaining_roster, strict=True):
            set_name(pi, roster[ri])


def match_cards_to_roster(cards: list, teams: list) -> None:
    """Fuzzy-match each card's players against the event roster and attach
    slot/teamName/matchScore in place. Each slot is used at most once."""
    rosters = []
    for t in teams:
        players = [p for p in t.get("players", []) if p]
        if players:
            rosters.append((int(t["teamId"]),
                            t.get("teamName") or t.get("shortName") or "",
                            players))

    scored = []
    for ci, card in enumerate(cards):
        card["slot"] = None
        card["teamName"] = ""
        card["matchScore"] = 0.0
        names = [_display_name(p["name"]) for p in card["players"] if p.get("name")]
        names = [n for n in names if _looks_like_name(n)]
        if not names:
            continue
        for slot, team_name, roster in rosters:
            score = _team_match_score(names, roster)
            scored.append((score, ci, slot, team_name, roster))

    scored.sort(key=lambda item: item[0], reverse=True)
    used_cards, used_slots = set(), set()
    for score, ci, slot, team_name, roster in scored:
        names_count = len([p for p in cards[ci].get("players", []) if p.get("name")])
        threshold = 0.66 if names_count <= 1 else 0.5
        if score < threshold or ci in used_cards or slot in used_slots:
            continue
        cards[ci]["slot"] = slot
        cards[ci]["teamName"] = team_name
        cards[ci]["matchScore"] = round(score, 2)
        _repair_card_players_from_roster(cards[ci], roster)
        used_cards.add(ci)
        used_slots.add(slot)
