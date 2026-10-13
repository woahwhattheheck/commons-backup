"""Independent recovery regressions; not COPPERLEAF-63's historical 43 tests."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import io
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from revenue.uiowa_rfq_18649_delivery_flow import delivery_flow as d

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "synthetic.json"


class DeliveryFlowTests(unittest.TestCase):
    def setUp(self):
        self.packet = d.decode(FIXTURE.read_bytes())

    def report(self, index=0):
        return d.assess(self.packet)["traces"][index]

    def test_parallel_union(self):
        m = self.report()["metrics"]
        self.assertEqual(m["execution_attempt_seconds_sum"], 1860)
        self.assertEqual(m["execution_union_seconds"], 1380)
        self.assertEqual(m["queue_union_seconds"], 960)
        self.assertEqual(m["queue_execution_overlap_seconds"], 60)
        self.assertEqual(m["observed_activity_union_seconds"], 2280)
        self.assertEqual(m["unattributed_window_seconds"], 1320)

    def test_manual_queue(self):
        self.assertEqual(self.report()["metrics"]["manual_queue_union_seconds"], 600)

    def test_failure_and_repeat_can_overlap(self):
        self.packet["traces"][0]["attempts"][2]["result"] = "failure"
        m = self.report()["metrics"]
        self.assertEqual(m["failed_execution_seconds_lower_bound"], 480)
        self.assertEqual(m["repeat_execution_seconds_lower_bound"], 240)
        self.assertEqual(m["repeat_attempt_count"], 1)

    def test_running_is_censored(self):
        row = self.report(1)["attempts"][1]
        self.assertEqual(row["execution_measure"], "censored")
        self.assertEqual(row["execution_seconds"], 2640)

    def test_queued_is_censored(self):
        row = self.report(1)["attempts"][2]
        self.assertEqual(row["queue_measure"], "censored")
        self.assertEqual(row["queue_seconds"], 2400)
        self.assertIsNone(row["execution_seconds"])

    def test_unknown_state_is_not_observed_queue(self):
        row = self.report(1)["attempts"][3]
        self.assertIsNone(row["queue_seconds"])
        self.assertEqual(row["queue_measure"], "unknown")

    def test_missing_start_is_not_queue_until_finish(self):
        row = self.report(2)["attempts"][0]
        self.assertIsNone(row["queue_seconds"])
        self.assertIsNone(row["execution_seconds"])
        self.assertEqual(row["result"], "success")

    def test_missing_stages_and_attempts_are_questions(self):
        report = self.report(2)
        self.assertEqual([r["stage"] for r in report["stage_matrix"] if r["coverage"] == "unknown"],
                         ["verification", "packaging", "promotion"])
        self.assertIn("ATTEMPT_GAPS", {q["code"] for q in report["follow_up"]})

    def test_empty_trace_is_unassessed_not_failed(self):
        self.packet["traces"][0]["attempts"] = []
        r = self.report()
        self.assertTrue(all(row["coverage"] == "unknown" for row in r["stage_matrix"]))
        self.assertEqual(r["metrics"]["failed_attempt_count"], 0)
        self.assertIsNone(r["metrics"]["recorded_first_deployment_latency_seconds"])

    def test_no_release_authority(self):
        report = d.assess(self.packet)
        self.assertIs(report["external_action_authorized"], False)
        self.assertIn("not release approval", " ".join(report["interpretation"]))

    def test_reproducibility_is_not_invented(self):
        self.assertEqual(self.report(1)["reproducibility"]["status"], "documented_only")
        self.assertIn("REPRODUCIBILITY_REVIEW", {q["code"] for q in self.report(1)["follow_up"]})

    def test_evidence_locators_retained(self):
        self.assertEqual(self.report()["evidence_register"], self.packet["traces"][0]["evidence"])

    def test_unknown_owner_and_unreferenced_record_retained(self):
        codes = {q["code"] for q in self.report(2)["follow_up"]}
        self.assertTrue({"OWNER_UNKNOWN", "UNREFERENCED_RECORD"} <= codes)

    def test_original_unchanged(self):
        before = deepcopy(self.packet)
        d.assess(self.packet)
        self.assertEqual(before, self.packet)

    def test_offset_equivalence(self):
        self.packet["observed_at"] = "2026-09-01T06:00:00-04:00"
        self.assertEqual(self.report()["metrics"]["observation_window_seconds"], 3600)

    def test_microsecond_interval_union(self):
        start = d.timestamp("2026-09-01T09:00:00Z", "test")
        spans = [(start + timedelta(microseconds=i * 2), start + timedelta(microseconds=i * 2 + 1))
                 for i in range(1000)]
        self.assertEqual(d.union_seconds(spans), 0.001)

    def test_interval_union_independent_occupancy(self):
        rng = random.Random(62086)
        start = d.timestamp("2026-09-01T09:00:00Z", "test")
        for _ in range(250):
            pairs = [sorted(rng.sample(range(61), 2)) for _ in range(rng.randrange(20))]
            occupied = set().union(*(set(range(a, b)) for a, b in pairs))
            spans = [(start + timedelta(seconds=a), start + timedelta(seconds=b)) for a, b in pairs]
            self.assertEqual(d.union_seconds(spans), len(occupied))
            self.assertEqual(d.union_seconds(spans + spans), len(occupied))

    def test_zero_and_touching_intervals(self):
        t = d.timestamp("2026-09-01T09:00:00Z", "test")
        self.assertEqual(d.union_seconds([(t, t)]), 0)
        self.assertEqual(d.union_seconds([(t, t + timedelta(seconds=1)),
                                         (t + timedelta(seconds=1), t + timedelta(seconds=2))]), 2)

    def test_negative_interval_refused(self):
        t = d.timestamp("2026-09-01T09:00:00Z", "test")
        with self.assertRaises(d.InputError):
            d.union_seconds([(t + timedelta(seconds=1), t)])

    def test_markdown_escapes_supplied_text(self):
        self.packet["traces"][0]["service"] = '<script>|[click](https://example.invalid)\nnext'
        out = d.markdown(d.assess(self.packet))
        self.assertNotIn("<script>", out)
        self.assertIn("&#124;", out)
        self.assertNotIn("[click]", out)
        self.assertIn("<br>", out)

    def test_duplicate_json_keys_refused(self):
        with self.assertRaisesRegex(d.InputError, "duplicate JSON key"):
            d.decode(b'{"a":1,"a":2}')

    def test_nonfinite_and_invalid_utf8_refused(self):
        for raw in (b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}', b'{"a":"\xff"}'):
            with self.subTest(raw=raw), self.assertRaises(d.InputError):
                d.decode(raw)

    def test_oversized_input_refused(self):
        with self.assertRaisesRegex(d.InputError, "4 MiB"):
            d.decode(b" " * (d.MAX_BYTES + 1))

    def test_bad_timestamp_variants(self):
        for value in ("2026-09-01", "2026-09-01T09:00:00", "2026-09-01T09:00:00+00:99",
                      "2026-02-30T09:00:00Z", "2026-9-01T09:00:00Z", "2026-09-01 09:00:00Z",
                      "2026-09-01T09:00:00+24:00", "2026-09-01T09:00:60Z"):
            with self.subTest(value=value), self.assertRaises(d.InputError):
                d.timestamp(value, "test")

    def test_attempt_validation_matrix(self):
        cases = [("attempt", True), ("attempt", 1.0), ("attempt", 0), ("attempt", 1001),
                 ("id", " B1"), ("stage", "compile"), ("stage", []), ("mode", "maybe"),
                 ("progress_state", "maybe"), ("result", "maybe"), ("owner_role", ""),
                 ("evidence_refs", ["missing"]), ("evidence_refs", ["E1", "E1"]),
                 ("evidence_refs", None), ("started_at", "2026-09-01T08:59:00Z"),
                 ("finished_at", "2026-09-01T10:01:00Z"), ("finished_at", None)]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(d.InputError):
                p = deepcopy(self.packet)
                p["traces"][0]["attempts"][0][key] = value
                d.assess(p)

    def test_duplicate_trace_attempt_and_ordinal(self):
        for target in ("trace", "id", "ordinal"):
            with self.subTest(target=target), self.assertRaises(d.InputError):
                p = deepcopy(self.packet)
                if target == "trace":
                    p["traces"].append(deepcopy(p["traces"][0]))
                else:
                    row = deepcopy(p["traces"][0]["attempts"][0])
                    if target == "ordinal":
                        row["id"] = "NEW"
                    p["traces"][0]["attempts"].append(row)
                d.assess(p)

    def test_evidence_time_and_identity(self):
        for kind in ("duplicate", "future", "missing_locator"):
            with self.subTest(kind=kind), self.assertRaises(d.InputError):
                p = deepcopy(self.packet)
                evidence = p["traces"][0]["evidence"]
                if kind == "duplicate":
                    evidence.append(deepcopy(evidence[0]))
                elif kind == "future":
                    evidence[0]["recorded_at"] = "2026-09-01T10:01:00Z"
                else:
                    evidence[0]["locator"] = ""
                d.assess(p)

    def test_nonunknown_reproducibility_needs_source(self):
        self.packet["traces"][0]["reproducibility"]["evidence_refs"] = []
        with self.assertRaises(d.InputError):
            d.assess(self.packet)

    def test_progress_consistency(self):
        changes = [("queued", "unknown", 0, None), ("running", "unknown", None, None),
                   ("finished", "unknown", 0, 1), ("unknown", "success", None, None)]
        for state, result, start, finish in changes:
            with self.subTest(state=state), self.assertRaises(d.InputError):
                p = deepcopy(self.packet)
                row = p["traces"][0]["attempts"][0]
                row.update(progress_state=state, result=result,
                           started_at=None if start is None else "2026-09-01T09:00:00Z",
                           finished_at=None if finish is None else "2026-09-01T09:01:00Z")
                d.assess(p)

    def test_packet_and_trace_shape(self):
        for key, value in (("schema_version", "v2"), ("synthetic", "true"), ("traces", []), ("traces", {})):
            with self.subTest(key=key), self.assertRaises(d.InputError):
                p = deepcopy(self.packet)
                p[key] = value
                d.assess(p)

    def call(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = d.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_cli_digest_binds_exact_input(self):
        code, out, err = self.call("--input", str(FIXTURE), "--format", "json")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["source_sha256"], hashlib.sha256(FIXTURE.read_bytes()).hexdigest())

    def test_cli_deterministic(self):
        self.assertEqual(self.call("--input", str(FIXTURE)), self.call("--input", str(FIXTURE)))

    def test_cli_writes_only_new_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "report.md"
            self.assertEqual(self.call("--input", str(FIXTURE), "--output", str(dest))[0], 0)
            before = dest.read_bytes()
            self.assertEqual(self.call("--input", str(FIXTURE), "--output", str(dest))[0], 2)
            self.assertEqual(dest.read_bytes(), before)

    def test_cli_input_alias_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "input.json"
            src.write_bytes(FIXTURE.read_bytes())
            before = src.read_bytes()
            self.assertEqual(self.call("--input", str(src), "--output", str(src))[0], 2)
            self.assertEqual(src.read_bytes(), before)

    def test_cli_symlink_and_hardlink_preserved(self):
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                src, alias = Path(tmp) / "in.json", Path(tmp) / "alias.json"
                src.write_bytes(FIXTURE.read_bytes())
                if kind == "symlink":
                    alias.symlink_to(src)
                else:
                    alias.hardlink_to(src)
                self.assertEqual(self.call("--input", str(src), "--output", str(alias))[0], 2)
                self.assertEqual(src.read_bytes(), FIXTURE.read_bytes())

    def test_cli_invalid_input_has_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dest = Path(tmp) / "bad.json", Path(tmp) / "out.json"
            src.write_text('{"invalid":true}')
            self.assertEqual(self.call("--input", str(src), "--output", str(dest))[0], 2)
            self.assertFalse(dest.exists())

    def test_cli_missing_file_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = self.call("--input", str(Path(tmp) / "missing.json"))
            self.assertEqual((code, out), (2, ""))
            self.assertIn("delivery-flow:", err)

    def test_real_optimized_cli_parity(self):
        argv = [str(HERE / "delivery_flow.py"), "--input", str(FIXTURE), "--format", "json"]
        normal = subprocess.run([sys.executable, *argv], capture_output=True, check=False)
        optimized = subprocess.run([sys.executable, "-O", *argv], capture_output=True, check=False)
        self.assertEqual((normal.returncode, optimized.returncode), (0, 0))
        self.assertEqual(normal.stdout, optimized.stdout)
        self.assertEqual(normal.stderr, b"")
        self.assertEqual(optimized.stderr, b"")

    def test_synthetic_report_matches_cli(self):
        argv = [str(HERE / "delivery_flow.py"), "--input", str(FIXTURE)]
        proc = subprocess.run([sys.executable, *argv], capture_output=True, check=False)
        self.assertEqual((proc.returncode, proc.stderr), (0, b""))
        self.assertEqual(proc.stdout, (HERE / "synthetic-report.md").read_bytes())

    def test_execution_record_binds_landed_files(self):
        record = json.loads((HERE / "EXECUTION.json").read_text())
        root = HERE.parents[1]
        for path, rec in record["files"].items():
            raw = (root / path).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), rec["sha256"], path)
            header = ("blob %d\0" % len(raw)).encode()
            self.assertEqual(hashlib.sha1(header + raw).hexdigest(), rec["git_blob"], path)

    def test_execution_json_stdout_and_metrics(self):
        record = json.loads((HERE / "EXECUTION.json").read_text())
        argv = [str(HERE / "delivery_flow.py"), "--input", str(FIXTURE), "--format", "json"]
        proc = subprocess.run([sys.executable, *argv], capture_output=True, check=False)
        self.assertEqual((proc.returncode, proc.stderr), (0, b""))
        self.assertEqual(hashlib.sha256(proc.stdout).hexdigest(), record["json_stdout_sha256"])
        report = json.loads(proc.stdout.decode())
        self.assertEqual({row["id"]: row["metrics"] for row in report["traces"]}, record["result_metrics"])


if __name__ == "__main__":
    unittest.main()
