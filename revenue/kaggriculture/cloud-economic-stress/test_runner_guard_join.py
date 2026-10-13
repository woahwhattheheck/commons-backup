# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual stress-runner deadline path, not the adapter in isolation.

Optional --runtime/--engine/--frame-stream adds three real-source join methods.
The retained frame provides initial state; no new game or random seed is drawn.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sys
import time
import types
import unittest
from unittest.mock import patch

R = None
ARGS = None
DETAILS = []
SELECTED = {"farmer": ["WEST"], "hands": [["CARE"]],
            "market": [["SELL", "MILK", 2]]}
CHANGED = {"farmer": ["WEST"], "hands": [["CARE"]],
           "market": [["SELL", "MILK", 3]]}


def observation(step=100):
    farm = {"money": 3000, "hires_today": 0, "unlocked_quadrants": ["NW"],
            "farmer": [4, 4], "hands": [[0, 0]],
            "tiles": [[None] * 10 for _ in range(10)]}
    return {"step": step, "day": step // 24, "hour": step % 24, "player": 0,
            "farms": [farm, copy.deepcopy(farm)],
            "private": {"shed": {"MILK": 2}, "inventories": [{"MILK": 1}, {}]},
            "market": {"prices": {"MILK": 160}}}


class Owner:
    def __init__(self, production=None, transform=None):
        self.production_body = production
        self.transform_body = transform
        self.production_calls = self.transform_calls = 0
        self.diagnostics = {"status": "not_called"}
        self.last_packet = None
        self.production = types.SimpleNamespace(act=self.produce)

    def produce(self, obs):
        self.production_calls += 1
        return self.production_body(obs) if self.production_body else copy.deepcopy(SELECTED)

    def transform(self, obs, cfg, selected, **kwargs):
        self.transform_calls += 1
        if self.transform_body:
            return self.transform_body(obs, cfg, selected, **kwargs)
        self.diagnostics = {"status": "selected", "seed_reason": "fixture"}
        return copy.deepcopy(CHANGED)


def actor(owner=None, budget=.04, **kwargs):
    owner = owner or Owner()
    module = types.SimpleNamespace(make_agent=lambda **_: owner)
    return R.InstrumentedIntegrated(module, deadline_s=budget, **kwargs), owner


class RunnerJoinTests(unittest.TestCase):
    def setUp(self):
        self.handler = signal.getsignal(signal.SIGALRM)
        self.timer = signal.setitimer(signal.ITIMER_REAL, 0)

    def tearDown(self):
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.handler)
        signal.setitimer(signal.ITIMER_REAL, *self.timer)

    def test_natural_production_is_inside_guard(self):
        finished = []
        def produce(obs):
            time.sleep(.12); finished.append(True); return copy.deepcopy(SELECTED)
        a, o = actor(Owner(production=produce))
        started = time.perf_counter()
        try:
            out = a(observation())
        finally:
            DETAILS.append({"case": "natural_production", "elapsed": time.perf_counter()-started,
                            "finished": bool(finished), "production_calls": o.production_calls,
                            "transform_calls": o.transform_calls})
        self.assertFalse(finished)
        self.assertEqual(out, R.deadline_fix.legal_pass(observation()))
        self.assertEqual((o.production_calls, o.transform_calls, a.timeouts), (1, 0, 1))
        self.assertEqual(a.calls[-1]["fallback_stage"], "production")

    def test_transform_cannot_swallow_guard_cancellation(self):
        swallowed = []
        def transform(*args, **kwargs):
            try:
                time.sleep(.12)
            except Exception:
                swallowed.append(True)
            return copy.deepcopy(CHANGED)
        a, o = actor(Owner(transform=transform))
        started = time.perf_counter(); out = a(observation())
        DETAILS.append({"case": "swallowed_transform", "elapsed": time.perf_counter()-started,
                        "swallowed": bool(swallowed), "timeouts": a.timeouts})
        self.assertFalse(swallowed)
        self.assertEqual(out, SELECTED)
        self.assertEqual((o.production_calls, o.transform_calls, a.timeouts), (1, 1, 1))

    def test_production_cannot_swallow_guard_cancellation(self):
        swallowed = []
        def produce(obs):
            try:
                time.sleep(.12)
            except Exception:
                swallowed.append(True)
            return copy.deepcopy(SELECTED)
        a, o = actor(Owner(production=produce))
        out = a(observation())
        self.assertFalse(swallowed)
        self.assertEqual(out, R.deadline_fix.legal_pass(observation()))
        self.assertEqual(o.transform_calls, 0)

    def test_completed_path_keeps_action_diagnostics_and_one_parent(self):
        a, o = actor(budget=.5)
        self.assertEqual(a(observation()), CHANGED)
        self.assertEqual((o.production_calls, o.transform_calls), (1, 1))
        row = a.calls[-1]
        self.assertEqual((row["selected"], row["output"]), (SELECTED, CHANGED))
        self.assertEqual((row["status"], row["seed_reason"], row["timed_out"]),
                         ("selected", "fixture", False))

    def test_no_deadline_keeps_direct_behavior(self):
        a, o = actor(budget=None)
        with patch.object(R.deadline_fix, "DeadlineFallbackAgent", side_effect=AssertionError("guard")):
            self.assertEqual(a(observation()), CHANGED)
        self.assertEqual((o.production_calls, o.transform_calls, a.timeouts), (1, 1, 0))

    def test_deadline_path_uses_existing_guard_once(self):
        a, _ = actor(budget=.5)
        guard = R.deadline_fix.DeadlineFallbackAgent
        with patch.object(R.deadline_fix, "DeadlineFallbackAgent", wraps=guard) as used:
            a(observation())
        self.assertEqual(used.call_count, 1)

    def test_input_is_detached_in_both_modes(self):
        def produce(obs):
            obs["farms"][0]["money"] = 9
            return copy.deepcopy(SELECTED)
        for budget in (None, .5):
            a, _ = actor(Owner(production=produce), budget)
            obs = observation(); before = copy.deepcopy(obs)
            a(obs)
            self.assertEqual(obs, before)

    def test_original_production_exception_propagates(self):
        error = ValueError("producer failure")
        def produce(obs): raise error
        a, o = actor(Owner(production=produce))
        with self.assertRaises(ValueError) as caught: a(observation())
        self.assertIs(caught.exception, error)
        self.assertEqual((o.transform_calls, a.timeouts, a.calls), (0, 0, []))

    def test_original_transform_exception_propagates(self):
        error = RuntimeError("transform failure")
        def transform(*args, **kwargs): raise error
        a, _ = actor(Owner(transform=transform))
        with self.assertRaises(RuntimeError) as caught: a(observation())
        self.assertIs(caught.exception, error)
        self.assertEqual((a.timeouts, a.calls), (0, []))

    def test_foreign_cancellation_propagates(self):
        error = R.deadline_fix.DeadlineExceeded("foreign cancellation")
        def transform(*args, **kwargs): raise error
        a, _ = actor(Owner(transform=transform))
        with self.assertRaises(R.deadline_fix.DeadlineExceeded) as caught: a(observation())
        self.assertIs(caught.exception, error)
        self.assertEqual(a.timeouts, 0)

    def test_earlier_caller_alarm_remains_caller_exception(self):
        error = LookupError("caller deadline")
        def outer(*_): raise error
        def transform(*args, **kwargs): time.sleep(.07); return CHANGED
        a, _ = actor(Owner(transform=transform), .2)
        signal.signal(signal.SIGALRM, outer)
        signal.setitimer(signal.ITIMER_REAL, .02)
        with self.assertRaises(LookupError) as caught: a(observation())
        self.assertIs(caught.exception, error)
        self.assertEqual(a.timeouts, 0)
        self.assertIs(signal.getsignal(signal.SIGALRM), outer)

    def test_later_caller_alarm_is_not_erased(self):
        def outer(*_): pass
        a, _ = actor(budget=.1)
        signal.signal(signal.SIGALRM, outer)
        signal.setitimer(signal.ITIMER_REAL, .4)
        a(observation())
        remaining, interval = signal.getitimer(signal.ITIMER_REAL)
        self.assertGreater(remaining, .1)
        self.assertLess(remaining, .4)
        self.assertEqual(interval, 0)
        self.assertIs(signal.getsignal(signal.SIGALRM), outer)

    def test_periodic_caller_alarm_retains_cadence(self):
        fired = []
        def outer(*_): fired.append(time.monotonic())
        def transform(*args, **kwargs): time.sleep(.06); return CHANGED
        a, _ = actor(Owner(transform=transform), .3)
        signal.signal(signal.SIGALRM, outer)
        signal.setitimer(signal.ITIMER_REAL, .01, .015)
        self.assertEqual(a(observation()), CHANGED)
        remaining, interval = signal.getitimer(signal.ITIMER_REAL)
        self.assertGreaterEqual(len(fired), 2)
        self.assertGreater(remaining, 0)
        self.assertAlmostEqual(interval, .015, places=5)

    def test_injected_production_interrupts_before_parent(self):
        a, o = actor(inject_step=100, inject_stage="production", inject_seconds=.12)
        self.assertEqual(a(observation()), R.deadline_fix.legal_pass(observation()))
        self.assertEqual((o.production_calls, o.transform_calls, a.timeouts), (0, 0, 1))

    def test_injected_transform_keeps_exact_selected(self):
        a, o = actor(inject_step=100, inject_stage="transform", inject_seconds=.12)
        self.assertEqual(a(observation()), SELECTED)
        self.assertEqual((o.production_calls, o.transform_calls, a.timeouts), (1, 0, 1))

    def test_short_production_injection_runs_only_in_production(self):
        a, o = actor(budget=.5, inject_step=100, inject_stage="production", inject_seconds=.001)
        calls = []
        def pause(seconds): calls.append((o.production_calls, o.transform_calls, seconds))
        with patch.object(R.time, "sleep", side_effect=pause): a(observation())
        self.assertEqual(calls, [(0, 0, .001)])

    def test_nonmatching_injection_does_not_sleep(self):
        a, _ = actor(budget=.5, inject_step=101)
        with patch.object(R.time, "sleep", side_effect=AssertionError("unexpected delay")):
            self.assertEqual(a(observation()), CHANGED)

    def test_terminal_legacy_and_repaired_treatments_remain_distinct(self):
        obs = observation(718)
        for mode in ("pass", "terminal_liquidation"):
            a, o = actor(inject_step=718, inject_stage="production", inject_seconds=.12)
            a.production_timeout_fallback = mode
            out = a(obs)
            expected = (R.deadline_fix.legal_pass(obs) if mode == "pass" else
                        R.deadline_fix.terminal_liquidation_fallback(obs))
            self.assertEqual(out, expected)
            self.assertEqual((o.production_calls, o.transform_calls), (0, 0))

    def test_production_delay_does_not_get_a_second_full_budget(self):
        def produce(obs): time.sleep(.03); return copy.deepcopy(SELECTED)
        finished = []
        def transform(*args, **kwargs):
            time.sleep(.07); finished.append(True); return CHANGED
        a, o = actor(Owner(production=produce, transform=transform), .06)
        self.assertEqual(a(observation()), SELECTED)
        self.assertFalse(finished)
        self.assertEqual((o.production_calls, o.transform_calls, a.timeouts), (1, 1, 1))

    def test_repeated_calls_keep_one_persistent_owner(self):
        a, o = actor(budget=.5)
        for step in (100, 101, 102): a(observation(step))
        self.assertIs(a.owner, o)
        self.assertEqual((o.production_calls, o.transform_calls, len(a.calls)), (3, 3, 3))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def structify(value):
    if isinstance(value, dict): return R.Struct({k: structify(v) for k, v in value.items()})
    if isinstance(value, list): return [structify(v) for v in value]
    return value


class ActualSourceJoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = json.loads((ARGS.runtime / "SOURCE.json").read_text())
        for name, item in manifest["runtime"].items():
            if digest(ARGS.runtime/name) != item["sha256"]:
                raise ValueError("Runtime source mismatch: " + name)
        cls.engine = R.load_engine(ARGS.engine)
        with gzip.open(ARGS.frame_stream, "rt") as f: cls.frame = json.loads(next(f))
        if cls.frame["frame"] != 0: raise ValueError("Expected retained initial frame")
        cls.module = R.load_runtime(ARGS.runtime)

    def test_real_persistent_producer_transform_and_official_transitions(self):
        rows = []
        for seat in (0, 1):
            state = structify(copy.deepcopy(self.frame["state"]))
            cfg = structify(copy.deepcopy(self.frame["configuration"]))
            env = R.Struct(configuration=cfg, done=False, info=copy.deepcopy(self.frame["info"]))
            natural = R.InstrumentedIntegrated(self.module)
            guarded = R.InstrumentedIntegrated(self.module, deadline_s=1.0)
            rival = R.intact_arlene(ARGS.runtime)
            with patch.object(guarded.owner.production, "act", wraps=guarded.owner.production.act) as prod, \
                 patch.object(guarded.owner.controller, "act", wraps=guarded.owner.controller.act) as parent, \
                 patch.object(guarded.owner, "transform", wraps=guarded.owner.transform) as transform:
                for step in range(3):
                    obs = copy.deepcopy(state[seat].observation); obs["step"] = step
                    before = copy.deepcopy(obs)
                    expected = natural(obs, cfg); actual = guarded(obs, cfg)
                    self.assertEqual(actual, expected); self.assertEqual(obs, before)
                    self.assertEqual(guarded.calls[-1]["selected"], natural.calls[-1]["selected"])
                    self.assertEqual(guarded.owner.diagnostics, natural.owner.diagnostics)
                    state[seat].action = actual
                    other = copy.deepcopy(state[1-seat].observation); other["step"] = step
                    state[1-seat].action = rival(other, cfg)
                    for s in state: s.observation.step = step
                    self.engine.interpreter(state, env)
                    rows.append({"seat": seat, "step": step, "action": actual,
                                 "status": guarded.calls[-1]["status"]})
                self.assertEqual((prod.call_count, parent.call_count, transform.call_count), (3, 3, 3))
        DETAILS.append({"case": "real_prefix", "rows": rows,
                        "guarded_calls": 6, "control_calls": 6, "official_transitions": 6})

    def test_real_transform_deadline_returns_selected_with_stage_receipt(self):
        # Interrupt inside the actual transform by delaying its ordinary
        # atlas._units dependency. The caller still gets the exact selected action.
        for seat in (0, 1):
            a = R.InstrumentedIntegrated(self.module, deadline_s=.08)
            obs = copy.deepcopy(self.frame["state"][seat]["observation"]); obs["step"] = 0
            cfg = self.frame["configuration"]
            original_units = self.module.atlas._units
            def delayed(*args, **kwargs):
                time.sleep(.2)
                return original_units(*args, **kwargs)
            with patch.object(a.owner.production, "act", wraps=a.owner.production.act) as prod, \
                 patch.object(self.module.atlas, "_units", side_effect=delayed):
                out = a(obs, cfg)
            self.assertEqual(prod.call_count, 1)
            self.assertEqual(a.timeouts, 1)
            self.assertTrue(a.calls[-1]["timed_out"])
            self.assertEqual(a.calls[-1].get("fallback_stage"), "transform")
            self.assertEqual(out, a.calls[-1]["selected"])
            DETAILS.append({"case": "real_transform_cancellation", "seat": seat,
                            "elapsed": a.calls[-1]["elapsed_s"], "output": out,
                            "timeouts": a.timeouts})


    def test_actual_planoverlay_commit_is_cancelled_through_runner(self):
        # A manufactured bookkeeping invocation reaches the ACTUAL unchanged
        # PlanOverlay._commit broad Exception handler, inside the real runner.
        # It is not represented as a naturally chosen errand or a full game.
        for seat in (0, 1):
            a = R.InstrumentedIntegrated(self.module, deadline_s=.08)
            policy = a.owner.production
            original_act = policy.act
            obs = copy.deepcopy(self.frame["state"][seat]["observation"]); obs["step"] = 0
            calls = []
            def delayed_risk(*args):
                calls.append("risk"); time.sleep(.2); return 1
            def with_commit(obs):
                policy._commit({"errand_id": "runner-guard-test"},
                               {"at": [4, 4], "product": "MILK", "units": 1},
                               obs, 0, 0, seat)
                return original_act(obs)
            with patch.object(policy, "act", side_effect=with_commit) as prod, \
                 patch.object(policy.chooser, "at_risk", side_effect=delayed_risk), \
                 patch.object(a.owner, "transform", wraps=a.owner.transform) as transform:
                out = a(obs, self.frame["configuration"])
            self.assertEqual(prod.call_count, 1)
            self.assertEqual(calls, ["risk"])
            self.assertNotIn("runner-guard-test", policy.errands)
            self.assertEqual(transform.call_count, 0)
            self.assertEqual(out, R.deadline_fix.legal_pass(obs))
            self.assertEqual(a.calls[-1].get("fallback_stage"), "production")
            DETAILS.append({"case": "actual_commit_cancellation", "seat": seat,
                            "elapsed": a.calls[-1]["elapsed_s"], "timeouts": a.timeouts,
                            "committed": "runner-guard-test" in policy.errands})


def main():
    global ARGS, R
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path, default=Path(__file__).with_name("runner.py"))
    parser.add_argument("--runtime", type=Path)
    parser.add_argument("--engine", type=Path)
    parser.add_argument("--frame-stream", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    ARGS = parser.parse_args()
    options = (ARGS.runtime, ARGS.engine, ARGS.frame_stream)
    if any(options) and not all(options): parser.error("Supply all three actual-source arguments")
    ARGS.runner = ARGS.runner.resolve()
    sys.path.insert(0, str(ARGS.runner.parent))
    R = load(ARGS.runner, "stress_runner_under_test")
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RunnerJoinTests)
    if all(options): suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(ActualSourceJoinTests))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"runner_sha256": digest(ARGS.runner),
              "adapter_sha256": digest(ARGS.runner.with_name("deadline_adapter.py")),
              "test_sha256": digest(__file__), "tests_run": result.testsRun,
              "failures": [[str(t), e] for t, e in result.failures],
              "errors": [[str(t), e] for t, e in result.errors],
              "skipped": [[str(t), e] for t, e in result.skipped], "details": DETAILS,
              "full_games": 0, "new_game_seeds": [], "actual_source": bool(all(options))}
    if all(options):
        report["actual_inputs"] = {"runtime_manifest": digest(ARGS.runtime/"SOURCE.json"),
                                  "engine": digest(ARGS.engine/"kaggriculture.py"),
                                  "seed_helper": digest(ARGS.engine/"utils.py"),
                                  "frame_stream": digest(ARGS.frame_stream)}
    ARGS.report.parent.mkdir(parents=True, exist_ok=True)
    ARGS.report.write_text(json.dumps(report, indent=2)+"\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
