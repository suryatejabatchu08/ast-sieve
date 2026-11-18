#!/usr/bin/env python3
"""Score AST-Sieve against demo-messy-repo/expected.json (precision, recall, F1)."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from ast_sieve.engine import scan

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "demo-messy-repo"


def expected_set(online: bool) -> set[tuple[str, str, int]]:
    """Ground-truth (file, rule, line) triples; online mode uses the upgraded rule."""
    data = json.loads((BENCH / "expected.json").read_text(encoding="utf-8"))
    return {
        (e["file"], e.get("online_rule", e["rule"]) if online else e["rule"], e["line"])
        for e in data["findings"]
    }


def score(online: bool, min_confidence: float) -> dict[str, object]:
    """Run the scanner on the benchmark and compare with ground truth."""
    truth = expected_set(online)
    found = {
        (f.file, f.rule, f.start_line)
        for f in scan(BENCH, online=online)
        if f.confidence >= min_confidence
    }
    tp, fp, fn = truth & found, found - truth, truth - found
    precision = len(tp) / len(found) if found else 0.0
    recall = len(tp) / len(truth) if truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if tp else 0.0
    return {"tp": sorted(tp), "fp": sorted(fp), "fn": sorted(fn),
            "precision": precision, "recall": recall, "f1": f1}


def per_rule(result: dict[str, object]) -> dict[str, list[int]]:
    """Counts of [tp, fp, fn] for each rule."""
    table: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
    for index, key in enumerate(("tp", "fp", "fn")):
        for _, rule, _ in result[key]:  # type: ignore[attr-defined]
            table[rule][index] += 1
    return dict(sorted(table.items()))


def main() -> int:
    """CLI entry point; exits 1 when thresholds are not met."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="include registry checks (DEP001)")
    parser.add_argument("--min-confidence", type=float, default=0.4)
    parser.add_argument("--min-recall", type=float, default=0.0)
    parser.add_argument("--min-precision", type=float, default=0.0)
    parser.add_argument("--json", action="store_true", help="print machine-readable result")
    args = parser.parse_args()
    result = score(args.online, args.min_confidence)
    if args.json:
        sys.stdout.write(json.dumps(result, indent=2) + "\n")
    else:
        sys.stdout.write(
            f"precision {result['precision']:.3f}  recall {result['recall']:.3f}  "
            f"f1 {result['f1']:.3f}  (tp {len(result['tp'])}, fp {len(result['fp'])}, "  # type: ignore[arg-type]
            f"fn {len(result['fn'])})\n"  # type: ignore[arg-type]
        )
        for rule, (tp, fp, fn) in per_rule(result).items():
            sys.stdout.write(f"  {rule}: tp {tp} fp {fp} fn {fn}\n")
        for label in ("fp", "fn"):
            for item in result[label]:  # type: ignore[attr-defined]
                sys.stdout.write(f"  {label.upper()}: {item}\n")
    ok = result["recall"] >= args.min_recall and result["precision"] >= args.min_precision  # type: ignore[operator]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
