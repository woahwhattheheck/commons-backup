# SPDX-License-Identifier: Apache-2.0
"""Execute the pinned native return seam, not a replacement runtime.

Arguments are paths to a materialized native package and the two existing
canonical V4 donor modules. The official interpreter is loaded from that
package's preserved checks/reference/engine, without network or game stubs.
Controlled final-action witnesses are not natural policy engagement.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import port_native_eod as port

COUNTS = {"paired_interpreter_cells": 0, "rescue_activations": 0,
          "native_finalizer_calls": 0, "natural_opening_callbacks": 0}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class NativeEod(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="native-eod-test-")
        cls.root = Path(cls.tmp.name)
        cls.on = cls.root / "on"
        cls.off = cls.root / "off"
        cls.receipt = port.stage(ARGS.package, ARGS.donor, ARGS.h3c, cls.on, enabled=True)
        port.stage(ARGS.package, ARGS.donor, ARGS.h3c, cls.off, enabled=False)
        if ARGS.mutant:
            caller = cls.on / "main.py"
            text = caller.read_text()
            if ARGS.mutant == "disabled":
                text = text.replace("return apply_eod_capacity_rescue(returned, obs, cfg, enabled=True)", "return returned")
            elif ARGS.mutant == "stale-queue":
                text = text.replace("apply_eod_capacity_rescue(returned, obs, cfg, enabled=True)", "apply_eod_capacity_rescue(selected, obs, cfg, enabled=True)")
            elif ARGS.mutant == "fallback-on":
                text = text.replace("            if self.diagnostics.get('status') != 'completed':\n                return returned\n", "")
            elif ARGS.mutant == "after-receipts":
                text = text.replace("return apply_eod_capacity_rescue(returned, obs, cfg, enabled=True)", "return returned")
                text = text.replace("    admission = None", """        def _finish_production(self, obs, returned, cfg=None):
            result = super()._finish_production(obs, returned, cfg)
            from r04_eod_capacity_rescue import apply_eod_capacity_rescue
            return apply_eod_capacity_rescue(result, obs, cfg or {}, enabled=True)

    admission = None""")
            elif ARGS.mutant == "partial-budget":
                helper = cls.on / "r04_eod_capacity_rescue.py"
                helper.write_text(helper.read_text().replace("len(market) + len(discarded)", "len(market)"))
            elif ARGS.mutant == "legacy-import":
                helper = cls.on / "r04_eod_capacity_rescue.py"
                helper.write_bytes(helper.read_bytes().replace(port.NEW_IMPORT, port.OLD_IMPORT))
            else:
                raise ValueError("unknown mutation control")
            caller.write_text(text)
        sys.path.insert(0, str(cls.on))
        cls.main_on = load("native_eod_on_main", cls.on / "main.py")
        cls.main_off = load("native_eod_off_main", cls.off / "main.py")
        cls.runtime = __import__("titan_runtime")
        cls.rescue = __import__("r04_eod_capacity_rescue")
        cls.ev = load("native_eod_evaluator", cls.on / "checks/reference/evaluator/evaluate.py")
        cls.engine, cls.engine_hashes = cls.ev.get_engine(
            cls.on / "checks/reference/engine", cls.on / "checks/reference/evaluator/loader.py")
        cls.features = json.loads((cls.on / "TITAN-CONFIG.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def fixture(self, seat=0, step=119, shed=None, cargo=None, market=None, rival=(), floor=False):
        e, S = self.engine, self.ev.Struct
        cfg = S({k: v.get("default") if isinstance(v, dict) else v
                 for k, v in e.specification["configuration"].items()})
        cfg.weedSpawnChance = 0
        cfg.seed = 9611911
        farms = [e._new_farm(10, 10000), e._new_farm(10, 10000)]
        cargo = copy.deepcopy(cargo if cargo is not None else [{"WHEAT": 2}, {"WHEAT": 1}])
        farms[seat]["hands"] = [[4, 4] for _ in cargo[1:]]
        public_market = e._new_market()
        if floor:
            public_market["inventory"] = {p: 1000000 for p in e.PRODUCTS}
            e._refresh_prices(public_market)
        state = []
        for player in (0, 1):
            private = e._new_private()
            private["shed"] = copy.deepcopy(shed if shed is not None else {"WHEAT": 99}) if player == seat else {"WHEAT": 40}
            private["inventories"] = copy.deepcopy(cargo) if player == seat else [{}]
            obs = S(step=step, day=step // 24, hour=step % 24, player=player,
                    farms=farms, private=private, market=public_market, town=e._new_town())
            action = {"farmer": ["PASS"], "hands": [["PASS"] for _ in farms[player]["hands"]],
                      "market": copy.deepcopy(list(market or []) if player == seat else list(rival))}
            state.append(S(observation=obs, action=action, status="ACTIVE", reward=0))
        return state, S(configuration=cfg, info={"seed": 9611911}, done=False)

    def instance(self, on=True):
        obj = (self.main_on if on else self.main_off)._new_instance(self.on, self.features)
        obj._initialize()
        obj.diagnostics = {"status": "completed"}
        return obj

    def finish(self, obj, obs, action, cfg):
        COUNTS["native_finalizer_calls"] += 1
        return obj._finish_production(copy.deepcopy(obs), copy.deepcopy(action), cfg)

    def pair(self, *, seat=0, expect_change=True, **kwargs):
        state, env = self.fixture(seat=seat, **kwargs)
        control, candidate = copy.deepcopy(state), copy.deepcopy(state)
        env0, env1 = copy.deepcopy(env), copy.deepcopy(env)
        baseline = self.finish(self.instance(False), control[seat].observation, control[seat].action, env0.configuration)
        changed = self.finish(self.instance(), candidate[seat].observation, candidate[seat].action, env1.configuration)
        self.assertEqual(changed != baseline, expect_change)
        control[seat].action, candidate[seat].action = baseline, changed
        self.engine.interpreter(control, env0)
        self.engine.interpreter(candidate, env1)
        self.assertEqual(candidate[seat].observation.private, control[seat].observation.private)
        f0, f1 = copy.deepcopy(control[0].observation.farms), copy.deepcopy(candidate[0].observation.farms)
        own_delta = f1[seat]["money"] - f0[seat]["money"]
        rival_delta = f1[1-seat]["money"] - f0[1-seat]["money"]
        for farms in (f0, f1):
            for farm in farms:
                farm.pop("money")
        self.assertEqual(f1, f0)
        self.assertGreaterEqual(own_delta, 0)
        COUNTS["paired_interpreter_cells"] += 1
        COUNTS["rescue_activations"] += int(expect_change)
        return baseline, changed, own_delta, rival_delta

    def test_01_disabled_package_is_byte_identical(self):
        original = {p.relative_to(ARGS.package): p.read_bytes() for p in ARGS.package.rglob("*") if p.is_file()}
        staged = {p.relative_to(self.off): p.read_bytes() for p in self.off.rglob("*")
                  if p.is_file() and "__pycache__" not in p.parts}
        original = {k: v for k, v in original.items() if "__pycache__" not in k.parts}
        self.assertEqual(staged, original)
        self.assertEqual((self.on / "TITAN-CONFIG.json").read_bytes(), (ARGS.package / "TITAN-CONFIG.json").read_bytes())
        self.assertEqual((self.on / "titan_runtime.py").read_bytes(), (ARGS.package / "titan_runtime.py").read_bytes())

    def test_02_port_changes_only_existing_product_import(self):
        native = (self.on / "r04_eod_capacity_rescue.py").read_bytes()
        self.assertEqual(native.replace(port.NEW_IMPORT, port.OLD_IMPORT), ARGS.donor.read_bytes())
        self.assertNotIn("r04_full_router", sys.modules)
        self.assertEqual((self.on / "h3c_goose_eod_cap_rescue.py").read_bytes(), ARGS.h3c.read_bytes())

    def test_03_drift_for_every_source_is_blocked_before_output(self):
        sources = [(ARGS.package / n).read_bytes() for n in port.PINS]
        sources += [ARGS.donor.read_bytes(), ARGS.h3c.read_bytes()]
        for index in range(len(sources)):
            bad = list(sources)
            bad[index] += b"\n# drift\n"
            with self.subTest(index=index), self.assertRaises(ValueError):
                port.port_sources(*bad, enabled=True)
        with self.assertRaises(ValueError):
            port.port_sources(*sources, enabled=1)

    def test_04_existing_output_and_overlap_are_refused(self):
        for destination in (self.on, ARGS.package, ARGS.package / "child"):
            with self.subTest(path=str(destination)), self.assertRaises(ValueError):
                port.stage(ARGS.package, ARGS.donor, ARGS.h3c, destination, enabled=True)

    def test_05_cli_drift_fails_closed(self):
        bad = self.root / "bad-donor.py"
        bad.write_bytes(ARGS.donor.read_bytes() + b"\n")
        out = self.root / "must-not-exist"
        cmd = [sys.executable, str(Path(port.__file__)), "--package", str(ARGS.package),
               "--donor", str(bad), "--h3c", str(ARGS.h3c), "--output", str(out), "--enabled"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("source drift", result.stderr)
        self.assertFalse(out.exists())

    def test_06_native_finalizer_positive_both_seats_and_floor(self):
        for seat in (0, 1):
            for floor in (False, True):
                for room in (0, 1, 2):
                    with self.subTest(seat=seat, floor=floor, room=room):
                        _, action, gain, _ = self.pair(seat=seat, floor=floor, shed={"WHEAT": 100-room})
                        self.assertEqual(action["market"], [["SELL", "WHEAT", 3-room]])
                        self.assertGreater(gain, 0)

    def test_07_mixed_vector_and_complete_row_budget(self):
        for seat in (0, 1):
            for row_count in (0, 1, 8, 9, 10):
                with self.subTest(seat=seat, rows=row_count):
                    self.pair(seat=seat, shed={"WHEAT": 50, "CARROT": 50},
                              cargo=[{"WHEAT": 2}, {"CARROT": 3}],
                              market=[[] for _ in range(row_count)], expect_change=row_count <= 8)

    def test_08_ambiguous_actor_boundary_stays_identity(self):
        for seat in (0, 1):
            for cargo in ([{"WHEAT": 2, "CARROT": 2}], [{"CARROT": 2, "WHEAT": 2}]):
                self.pair(seat=seat, shed={"WHEAT": 50, "CARROT": 49}, cargo=cargo, expect_change=False)

    def test_09_final_status_gate_preserves_fallback_identity(self):
        state, env = self.fixture()
        obs, action = state[0].observation, state[0].action
        for status in (None, "deadline_fallback", "entrypoint_prelude", "interrupted"):
            obj = self.instance()
            obj.diagnostics = {"status": status}
            with patch.object(self.rescue, "apply_eod_capacity_rescue", side_effect=AssertionError("must not call")):
                self.assertIs(obj._early_capital_selected(obs, env.configuration, action), action)

    def test_10_latest_queue_is_guarded_not_stale_input(self):
        state, env = self.fixture()
        obs, action = state[0].observation, state[0].action
        # The real native FinalPressure method stays in the call chain; only
        # its downstream pressure transform is instrumented as a boundary probe.
        for final_rows in ([["SELL", "WHEAT", 1]], [["BUY_PRODUCT", "FERTILIZER", 1]], [[]] * 10):
            latest = copy.deepcopy(action)
            latest["market"] = final_rows
            obj = self.instance()
            with patch.object(self.runtime.TitanAgent, "_market_pressure_selected", return_value=latest):
                self.assertIs(obj._early_capital_selected(obs, env.configuration, action), latest)
        latest = copy.deepcopy(action)
        latest["market"] = [[]] * 9
        with patch.object(self.runtime.TitanAgent, "_market_pressure_selected", return_value=latest):
            out = self.instance()._early_capital_selected(obs, env.configuration, action)
        self.assertEqual(out["market"], [[]] * 9 + [["SELL", "WHEAT", 2]])

    def test_11_rescue_runs_after_all_guards_before_all_receipts(self):
        state, env = self.fixture()
        obj = self.instance()
        events = []
        def record(label, function):
            def wrapper(*args, **kwargs):
                events.append(label)
                return function(*args, **kwargs)
            return wrapper
        with patch.object(obj.spatial, "guard_returned", record("unit_guard", obj.spatial.guard_returned)), \
             patch.object(obj.spatial, "guard_crop_returned", record("crop_guard", obj.spatial.guard_crop_returned)), \
             patch.object(obj, "_feed_stock_selected", record("feed", obj._feed_stock_selected)), \
             patch.object(self.runtime.TitanAgent, "_early_capital_selected", record("capital", self.runtime.TitanAgent._early_capital_selected)), \
             patch.object(self.runtime.TitanAgent, "_market_pressure_selected", record("pressure", self.runtime.TitanAgent._market_pressure_selected)), \
             patch.object(self.rescue, "apply_eod_capacity_rescue", record("rescue", self.rescue.apply_eod_capacity_rescue)), \
             patch.object(obj.spatial, "finish", record("spatial_receipt", obj.spatial.finish)), \
             patch.object(obj.spatial, "finish_crop", record("crop_receipt", obj.spatial.finish_crop)), \
             patch.object(obj.history, "remember", record("history_receipt", obj.history.remember)):
            out = self.finish(obj, state[0].observation, state[0].action, env.configuration)
        self.assertEqual(events, ["unit_guard", "crop_guard", "feed", "capital", "pressure", "rescue",
                                  "spatial_receipt", "crop_receipt", "history_receipt"])
        self.assertEqual(out["market"], [["SELL", "WHEAT", 2]])
        self.assertFalse(obj._final_pressure_boundary)

    def test_12_history_binds_final_rescue_and_matching_unit_snapshot(self):
        state, env = self.fixture()
        obj = self.instance()
        # Request existing native snapshot retention without invoking the
        # unrelated terminal optimizer in this finalizer-only witness.
        obj.features = replace(obj.features, terminal_history=True, history_hypotheses={})
        out = self.finish(obj, state[0].observation, state[0].action, env.configuration)
        before, cfg, recorded, post = obj.history.pending
        self.assertEqual(recorded, out)
        self.assertEqual(post, state[0].observation)
        self.assertEqual(out["farmer"], state[0].action["farmer"])
        self.assertEqual(out["hands"], state[0].action["hands"])
        self.assertIsNot(post, state[0].observation)

    def test_13_exception_restores_pressure_flag_and_skips_receipts(self):
        state, env = self.fixture()
        obj = self.instance()
        class Interrupted(BaseException):
            pass
        with patch.object(self.rescue, "apply_eod_capacity_rescue", side_effect=Interrupted), \
             patch.object(obj.history, "remember") as remember:
            with self.assertRaises(Interrupted):
                self.finish(obj, state[0].observation, state[0].action, env.configuration)
            remember.assert_not_called()
        self.assertFalse(obj._final_pressure_boundary)

    def test_14_pressure_does_not_reorder_appended_rescue_afterward(self):
        state, env = self.fixture(shed={"CARROT": 50, "WHEAT": 50}, cargo=[{"CARROT": 3}, {"WHEAT": 2}])
        obj = self.instance()
        with patch.object(self.runtime.TitanAgent, "_market_pressure_selected", wraps=lambda *args: args[-1]) as pressure:
            out = self.finish(obj, state[0].observation, state[0].action, env.configuration)
        self.assertEqual(pressure.call_count, 1)
        self.assertEqual(out["market"], [["SELL", "CARROT", 3], ["SELL", "WHEAT", 2]])

    def test_15_native_season_and_market_block_controls(self):
        for seat in (0, 1):
            for step in (118, 718, 719):
                self.pair(seat=seat, step=step, expect_change=False)
            for market in ([["SELL", "WHEAT", 1]], [["BUY_PRODUCT", "WHEAT", 1]], [["BOGUS"]]):
                self.pair(seat=seat, market=market, expect_change=False)

    def test_16_rival_buy_effect_is_recorded_separately(self):
        for seat in (0, 1):
            _, _, own, rival = self.pair(seat=seat, shed={"WHEAT": 100}, cargo=[{"WHEAT": 20}],
                                         rival=[["BUY_PRODUCT", "WHEAT", 20]])
            self.assertGreater(own, 0)
            self.assertGreaterEqual(rival, 0)
            COUNTS[f"co_buy_seat_{seat}"] = {"own_cash_delta": own, "rival_cash_delta": rival, "margin_delta": own-rival}

    def test_17_h3c_unit_change_cannot_slip_through_capacity_rescue(self):
        state, env = self.fixture()
        obs, action = state[0].observation, state[0].action
        changed_units = copy.deepcopy(action)
        changed_units["farmer"] = ["HARVEST"]
        with patch.object(self.runtime.TitanAgent, "_market_pressure_selected", return_value=changed_units):
            self.assertIs(self.instance()._early_capital_selected(obs, env.configuration, action), changed_units)

    def test_18_native_real_opening_off_on_identity(self):
        # Actual selected actions; these opening positions have no EOD overflow.
        # They prove an integrated no-op control, not rescue engagement or EV.
        for seat in (0, 1):
            state0, env0 = self.fixture(seat=seat, step=0, shed={}, cargo=[{}])
            state1, env1 = copy.deepcopy(state0), copy.deepcopy(env0)
            a0, a1 = self.instance(False), self.instance(True)
            for step in range(12):
                for state in (state0, state1):
                    for row in state:
                        row.observation.step = step
                        row.observation.day, row.observation.hour = divmod(step, 24)
                action0 = a0.act(copy.deepcopy(state0[seat].observation), env0.configuration)
                action1 = a1.act(copy.deepcopy(state1[seat].observation), env1.configuration)
                self.assertEqual(a0.diagnostics["status"], "completed")
                self.assertEqual(a1.diagnostics["status"], "completed")
                self.assertEqual(action1, action0)
                state0[seat].action, state1[seat].action = action0, action1
                self.engine.interpreter(state0, env0)
                self.engine.interpreter(state1, env1)
                self.assertEqual(state1, state0)
                COUNTS["natural_opening_callbacks"] += 2

    def test_19_outer_entrypoint_cancels_rescue_and_discards_instance(self):
        state, env = self.fixture()
        obj = self.instance()
        original = copy.deepcopy(state[0].action)
        def selected_finalization(obs, cfg, *, entry_started=None):
            # Controlled completed-producer witness, under the ACTUAL outer
            # caller and its live timer. Not a synthetic deadline implementation.
            obj.selected = copy.deepcopy(original)
            obj.diagnostics = {"status": "completed"}
            return obj._finish_production(obs, original, cfg)
        def interrupt(*args, **kwargs):
            active = self.runtime.deadline._ACTIVE_TIMER.get()
            self.assertIsNotNone(active)
            raise active.expired
        self.main_on._INSTANCE = obj
        try:
            with patch.object(obj, "act", side_effect=selected_finalization), \
                 patch.object(self.rescue, "apply_eod_capacity_rescue", side_effect=interrupt), \
                 patch.object(obj.history, "remember") as remember:
                returned = self.main_on.agent(state[0].observation, env.configuration)
                remember.assert_not_called()
            self.assertEqual(returned, original)
            self.assertIsNone(self.main_on._INSTANCE)
            self.assertEqual(obj.diagnostics["fallback_stage"], "entrypoint_finalization")
            self.assertFalse(obj._final_pressure_boundary)
        finally:
            self.main_on._INSTANCE = None

    def test_20_public_entrypoint_positive_finalization(self):
        state, env = self.fixture()
        obj = self.instance()
        original = copy.deepcopy(state[0].action)
        def selected_finalization(obs, cfg, *, entry_started=None):
            obj.selected = copy.deepcopy(original)
            obj.diagnostics = {"status": "completed"}
            return obj._finish_production(obs, original, cfg)
        self.main_on._INSTANCE = obj
        try:
            with patch.object(obj, "act", side_effect=selected_finalization):
                returned = self.main_on.agent(state[0].observation, env.configuration)
            self.assertEqual(returned["market"], [["SELL", "WHEAT", 2]])
            self.assertIs(self.main_on._INSTANCE, obj)
            self.assertEqual(obj.diagnostics["status"], "completed")
        finally:
            self.main_on._INSTANCE = None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--donor", type=Path, required=True)
    parser.add_argument("--h3c", type=Path, required=True)
    parser.add_argument("--mutant", choices=("disabled", "stale-queue", "fallback-on", "after-receipts", "partial-budget", "legacy-import"))
    ARGS = parser.parse_args()
    ARGS.package = ARGS.package.resolve()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(NativeEod)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(json.dumps({"counts": COUNTS, "tests": result.testsRun, "ok": result.wasSuccessful(),
                      "optimized": not __debug__, "mutant": ARGS.mutant, "engine": getattr(NativeEod, "engine_hashes", None)},
                     indent=2, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
