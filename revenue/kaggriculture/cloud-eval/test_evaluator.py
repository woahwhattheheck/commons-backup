"""Unit fault injection plus opt-in REAL pinned-interpreter tests.

KAG_EVAL_ENGINE_DIR enables the live tests; CI requires them, never silently skips.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest

import evaluate as ev

AGENTS = '''import random, time, os
count = 0
def good(obs, cfg):
    return {"farmer": ["PASS"], "market": []}
def one(obs):
    return {}
def counter(obs, cfg):
    global count
    count += 1
    obs["private"]["probe"] = count
    return {"count": count, "farmer": ["PASS"]}
def rng(obs, cfg):
    return {"value": random.randrange(100000000)}
def crash(obs, cfg):
    raise RuntimeError("injected crash")
def die(obs, cfg):
    os._exit(23)
def hang(obs, cfg):
    time.sleep(5)
    return {}
def hungry(obs, cfg):
    value = bytearray(32 * 1024 * 1024)
    time.sleep(5)
    return {}
def bad(obs, cfg):
    return ["PASS"]
def nan(obs, cfg):
    return {"value": float("nan")}
def huge(obs, cfg):
    return {"value": "x" * 3000000}
def noisy(obs, cfg):
    print("agent log is not protocol")
    return {}
def partial(obs, cfg):
    os.write(1, b'{"kind":')
    time.sleep(5)
    return {}
def checks(obs, cfg):
    assert cfg.get("seed") is None
    assert "seed" not in obs and "info" not in obs
    assert isinstance(obs.private, dict)
    assert "private" not in obs.farms[1 - obs.player]
    assert obs.remainingOverageTime == 0
    return {"farmer": ["PASS"]}
'''


class ActorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "agents.py"
        self.path.write_text(AGENTS)
        self.actors = []

    def tearDown(self):
        for actor in self.actors:
            actor.close()
        self.temp.cleanup()

    def actor(self, name, seed=123):
        actor = ev.Actor(str(self.path) + "::" + name, self.temp.name, self.path, seed)
        self.actors.append(actor)
        return actor

    def test_two_argument_agent(self):
        actor = self.actor("good")
        self.assertEqual(actor.ready["kind"], "ready")
        self.assertEqual(actor.act({}, {}, 1)["action"]["farmer"], ["PASS"])
        self.assertGreater(actor.report()["peak_rss_kib"], 0)

    def test_one_argument_agent(self):
        self.assertEqual(self.actor("one").act({}, {}, 1)["action"], {})

    def test_state_persists_only_in_own_process(self):
        first, second = self.actor("counter"), self.actor("counter")
        obs = {"private": {}}
        self.assertEqual(first.act(obs, {}, 1)["action"]["count"], 1)
        self.assertEqual(first.act(obs, {}, 1)["action"]["count"], 2)
        self.assertEqual(second.act(obs, {}, 1)["action"]["count"], 1)
        self.assertEqual(obs, {"private": {}})

    def test_independent_seed_repeat(self):
        a, b, c = self.actor("rng", 29), self.actor("rng", 29), self.actor("rng", 31)
        x = a.act({}, {}, 1)["action"]
        self.assertEqual(x, b.act({}, {}, 1)["action"])
        self.assertNotEqual(x, c.act({}, {}, 1)["action"])

    def test_crash(self):
        result = self.actor("crash").act({}, {}, 1)
        self.assertEqual(result["kind"], "crash")
        self.assertIn("injected crash", result["error"])

    def test_abrupt_exit(self):
        self.assertEqual(self.actor("die").act({}, {}, 1)["kind"], "process_exit")

    def test_hard_timeout(self):
        actor = self.actor("hang")
        before = time.monotonic()
        self.assertEqual(actor.act({}, {}, 0.1)["kind"], "timeout")
        self.assertLess(time.monotonic() - before, 1.0)

    def test_partial_frame_timeout(self):
        actor = self.actor("partial")
        before = time.monotonic()
        self.assertEqual(actor.act({}, {}, 0.1)["kind"], "timeout")
        self.assertLess(time.monotonic() - before, 1.0)

    @unittest.skipUnless(hasattr(os, "wait4") or os.path.isdir("/proc"), "OS child resource measurement")
    def test_timeout_resource_measurement(self):
        actor = self.actor("hungry")
        initial_rss = actor.report()["peak_rss_kib"]
        self.assertEqual(actor.act({}, {}, 0.2)["kind"], "timeout")
        try:
            # The independent reference must also use the worker's PID view.
            if int(Path("/proc/self/stat").read_text().split(maxsplit=1)[0]) != os.getpid():
                raise ValueError("procfs PID namespace differs from process APIs")
            status = Path(f"/proc/{actor.proc.pid}/status").read_text()
            observed = int(next(line for line in status.splitlines() if line.startswith("VmHWM:")).split()[1])
        except (OSError, ValueError, IndexError):
            observed = None
        actor.close()
        report = actor.report()
        if observed is not None:
            self.assertGreaterEqual(report["peak_rss_kib"], observed)
            self.assertEqual(report["resource_sample"], "child_rusage_plus_linux_procfs")
        else:
            self.assertEqual(report["final_resource_sample"], "wait4")
            self.assertGreater(report["peak_rss_kib"], initial_rss + 8 * 1024)
        self.assertEqual(report["exit_code"], -9)

    def test_invalid_actions(self):
        for name in ("bad", "nan", "huge"):
            with self.subTest(name=name):
                self.assertEqual(self.actor(name).act({}, {}, 1)["kind"], "invalid_action")

    def test_logs_do_not_break_protocol(self):
        self.assertEqual(self.actor("noisy").act({}, {}, 1)["kind"], "action")

    def test_load_failure(self):
        self.assertEqual(self.actor("missing").ready["kind"], "load_error")

    def test_packet_size(self):
        self.assertEqual(self.actor("good").act({"large": "x" * ev.MAX_PACKET}, {}, 1)["kind"], "protocol_error")


class SummaryTests(unittest.TestCase):
    def test_failures_do_not_become_wins(self):
        rows = [dict(opponent="r", status="complete", candidate_seat=0, scores=[8, 3]),
                dict(opponent="r", status="complete", candidate_seat=1, scores=[5, 5]),
                dict(opponent="r", status="complete", candidate_seat=1, scores=[9, 1]),
                dict(opponent="r", status="failed", candidate_seat=0, scores=None, failure={"seat": 1}),
                dict(opponent="r", status="failed", candidate_seat=1, scores=None, failure={"seat": 1})]
        result = ev.summarize(rows)["r"]
        self.assertEqual((result["wins"], result["ties"], result["losses"], result["failed"]), (1, 1, 1, 2))
        self.assertEqual(result["candidate_failures"], 1)
        self.assertEqual(result["opponent_failures"], 1)
        self.assertEqual(result["mean_margin"], -1)

    def test_no_valid_games_has_no_mean(self):
        row = dict(opponent="r", status="failed", candidate_seat=0, scores=None, failure={"seat": None})
        self.assertIsNone(ev.summarize([row])["r"]["mean_margin"])

    def test_corrupt_source_is_rejected_before_loading(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "kaggriculture.py").write_text("raise AssertionError('must not execute')")
            with self.assertRaisesRegex(ValueError, "source mismatch"):
                ev.get_engine(root, Path(root) / "missing-loader.py")

    def test_missing_source_is_not_downloaded(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(FileNotFoundError):
                ev.get_engine(root, Path(root) / "missing-loader.py")
            self.assertEqual(list(Path(root).iterdir()), [])


@unittest.skipUnless(os.environ.get("KAG_EVAL_ENGINE_DIR"), "Live engine cache not supplied")
class OfficialEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cache = Path(os.environ["KAG_EVAL_ENGINE_DIR"])
        cls.engine, cls.hashes = ev.get_engine(cls.cache)
        cls.temp = tempfile.TemporaryDirectory()
        cls.agent = Path(cls.temp.name) / "probes.py"
        cls.agent.write_text(AGENTS)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def play(self, left="good", right="good", seed=2027, seat=0, steps=25, timeout=1):
        return ev.play(self.engine, [str(self.agent) + "::" + left, str(self.agent) + "::" + right],
                       self.cache, ev.LOADER, seed, seat, action_timeout=timeout, episode_steps=steps)

    def test_terminal_step_and_score(self):
        result = self.play()
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["steps"], 24)  # episodeSteps includes the initial state.
        self.assertEqual(result["scores"], [3000, 3000])
        self.assertEqual(result["daily_bank"][-1]["bank"], [3000, 3000])

    def test_actual_observation_privacy_and_hidden_seed(self):
        self.assertEqual(self.play("checks", "checks")["status"], "complete")

    def test_environment_repeatability(self):
        first, second = self.play(seed=6607), self.play(seed=6607)
        self.assertEqual(first["trace_sha256"], second["trace_sha256"])
        self.assertEqual(first["scores"], second["scores"])

    def test_environment_seed_changes_state(self):
        first, second = self.play(seed=31, steps=241), self.play(seed=104729, steps=241)
        self.assertNotEqual(first["trace_sha256"], second["trace_sha256"])

    def test_agent_crash_has_no_final_score(self):
        result = self.play("crash")
        self.assertEqual(result["failure"]["kind"], "crash")
        self.assertEqual(result["failure"]["seat"], 0)
        self.assertIsNone(result["scores"])
        self.assertEqual(result["steps"], 0)

    def test_opponent_timeout_has_no_final_score(self):
        result = self.play("good", "hang", timeout=0.1)
        self.assertEqual(result["failure"]["kind"], "timeout")
        self.assertEqual(result["failure"]["seat"], 1)
        self.assertIsNone(result["scores"])

    def test_compact_policy_is_read_only_and_isolated(self):
        source = ev.LOADER.with_name("main.py")
        before = ev.sha256(source)
        candidate = ev.import_file(source, "candidate_policy_probe")
        policy = dict(candidate.POLICY)
        opponents = ev.import_file(ev.HERE / "opponents.py", "opponent_policy_probe")
        opponents.compact_no_expansion({"farms": []}, {})
        self.assertEqual(opponents._COMPACT.POLICY["animal_cap"], 22)
        self.assertFalse(opponents._COMPACT.POLICY["expansion"])
        self.assertEqual(opponents._COMPACT.POLICY["max_hands"], 9)
        self.assertEqual(candidate.POLICY, policy)
        self.assertEqual(ev.sha256(source), before)

    def test_player_positions(self):
        left = ev.play(self.engine, [str(self.agent) + "::good", "official_starter"], self.cache,
                       ev.LOADER, 2027, 0, episode_steps=49)
        right = ev.play(self.engine, ["official_starter", str(self.agent) + "::good"], self.cache,
                        ev.LOADER, 2027, 1, episode_steps=49)
        self.assertEqual(left["status"], "complete")
        self.assertEqual(right["status"], "complete")
        self.assertEqual(left["scores"][0], right["scores"][1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
