"""Single entry point both UIs use to turn screenshots into review rows.

The desktop app and the web app used to each carry their own copy of "parse
every file, merge, match the roster, shape rows, collect problems". They drifted.
Everything lives here now; `web_app.py` and `app.py` are thin callers.

Engine modes:
    local   RapidOCR only. Offline, free, and the default. Needs no account,
            no API key and no internet; nothing ever leaves the machine.
    hybrid  RapidOCR, then re-read only the cards the confidence model
            distrusts with Claude vision. Opt-in, costs money per screenshot.
    vision  Claude vision for every screenshot, RapidOCR as the fallback.

The paid modes exist for lobbies full of non-Latin team names, where a Latin
OCR model genuinely cannot help. They are never the default: this tool has to
work for a buyer who has no API account and never intends to get one, so the
free path is the one that runs unless somebody deliberately asks otherwise.
"""

from __future__ import annotations

import os
from pathlib import Path

from .ocr_confidence import card_verdict, sequence_problems
from .ocr_results import (
    match_cards_to_roster,
    merge_result_cards,
    parse_results_screenshot,
)
from .ocr_roster import parse_slot_screenshot, suggest_tag

MODES = ("local", "hybrid", "vision")
DEFAULT_MODE = os.environ.get("OCR_ENGINE", "local")


def resolve_mode(mode: str | None = None) -> str:
    """The mode we can actually run, given what is configured."""
    mode = (mode or DEFAULT_MODE or "local").lower()
    if mode not in MODES:
        mode = "local"
    if mode == "local":
        return "local"
    from . import ocr_vision
    return mode if ocr_vision.available() else "local"


def engine_status() -> dict:
    """What the UI shows so the operator knows which engine will run."""
    from . import ocr_vision
    requested = (DEFAULT_MODE or "local").lower()
    return {
        "requested": requested if requested in MODES else "local",
        "effective": resolve_mode(),
        "visionAvailable": ocr_vision.available(),
        "visionModel": ocr_vision.MODEL,
    }


# --------------------------------------------------------------------------
# results screenshots
# --------------------------------------------------------------------------

def run_results_ocr(paths, teams, mode: str | None = None) -> dict:
    """Parse result screenshots into review rows.

    Returns {"rows", "cards", "errors", "problems", "engineUsed"}. Rows are the
    shape the review tables render; cards keep the raw parse for re-scoring
    after the operator edits something.
    """
    mode = resolve_mode(mode)
    per_shot, errors, escalated = [], [], 0

    for path in paths:
        try:
            if mode == "vision":
                cards, used_vision = _vision_first(path)
                escalated += 1 if used_vision else 0
            else:
                cards = parse_results_screenshot(path)
            per_shot.append(cards)
        except Exception as exc:                       # noqa: BLE001 - surfaced to the operator
            errors.append(f"{Path(path).name}: {exc}")

    cards = merge_result_cards(per_shot)
    match_cards_to_roster(cards, teams)

    if mode == "hybrid":
        cards, escalated, vision_errors = _escalate_weak_cards(paths, cards, teams)
        errors.extend(vision_errors)

    rows = build_rows(cards)
    problems = collect_problems(rows, errors)
    return {
        "rows": rows,
        "cards": cards,
        "errors": errors,
        "problems": problems,
        "engineUsed": mode,
        "escalatedCards": escalated,
    }


def build_rows(cards: list) -> list:
    """Cards -> review-table rows, sorted by rank with unranked cards last."""
    rows = []
    ordered = sorted(cards, key=lambda c: (c.get("rank") is None, c.get("rank") or 99))
    verdicts = score_cards(ordered)
    for idx, (card, verdict) in enumerate(zip(ordered, verdicts, strict=True), start=1):
        players = [
            {"name": p.get("name", ""), "kills": int(p.get("kills", 0) or 0)}
            for p in card.get("players", [])
        ]
        rows.append({
            "rank": card.get("rank") or "",
            "slot": card.get("slot") or "",
            "teamName": card.get("teamName") or "",
            "kills": sum(p["kills"] for p in players),
            "matchScore": float(card.get("matchScore", 0) or 0),
            "players": players,
            "confidence": verdict["score"],
            "confidenceReasons": verdict["reasons"],
            "needsReview": verdict["needsReview"],
            "source": card.get("source", "local"),
            "sourceOrder": idx,
        })
    return rows


def score_cards(cards: list) -> list:
    """Confidence verdict per card, aware of the whole set (duplicate ranks,
    gaps in the rank sequence) rather than each card in isolation."""
    context = sequence_problems(cards)
    return [card_verdict(card, context) for card in cards]


def collect_problems(rows: list, errors: list) -> list:
    problems = []
    if any(not row["rank"] for row in rows):
        problems.append("Some rows need a rank.")
    if any(not row["slot"] for row in rows):
        problems.append("Some rows need a slot.")
    if any(row["needsReview"] for row in rows):
        low = sum(1 for row in rows if row["needsReview"])
        problems.append(f"{low} row(s) are low confidence — check them before saving.")

    ranks = [int(row["rank"]) for row in rows if row["rank"]]
    if ranks:
        missing = sorted(set(range(1, max(ranks) + 1)) - set(ranks))
        if missing:
            preview = ", ".join(str(m) for m in missing[:10])
            problems.append(
                f"Missing rank(s): {preview} — load the screenshot page that shows them.")
    problems.extend(errors)
    return problems


# --------------------------------------------------------------------------
# roster screenshots
# --------------------------------------------------------------------------

def run_roster_ocr(paths, mode: str | None = None) -> dict:
    """Parse lobby screenshots into {"cards", "errors"} where each card is
    {"slot", "players", "tag", "confidence"}."""
    mode = resolve_mode(mode)
    cards, errors = [], []
    for path in paths:
        try:
            if mode == "vision":
                parsed = _vision_roster(path)
            else:
                parsed = parse_slot_screenshot(path)
            cards.extend(parsed)
        except Exception as exc:                       # noqa: BLE001
            errors.append(f"{Path(path).name}: {exc}")

    merged = merge_roster_cards(cards)
    for card in merged:
        card["tag"] = suggest_tag(card.get("players", []))
    return {"cards": merged, "errors": errors, "engineUsed": mode}


def merge_roster_cards(cards: list) -> list:
    """One lobby spans several screenshots; the same slot appears more than
    once. Keep the reading with the most players."""
    by_slot, unknown = {}, []
    for card in cards:
        slot = card.get("slot")
        if slot is None:
            unknown.append(card)
            continue
        current = by_slot.get(slot)
        if current is None or len(card.get("players", [])) > len(current.get("players", [])):
            by_slot[slot] = card
    return [by_slot[s] for s in sorted(by_slot)] + unknown


# --------------------------------------------------------------------------
# vision escalation
# --------------------------------------------------------------------------

def _vision_first(path):
    """Vision mode: Claude reads the screenshot, RapidOCR covers a failure."""
    from . import ocr_vision
    try:
        cards = ocr_vision.read_results_screenshot(path)
        if cards:
            for card in cards:
                card["source"] = "vision"
            return cards, True
    except Exception:                                  # noqa: BLE001 - fall back, never fail the run
        pass
    return parse_results_screenshot(path), False


def _vision_roster(path):
    from . import ocr_vision
    try:
        cards = ocr_vision.read_roster_screenshot(path)
        if cards:
            return cards
    except Exception:                                  # noqa: BLE001
        pass
    return parse_slot_screenshot(path)


def _escalate_weak_cards(paths, cards, teams):
    """Hybrid mode: re-read only the screenshots that produced weak cards.

    Re-running a whole screenshot rather than a cropped card keeps the merge
    logic honest — a card the local pass split in two comes back whole.
    """
    from . import ocr_vision

    verdicts = score_cards(cards)
    if not any(v["needsReview"] for v in verdicts):
        return cards, 0, []

    escalated, errors, vision_shots = 0, [], []
    for path in paths:
        try:
            read = ocr_vision.read_results_screenshot(path)
        except Exception as exc:                       # noqa: BLE001
            errors.append(f"{Path(path).name}: vision pass failed ({exc})")
            continue
        if read:
            for card in read:
                card["source"] = "vision"
            vision_shots.append(read)
            escalated += 1

    if not vision_shots:
        return cards, 0, errors

    # vision cards win ties in the merge because they carry more complete rows
    merged = merge_result_cards(vision_shots + [cards])
    match_cards_to_roster(merged, teams)
    return merged, escalated, errors


# --------------------------------------------------------------------------
# benchmark hooks (used by scripts/ocr_bench.py and tests/test_accuracy.py)
# --------------------------------------------------------------------------

def parse_results_for_bench(path, engine: str = "local") -> list:
    """One screenshot, no merging, no roster matching — raw parser accuracy."""
    if resolve_mode(engine) in ("vision", "hybrid"):
        cards, _ = _vision_first(path)
        return cards
    return parse_results_screenshot(path)


def parse_roster_for_bench(path, engine: str = "local") -> list:
    if resolve_mode(engine) in ("vision", "hybrid"):
        return _vision_roster(path)
    return parse_slot_screenshot(path)
