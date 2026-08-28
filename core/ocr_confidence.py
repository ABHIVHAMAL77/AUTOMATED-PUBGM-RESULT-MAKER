"""How much to trust one parsed result card.

Both UIs used to decide this with a single literal — `matchScore < 0.7` — which
says nothing about *why* a row is suspect, and misses the failures that have
nothing to do with the roster match: a rank that was guessed from card order
rather than read, a team that came back with one player instead of four, two
cards claiming the same rank.

`card_verdict` returns a score in 0..1 plus the human-readable reasons behind
it, so the review table can explain itself instead of just glowing red.
"""

from __future__ import annotations

# Below this the row is flagged for review.
REVIEW_BELOW = 0.7

# Each rule is (weight, test) — weight is how much confidence it removes.
_MISSING_RANK = 0.55
_MISSING_SLOT = 0.35
_DUPLICATE_RANK = 0.60
_INFERRED_RANK = 0.20
_THIN_CARD = 0.15
_NO_PLAYERS = 0.90


def sequence_problems(cards: list) -> dict:
    """Facts about the card set as a whole, computed once and shared."""
    seen, duplicates = set(), set()
    for card in cards:
        rank = card.get("rank")
        if rank is None:
            continue
        rank = int(rank)
        if rank in seen:
            duplicates.add(rank)
        seen.add(rank)

    missing = sorted(set(range(1, max(seen) + 1)) - seen) if seen else []

    slots, duplicate_slots = set(), set()
    for card in cards:
        slot = card.get("slot")
        if not slot:
            continue
        if slot in slots:
            duplicate_slots.add(slot)
        slots.add(slot)

    return {
        "duplicateRanks": duplicates,
        "duplicateSlots": duplicate_slots,
        "missingRanks": missing,
        "cardCount": len(cards),
    }


def card_verdict(card: dict, context: dict | None = None) -> dict:
    """{"score": float, "reasons": [str], "needsReview": bool} for one card."""
    context = context or {}
    score = 1.0
    reasons = []

    players = [p for p in card.get("players", []) if p.get("name")]
    if not players:
        return {"score": round(1.0 - _NO_PLAYERS, 2),
                "reasons": ["No player names were read."],
                "needsReview": True}

    rank = card.get("rank")
    if not rank:
        score -= _MISSING_RANK
        reasons.append("Rank could not be read — the card was cut off or the "
                       "number was unreadable.")
    elif card.get("rankInferred"):
        score -= _INFERRED_RANK
        reasons.append("Rank was inferred from card order, not read from the screen.")
    elif int(rank) in context.get("duplicateRanks", ()):
        score -= _DUPLICATE_RANK
        reasons.append(f"Another row also claims rank {int(rank)}.")

    match_score = float(card.get("matchScore", 0) or 0)
    if not card.get("slot"):
        score -= _MISSING_SLOT
        reasons.append("No roster team matched these players.")
    else:
        if card.get("slot") in context.get("duplicateSlots", ()):
            score -= _DUPLICATE_RANK
            reasons.append(f"Slot {card['slot']} is used by another row too.")
        # a weak-but-accepted roster match costs proportionally
        if match_score < 0.85:
            penalty = min(0.45, (0.85 - match_score) * 0.9)
            score -= penalty
            reasons.append(
                f"Roster match is only {int(match_score * 100)}% — check the team is right.")

    if len(players) < 3:
        score -= _THIN_CARD
        reasons.append(f"Only {len(players)} player(s) read; PUBGM squads are up to 4.")

    if card.get("source") == "vision":
        reasons.append("Re-read with Claude vision.")

    score = max(0.0, min(1.0, score))
    return {
        "score": round(score, 2),
        "reasons": reasons,
        "needsReview": score < REVIEW_BELOW,
    }
