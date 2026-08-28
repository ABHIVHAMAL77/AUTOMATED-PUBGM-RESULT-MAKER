"""Claude vision fallback for screenshots the local engine reads badly.

RapidOCR is a Latin-script model. It does well on plain IGNs and gets the
numbers right most of the time, but it has no chance on the things that
actually cost the operator time: Devanagari and CJK names, heavy decorative
glyphs, and the wide-tracked rank digits whose leading "1" is thinner than the
detector's minimum stroke. Those are exactly what a vision model reads without
effort.

This module is strictly optional. With no ANTHROPIC_API_KEY configured,
`available()` returns False and the pipeline never calls in here — every test
and every offline install keeps working on the local engine alone.

The model's answer is data, not instruction. It comes back through the same
`merge_result_cards` / `match_cards_to_roster` path as a local parse, is scored
by the same confidence model, and is shown to the operator for review before
anything is written to disk.
"""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
from pathlib import Path

log = logging.getLogger(__name__)

MODEL = os.environ.get("OCR_VISION_MODEL", "claude-opus-5")

# One screenshot is ~20 cards of short JSON; this is roomy.
MAX_TOKENS = 8000

# PUBGM screenshots are already inside Claude's 2576px high-resolution limit,
# so they are sent as captured. Anything larger gets scaled down: past the
# limit the image is resampled anyway, and the extra pixels are billed.
MAX_EDGE = 2576

_RESULTS_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rank": {
                        "type": ["integer", "null"],
                        "description": "The placement number on the card. "
                                       "null if it is cut off or unreadable.",
                    },
                    "players": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "The in-game name exactly as "
                                                   "printed, including symbols.",
                                },
                                "kills": {
                                    "type": "integer",
                                    "description": "The eliminations count on "
                                                   "that player's row.",
                                },
                            },
                            "required": ["name", "kills"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["rank", "players"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["cards"],
    "additionalProperties": False,
}

_ROSTER_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slot": {
                        "type": ["integer", "null"],
                        "description": "The slot number in the card's top-left "
                                       "corner. null if unreadable.",
                    },
                    "players": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "In-game names on the card, top to bottom.",
                    },
                },
                "required": ["slot", "players"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["cards"],
    "additionalProperties": False,
}

_RESULTS_PROMPT = """This is the end-of-match results screen from PUBG Mobile.

Read every team card that is visible and return it as structured data.

Layout:
- The LEFT panel holds two cards: the winning team (marked with a crown icon
  and no number) is rank 1, and the team below it is rank 2.
- The RIGHT column is a scrolling list of gold cards. Each has a large rank
  number on its left and up to four player rows. Each row is an in-game name
  on the left and an eliminations count on the right ("3 eliminations").

Rules:
- Transcribe names EXACTLY as printed, including non-Latin scripts, decorative
  symbols, and unusual spacing. Do not translate, transliterate, or tidy them.
- `kills` is the number in that player's own eliminations text, not a team total.
- Cards clipped by the top or bottom edge: include them with whatever rows are
  legible, and set `rank` to null if the number is not fully visible.
- Set `rank` to null rather than guessing. A wrong number is worse than a blank
  one, because the operator can see a blank and cannot see a plausible mistake.
- Do not invent cards, players, or numbers. If a value is unreadable, leave the
  rank null or omit the row."""

_ROSTER_PROMPT = """This is the Observe-lobby team list from PUBG Mobile.

Read every team card that is visible and return it as structured data.

Layout: a grid of dark cards. Each card has a large coloured slot number in its
top-left corner (zero-padded, e.g. "05", "18") and up to four in-game names
listed below it, each with a "/0 Eliminations" counter on the right.

Rules:
- Transcribe names EXACTLY as printed, including non-Latin scripts, decorative
  symbols, and unusual spacing. Do not translate, transliterate, or tidy them.
- Ignore the "/N Eliminations" counters — they are not part of the name.
- This screen is translucent: the live match shows through behind it. Ignore any
  faint, low-contrast text that is not on a card.
- Set `slot` to null rather than guessing at a number you cannot read clearly.
- Do not invent cards or players."""


def available() -> bool:
    """True when a vision pass can actually run."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _client():
    import anthropic
    return anthropic.Anthropic()


def _encode_image(path) -> tuple[str, str]:
    """(base64 data, media type) for one screenshot, downscaled if oversized."""
    path = Path(path)
    media_type = mimetypes.guess_type(path.name)[0] or "image/png"

    from PIL import Image
    with Image.open(path) as im:
        if max(im.size) <= MAX_EDGE:
            return base64.standard_b64encode(path.read_bytes()).decode("ascii"), media_type

        from io import BytesIO
        scale = MAX_EDGE / max(im.size)
        resized = im.convert("RGB").resize(
            (int(im.width * scale), int(im.height * scale)))
        buf = BytesIO()
        resized.save(buf, "PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("ascii"), "image/png"


def _read(path, prompt: str, schema: dict) -> list:
    data, media_type = _encode_image(path)
    response = _client().messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        output_config={"format": {"type": "json_schema", "schema": schema}},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type, "data": data}},
                {"type": "text", "text": prompt},
            ],
        }],
    )

    if response.stop_reason == "refusal":
        raise RuntimeError("the vision model declined to read this screenshot")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("the vision response was cut off — screenshot too dense")

    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        raise RuntimeError("the vision model returned no content")

    log.info("vision read %s: %d input tokens, %d output tokens",
             Path(path).name, response.usage.input_tokens, response.usage.output_tokens)
    return json.loads(text).get("cards", [])


def read_results_screenshot(path) -> list:
    """One results screenshot -> the same card shape parse_results_screenshot
    produces: [{"rank": int|None, "players": [{"name", "kills"}]}]."""
    cards = []
    for card in _read(path, _RESULTS_PROMPT, _RESULTS_SCHEMA):
        players = [
            {"name": str(p.get("name", "")).strip(),
             "kills": max(0, int(p.get("kills", 0) or 0))}
            for p in card.get("players", [])
            if str(p.get("name", "")).strip()
        ][:4]
        if not players:
            continue
        cards.append({"rank": _as_rank(card.get("rank")), "players": players})
    return cards


def read_roster_screenshot(path) -> list:
    """One lobby screenshot -> [{"slot": int|None, "players": [str]}]."""
    cards = []
    for card in _read(path, _ROSTER_PROMPT, _ROSTER_SCHEMA):
        players = [str(p).strip() for p in card.get("players", []) if str(p).strip()][:4]
        if not players:
            continue
        cards.append({"slot": _as_rank(card.get("slot")), "players": players})
    return cards


def _as_rank(value) -> int | None:
    """Range-check whatever the model returned. Same 1..25 bound the local
    parser applies — a lobby never has more slots than that, so anything
    outside it is a misread rather than a real number."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= 25 else None
