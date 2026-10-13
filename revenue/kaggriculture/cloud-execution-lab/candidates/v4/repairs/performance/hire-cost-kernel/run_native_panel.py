# SPDX-License-Identifier: Apache-2.0
"""Reproduce or verify the fixed 16-pair, 32-game offline native panel."""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import native_gate

SEEDS = (9600911, 9600912)
SEATS = (0, 1)
OPPONENTS = ("starter", "pass")
MODES = ("normal", "optimized")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    for root in (args.baseline, args.candidate):
        native_gate.authenticate(root.resolve(), args.source_map)
    if not args.check_only:
        args.output.mkdir(parents=True, exist_ok=False)
    driver = Path(__file__).with_name("native_gate.py")
    pairs, sources = [], []
    for mode, seed, seat, opponent in itertools.product(MODES, SEEDS, SEATS, OPPONENTS):
        prefix = f"{mode}-{seed}-{seat}-{opponent}"
        python = [sys.executable] + (["-O"] if mode == "optimized" else [])
        reports = []
        for arm, root in (("baseline", args.baseline), ("candidate", args.candidate)):
            path = args.output / f"{prefix}-{arm}.json"
            reports.append(path)
            if not args.check_only:
                command = python + [str(driver), "worker", "--runtime", str(root.resolve()),
                                     "--source-map", str(args.source_map.resolve()), "--seed", str(seed),
                                     "--seat", str(seat), "--opponent", opponent, "--output", str(path)]
                run = subprocess.run(command, capture_output=True, text=True, timeout=30)
                path.with_suffix(".log").write_text(run.stdout + run.stderr)
                if run.returncode:
                    raise RuntimeError("native worker failed: " + str(path))
            raw = path.read_bytes()
            record = json.loads(raw)
            if record["status"] != {"completed": 719} or record["final_status"] != ["DONE", "DONE"]:
                raise RuntimeError("incomplete native report: " + str(path))
            if (record["seed"], record["seat"], record["opponent"]) != (seed, seat, opponent):
                raise RuntimeError("mislabeled native report")
            expected = native_gate.MECHANICS_SHA[0 if arm == "baseline" else 1]
            if record["mechanics_sha256"] != expected or record["authenticated_files"] != 109:
                raise RuntimeError("native source identity mismatch")
            sources.append({"file": path.name, "sha256": hashlib.sha256(raw).hexdigest()})
        native_gate.compare(reports)
        a = json.loads(reports[0].read_text())
        pairs.append({"mode": mode, "seed": seed, "seat": seat, "opponent": opponent,
                      "frames": a["steps"], "fib_calls_per_arm": a["kernel_calls"]["_fib"],
                      "extra_hand_rows_per_arm": a["raw_extra_hand_rows"], "scores": a["scores"],
                      "action_tape_sha256": a["action_tape_sha256"],
                      "state_tape_sha256": a["state_tape_sha256"]})
    for seed, seat, opponent, arm in itertools.product(SEEDS, SEATS, OPPONENTS, ("baseline", "candidate")):
        a = args.output / f"normal-{seed}-{seat}-{opponent}-{arm}.json"
        b = args.output / f"optimized-{seed}-{seat}-{opponent}-{arm}.json"
        native_gate.compare([a, b])
    summary = {"schema": "titan.v4.hire-cost.native-panel.v1", "games": len(sources),
               "paired_games": len(pairs), "native_callbacks_all_arms": sum(p["frames"] for p in pairs) * 2,
               "paired_frames": sum(p["frames"] for p in pairs), "all_pairs_equal": True,
               "cross_mode_equal": True, "fallbacks": 0, "pairs": pairs, "reports": sources}
    with (args.output / "SUMMARY.json").open("x") as stream:
        json.dump(summary, stream, indent=2); stream.write("\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("pairs", "reports")}))


if __name__ == "__main__":
    main()
