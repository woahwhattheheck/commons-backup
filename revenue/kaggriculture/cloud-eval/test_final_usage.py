"""Real worker teardown coverage; no engine, network, or tournament required."""
import errno
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest import mock

import evaluate as ev


AGENTS = '''import os, time

def good(obs, cfg):
    return {"farmer": ["PASS"], "market": []}

def hungry(obs, cfg):
    allocation = bytearray(32 * 1024 * 1024)
    until = time.process_time() + 0.08
    while time.process_time() < until:
        allocation[0] = (allocation[0] + 1) % 256
    time.sleep(5)
    return {}

def zero(obs, cfg):
    os._exit(0)

def abrupt(obs, cfg):
    allocation = bytearray(32 * 1024 * 1024)
    os._exit(23)
'''


class FinalUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "agents.py"
        self.path.write_text(AGENTS)
        self.actors = []

    def tearDown(self):
        for actor in self.actors:
            actor.close()
        self.temp.cleanup()

    def actor(self, name):
        actor = ev.Actor(str(self.path) + "::" + name, self.temp.name, self.path, 123)
        self.actors.append(actor)
        self.assertEqual(actor.ready["kind"], "ready")
        return actor

    def assert_clean(self, actor, expected_code):
        self.assertEqual(actor.report()["exit_code"], expected_code)
        self.assertEqual(actor.proc.returncode, expected_code)
        self.assertTrue(actor.proc.stdin.closed)
        self.assertTrue(actor.proc.stdout.closed)
        self.assertFalse(Path(actor.directory.name).exists())
        report = actor.report()
        actor.close()
        self.assertEqual(report, actor.report())

    @unittest.skipUnless(hasattr(os, "wait4"), "wait4 unavailable")
    def test_timeout_keeps_final_usage_without_procfs(self):
        actor = self.actor("hungry")
        initial = actor.report()
        self.assertEqual(actor.act({}, {}, 0.3)["kind"], "timeout")
        # Simulate the recorded cloud /proc restriction, not the child resource use.
        with mock.patch.object(ev.Path, "read_text", side_effect=PermissionError(errno.EACCES, "procfs unavailable")):
            actor.close()
        report = actor.report()
        self.assertEqual(report["final_resource_sample"], "wait4")
        self.assertEqual(report["resource_sample"], "child_rusage")
        self.assertGreater(report["peak_rss_kib"], initial["peak_rss_kib"] + 16 * 1024)
        self.assertGreater(report["cpu_seconds"], initial["cpu_seconds"] + 0.05)
        self.assert_clean(actor, -signal.SIGKILL)

    @unittest.skipUnless(hasattr(os, "wait4"), "wait4 unavailable")
    def test_abrupt_exit_keeps_usage_and_exit_status(self):
        actor = self.actor("abrupt")
        initial = actor.report()
        self.assertEqual(actor.act({}, {}, 2)["kind"], "process_exit")
        with mock.patch.object(ev.Path, "read_text", side_effect=FileNotFoundError("exited proc")):
            actor.close()
        report = actor.report()
        self.assertEqual(report["final_resource_sample"], "wait4")
        self.assertGreater(report["peak_rss_kib"], initial["peak_rss_kib"] + 16 * 1024)
        self.assert_clean(actor, 23)

    @unittest.skipUnless(hasattr(os, "wait4"), "wait4 unavailable")
    def test_successful_action_and_bounded_cleanup_keep_usage(self):
        actor = self.actor("good")
        self.assertEqual(actor.act({}, {}, 1)["action"], {"farmer": ["PASS"], "market": []})
        actor.close()
        self.assertEqual(actor.report()["final_resource_sample"], "wait4")
        self.assertEqual(actor.report()["calls"], 1)
        # Interpreter shutdown may outlast the existing 100-ms grace.
        self.assertIn(actor.report()["exit_code"], (0, -signal.SIGKILL))
        self.assert_clean(actor, actor.report()["exit_code"])

    @unittest.skipUnless(hasattr(os, "wait4"), "wait4 unavailable")
    def test_zero_exit_status_is_not_confused_with_a_running_child(self):
        actor = self.actor("zero")
        self.assertEqual(actor.act({}, {}, 2)["kind"], "process_exit")
        actor.close()
        self.assertEqual(actor.report()["final_resource_sample"], "wait4")
        self.assert_clean(actor, 0)

    def test_missing_wait4_retains_fallback_and_cleans_up(self):
        actor = self.actor("hungry")
        self.assertEqual(actor.act({}, {}, 0.3)["kind"], "timeout")
        initial = actor.report()
        with mock.patch.object(ev.os, "wait4", None, create=True), mock.patch.object(
            ev.Path, "read_text", side_effect=PermissionError("procfs unavailable")
        ):
            actor.close()
        report = actor.report()
        self.assertEqual(report["final_resource_sample"], "unavailable:wait4_unsupported")
        self.assertEqual(report["cpu_seconds"], initial["cpu_seconds"])
        self.assertEqual(report["peak_rss_kib"], initial["peak_rss_kib"])
        self.assert_clean(actor, -signal.SIGKILL)

    def test_unavailable_wait4_does_not_break_cleanup(self):
        actor = self.actor("abrupt")
        self.assertEqual(actor.act({}, {}, 2)["kind"], "process_exit")
        with mock.patch.object(ev.os, "wait4", side_effect=OSError(errno.ENOSYS, "unsupported"), create=True):
            actor.close()
        self.assertEqual(actor.report()["final_resource_sample"], f"unavailable:wait4_errno_{errno.ENOSYS}")
        self.assert_clean(actor, 23)

    @unittest.skipUnless(hasattr(os, "wait4"), "wait4 unavailable")
    def test_interrupted_wait_retries_without_losing_usage(self):
        actor = self.actor("zero")
        self.assertEqual(actor.act({}, {}, 2)["kind"], "process_exit")
        real_wait4 = os.wait4
        calls = []

        def interrupted_once(pid, options):
            calls.append(pid)
            if len(calls) == 1:
                raise InterruptedError(errno.EINTR, "interrupted")
            return real_wait4(pid, options)

        with mock.patch.object(ev.os, "wait4", side_effect=interrupted_once):
            actor.close()
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(actor.report()["final_resource_sample"], "wait4")
        self.assert_clean(actor, 0)

    def test_previously_reaped_process_preserves_known_status(self):
        actor = self.actor("abrupt")
        self.assertEqual(actor.act({}, {}, 2)["kind"], "process_exit")
        self.assertEqual(actor.proc.wait(timeout=2), 23)
        actor.close()
        self.assertEqual(actor.report()["final_resource_sample"], "unavailable:already_reaped")
        self.assert_clean(actor, 23)

    @unittest.skipUnless(os.name == "posix" and ev.sys.platform.startswith("linux"), "Linux procfs only")
    @unittest.skipUnless(hasattr(os, "wait4"), "wait4 unavailable")
    def test_mismatched_procfs_namespace_never_samples_numeric_child(self):
        actor = self.actor("good")
        self.assertEqual(actor.act({}, {}, 1)["kind"], "action")
        reads = []

        def foreign_procfs(path, *args, **kwargs):
            reads.append(str(path))
            if str(path) == "/proc/self/stat":
                return f"{os.getpid() + 1000000} (parent) S 0 0"
            if str(path).endswith("/status"):
                return "VmHWM:\t134217728 kB\n"
            return f"{actor.proc.pid} (foreign process) " + " ".join(["S"] + ["1000000"] * 20)

        with mock.patch.object(ev.Path, "read_text", autospec=True, side_effect=foreign_procfs):
            actor.close()
        report = actor.report()
        self.assertEqual(reads, ["/proc/self/stat"])
        self.assertEqual(report["resource_sample"], "child_rusage")
        self.assertEqual(report["final_resource_sample"], "wait4")
        self.assertLess(report["cpu_seconds"], 1000)
        self.assertLess(report["peak_rss_kib"], 134217728)
        self.assert_clean(actor, report["exit_code"])

    @unittest.skipUnless(ev.sys.platform.startswith("linux"), "Linux procfs only")
    def test_matching_procfs_namespace_retains_worker_sample(self):
        actor = self.actor("good")
        self.assertEqual(actor.act({}, {}, 1)["kind"], "action")
        reads = []
        ticks = os.sysconf("SC_CLK_TCK")
        fields = ["S"] + ["0"] * 20
        fields[11], fields[12] = str(1200 * ticks), str(34 * ticks)
        samples = {
            "/proc/self/stat": f"{os.getpid()} (parent with spaces) S 0 0",
            f"/proc/{actor.proc.pid}/status": "VmHWM:\t134217728 kB\n",
            f"/proc/{actor.proc.pid}/stat": f"{actor.proc.pid} (worker with ) parentheses) " + " ".join(fields),
        }

        def matching_procfs(path, *args, **kwargs):
            reads.append(str(path))
            return samples[str(path)]

        with mock.patch.object(ev.Path, "read_text", autospec=True, side_effect=matching_procfs):
            actor.close()
        report = actor.report()
        self.assertEqual(reads, list(samples))
        self.assertEqual(report["resource_sample"], "child_rusage_plus_linux_procfs")
        self.assertEqual(report["cpu_seconds"], 1234)
        self.assertEqual(report["peak_rss_kib"], 134217728)
        self.assert_clean(actor, report["exit_code"])

    @unittest.skipUnless(ev.sys.platform.startswith("linux"), "Linux procfs only")
    def test_unavailable_or_malformed_procfs_identity_keeps_child_fallback(self):
        for self_sample in (PermissionError("procfs unavailable"), "", "invalid (parent) S 0 0"):
            with self.subTest(self_sample=repr(self_sample)):
                actor = self.actor("good")
                self.assertEqual(actor.act({}, {}, 1)["kind"], "action")
                initial = actor.report()
                reads = []

                def unavailable_identity(path, *args, **kwargs):
                    reads.append(str(path))
                    if str(path) == "/proc/self/stat":
                        if isinstance(self_sample, Exception):
                            raise self_sample
                        return self_sample
                    return "VmHWM:\t134217728 kB\n"

                with mock.patch.object(ev.Path, "read_text", autospec=True, side_effect=unavailable_identity), mock.patch.object(
                    ev.os, "wait4", None, create=True
                ):
                    actor.close()
                report = actor.report()
                self.assertEqual(reads, ["/proc/self/stat"])
                self.assertEqual(report["resource_sample"], "child_rusage")
                self.assertEqual(report["final_resource_sample"], "unavailable:wait4_unsupported")
                self.assertEqual(report["cpu_seconds"], initial["cpu_seconds"])
                self.assertEqual(report["peak_rss_kib"], initial["peak_rss_kib"])
                self.assert_clean(actor, report["exit_code"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
