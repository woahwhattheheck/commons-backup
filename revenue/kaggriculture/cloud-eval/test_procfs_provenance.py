"""Additive procfs diagnostics on real Actor processes; no engine/game replay."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

SOURCE = Path(os.environ.get("EVALUATOR_SOURCE", Path(__file__).with_name("evaluate.py")))
spec = importlib.util.spec_from_file_location("procfs_provenance_evaluator", SOURCE)
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux procfs boundary fixtures")
class ProcfsProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="procfs-provenance-test-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        candidate = root / "candidate.py"
        candidate.write_text("def agent(obs, cfg):\n    return {}\n", encoding="utf-8")
        self.actor = ev.Actor(str(candidate), root, root / "unused_loader.py", 19)
        self.addCleanup(self.actor.close)
        self.assertEqual(self.actor.ready["kind"], "ready")
        self.assertEqual(self.actor.act({}, {}, 1)["kind"], "action")
        self.initial = self.actor.report()
        self.reads = []

    def close_with(self, samples):
        def read(path, *args, **kwargs):
            key = str(path)
            self.reads.append(key)
            value = samples[key]
            if isinstance(value, Exception):
                raise value
            return value

        # Exercise actual close/reaping, while controlling only procfs input.
        with mock.patch.object(ev.Path, "read_text", autospec=True, side_effect=read):
            self.actor.close()
        report = self.actor.report()
        self.assertIsNotNone(report["exit_code"])
        self.assertFalse(Path(self.actor.directory.name).exists())
        self.assertTrue(self.actor.proc.stdout.closed)
        self.assertTrue(self.actor.proc.stdin.closed)
        self.assertEqual(report["calls"], 1)
        self.assertEqual(report["call_cpu_seconds"], self.initial["call_cpu_seconds"])
        self.assertEqual(report["max_call_seconds"], self.initial["max_call_seconds"])
        self.assertEqual(report["max_rpc_seconds"], self.initial["max_rpc_seconds"])
        # The diagnostic is serialized by the existing report writer unchanged.
        output = Path(self.temp.name) / "report.json"
        ev.write_report(output, {"actors": [report]})
        self.assertEqual(json.loads(output.read_text())["actors"][0], report)
        return report

    def identity(self):
        return f"{os.getpid()} (parent with spaces) S 0 0"

    def child_stat(self):
        fields = ["S"] + ["0"] * 20
        ticks = os.sysconf("SC_CLK_TCK")
        fields[11], fields[12] = str(1200 * ticks), str(34 * ticks)
        return f"{self.actor.proc.pid} (worker with ) parentheses) " + " ".join(fields)

    def test_initial_report_and_snapshot_remain_not_attempted(self):
        self.assertEqual(self.initial["procfs_sample_status"], "not_attempted")
        report = self.close_with({"/proc/self/stat": PermissionError("unavailable")})
        self.assertEqual(report["procfs_sample_status"], "error:self_stat:PermissionError")
        self.assertEqual(self.initial["procfs_sample_status"], "not_attempted")

    def test_pid_view_mismatch_never_reads_numeric_child(self):
        report = self.close_with({"/proc/self/stat": f"{os.getpid() + 1000000} (other view) S 0"})
        self.assertEqual(self.reads, ["/proc/self/stat"])
        self.assertEqual(report["procfs_sample_status"], "skipped:pid_view_mismatch")
        self.assertEqual(report["resource_sample"], "child_rusage")
        if hasattr(os, "wait4"):
            self.assertEqual(report["final_resource_sample"], "wait4")

    def test_success_retains_exact_sample_and_is_idempotent(self):
        samples = {"/proc/self/stat": self.identity(),
                   f"/proc/{self.actor.proc.pid}/status": "VmHWM:\t134217728 kB\n",
                   f"/proc/{self.actor.proc.pid}/stat": self.child_stat()}
        report = self.close_with(samples)
        self.assertEqual(self.reads, list(samples))
        self.assertEqual(report["procfs_sample_status"], "sampled")
        self.assertEqual(report["resource_sample"], "child_rusage_plus_linux_procfs")
        self.assertEqual(report["cpu_seconds"], 1234)
        self.assertEqual(report["peak_rss_kib"], 134217728)
        self.actor.close()
        self.assertEqual(self.actor.report(), report)

    def test_missing_self_stat_preserves_wait4_fallback(self):
        report = self.close_with({"/proc/self/stat": FileNotFoundError("gone")})
        self.assertEqual(report["procfs_sample_status"], "error:self_stat:FileNotFoundError")
        self.assertEqual(report["resource_sample"], "child_rusage")
        if hasattr(os, "wait4"):
            self.assertEqual(report["final_resource_sample"], "wait4")

    def test_malformed_self_stat_is_distinct_from_view_mismatch(self):
        report = self.close_with({"/proc/self/stat": "invalid (parent) S"})
        self.assertEqual(report["procfs_sample_status"], "error:self_stat:ValueError")
        self.assertEqual(self.reads, ["/proc/self/stat"])

    def test_empty_self_stat_retains_child_only_without_wait4(self):
        with mock.patch.object(ev.os, "wait4", None, create=True):
            report = self.close_with({"/proc/self/stat": ""})
        self.assertEqual(report["procfs_sample_status"], "error:self_stat:IndexError")
        self.assertEqual(report["final_resource_sample"], "unavailable:wait4_unsupported")
        self.assertEqual(report["cpu_seconds"], self.initial["cpu_seconds"])
        self.assertEqual(report["peak_rss_kib"], self.initial["peak_rss_kib"])

    def test_child_status_read_error_identifies_stage(self):
        report = self.close_with({"/proc/self/stat": self.identity(),
            f"/proc/{self.actor.proc.pid}/status": PermissionError("unavailable")})
        self.assertEqual(report["procfs_sample_status"], "error:child_status:PermissionError")
        self.assertEqual(report["resource_sample"], "child_rusage")
        self.assertEqual(len(self.reads), 2)

    def test_child_status_parse_error_identifies_stage(self):
        report = self.close_with({"/proc/self/stat": self.identity(),
            f"/proc/{self.actor.proc.pid}/status": "VmHWM:\tinvalid kB\n"})
        self.assertEqual(report["procfs_sample_status"], "error:child_status:ValueError")
        self.assertEqual(report["resource_sample"], "child_rusage")
        self.assertEqual(len(self.reads), 2)

    def test_child_stat_error_preserves_already_sampled_rss(self):
        report = self.close_with({"/proc/self/stat": self.identity(),
            f"/proc/{self.actor.proc.pid}/status": "VmHWM:\t134217728 kB\n",
            f"/proc/{self.actor.proc.pid}/stat": FileNotFoundError("exited")})
        self.assertEqual(report["procfs_sample_status"], "error:child_stat:FileNotFoundError")
        self.assertEqual(report["peak_rss_kib"], 134217728)
        self.assertEqual(report["resource_sample"], "child_rusage")

    def test_child_stat_parse_error_preserves_already_sampled_rss(self):
        report = self.close_with({"/proc/self/stat": self.identity(),
            f"/proc/{self.actor.proc.pid}/status": "VmHWM:\t134217728 kB\n",
            f"/proc/{self.actor.proc.pid}/stat": "truncated"})
        self.assertEqual(report["procfs_sample_status"], "error:child_stat:IndexError")
        self.assertEqual(report["peak_rss_kib"], 134217728)

    def test_success_without_rss_line_preserves_cpu_only_sampling(self):
        report = self.close_with({"/proc/self/stat": self.identity(),
            f"/proc/{self.actor.proc.pid}/status": "Name:\tworker\n",
            f"/proc/{self.actor.proc.pid}/stat": self.child_stat()})
        self.assertEqual(report["procfs_sample_status"], "sampled")
        self.assertEqual(report["cpu_seconds"], 1234)
        self.assertLess(report["peak_rss_kib"], 134217728)

    def test_non_linux_branch_avoids_procfs(self):
        # This exercises the branch on Linux, not native non-Linux execution.
        with mock.patch.object(ev.sys, "platform", "freebsd"):
            report = self.close_with({})
        self.assertEqual(self.reads, [])
        self.assertEqual(report["procfs_sample_status"], "not_applicable:non_linux")
        self.assertEqual(report["resource_sample"], "child_rusage")


if __name__ == "__main__":
    unittest.main(verbosity=2)
