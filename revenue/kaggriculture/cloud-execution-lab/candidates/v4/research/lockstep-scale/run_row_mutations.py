"""Behavioral mutation controls for the row-intervention experiment, not gameplay.

Each deliberately broken runner executes unchanged targeted unittest assertions
in a fresh child process. An exception/import failure is NOT accepted as a kill.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
MUTATIONS = (
    ("market-only-surrogate-skips-town-and-eod",
     '        engine.interpreter(state, env)\n        trace.append',
     '        engine._process_market(state, env)\n        trace.append',
     "test_24_native_product_empty_row0_horizon_can_lose"),
    ("own-only-margin", '"delta_margin": do - dr,', '"delta_margin": do,',
     "test_01_actual_dump_collateral_loss_both_seats"),
    ("compact-raw-empty-slots", 's.action = copy.deepcopy(ours if i == seat else theirs)',
     's.action = copy.deepcopy(ours if i == seat else theirs)\n            s.action["market"] = [o for o in s.action["market"] if o]',
     "test_04_existing_vacant_raw_slot_retains_collateral_pairing"),
    ("ignore-official-row-cap", 'cfg.update(seed=case["seed"], maxMarketOrdersPerTurn=case["max_orders"])',
     'cfg.update(seed=case["seed"], maxMarketOrdersPerTurn=100)',
     "test_09_raw_capped_suffix_is_not_executed"),
    ("shift-action-clock", 's.observation.step = case["start_step"] + offset',
     's.observation.step = case["start_step"] + offset + 1',
     "test_10_complete_interpreter_runs_town_on_the_actual_action_step"),
    ("swap-cash-role-order", 'cash = [farms[i].pop("money") for i in order]',
     'cash = [farms[i].pop("money") for i in reversed(order)]',
     "test_01_actual_dump_collateral_loss_both_seats"),
    ("erase-effects-with-equal-assets", '"delta_own": do, "delta_rival": dr, "delta_margin": do - dr,',
     '"delta_own": 0, "delta_rival": 0, "delta_margin": 0,',
     "test_06_terminal_asset_identity_does_not_imply_zero_cash_effect"),
    ("discard-rival-incumbent-orders", 's.action = copy.deepcopy(ours if i == seat else theirs)',
     's.action = copy.deepcopy(ours if i == seat else theirs)\n            if i != seat:\n                s.action["market"] = [o for o in s.action["market"] if len(o) > 1 and o[1] == "WHEAT"]',
     "test_01_actual_dump_collateral_loss_both_seats"),
    ("shed-only-asset-equality", '"final_assets_equal": before["final"]["assets"] == after["final"]["assets"],',
     '"final_assets_equal": [p["shed"] for p in before["final"]["assets"]["private"]] == [p["shed"] for p in after["final"]["assets"]["private"]],',
     "test_05_second_join_can_displace_incumbent_hire"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    source = (HERE / "row_intervention_controls.py").read_text()
    test = HERE / "check_row_intervention.py"
    rows = []
    for mode in ([], ["-O"]):
        for name, old, new, method in MUTATIONS:
            if source.count(old) != 1:
                raise RuntimeError(f"Mutation seam is not unique: {name}")
            with tempfile.TemporaryDirectory(prefix="estuary-row-mutant-") as temp:
                root = Path(temp)
                (root / "row_intervention_controls.py").write_text(source.replace(old, new, 1))
                shutil.copyfile(test, root / test.name)
                cmd = [sys.executable, *mode, str(root / test.name), "--runtime", str(args.runtime.resolve()),
                       "RowInterventionTests." + method]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                output = result.stdout + result.stderr
                # The test must fail an assertion, not crash due to bad imports/schema.
                failed = (result.returncode == 1 and "AssertionError" in output and
                          re.search(r"FAILED \(failures=\d+\)\s*$", output) is not None)
                rows.append({"mutation": name, "optimized": bool(mode), "test": method,
                             "behavioral_assertion_rejected": failed,
                             "exit_code": result.returncode,
                             "stdout_stderr_sha256": hashlib.sha256(output.encode()).hexdigest()})
                if not failed:
                    raise RuntimeError(f"Mutant survived or crashed: {name} {mode}\n{output}")
    args.output.write_text(json.dumps({"schema": "titan-v4-row-mutations-v1", "controls": rows,
                           "rejected": len(rows), "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                           "checker_sha256": hashlib.sha256(test.read_bytes()).hexdigest()}, indent=2) + "\n")
    print(json.dumps({"rejected": len(rows), "normal": len(MUTATIONS), "optimized": len(MUTATIONS)}))


if __name__ == "__main__":
    main()
