# SPDX-License-Identifier: Apache-2.0
"""Reproducible, fail-closed engine/owner acceptance and economic receipt CLI."""
from __future__ import annotations
import argparse
import copy
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import sys
import unittest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runtime", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--candidate", type=Path)
    p.add_argument("--candidate-blob")
    args = p.parse_args()
    if bool(args.candidate) != bool(args.candidate_blob):
        p.error("candidate path and full blob identity are required together")
    os.environ["FRUITPROOF_RUNTIME"] = str(args.runtime.resolve())
    import fruitproof_engine as fp
    import test_fruitproof_engine as checks
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    e = checks.ENGINE
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(checks))
    (out / "engine.log").write_text(log.getvalue())
    if not result.wasSuccessful() or result.skipped:
        print(log.getvalue(), file=sys.stderr)
        return 1
    baseline_counts = dict(checks.COUNTS)
    mutations = [
        ("unwatered_bonus", "_daily_refresh_plants", "was_watered and tile.get", "True and tile.get"),
        ("exclusive_coverage", "_daily_refresh_plants", ">= current_day", "> current_day"),
        ("three_unit_bonus", "_daily_refresh_plants", "(2 if fertilized else 1)", "(3 if fertilized else 1)"),
        ("fertilizer_free", "_apply_unit_action", 'if not _inv_take(inv, "FERTILIZER", 1):', 'if inv.get("FERTILIZER", 0) < 1:'),
        ("fertilizer_short_coverage", "_apply_unit_action", 'fertilized_until_day", -1), day + 2)', 'fertilized_until_day", -1), day + 1)'),
        ("reset_unwatered_survival", "_daily_refresh_plants", 'tile["consecutive_unwatered"] += 1', 'tile["consecutive_unwatered"] = 0'),
    ]
    controls = []
    for name, function, old, new in mutations:
        original = getattr(e, function)
        src = inspect.getsource(original)
        if src.count(old) != 1:
            raise ValueError(f"changed source span for {name}")
        space = dict(e.__dict__)
        exec(compile(src.replace(old, new), f"<fruitproof-control:{name}>", "exec"), space)
        setattr(e, function, space[function])
        capture = io.StringIO()
        try:
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(checks.Semantics)
            # Drought survival is covered by the independent matrix.
            if name == "reset_unwatered_survival":
                suite = unittest.defaultTestLoader.loadTestsFromTestCase(checks.PulseMatrix)
            got = unittest.TextTestRunner(stream=capture, verbosity=2).run(suite)
        finally:
            setattr(e, function, original)
        (out / f"control-{name}.log").write_text(capture.getvalue())
        record = {"name": name, "tests": got.testsRun, "assertion_failures": len(got.failures),
                  "errors": len(got.errors), "skips": len(got.skipped)}
        controls.append(record)
        if not got.failures or got.errors or got.skipped:
            raise ValueError(f"semantic control failed to assertion-reject: {record}")
    for name, field, value in (("late_first_pulse", "first_yield_day", 9),
                               ("wrong_crop_cap", "max_yield", 5)):
        saved = e.CROPS["TOMATO"][field]
        e.CROPS["TOMATO"][field] = value
        capture = io.StringIO()
        try:
            got = unittest.TextTestRunner(stream=capture, verbosity=2).run(
                unittest.defaultTestLoader.loadTestsFromTestCase(checks.Semantics))
        finally:
            e.CROPS["TOMATO"][field] = saved
        (out / f"control-{name}.log").write_text(capture.getvalue())
        record = {"name": name, "tests": got.testsRun, "assertion_failures": len(got.failures),
                  "errors": len(got.errors), "skips": len(got.skipped)}
        controls.append(record)
        if not got.failures or got.errors or got.skipped:
            raise ValueError(f"semantic control failed to assertion-reject: {record}")
    control_counts = {k: checks.COUNTS[k] - baseline_counts[k] for k in baseline_counts}
    economics = []
    economics_calls = 0
    for seat in (0, 1):
        for harvest in ("daily", "hold"):
            for inv in (10000, 9800, 9400, 10500):
                case = fp.Fixture(seat=seat, tomato_inventory=inv)
                game = fp.cycle_pair(e, checks.STRUCT, case, harvest=harvest)
                economics.append({"seat": seat, "harvest": harvest, "tomato_inventory": inv, "result": game})
                economics_calls += sum(game[a]["callbacks"] for a in ("baseline", "candidate"))
    (out / "economics.json").write_text(json.dumps(economics, indent=2, sort_keys=True) + "\n")
    candidate = {"status": "NOT_RUN", "reason": "no authenticated source supplied"}
    if args.candidate:
        from fruitproof_owner import verify_owner
        candidate = verify_owner(args.candidate, args.candidate_blob, e, checks.STRUCT, out)
        from fruitproof_owner_controls import verify_owner_controls
        candidate["semantic_controls"] = verify_owner_controls(
            args.candidate, args.candidate_blob, e, checks.STRUCT, out)
    sources = {name: fp.git_blob((Path(__file__).parent / name).read_bytes())
               for name in ("fruitproof_engine.py", "test_fruitproof_engine.py", "run_fruitproof.py", "fruitproof_owner.py", "fruitproof_owner_controls.py")}
    receipt = {"kind": "CONSTRUCTED_FULL_INTERPRETER_ACCEPTANCE_NOT_FIELD_EV",
               "python": sys.version, "optimized": sys.flags.optimize,
               "reference_pins": fp.PINS, "source_blobs": sources,
               "engine_tests": result.testsRun, "engine_counts": baseline_counts,
               "semantic_controls": controls, "control_counts": control_counts,
               "economic_pairs": len(economics), "economic_calls": economics_calls,
               "candidate": candidate,
               "limits": ["Not an original-B5 donor reproduction.",
                          "Constructed tomato at shed-access tile; not native or reachable-grower evidence.",
                          "Zero native opportunities do not establish harm or tested inertness.",
                          "Official-engine mutants are not owner-source mutants.",
                          "No default activation, production archive, Kaggle, hosted or competitive gate."]}
    receipt["files"] = {f.name: hashlib.sha256(f.read_bytes()).hexdigest()
                        for f in out.iterdir() if f.is_file() and f.name != "receipt.json"}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({k: receipt[k] for k in ("engine_tests", "engine_counts", "economic_pairs", "economic_calls", "candidate")}, indent=2))
    print("SEMANTIC_CONTROLS", len(controls), "ASSERTION_REJECTED; OPTIMIZE", sys.flags.optimize)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
