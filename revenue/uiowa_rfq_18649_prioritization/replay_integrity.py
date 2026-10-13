#!/usr/bin/env python3
"""Reproduce UIOWA-084's integrity repair and synthetic decision change offline."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import io
import json
import random
import sys
import tempfile
from pathlib import Path

import prioritize

HERE = Path(__file__).resolve().parent
BASELINE_BLOB = "007697dd2485f7470107d1962c8f660873b4dd84"
FIXTURE_BLOBS = {
    "recommendations.synthetic.csv": "2fa2751292642124d323525a6c5f84ca1f74aad5",
    "weights.json": "6e699f243338df7477519c48592c4f8b8eb784b8",
}


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def replay(baseline_path: Path, out: Path) -> dict:
    baseline_bytes = baseline_path.read_bytes()
    require(git_blob(baseline_bytes) == BASELINE_BLOB, "baseline does not match the retained Git blob")
    for name, digest in FIXTURE_BLOBS.items():
        require(git_blob((HERE / name).read_bytes()) == digest, f"synthetic fixture changed: {name}")
    require(not out.exists() and not out.is_symlink(), "choose a fresh output directory")
    spec = importlib.util.spec_from_file_location("uiowa084_retained_baseline", baseline_path)
    require(spec is not None and spec.loader is not None, "cannot load retained baseline")
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    config = prioritize.load_weights(HERE / "weights.json")
    records = prioritize.load_recommendations(HERE / "recommendations.synthetic.csv")
    rng = random.Random(20260919)
    for case in range(250):
        items = copy.deepcopy(records)
        for item in items:
            for dimension in (*prioritize.DIMENSIONS, "complexity"):
                item[dimension] = None if rng.randrange(10) == 0 else rng.randrange(501) / 100
        weights = config["profiles"][rng.choice(list(config["profiles"]))]
        epsilon = rng.choice([0, 0.02, 0.1, 1, 4])
        require(old.rank_profile(items, "equivalence", weights, epsilon) ==
                prioritize.rank_profile(items, "equivalence", weights, epsilon),
                f"ranking changed in seeded case {case}")
    with tempfile.TemporaryDirectory(prefix="uiowa084-reference-") as temp:
        temp = Path(temp)
        original = old.run(HERE / "recommendations.synthetic.csv", HERE / "weights.json", temp / "old")
        repaired = prioritize.run(HERE / "recommendations.synthetic.csv", HERE / "weights.json", temp / "new")
        require(original == repaired, "original fixture rows changed")
        original_outputs = {path.name: path.read_bytes() for path in (temp / "old").iterdir()}
        require(len(original_outputs) == 7, "unexpected baseline output count")
        require(all((temp / "new" / name).read_bytes() == data for name, data in original_outputs.items()),
                "original exported bytes changed")
    # Only now create persistent demonstration artifacts, all with exclusive paths.
    out.mkdir(parents=True, exist_ok=False)
    rows = list(csv.reader(io.StringIO((HERE / "recommendations.synthetic.csv").read_text(encoding="utf-8"), newline="")))
    for row in rows[1:]:
        if row[0] == "R006":
            row[3] = "5"
            row[-1] = "SYNTHETIC WHAT-IF: security effect assumed 5; not observed evidence"
    changed = out / "security_assumption.synthetic.csv"
    with changed.open("x", encoding="utf-8", newline="") as stream:
        csv.writer(stream).writerows(rows)
    before = prioritize.run(HERE / "recommendations.synthetic.csv", HERE / "weights.json", out / "baseline")
    after = prioritize.run(changed, HERE / "weights.json", out / "security_assumption")
    table = []
    for name in config["profiles"]:
        old_row = next(row for row in before[name] if row["id"] == "R006")
        new_row = next(row for row in after[name] if row["id"] == "R006")
        require(old_row["status"] == "HOLD_MISSING_ESTIMATE" and old_row["priority_score"] is None,
                "missing estimate lost its HOLD")
        table.append({"profile": name, "before_status": old_row["status"],
                      "after_rank": new_row["rank"], "after_score": new_row["priority_score"],
                      "leaders_before": [row["id"] for row in before[name] if row["rank"] == 1],
                      "leaders_after": [row["id"] for row in after[name] if row["rank"] == 1]})
    receipt = {"provenance": "SYNTHETIC PLANNING EXPERIMENT; no University findings or decisions",
               "seed": 20260919, "seeded_comparisons_passed": 250,
               "unchanged_profile_record_rows": sum(map(len, before.values())),
               "unchanged_output_files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(original_outputs.items())},
               "baseline_blob": BASELINE_BLOB,
               "tested_source_blob": git_blob((HERE / "prioritize.py").read_bytes()),
               "python": sys.version, "optimized": bool(sys.flags.optimize), "change": table}
    with (out / "replay_receipt.json").open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print("PASS: 250 seeded comparisons; 35 unchanged profile/record rows; 7 byte-identical original outputs")
    for row in table:
        print(f"{row['profile']}: R006 HOLD -> rank {row['after_rank']}, score {row['after_score']:.4f}")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        replay(args.baseline, args.out)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
