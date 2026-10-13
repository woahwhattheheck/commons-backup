# SPDX-License-Identifier: MIT
"""Reject seven broken corpus/oracle variants with the same real test suite."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
MUTANTS = {
    "skip_dependency_pin": ("if git_blob(data) != ENGINE_PINS[name]:", "if False:"),
    "compact_raw_market_slots": (
        '"hands": [], "market": copy.deepcopy(spec.get("own" if who == seat else "rival", []))}',
        '"hands": [], "market": copy.deepcopy([o for o in spec.get("own" if who == seat else "rival", []) if o])}'),
    "physical_fill_is_admitted_flow": (
        'change = market["inventory"][item] - old[item]',
        'change = 1 if op == "SELL" else -1'),
    "charge_all_commits_to_seat_zero": ('who = private_ids[id(private)]', 'who = 0'),
    "consume_using_next_step": ('result = original_town(e, s, step)',
                               'result = original_town(e, s, step + 1)'),
    "suppress_town_truth": ('town_delta[p] += s[0].observation.market["inventory"][p] - old[p]',
                            'town_delta[p] += 0'),
    "leak_rival_private_to_candidate": (
        'current = copy.deepcopy(state[seat].observation)',
        'current = copy.deepcopy(state[seat].observation)\n'
        '    current["rival_private"] = copy.deepcopy(state[1-seat].observation.private)'),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    source = (HERE / "flow_engine_corpus.py").read_text(encoding="utf-8")
    test = (HERE / "test_flow_engine_corpus.py").read_bytes()
    rows = []
    for optimized in (False, True):
        for name, (old, new) in MUTANTS.items():
            if source.count(old) != 1:
                raise ValueError(f"mutation seam drift: {name}")
            with tempfile.TemporaryDirectory(prefix="flow-mutant-") as temp:
                root = Path(temp)
                (root / "flow_engine_corpus.py").write_text(source.replace(old, new), encoding="utf-8")
                (root / "test_flow_engine_corpus.py").write_bytes(test)
                command = [sys.executable] + (["-O"] if optimized else []) + [str(root / "test_flow_engine_corpus.py")]
                run = subprocess.run(command, cwd=root, env=dict(os.environ,
                    FLOW_ENGINE_DIR=str(args.engine.resolve())), capture_output=True, timeout=30)
                output = run.stdout + run.stderr
                # Syntax/import failures are NOT evidence that an assertion found
                # the injected semantic defect. Require an executed unittest failure.
                detected = run.returncode != 0 and b"FAILED (" in output and b"SyntaxError" not in output
                rows.append({"mutant": name, "optimized": optimized, "detected": detected,
                             "returncode": run.returncode,
                             "log_sha256": hashlib.sha256(output).hexdigest(),
                             "log": output.decode("utf-8", errors="replace")})
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump({"controls": rows}, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({"controls": len(rows), "detected": sum(r["detected"] for r in rows)}, sort_keys=True))
    return 0 if all(r["detected"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
