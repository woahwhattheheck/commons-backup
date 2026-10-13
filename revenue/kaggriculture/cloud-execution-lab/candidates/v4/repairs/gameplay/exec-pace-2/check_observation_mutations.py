# SPDX-License-Identifier: Apache-2.0
"""Run exact-helper baseline and eight behavioral negative controls. Also run -O."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

HERE = Path(__file__).resolve().parent
PIN = "f67c93ec9b295575b73a242e5acbedffc796415d"
MUTATIONS = {
    "ignore_gap": ('elif player != _last_player[0] or step != _last_step[0] + 1:',
                   'elif player != _last_player[0]:'),
    "duplicate_resets": ('if values == _last_prices[0]:\n                return',
                         'if values == _last_prices[0]:\n                reset()\n                return'),
    "invalid_time_retains_stale": ('or player not in (0, 1) or not isinstance(market, Mapping)):\n            reset()',
                                   'or player not in (0, 1) or not isinstance(market, Mapping)):\n            pass'),
    "invent_zero_quote": ('px if type(px) is int and px >= 1 else None',
                          'px if type(px) is int and px >= 1 else 0'),
    "accept_float_quote": ('px if type(px) is int and px >= 1 else None',
                           'px if type(px) in (int, float) and px >= 1 else None'),
    "short_warmup": ('hist is None or len(hist) != HIST_WINDOW',
                     'hist is None or len(hist) < 2'),
    "invalid_good_keeps_history": ('_phist.pop(good, None)', 'pass'),
    "flat_is_rising": ('value > SLOPE_THRESHOLD', 'value >= 0.0'),
}


def main():
    import importlib.util
    import io
    import unittest

    source = (HERE / "r04_exec_adaptive.py").read_text(encoding="utf-8")
    data = source.encode()
    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if actual != PIN:
        raise RuntimeError(f"source pin mismatch: {actual}")
    report = {"source_blob": actual, "optimized": not __debug__, "mutations": []}

    def run(path):
        previous = os.environ.get("EXEC_PACE_SOURCE")
        os.environ["EXEC_PACE_SOURCE"] = str(path)
        try:
            spec = importlib.util.spec_from_file_location("mutation_contract_tests", HERE / "test_observation_state.py")
            tests = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tests)
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(tests.ObservationState)
            return unittest.TextTestRunner(stream=io.StringIO()).run(suite)
        finally:
            if previous is None:
                os.environ.pop("EXEC_PACE_SOURCE", None)
            else:
                os.environ["EXEC_PACE_SOURCE"] = previous

    baseline = run(HERE / "r04_exec_adaptive.py")
    if not baseline.wasSuccessful() or baseline.testsRun != 24 or baseline.skipped:
        raise RuntimeError("baseline failed")
    report["baseline"] = {"tests": 24, "passed": True}
    with tempfile.TemporaryDirectory(prefix="exec-pace-mutations-") as directory:
        for name, (before, after) in MUTATIONS.items():
            if source.count(before) != 1:
                raise RuntimeError(f"mutation anchor mismatch: {name}")
            changed = source.replace(before, after, 1)
            compile(changed, name, "exec")
            path = Path(directory) / (name + ".py")
            path.write_text(changed, encoding="utf-8")
            result = run(path)
            if result.testsRun != 24 or not result.failures or result.errors or result.skipped:
                raise RuntimeError(f"mutation did not fail by assertion: {name}")
            report["mutations"].append({"name": name, "assertion_failures": len(result.failures), "rejected": True})
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
