"""Run the OCR accuracy harness over the labelled fixtures.

    python scripts/ocr_bench.py                      # results + roster, local engine
    python scripts/ocr_bench.py --set results -v     # per-fixture failure detail
    python scripts/ocr_bench.py --engine hybrid      # escalate weak cards to Claude
    python scripts/ocr_bench.py --save-baseline      # freeze current numbers

The baseline written by --save-baseline is what tests/test_accuracy.py asserts
against, so a pipeline change that makes things worse fails the test suite.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# IGNs are full of glyphs the Windows console codepage cannot encode
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from tests.accuracy import (  # noqa: E402
    RESULTS_DIR,
    ROSTER_DIR,
    Report,
    load_fixtures,
    score_results_image,
    score_roster_image,
    score_roster_slots,
)

BASELINE_PATH = ROOT / "tests" / "accuracy_baseline.json"


def run_results(engine: str) -> tuple[Report, float]:
    from core.ocr_pipeline import parse_results_for_bench

    total = Report()
    started = time.time()
    for image, expected in load_fixtures(RESULTS_DIR):
        cards = parse_results_for_bench(image, engine=engine)
        total.merge(score_results_image(cards, expected, image.stem))
    return total, time.time() - started


def run_roster(engine: str) -> tuple[Report, float]:
    from core.ocr_pipeline import parse_roster_for_bench

    total = Report()
    started = time.time()
    for image, expected in load_fixtures(ROSTER_DIR):
        cards = parse_roster_for_bench(image, engine=engine)
        total.merge(score_roster_image(cards, expected, image.stem))
        total.merge(score_roster_slots(cards, expected))
    return total, time.time() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", choices=["results", "roster", "all"], default="all")
    parser.add_argument("--engine", choices=["local", "hybrid", "vision"], default="local")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print every per-field mismatch")
    parser.add_argument("--save-baseline", action="store_true",
                        help="write the run to tests/accuracy_baseline.json")
    args = parser.parse_args()

    baseline = {}
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    results = {}
    for name, runner in (("results", run_results), ("roster", run_roster)):
        if args.set not in (name, "all"):
            continue
        report, elapsed = runner(args.engine)
        results[name] = report.as_dict()
        print(f"\n=== {name} ({args.engine} engine, {elapsed:.1f}s) ===")
        print(report.table())
        prev = (baseline.get(args.engine) or {}).get(name)
        if prev:
            print("  --- vs baseline ---")
            for key, value in report.as_dict().items():
                old = prev.get(key)
                if old is None or old == value:
                    continue
                better = value < old if key == "cards_hallucinated" else value > old
                arrow = "+" if better else "-"
                print(f"  {arrow} {key}: {old} -> {value}")
        if args.verbose and report.notes:
            print("  --- detail ---")
            for note in report.notes:
                print(f"    {note}")

    if args.save_baseline:
        baseline[args.engine] = results
        BASELINE_PATH.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
        print(f"\nbaseline written to {BASELINE_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
