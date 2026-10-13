#!/usr/bin/env python3
"""Exact consumption of the pinned checker's six-place scientific output.

Set ROADEF_NATIVE_CHECKER to an already-built official checker for the native
cases; missing executables produce explicit skips, not synthetic substitutes.
No solver search, public benchmark, or network access is performed.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from decimal import Decimal
from unittest.mock import patch

import compare_checker as reader

HERE = Path(__file__).resolve().parent
CHECKER = os.environ.get("ROADEF_NATIVE_CHECKER")
EVIDENCE = []


def document(values, cost=0):
    return {"valid": True, "total_cost": cost,
            "saturations": [{"t": i, "from": 0, "to": 1, "sat": v}
                            for i, v in enumerate(values)]}


class ReaderSerialization(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="checker-serialization-")
        self.root = Path(self.tmp.name)
        self.count = 0

    def tearDown(self):
        self.tmp.cleanup()

    def result(self, values, cost=0):
        self.count += 1
        path = self.root / (str(self.count) + ".json")
        path.write_text(json.dumps(document(values, cost)) + "\n")
        return reader.load_result(path)

    def test_reported_native_witness_kept_exact(self):
        value = "9.933579335793359E-7"
        result = self.result([value, "0.0"])
        self.assertEqual(result["vector"], [Decimal(value), Decimal(0)])
        self.assertNotEqual(result["vector"][0], Decimal("0.000001"))
        self.assertNotEqual(result["vector"][0], Decimal(0))

    def test_scientific_band_boundaries(self):
        for value in ("1e-7", "1.000000000000001e-7", "5.123456789012345e-7", "9.999999999999999e-7"):
            with self.subTest(value=value):
                self.assertEqual(self.result([value])["vector"], [Decimal(value)])

    def test_decimal_spelling_has_same_exact_value(self):
        a = self.result(["9.933579335793359e-7"])
        b = self.result(["0.0000009933579335793359"])
        self.assertEqual(reader.compare(a, b)["winner"], "tie")

    def test_ordinary_six_place_values_unchanged(self):
        values = ["0", "0.000001", "0.123456", "1.234567", "100", "1e21"]
        self.assertEqual(self.result(values)["vector"], sorted(map(Decimal, values), reverse=True))

    def test_precision_outside_native_band_is_still_rejected(self):
        for value in ("0.1234567", "1.0000001", "1.234567e-6", "1e-8", "9.999999e-8"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.result([value])

    def test_submicro_values_remain_distinguishable(self):
        a = self.result(["1", "9.1e-7"])
        b = self.result(["1", "9.2e-7"])
        out = reader.compare(a, b)
        self.assertEqual(out["winner"], "left")
        self.assertEqual(out["first_changed_rank"], 2)
        self.assertEqual(Decimal(out["left_at_first_change"]), Decimal("9.1e-7"))

    def test_cost_does_not_break_exact_objective_tie(self):
        a = self.result(["9.933579335793359e-7", "1"], 999)
        b = self.result(["1", "9.933579335793359e-7"], 1)
        # Coordinates match; objective is sorted vector rather than row order.
        out = reader.compare(a, b)
        self.assertEqual(out["winner"], "tie")
        self.assertFalse(out["cost_used_in_ranking"])

    def test_nonfinite_negative_and_malformed_numbers_remain_errors(self):
        for value in ("NaN", "Infinity", "-0.0000009", "not-a-number"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.result([value])

    def test_duplicate_coordinate_still_rejected(self):
        data = document(["9e-7"])
        data["saturations"].append(dict(data["saturations"][0]))
        path = self.root / "duplicate.json"
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            reader.load_result(path)

    def test_invalid_result_does_not_acquire_a_vector(self):
        path = self.root / "invalid.json"
        path.write_text('{"valid":false}')
        result = reader.load_result(path)
        self.assertFalse(result["valid"])
        self.assertNotIn("vector", result)

    def test_cli_consumes_scientific_values_without_rounding(self):
        left, right = self.root / "left.json", self.root / "right.json"
        left.write_text(json.dumps(document(["1", "8.9e-7"])))
        right.write_text(json.dumps(document(["1", "9.1e-7"])))
        run = subprocess.run([sys.executable, str(Path(reader.__file__)), str(left), str(right)],
                             capture_output=True, text=True, check=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result["counts"]["left"], 1)
        self.assertEqual(result["instances"][0]["first_changed_rank"], 2)
        self.assertEqual(result["instances"][0]["left_checker_sha256"], hashlib.sha256(left.read_bytes()).hexdigest())


@unittest.skipUnless(CHECKER and Path(CHECKER).is_file(), "Set ROADEF_NATIVE_CHECKER to the existing official binary")
class NativeChecker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="native-scientific-")
        self.root = Path(self.tmp.name)
        self.network = self.root / "net.json"
        self.traffic = self.root / "tm.json"
        self.scenario = self.root / "scenario.json"
        self.solution = self.root / "srpaths.json"
        net = {"directed": True, "multigraph": False,
               "nodes": [{"id": 0, "name": "a"}, {"id": 1, "name": "b"}],
               "links": [{"id": 0, "from": 0, "to": 1, "metric": 1, "capacity": 10_000_000},
                         {"id": 1, "from": 1, "to": 0, "metric": 1, "capacity": 10_000_000}]}
        self.network.write_text(json.dumps(net) + "\n")
        self.scenario.write_text('{"max_segments":8,"interventions":[],"budget":[]}\n')
        self.solution.write_text('{"srpaths":[]}\n')

    def tearDown(self):
        self.tmp.cleanup()

    def native(self, volume, places=6):
        self.traffic.write_text(json.dumps({"num_time_slots": 1, "demands": [{"s": 0, "t": 1, "v": [volume]}]}) + "\n")
        command = [str(Path(CHECKER).resolve()), "--net", str(self.network), "--tm", str(self.traffic),
                   "--scenario", str(self.scenario), "--srpaths", str(self.solution), "--max-decimal-places", str(places)]
        run = subprocess.run(command, capture_output=True, timeout=20, check=False)
        result_path = self.root / f"checker-{places}.json"
        result_path.write_bytes(run.stdout)
        EVIDENCE.append({"kind": "native_checker", "volume": volume, "places": places,
                         "returncode": run.returncode, "stdout": run.stdout.decode(), "stderr": run.stderr.decode(),
                         "stdout_sha256": hashlib.sha256(run.stdout).hexdigest(),
                         "inputs": {p.name: json.loads(p.read_bytes()) for p in
                                    (self.network, self.traffic, self.scenario, self.solution)}})
        self.assertEqual(run.returncode, 0, run.stderr.decode())
        self.assertTrue(json.loads(run.stdout)["valid"])
        return result_path

    def test_official_six_place_writer_boundaries(self):
        # Each is an actual complete checker invocation, not an emulated formatter.
        for volume in (0.5, 1.0, 1.000000001, 5.123456789, 9.933579335793359,
                       9.999999999, 10.0, 10.123456789, 1234567.891):
            with self.subTest(volume=volume):
                path = self.native(volume)
                raw = json.loads(path.read_bytes(), parse_float=Decimal)
                expected = sorted((Decimal(x["sat"]) for x in raw["saturations"]), reverse=True)
                self.assertEqual(reader.load_result(path)["vector"], expected)

    def test_actual_native_witness_is_not_rounded(self):
        path = self.native(9.933579335793359)
        self.assertIn(b'9.933579335793359e-7', path.read_bytes())
        self.assertEqual(reader.load_result(path)["vector"][0], Decimal("9.933579335793359e-7"))

    def test_twelve_place_ordinary_output_still_not_six_place_input(self):
        path = self.native(1234567.891, places=12)
        with self.assertRaises(ValueError):
            reader.load_result(path)

    def test_existing_supervisor_accepts_actual_native_checkpoint(self):
        # Keep Supervisor source unchanged and invoke its normal real checker road.
        import supervisor
        self.traffic.write_text(json.dumps({"num_time_slots": 1, "demands": [{"s": 0, "t": 1, "v": [9.933579335793359]}]}) + "\n")
        out = self.root / "accepted.json"
        with patch.dict(os.environ, {"PORTFOLIO_CHECKER": str(Path(CHECKER).resolve()),
                                     "PORTFOLIO_SECONDS": "10", "PORTFOLIO_ARTIFACTS": str(self.root)}):
            engine = supervisor.Supervisor([self.network, self.traffic, self.scenario], out)
            engine.pending_baseline = None
            try:
                self.assertTrue(engine.enqueue(self.solution, "native_fixture"))
                deadline = time.monotonic() + 20
                while engine.check is not None and time.monotonic() < deadline:
                    engine.poll_checker()
                    time.sleep(0.01)
                self.assertIsNone(engine.check, "Checker did not terminate")
                outputs = {p.name: p.read_text() for p in engine.work.glob('*.checker-6.json')}
                EVIDENCE.append({"kind": "supervisor_native", "events": engine.events,
                                 "checker_reports": outputs, "accepted": out.exists()})
                self.assertIsNotNone(engine.best, "Valid native scientific report was discarded")
                self.assertEqual(out.read_bytes(), self.solution.read_bytes())
                self.assertEqual(engine.best["vector"][0], Decimal("9.933579335793359e-7"))
                self.assertFalse(any(e["event"].startswith("check_retry") for e in engine.events))
            finally:
                if engine.check is not None:
                    process = engine.check["process"]
                    supervisor.stop_process(process, force=True)
                    process.wait(timeout=3)
                    engine.check["stdout"].close()
                    engine.check["stderr"].close()


if __name__ == '__main__':
    result = unittest.main(exit=False, verbosity=2).result
    if os.environ.get('ROADEF_SERIALIZATION_REPORT'):
        report = {"tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                  "skipped": len(result.skipped), "success": result.wasSuccessful(),
                  "reader_sha256": hashlib.sha256(Path(reader.__file__).read_bytes()).hexdigest(),
                  "checker_sha256": hashlib.sha256(Path(CHECKER).read_bytes()).hexdigest() if CHECKER else None,
                  "native_checker_invocations": sum(x['kind'] == 'native_checker' for x in EVIDENCE),
                  "supervisor_checker_invocations": sum(x['kind'] == 'supervisor_native' for x in EVIDENCE),
                  "evidence": EVIDENCE}
        Path(os.environ['ROADEF_SERIALIZATION_REPORT']).write_text(json.dumps(report, indent=2) + '\n')
    sys.exit(0 if result.wasSuccessful() else 1)
