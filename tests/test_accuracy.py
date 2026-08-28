"""Regression guard on OCR accuracy.

The numbers in tests/accuracy_baseline.json are what the local engine scored
when it was last measured. This test re-measures and fails if any field drops
below its baseline (with a small tolerance, since OCR is deterministic but the
fixture set is small enough that one card swings a percent or two).

Refresh the baseline after a deliberate improvement:

    python scripts/ocr_bench.py --save-baseline
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.accuracy import (
    RESULTS_DIR,
    ROSTER_DIR,
    Report,
    load_fixtures,
    score_results_image,
    score_roster_image,
    score_roster_slots,
)

BASELINE_PATH = Path(__file__).parent / "accuracy_baseline.json"
TOLERANCE = 2.0  # percentage points


def _baseline(section: str) -> dict:
    if not BASELINE_PATH.exists():
        pytest.skip("no accuracy baseline recorded yet "
                    "(run: python scripts/ocr_bench.py --save-baseline)")
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    local = data.get("local") or {}
    if section not in local:
        pytest.skip(f"no baseline for {section}")
    return local[section]


def _assert_not_worse(report: Report, baseline: dict, label: str) -> None:
    got = report.as_dict()
    failures = []
    for key, old in baseline.items():
        new = got[key]
        if key == "cards_hallucinated":
            if new > old:
                failures.append(f"{key}: {old} -> {new} (more junk cards)")
        elif new < old - TOLERANCE:
            failures.append(f"{key}: {old}% -> {new}%")
    assert not failures, (
        f"{label} accuracy regressed:\n  " + "\n  ".join(failures)
        + f"\n\nfull report:\n{report.table()}"
    )


@pytest.mark.slow
def test_results_accuracy_not_worse_than_baseline():
    fixtures = load_fixtures(RESULTS_DIR)
    if not fixtures:
        pytest.skip("no labelled results fixtures")
    from core.ocr_pipeline import parse_results_for_bench

    total = Report()
    for image, expected in fixtures:
        cards = parse_results_for_bench(image, engine="local")
        total.merge(score_results_image(cards, expected, image.stem))

    print("\nresults accuracy:\n" + total.table())
    _assert_not_worse(total, _baseline("results"), "results")


@pytest.mark.slow
def test_roster_accuracy_not_worse_than_baseline():
    fixtures = load_fixtures(ROSTER_DIR)
    if not fixtures:
        pytest.skip("no labelled roster fixtures")
    from core.ocr_pipeline import parse_roster_for_bench

    total = Report()
    for image, expected in fixtures:
        cards = parse_roster_for_bench(image, engine="local")
        total.merge(score_roster_image(cards, expected, image.stem))
        total.merge(score_roster_slots(cards, expected))

    print("\nroster accuracy:\n" + total.table())
    _assert_not_worse(total, _baseline("roster"), "roster")


def test_vision_is_optional():
    """The whole pipeline must work with no API key configured."""
    import core.ocr_vision as vision
    from core.ocr_pipeline import resolve_mode

    if not vision.available():
        assert resolve_mode("hybrid") == "local"
        assert resolve_mode("vision") == "local"
    assert resolve_mode("local") == "local"
    assert resolve_mode("nonsense") == "local"
