# SPDX-License-Identifier: Apache-2.0
"""Reject broken fixture/measurement code by behavioral assertions, not errors."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = ("reachable_goose_setup.py", "run_reachable_goose_gate.py", "test_reachable_goose_setup.py")
MUTANTS = (
    ("care_positive_control_disabled", "reachable_goose_setup.py",
     '    if hour != 21 or not 2 <= day <= 27 or action["farmer"] != ["PASS"]:',
     '    if True:', "test_positive_control_is_distinct_from_source_candidate"),
    ("harvest_orders_mistaken_for_units", "run_reachable_goose_gate.py",
     '        counts["egg_harvested"] += actual_egg_harvest',
     '        counts["egg_harvested"] += int(actual_egg_harvest > 0)',
     "test_candidate_extra_eggs_are_produced_harvested_and_sold"),
    ("terminal_liquidation_omitted", "reachable_goose_setup.py",
     '    if day == 29 and hour == 22:', '    if False and day == 29 and hour == 22:',
     "test_terminal_stock_is_actually_liquidated"),
    ("input_mutation_guard_removed", "run_reachable_goose_gate.py",
     '        if encoded([obs, parent, public_cfg]) != before_args:', '        if False:',
     "test_input_mutation_is_rejected"),
    ("opportunities_never_recorded", "run_reachable_goose_gate.py",
     '    return True, "eligible_before_price"', '    return False, "eligible_before_price"',
     "test_baseline_has_twenty_six_mechanical_opportunities"),
    ("own_cash_mistaken_for_margin", "run_reachable_goose_gate.py",
     '            "delta_margin": candidate["margin"] - base["margin"],',
     '            "delta_margin": candidate["own"] - base["own"],',
     "test_pair_uses_own_minus_rival_not_raw_own_gain"),
)


def execute(directory: Path, root: Path, candidate: Path, optimized: bool, test: str | None) -> dict:
    command = [sys.executable, *( ["-O"] if optimized else []),
               str(directory / "test_reachable_goose_setup.py"),
               "--native-root", str(root), "--candidate", str(candidate)]
    if test:
        command.append("ReachableGoose." + test)
    completed = subprocess.run(command, capture_output=True, text=True, timeout=90)
    output = completed.stdout + completed.stderr
    return {"command": command, "returncode": completed.returncode,
            "log": output, "log_sha256": hashlib.sha256(output.encode()).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-root", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--optimized", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, candidate = args.native_root.resolve(), args.candidate.resolve()
    baseline = execute(HERE, root, candidate, args.optimized, None)
    if baseline["returncode"] != 0 or not re.search(r"Ran 26 tests.*\n\nOK\s*$", baseline["log"], re.S):
        raise RuntimeError("Unmodified test gate is not green; mutation credit forbidden")
    results = []
    for name, filename, old, new, test in MUTANTS:
        with tempfile.TemporaryDirectory(prefix="reachable-goose-mutation-") as tmp:
            folder = Path(tmp)
            for member in FILES:
                shutil.copyfile(HERE / member, folder / member)
            path = folder / filename
            text = path.read_text(encoding="utf-8")
            if text.count(old) != 1:
                raise RuntimeError(f"Mutant source anchor drift: {name}")
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
            result = execute(folder, root, candidate, args.optimized, test)
            # An import failure, environment error or test error is NOT a kill.
            rejected = (result["returncode"] == 1
                        and re.search(r"FAILED \(failures=[1-9][0-9]*\)\s*$", result["log"]) is not None
                        and "ERROR:" not in result["log"] and "skipped=" not in result["log"])
            results.append({"mutant": name, "target_test": test,
                            "assertion_rejected": rejected, **result})
            print(f"{name}: {'ASSERTION_REJECTED' if rejected else 'NOT_REJECTED'}", flush=True)
    payload = {"schema": "titan-v4-reachable-goose-mutations/v1", "optimized": args.optimized,
               "baseline": baseline, "mutants": results,
               "assertion_rejections": sum(r["assertion_rejected"] for r in results),
               "infrastructure_error_credit": False,
               "source_sha256": {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in FILES}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0 if all(r["assertion_rejected"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
