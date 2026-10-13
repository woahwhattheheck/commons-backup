# SPDX-License-Identifier: Apache-2.0
"""Run isolated behavioral negative controls after both complete green suites.

Uses the same explicit S2_SOURCE and S2_NATIVE_ROOT environment as the tests.
A syntax/import failure is NOT accepted as a rejected semantic mutant.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
MUTANTS = (
    ("eod_ignores_market_deposits", "s2_unit_custody.py",
     '100 - sum(private["shed"].values()) - possible_deposits',
     '100 - sum(private["shed"].values())',
     "test_eod_market_deposit_conservative_lower_bound"),
    ("eod_keeps_vanished_hands", "s2_unit_custody.py",
     '    if (step + 1) % 24 == 0:', '    if False:',
     "test_eod_hands_retired_and_real_sheep_rejoin"),
    ("plant_counts_only_real_actors", "s2_unit_custody.py",
     '    for work in workers:',
     '    for work in workers[:1 + len(farm.get("hands", []))]:',
     "test_ghost_plant_demand_changes_structure_prefix"),
    ("placement_debited_twice", "build_s2_lifecycle.py",
     'source = source.replace(old, "", 1)', 'source = source.replace(old, old, 1)',
     "test_owned_native_sheep_place_confirmed_once"),
    ("harvest_credit_lost", "s2_unit_custody.py",
     'units = max(0, inventory.get("WOOL", 0) - before_wool)', 'units = 0',
     "test_harvest_credit_matches_real_multi_actor_output"),
    ("final_action_guard_removed", "s2_unit_custody.py",
     'not _s2_same(state, self._before) or not _s2_same(returned_action, self._action)',
     'not _s2_same(state, self._before)',
     "test_rejected_final_action_cannot_create_purchase_receipt"),
    ("live_state_guard_removed", "s2_unit_custody.py",
     'not _s2_same(state, self._before) or not _s2_same(returned_action, self._action)',
     'not _s2_same(returned_action, self._action)',
     "test_proposal_rejects_state_drift"),
    ("native_pickup_ownership_lost", "s2_unit_custody.py",
     '        if len(work) >= 2 and work[:2] == ["PICKUP", "SHEEP"]:',
     '        if False:',
     "test_earlier_native_pickup_cannot_mint_second_carry"),
)


def execute(directory, optimized, arguments):
    command = [sys.executable] + (["-O"] if optimized else []) + arguments
    result = subprocess.run(command, cwd=directory, env=os.environ.copy(),
                            text=True, capture_output=True, timeout=30)
    return result.returncode, result.stdout + result.stderr


def main():
    results = []
    for optimized in (False, True):
        code, log = execute(HERE, optimized, ["test_s2_lifecycle.py"])
        if code != 0 or not re.search(r"Ran 31 tests", log) or "\nOK\n" not in log:
            raise RuntimeError("full green control failed: " + log)
        for name, filename, old, new, test in MUTANTS:
            with tempfile.TemporaryDirectory(prefix="s2-negative-") as tmp:
                directory = Path(tmp)
                for source in ("build_s2_lifecycle.py", "s2_unit_custody.py", "test_s2_lifecycle.py"):
                    shutil.copyfile(HERE / source, directory / source)
                path = directory / filename
                text = path.read_text()
                if text.count(old) != 1:
                    raise RuntimeError("mutation anchor changed: " + name)
                path.write_text(text.replace(old, new, 1))
                code, log = execute(directory, optimized, ["-m", "unittest",
                    "test_s2_lifecycle.LifecycleTests." + test])
                behavioral = (code != 0 and "AssertionError" in log
                              and "Ran 1 test" in log and "FAILED (failures=1)" in log
                              and "ERROR:" not in log and "skipped=" not in log)
                if not behavioral:
                    raise RuntimeError("mutant did not fail behaviorally: " + name + "\n" + log)
                results.append({"name": name, "optimized": optimized,
                                "result": "ASSERTION_REJECTED", "tests": 1,
                                "failures": 1, "errors": 0})
    print(json.dumps({"green_controls": {"normal": 31, "optimized": 31},
                      "mutants": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
