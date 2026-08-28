"""Scoring harness for the OCR pipeline.

Loads labelled screenshots from tests/fixtures/, runs a parse function over
them, and reports per-field accuracy so a pipeline change can be measured
instead of eyeballed.

Fixture layout:
    tests/fixtures/results/<name>.png
    tests/fixtures/results/<name>.expected.json
    tests/fixtures/roster/<name>.png
    tests/fixtures/roster/<name>.expected.json

A results fixture holds the cards a human can read off that one screenshot:

    {"partial_ranks": [16],
     "cards": [{"rank": 17, "players": [{"name": "...", "kills": 2}, ...]}]}

`partial_ranks` are cards clipped by the screen edge. The parser is free to
emit them or not — they are neither rewarded nor punished, because the
neighbouring screenshot carries the complete version and `merge_result_cards`
picks that one.

Names are scored two ways. `name_exact` compares the ASCII-folded string, which
is what a Latin OCR model can realistically hope to produce; PUBGM IGNs are
full of glyphs no Latin model has ever seen. `name_close` is the fuzzy score
the roster matcher itself uses (>= 0.72 counts as a hit), which is what
actually decides whether a card lands on the right team.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
RESULTS_DIR = FIXTURES / "results"
ROSTER_DIR = FIXTURES / "roster"

# a fuzzy name score at or above this is "the operator would not have to retype it"
NAME_CLOSE = 0.72


def _fold(text: str) -> str:
    """Lowercase ASCII skeleton of a name, for exact comparison."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = text.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _similarity(left: str, right: str) -> float:
    from core.ocr_results import _name_similarity
    return _name_similarity(left, right)


@dataclass
class Counter:
    hit: int = 0
    total: int = 0

    def add(self, ok: bool) -> None:
        self.total += 1
        self.hit += 1 if ok else 0

    @property
    def pct(self) -> float:
        return 100.0 * self.hit / self.total if self.total else 100.0

    def __str__(self) -> str:
        return f"{self.pct:5.1f}%  ({self.hit}/{self.total})"


@dataclass
class Report:
    """Per-field tallies across every fixture in a run."""

    rank: Counter = field(default_factory=Counter)
    name_exact: Counter = field(default_factory=Counter)
    name_close: Counter = field(default_factory=Counter)
    kills: Counter = field(default_factory=Counter)
    roster_slot: Counter = field(default_factory=Counter)
    cards_found: Counter = field(default_factory=Counter)
    cards_hallucinated: int = 0
    notes: list = field(default_factory=list)

    def merge(self, other: Report) -> None:
        for name in ("rank", "name_exact", "name_close", "kills",
                     "roster_slot", "cards_found"):
            mine, theirs = getattr(self, name), getattr(other, name)
            mine.hit += theirs.hit
            mine.total += theirs.total
        self.cards_hallucinated += other.cards_hallucinated
        self.notes.extend(other.notes)

    def as_dict(self) -> dict:
        return {
            "cards_found": round(self.cards_found.pct, 1),
            "cards_hallucinated": self.cards_hallucinated,
            "rank": round(self.rank.pct, 1),
            "name_exact": round(self.name_exact.pct, 1),
            "name_close": round(self.name_close.pct, 1),
            "kills": round(self.kills.pct, 1),
            "roster_slot": round(self.roster_slot.pct, 1),
        }

    def table(self) -> str:
        rows = [
            ("cards found", str(self.cards_found)),
            ("cards hallucinated", str(self.cards_hallucinated)),
            ("rank correct", str(self.rank)),
            ("name exact (ascii)", str(self.name_exact)),
            (f"name close (>={NAME_CLOSE})", str(self.name_close)),
            ("kills correct", str(self.kills)),
            ("roster slot correct", str(self.roster_slot)),
        ]
        width = max(len(label) for label, _ in rows)
        return "\n".join(f"  {label.ljust(width)}  {value}" for label, value in rows)


def load_fixtures(directory: Path) -> list:
    """[(image_path, expected_dict), ...] sorted by name."""
    out = []
    for expected_path in sorted(directory.glob("*.expected.json")):
        stem = expected_path.name[: -len(".expected.json")]
        for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            image = directory / f"{stem}{ext}"
            if image.exists():
                out.append((image, json.loads(expected_path.read_text(encoding="utf-8"))))
                break
    return out


def _match_players(got: list, want: list, report: Report, where: str) -> None:
    """Greedy best-first pairing of parsed players against expected ones."""
    pairs = []
    for gi, g in enumerate(got):
        for wi, w in enumerate(want):
            pairs.append((_similarity(g.get("name", ""), w["name"]), gi, wi))
    pairs.sort(key=lambda p: -p[0])

    used_got, used_want = set(), set()
    for score, gi, wi in pairs:
        if gi in used_got or wi in used_want:
            continue
        used_got.add(gi)
        used_want.add(wi)
        g, w = got[gi], want[wi]
        exact = _fold(g.get("name", "")) == _fold(w["name"])
        close = score >= NAME_CLOSE
        report.name_exact.add(exact)
        report.name_close.add(close)
        report.kills.add(int(g.get("kills", -1)) == int(w["kills"]))
        if not close:
            report.notes.append(
                f"{where}: name {g.get('name','')!r} != {w['name']!r} (score {score:.2f})")
        elif int(g.get("kills", -1)) != int(w["kills"]):
            report.notes.append(
                f"{where}: {w['name']!r} kills {g.get('kills')} != {w['kills']}")

    # expected players the parser never produced
    for wi, w in enumerate(want):
        if wi in used_want:
            continue
        report.name_exact.add(False)
        report.name_close.add(False)
        report.kills.add(False)
        report.notes.append(f"{where}: missing player {w['name']!r}")


def score_results_image(cards: list, expected: dict, label: str) -> Report:
    """Score one results screenshot's parsed cards against its labels."""
    report = Report()
    partial = set(expected.get("partial_ranks", []))
    want_cards = expected["cards"]
    by_rank = {}
    unranked = []
    for c in cards:
        if c.get("rank") is None:
            unranked.append(c)
        else:
            by_rank.setdefault(int(c["rank"]), c)

    matched_ids = set()
    for want in want_cards:
        rank = want["rank"]
        got = by_rank.get(rank)
        if got is None:
            # the players may still be there under a wrong/missing rank
            got = _best_unranked(unranked + list(by_rank.values()), want, matched_ids)
            report.rank.add(False)
        else:
            report.rank.add(True)
        if got is None:
            report.cards_found.add(False)
            for _ in want["players"]:
                report.name_exact.add(False)
                report.name_close.add(False)
                report.kills.add(False)
            report.notes.append(f"{label}: card rank {rank} not found at all")
            continue
        matched_ids.add(id(got))
        report.cards_found.add(True)
        _match_players(got.get("players", []), want["players"], report,
                       f"{label} rank {rank}")

    # anything the parser produced that is neither an expected card nor a
    # known edge-clipped card is a hallucination
    expected_ranks = {c["rank"] for c in want_cards}
    for c in cards:
        if id(c) in matched_ids:
            continue
        rank = c.get("rank")
        if rank is not None and (int(rank) in partial or int(rank) in expected_ranks):
            continue
        if rank is None and _looks_like_partial(c, want_cards):
            continue
        report.cards_hallucinated += 1
        names = ", ".join(p.get("name", "") for p in c.get("players", []))
        report.notes.append(f"{label}: extra card rank={rank} ({names})")
    return report


def _best_unranked(candidates: list, want: dict, taken: set):
    from core.ocr_results import _cards_similarity
    best, best_score = None, 0.0
    for c in candidates:
        if id(c) in taken:
            continue
        score = _cards_similarity(c, want)
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= 0.6 else None


def _looks_like_partial(card: dict, want_cards: list) -> bool:
    """A rank-less card whose players belong to an expected card is just the
    same card read without its number — not an invented one."""
    from core.ocr_results import _cards_similarity
    return any(_cards_similarity(card, w) >= 0.6 for w in want_cards)


def score_roster_image(cards: list, expected: dict, label: str) -> Report:
    """Score one lobby screenshot. Roster cards have slots, not ranks, and
    plain string players with no kill counts."""
    report = Report()
    partial = set(expected.get("partial_slots", []))
    want_cards = expected["cards"]
    by_slot = {}
    for c in cards:
        if c.get("slot") is not None:
            by_slot.setdefault(int(c["slot"]), c)

    matched_ids = set()
    for want in want_cards:
        slot = want["slot"]
        got = by_slot.get(slot)
        want_players = [{"name": n, "kills": 0} for n in want["players"]]
        if got is None:
            got = _best_unranked(
                [{"players": [{"name": n, "kills": 0} for n in c.get("players", [])],
                  "_src": c}
                 for c in cards if id(c) not in matched_ids],
                {"players": want_players}, matched_ids)
            report.rank.add(False)
        else:
            report.rank.add(True)
        if got is None:
            report.cards_found.add(False)
            for _ in want["players"]:
                report.name_exact.add(False)
                report.name_close.add(False)
            report.notes.append(f"{label}: slot {slot} not found at all")
            continue
        matched_ids.add(id(got.get("_src", got)))
        report.cards_found.add(True)
        got_players = got.get("players", [])
        if got_players and isinstance(got_players[0], str):
            got_players = [{"name": n, "kills": 0} for n in got_players]
        # roster screens carry no kill counts; keep the kills counter untouched
        before = (report.kills.hit, report.kills.total)
        _match_players(got_players, want_players, report, f"{label} slot {slot}")
        report.kills.hit, report.kills.total = before

    expected_slots = {c["slot"] for c in want_cards}
    for c in cards:
        if id(c) in matched_ids:
            continue
        slot = c.get("slot")
        if slot is not None and (int(slot) in partial or int(slot) in expected_slots):
            continue
        report.cards_hallucinated += 1
        report.notes.append(
            f"{label}: extra card slot={slot} ({', '.join(map(str, c.get('players', [])))})")
    return report


def score_roster_slots(cards: list, expected: dict) -> Report:
    """Slot-number accuracy alone, keyed by player set rather than by slot."""
    report = Report()
    for want in expected["cards"]:
        want_players = {"players": [{"name": n, "kills": 0} for n in want["players"]]}
        got = _best_unranked(
            [{"players": [{"name": n, "kills": 0} for n in c.get("players", [])],
              "_slot": c.get("slot")} for c in cards],
            want_players, set())
        report.roster_slot.add(got is not None and got.get("_slot") == want["slot"])
    return report
