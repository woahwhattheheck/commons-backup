# SPDX-License-Identifier: Apache-2.0
"""Execute the actual pinned TitanAgent class with controlled collaborators.

No game, real SELL economics, real deadline backend, or release entrypoint is
claimed. Timer, producer, SELL, route, and market-guard collaborators are doubles;
TitanAgent.act/_initialize/_finish_production and the entire C5 donor are actual
compiled source. Inputs are mandatory and Git-blob pinned before execution.
"""
from __future__ import annotations

import argparse
import copy
import dataclasses
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest

import compose_current_runtime as composer

RUNTIME = b""
DONOR = b""
VARIANT = "correct"
ACTUAL_CALLS = 0
MATRIX_CELLS = 0

TIMER_SOURCE = '''
class DeadlineExceeded(Exception):
    pass
active = False
last = None
expire_on_exit = False
class _DeadlineTimer:
    def __init__(self, seconds):
        self.expired = DeadlineExceeded('controlled runtime cancellation')
    def __enter__(self):
        global active, last
        active = True
        last = self
        return self
    def __exit__(self, kind, value, tb):
        global active
        active = False
        if kind is None and expire_on_exit:
            raise self.expired
        return False

def legal_pass(obs):
    return {'farmer': ['PASS'], 'hands': [], 'market': []}

def terminal_liquidation_fallback(obs, cfg):
    return {'farmer': ['PASS'], 'hands': [], 'market': [['SELL', 'WHEAT', 1]]}
'''


def observation(step=1, inventory=100, player=0, price=25, shops=()):
    return {"step": step, "player": player, "day": int(step) // 24,
            "hour": int(step) % 24,
            "farms": [{"tiles": [], "hands": [], "farmer": [4, 4]},
                      {"tiles": [], "hands": [], "farmer": [4, 4]}],
            "private": {"shed": {}, "inventories": [{}]},
            "market": {"inventory": {"WHEAT": inventory}, "prices": {"WHEAT": price}},
            "town": {"unlocked_shops": list(shops)}}


def action(*rows):
    return {"farmer": ["PASS"], "hands": [], "market": [list(r) for r in rows]}


SUPPORT = types.SimpleNamespace(current=None)


class Producer:
    def __init__(self, control):
        self.control = control
        self.cur = 0
        self.R = [[]]

    def act(self, obs):
        self.control.calls += 1
        self.control.events.append("produce")
        if self.control.timeout == "production":
            raise self.control.runtime.deadline.last.expired
        if self.control.error == "production":
            raise ValueError("controlled producer failure")
        return copy.deepcopy(self.control.action)


class Consumer:
    def __init__(self):
        self.control = SUPPORT.current
        self.controller = Producer(self.control)
        self.planned = {}
        self.pending = {}
        self.previous = None
        self.observed_harvests = {}
        self.selected_post_units = None
        self.selected_post_units_binding = None

    def observe(self, obs):
        pass

    def transform(self, obs, cfg, selected):
        self.control.events.append("sell_transform")
        if self.control.timeout == "transform":
            raise self.control.runtime.deadline.last.expired
        if self.control.error == "transform":
            raise ValueError("controlled transform failure")
        self.selected_post_units = (obs['farms'][int(obs['player'])], obs['private'])
        self.selected_post_units_binding = (int(obs['step']), int(obs['player']),
                                           selected['farmer'], selected['hands'])
        return copy.deepcopy(selected)


class Spatial:
    def __init__(self, *args, **kwargs):
        self.control = SUPPORT.current
        self.plans = {}
        self._pending = {}
        self.crop_intent = None
        self.sale_obligation = None
        self.events = []
        self.receipt_events = []
        self._crop_repair = None

    def transform(self, obs, selected, controller):
        return selected

    def install(self, controller):
        pass

    def configure(self, cfg):
        pass

    def observe_market_receipt(self, *args):
        pass

    def observe_crop_receipts(self, *args):
        pass

    def guard_returned(self, obs, returned, **kwargs):
        return returned

    def guard_crop_returned(self, obs, returned, post):
        return returned

    def finish(self, obs, returned, post):
        self.control.events.append("finish")
        self.control.final_seen = copy.deepcopy(returned)
        if self.control.finalizer is not None:
            self.control.finalizer(returned)

    def finish_crop(self, *args, **kwargs):
        pass


def make_module(name, **attributes):
    module = types.ModuleType(name)
    module.__dict__.update(attributes)
    sys.modules[name] = module
    return module


def feed_guard(*args):
    control = SUPPORT.current
    control.events.append("feed_guard")
    selected = copy.deepcopy(args[3])
    if control.feed_edit is not None:
        selected = control.feed_edit(selected)
    return selected, {"fixture": True}


def capital_guard(*args):
    control = SUPPORT.current
    control.events.append("capital_guard")
    selected = copy.deepcopy(args[3])
    if control.capital_edit is not None:
        selected = control.capital_edit(selected)
    return selected, {"fixture": True}


def mutate(source):
    changes = {
        "no_clone": ("pending = deepcopy(self._c5_rider)", "pending = self._c5_rider"),
        "fallback_relocates": ("pending.enabled = self.diagnostics.get('status') == 'completed'",
                               "pending.enabled = True"),
        "no_return_binding": ("if not self._c5_same_value(returned, expected):", "if False:"),
        "no_prelude_reset": ("                self._c5_rider.reset()\n            # No current state",
                             "                pass\n            # No current state"),
        "early_seam": (
            "        returned = self._feed_stock_selected(obs, cfg or {}, returned)\n"
            "        returned = self._early_capital_selected(obs, cfg or {}, returned)\n"
            "        returned = self._c5_prepare_return(obs, cfg or {}, returned)\n",
            "        returned = self._c5_prepare_return(obs, cfg or {}, returned)\n"
            "        returned = self._feed_stock_selected(obs, cfg or {}, returned)\n"
            "        returned = self._early_capital_selected(obs, cfg or {}, returned)\n"),
    }
    if VARIANT == "correct":
        return source
    old, new = changes[VARIANT]
    return composer.replace_exact(source, old, new)


class RuntimeCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.counter = 0
        self.saved_modules = {name: sys.modules.get(name) for name in
                              ("frozen_selected", "spatial_tempo", "scheduler", "mechanics",
                               "operating_stock", "early_capital")}
        make_module("frozen_selected", FrozenSelected=Consumer)
        make_module("spatial_tempo", SpatialTempo=Spatial)
        make_module("scheduler", m=object(), parent=types.SimpleNamespace(DECISIONS=[]))
        make_module("mechanics")
        make_module("operating_stock", protect_feed_stock=feed_guard)
        make_module("early_capital", order_early_capital=capital_guard)
        for path, text in {
            "reference/titan-current/deadline_adapter.py": TIMER_SOURCE,
            "reference/titan-current/seed_funding.py": "select_seed_queue = None\n",
            "reference/integrated-selected/alder/seed_budget.py":
                "class SeedBudget:\n    def __init__(self, route): pass\n",
        }.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        (self.root / "r04_c5_wheat_demand.py").write_bytes(DONOR)
        self.candidate = self.load(mutate(composer.compose(RUNTIME, DONOR).decode()))
        self.baseline = self.load(RUNTIME.decode())

    def tearDown(self):
        for name, old in self.saved_modules.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old
        self.tmp.cleanup()

    def load(self, source):
        self.counter += 1
        name = f"_actual_c5_runtime_{id(self)}_{self.counter}"
        path = self.root / (name + ".py")
        path.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        self.addCleanup(sys.modules.pop, name, None)
        spec.loader.exec_module(module)
        return module

    def agent(self, enabled=True, baseline=False, **features):
        runtime = self.baseline if baseline else self.candidate
        values = dict(seed=False, funding=False)
        values.update(features)
        if not baseline:
            values[composer.KEY] = enabled
        control = types.SimpleNamespace(runtime=runtime, action=action(), calls=0,
            timeout=None, error=None, finalizer=None, events=[], final_seen=None,
            feed_edit=None, capital_edit=None)
        SUPPORT.current = control
        return runtime.TitanAgent(runtime.Features(**values)), control

    def call(self, agent, control, obs=None, cfg=None, **kwargs):
        global ACTUAL_CALLS
        SUPPORT.current = control
        ACTUAL_CALLS += 1
        return agent.act(observation() if obs is None else obs, cfg or {}, **kwargs)

    def test_defaults_off_frozen_and_strict_types(self):
        f = self.candidate.Features()
        self.assertIs(f.r04_c5_wheat_demand, False)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            f.r04_c5_wheat_demand = True
        for value in (0, 1, None, "false"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.candidate.Features(r04_c5_wheat_demand=value)
        for settings in ({"consumer": "ordered"}, {"consumer": "parent"}, {"terminal_route": True}):
            with self.assertRaises(ValueError):
                self.candidate.Features(r04_c5_wheat_demand=True, **settings)

    def test_off_no_donor_import_or_state_and_baseline_parity(self):
        a, c = self.agent(enabled=False)
        b, d = self.agent(baseline=True)
        original = self.candidate.load
        def loader(name, path, **kw):
            self.assertNotEqual(name, "_titan_c5_donor")
            return original(name, path, **kw)
        self.candidate.load = loader
        for step in range(1, 12):
            c.action = d.action = action(("SELL", "WHEAT", 3))
            out = self.call(a, c, observation(step, 100-step))
            expected = self.call(b, d, observation(step, 100-step))
            self.assertEqual(out, expected)
            self.assertIsNone(a._c5_rider)
            self.assertNotIn("c5_wheat_demand", a.diagnostics)
        self.assertEqual(c.calls, d.calls)
        parent = action(("SELL", "WHEAT", 1))
        self.assertIs(a._c5_prepare_return(observation(), {}, parent), parent)

    def test_enabled_load_is_inside_existing_timer(self):
        a, c = self.agent()
        original = self.candidate.load
        seen = []
        def loader(name, path, **kw):
            if name == "_titan_c5_donor":
                seen.append(self.candidate.deadline.active)
            return original(name, path, **kw)
        self.candidate.load = loader
        self.call(a, c)
        self.assertEqual(seen, [True])

    def test_final_sale_relocation_and_observer_order(self):
        a, c = self.agent()
        self.call(a, c, observation(1, 100))
        c.action = action(("SELL", "WHEAT", 3), ("SELL", "MILK", 2))
        before = copy.deepcopy(c.action)
        out = self.call(a, c, observation(2, 99))
        self.assertEqual(out['market'], [[], ["SELL", "MILK", 2], ["SELL", "WHEAT", 3]])
        self.assertEqual(c.final_seen, out)
        self.assertEqual(c.action, before)
        self.assertEqual(c.calls, 2)
        self.assertEqual(a._c5_rider.players[0]['step'], 2)
        self.assertEqual(a.diagnostics['c5_wheat_demand']['telemetry']['relocations'], 1)

    def test_agent_and_seat_isolation(self):
        a, c = self.agent()
        b, d = self.agent()
        self.call(a, c, observation(1, 100, 0))
        self.call(a, c, observation(1, 300, 1))
        d.action = action(("SELL", "WHEAT", 2))
        out = self.call(b, d, observation(2, 99, 0))
        self.assertEqual(out, d.action)
        self.assertIsNot(a._c5_rider, b._c5_rider)
        c.action = d.action
        self.assertEqual(self.call(a, c, observation(2, 300, 1)), c.action)
        self.assertEqual(self.call(a, c, observation(2, 99, 0))['market'][0], [])

    def test_fallback_observes_actual_buy_without_relocating(self):
        a, c = self.agent()
        self.call(a, c, observation(1, 100))
        c.action = action(("SELL", "WHEAT", 3))
        c.timeout = "transform"
        out = self.call(a, c, observation(2, 99))
        self.assertEqual(out, c.action)
        self.assertTrue(a.diagnostics['c5_wheat_demand']['observe_only'])
        c.action = action(("BUY_PRODUCT", "WHEAT", 4))
        self.call(a, c, observation(3, 99))
        self.assertEqual(a._c5_rider.players[0]['own_buy_upper'], 4)
        c.timeout = None
        c.action = action(("SELL", "WHEAT", 3))
        self.assertEqual(self.call(a, c, observation(4, 95)), c.action)

    def test_production_cancellation_records_pass_not_speculation(self):
        a, c = self.agent()
        self.call(a, c, observation(1, 100))
        c.action = action(("BUY_PRODUCT", "WHEAT", 7))
        c.timeout = "production"
        self.assertEqual(self.call(a, c, observation(2, 99)), action())
        self.assertEqual(a._c5_rider.players[0]['own_buy_upper'], 0)
        c.timeout = None
        c.action = action(("SELL", "WHEAT", 3))
        self.assertEqual(self.call(a, c, observation(3, 98))['market'][0], [])

    def test_timer_exit_cancellation_discards_completed_transform(self):
        a, c = self.agent()
        self.call(a, c, observation(1, 100))
        c.action = action(("SELL", "WHEAT", 3))
        self.candidate.deadline.expire_on_exit = True
        out = self.call(a, c, observation(2, 99))
        self.assertEqual(out, c.action)
        self.assertTrue(a.diagnostics['c5_wheat_demand']['observe_only'])

    def test_prelude_fallback_invalidates_evidence(self):
        a, c = self.agent()
        self.call(a, c, observation(1, 100))
        prior_calls = c.calls
        self.assertEqual(self.call(a, c, observation(2, 99), entry_started=0), action())
        self.assertEqual(c.calls, prior_calls)
        self.assertEqual(a._c5_rider.players, {})
        c.action = action(("SELL", "WHEAT", 3))
        self.assertEqual(self.call(a, c, observation(3, 98)), c.action)

    def test_failed_finalizer_does_not_commit_preview(self):
        a, c = self.agent()
        self.call(a, c, observation(1, 100))
        old = copy.deepcopy(a._c5_rider.players)
        c.action = action(("BUY_PRODUCT", "WHEAT", 7))
        def fail(out):
            raise RuntimeError("controlled finalizer failure")
        c.finalizer = fail
        with self.assertRaises(RuntimeError):
            self.call(a, c, observation(2, 99))
        self.assertEqual(a._c5_rider.players, old)
        c.finalizer = None
        c.action = action(("SELL", "WHEAT", 3))
        self.assertEqual(self.call(a, c, observation(2, 99))['market'][0], [])

    def test_post_finalizer_action_drift_invalidates(self):
        for quantity in (2, True):
            with self.subTest(quantity=quantity):
                a, c = self.agent()
                self.call(a, c)
                c.action = action(("BUY_PRODUCT", "WHEAT", 1))
                c.finalizer = lambda out: out['market'][0].__setitem__(2, quantity)
                self.call(a, c, observation(2, 100))
                self.assertEqual(a._c5_rider.players, {})
                self.assertFalse(a.diagnostics['c5_wheat_demand']['committed'])

    def test_final_capital_buy_is_in_record_and_keeps_rival_residual(self):
        a, c = self.agent(operating_stock=True, early_capital=True)
        c.action = action(("SELL", "WHEAT", 3))
        def add_buy(out):
            out['market'].append(["BUY_PRODUCT", "WHEAT", 2])
            return out
        c.capital_edit = add_buy
        self.call(a, c, observation(1, 100))
        self.assertIn(0, a._c5_rider.players)
        self.assertEqual(a._c5_rider.players[0]['own_buy_upper'], 2)
        c.capital_edit = None
        out = self.call(a, c, observation(2, 97))
        self.assertEqual(out['market'][0], [])
        self.assertLess(c.events.index('feed_guard'), c.events.index('capital_guard'))
        self.assertEqual(c.final_seen, out)

    def test_later_buy_from_final_guard_vetoes_sale_move(self):
        a, c = self.agent(operating_stock=True, early_capital=True)
        self.call(a, c)
        c.action = action(("SELL", "WHEAT", 3))
        def add_hire(out):
            out['market'].append(["HIRE"])
            return out
        c.capital_edit = add_hire
        out = self.call(a, c, observation(2, 99))
        self.assertEqual(out['market'], [["SELL", "WHEAT", 3], ["HIRE"]])

    def test_raw_clock_coercion_cannot_seed_rider(self):
        for value in (True, "2", 2.0):
            a, c = self.agent()
            self.call(a, c)
            obs = observation(2, 99)
            obs['step'] = value
            c.action = action(("SELL", "WHEAT", 3))
            self.assertEqual(self.call(a, c, obs), c.action)
            self.assertEqual(a._c5_rider.players, {})

    def test_malformed_public_evidence_clears_latch(self):
        for path, value in ((('market', 'inventory', 'WHEAT'), True),
                            (('market', 'prices', 'WHEAT'), '30'),
                            (('town', 'unlocked_shops'), ['UNKNOWN'])):
            a, c = self.agent()
            self.call(a, c)
            obs = observation(2, 99)
            target = obs
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
            c.action = action(("SELL", "WHEAT", 3))
            self.assertEqual(self.call(a, c, obs), c.action)
            self.assertEqual(a._c5_rider.players, {})

    def test_gap_rewind_and_repeated_step(self):
        for step in (1, 0, 3):
            a, c = self.agent()
            self.call(a, c)
            c.action = action(("SELL", "WHEAT", 3))
            self.assertEqual(self.call(a, c, observation(step, 90)), c.action)

    def test_floor_and_raw_cap_guards(self):
        for cap, price in ((10, 1), (1, 30), (0, 30), (-1, 30), (True, 30), (3.0, 30)):
            a, c = self.agent()
            self.call(a, c)
            c.action = action(("SELL", "WHEAT", 3))
            self.assertEqual(self.call(a, c, observation(2, 99, price=price),
                                       {"maxMarketOrdersPerTurn": cap}), c.action)
        a, c = self.agent()
        self.call(a, c)
        c.action = action(("SELL", "WHEAT", 3), ("SELL", "MILK", 1), ("HIRE",), ("BUY_PRODUCT", "EGG", 1))
        self.assertEqual(self.call(a, c, observation(2, 99), {"maxMarketOrdersPerTurn": 3}), c.action)

    def test_own_buy_in_dead_suffix_is_not_counted(self):
        a, c = self.agent()
        c.action = action((), (), (), ("BUY_PRODUCT", "WHEAT", 9))
        self.call(a, c, observation(1, 100), {"maxMarketOrdersPerTurn": 3})
        self.assertEqual(a._c5_rider.players[0]['own_buy_upper'], 0)
        c.action = action(("SELL", "WHEAT", 1))
        self.assertEqual(self.call(a, c, observation(2, 99), {"maxMarketOrdersPerTurn": 3})['market'][0], [])

    def test_negative_market_inventory_is_valid(self):
        a, c = self.agent()
        self.call(a, c, observation(1, -10))
        c.action = action(("SELL", "WHEAT", 2))
        self.assertEqual(self.call(a, c, observation(2, -11))['market'][0], [])

    def test_callable_uses_same_wired_act(self):
        global ACTUAL_CALLS
        ACTUAL_CALLS += 2
        a, c = self.agent()
        SUPPORT.current = c
        a(observation(1, 100))
        c.action = action(("SELL", "WHEAT", 2))
        self.assertEqual(a(observation(2, 99))['market'][0], [])

    def test_no_cross_callback_output_alias(self):
        a, c = self.agent()
        self.call(a, c)
        c.action = action(("BUY_PRODUCT", "WHEAT", 2))
        out = self.call(a, c, observation(2, 100))
        out['market'][0][2] = 999
        self.assertEqual(a._c5_rider.players[0]['own_buy_upper'], 2)

    def test_transition_matrix(self):
        global MATRIX_CELLS
        for seat in (0, 1):
            for fallback in (False, True):
                for own_buy in range(4):
                    for towns in range(3):
                        for rival in range(4):
                            with self.subTest(seat=seat, fallback=fallback, own=own_buy, towns=towns, rival=rival):
                                a, c = self.agent()
                                c.action = action(("BUY_PRODUCT", "WHEAT", own_buy)) if own_buy else action()
                                shops = ["BAKERY", "PIZZA_SHOP"][:towns]
                                self.call(a, c, observation(4, 100, seat, shops=shops))
                                c.timeout = "transform" if fallback else None
                                c.action = action(("SELL", "WHEAT", 3), ("SELL", "MILK", 1))
                                out = self.call(a, c, observation(5, 100-own_buy-towns-rival, seat, shops=shops))
                                expected = ([[], ["SELL", "MILK", 1], ["SELL", "WHEAT", 3]]
                                            if rival > 0 and not fallback else c.action['market'])
                                self.assertEqual(out['market'], expected)
                                self.assertEqual(c.calls, 2)
                                MATRIX_CELLS += 1


class ComposerCase(unittest.TestCase):
    def test_pin_refusals(self):
        with self.assertRaises(ValueError):
            composer.compose(RUNTIME + b"\n", DONOR)
        with self.assertRaises(ValueError):
            composer.compose(RUNTIME, DONOR + b"\n")

    def test_anchor_refusals(self):
        with self.assertRaises(ValueError):
            composer.replace_exact("a a", "a", "b")
        with self.assertRaises(ValueError):
            composer.replace_exact("a", "z", "b")

    def test_cli_create_only_and_inputs_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime, donor, out = root / "runtime.py", root / "donor.py", root / "scratch"
            runtime.write_bytes(RUNTIME)
            donor.write_bytes(DONOR)
            cmd = [sys.executable, str(Path(composer.__file__).resolve()),
                   "--runtime", str(runtime), "--donor", str(donor), "--out", str(out)]
            first = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.assertEqual(first.returncode, 0, first.stderr)
            candidate = (out / "titan_runtime.py").read_bytes()
            self.assertEqual(candidate, composer.compose(RUNTIME, DONOR))
            self.assertEqual((out / "r04_c5_wheat_demand.py").read_bytes(), DONOR)
            second = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual((out / "titan_runtime.py").read_bytes(), candidate)
            self.assertEqual(runtime.read_bytes(), RUNTIME)
            self.assertEqual(donor.read_bytes(), DONOR)
            runtime.write_bytes(RUNTIME + b"\n")
            new_out = root / "must-not-exist"
            cmd[-1] = str(new_out)
            bad = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(bad.returncode, 0)
            self.assertFalse(new_out.exists())

    def test_determinism_and_compile(self):
        first = composer.compose(RUNTIME, DONOR)
        self.assertEqual(first, composer.compose(RUNTIME, DONOR))
        compile(first, "composed.py", "exec")
        self.assertNotIn(b"r04_full_router", first)
        self.assertEqual(first.count(b"self.production.act(obs)"), 1)


def main():
    global RUNTIME, DONOR, VARIANT
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--donor', type=Path, required=True)
    p.add_argument('--mutant', choices=['correct', 'no_clone', 'fallback_relocates',
                                      'no_return_binding', 'no_prelude_reset', 'early_seam'], default='correct')
    p.add_argument('--mutations', action='store_true')
    args = p.parse_args()
    RUNTIME, DONOR = args.runtime.read_bytes(), args.donor.read_bytes()
    composer.require_pin(RUNTIME, composer.RUNTIME_BLOB, 'runtime')
    composer.require_pin(DONOR, composer.DONOR_BLOB, 'donor')
    VARIANT = args.mutant
    suite = unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeCase),
                               unittest.defaultTestLoader.loadTestsFromTestCase(ComposerCase)])
    output = io.StringIO()
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    sys.stderr.write(output.getvalue())
    report = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'skipped': len(result.skipped), 'passed': result.wasSuccessful(),
              'variant': VARIANT, 'optimized': not __debug__, 'actual_act_calls': ACTUAL_CALLS,
              'matrix_cells': MATRIX_CELLS, 'runtime_input_blob': composer.RUNTIME_BLOB,
              'donor_blob': composer.DONOR_BLOB,
              'runtime_output_blob': composer.blob_id(composer.compose(RUNTIME, DONOR)),
              'scope': 'actual compiled class, controlled collaborators; no games/economics/deadline-backend proof'}
    if args.mutations and result.wasSuccessful():
        killed = []
        for mutant in ('no_clone', 'fallback_relocates', 'no_return_binding', 'no_prelude_reset', 'early_seam'):
            cmd = [sys.executable] + (['-O'] if not __debug__ else []) + [str(Path(__file__).resolve()),
                '--runtime', str(args.runtime.resolve()), '--donor', str(args.donor.resolve()), '--mutant', mutant]
            child = subprocess.run(cmd, text=True, capture_output=True, timeout=40)
            last = json.loads(child.stdout.strip().splitlines()[-1])
            if child.returncode != 1 or last['errors'] or not last['failures']:
                raise RuntimeError(f'mutant was not killed by an assertion: {mutant}: {child.stdout}\n{child.stderr}')
            killed.append({'variant': mutant, 'assertion_failures': last['failures']})
        report['mutations_killed'] = killed
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
