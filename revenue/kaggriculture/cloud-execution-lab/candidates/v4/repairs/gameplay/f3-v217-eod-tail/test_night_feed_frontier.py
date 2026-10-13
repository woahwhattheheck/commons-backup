# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import copy
from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import random
import unittest

from night_feed_frontier import STANDARD, propose_feed_tails, incumbent_feeds, unit
from night_feed_engine import Engine, digest, pass_action

ENGINE = None

def setUpModule():
    global ENGINE
    root = os.environ.get("TITAN_NATIVE_ROOT")
    if not root:
        raise RuntimeError("TITAN_NATIVE_ROOT must point to the authenticated b567 native archive")
    ENGINE = Engine(Path(root))


def fixture(seat=0, step=21, actor=0, targets=((0, 0), (1, 0)), wheat=3):
    state, env = ENGINE.initialize()
    farm = state[seat].observation.farms[seat]
    farm["tiles"] = [[None for _ in range(10)] for _ in range(10)]
    farm["farmer"] = [0, 0] if actor == 0 else [8, 8]
    farm["hands"] = [[0, 0] for _ in range(actor)]
    private = state[seat].observation.private
    private["inventories"] = [{} for _ in range(actor + 1)]
    private["inventories"][actor] = {"WHEAT": wheat}
    private["shed"] = {}
    for x, y in targets:
        animal = ENGINE.engine._new_animal("COW", -8)
        animal["consecutive_unfed"] = 1
        farm["tiles"][y][x] = animal
    for s in state:
        s.observation.step = step
        s.observation.day = step // 24
        s.observation.hour = step % 24
    route = [pass_action(actor) for _ in range(720)]
    return state, env, route


def proposals(state, env, route, seat=0, **kw):
    obs = state[seat].observation
    return propose_feed_tails(obs, route[obs.step], route, env.configuration, enabled=True, **kw)


class PlannerTests(unittest.TestCase):
    def test_opt_in_only(self):
        s, e, r = fixture()
        self.assertEqual(propose_feed_tails(s[0].observation, r[21], r, e.configuration), ())

    def test_two_targets_before_real_reset(self):
        s, e, r = fixture()
        p = proposals(s, e, r)[0]
        self.assertEqual(p.targets, ((0, 0), (1, 0)))
        self.assertEqual(p.commands, (("FEED",), ("EAST",), ("FEED",)))
        self.assertEqual(p.wheat_cost, 2)
        self.assertEqual(p.end, 24)

    def test_padding_and_early_feed(self):
        s, e, r = fixture(step=20, targets=((0, 0),))
        p = proposals(s, e, r)[0]
        self.assertEqual(p.commands, (("FEED",), ("PASS",), ("PASS",), ("PASS",)))

    def test_hand_actor_and_both_seats(self):
        for seat in (0, 1):
            s, e, r = fixture(seat=seat, actor=2)
            p = proposals(s, e, r, seat)[0]
            self.assertEqual((p.seat, p.actor), (seat, 2))
            self.assertEqual(len(p.targets), 2)

    def test_later_real_work_is_not_stolen(self):
        s, e, r = fixture()
        r[23]["farmer"] = ["HARVEST"]
        self.assertEqual(proposals(s, e, r), ())

    def test_current_return_overrules_tape(self):
        s, e, r = fixture()
        selected = pass_action(); selected["farmer"] = ["DROP"]
        self.assertEqual(propose_feed_tails(s[0].observation, selected, r, e.configuration, enabled=True), ())

    def test_redundant_future_feed_is_excluded(self):
        s, e, r = fixture(actor=1, targets=((0, 0),))
        farm = s[0].observation.farms[0]; farm["farmer"] = [1, 0]
        r[21]["farmer"] = ["WEST"]; r[23]["farmer"] = ["FEED"]
        self.assertEqual(proposals(s, e, r), ())

    def test_unknown_future_hand_is_conservative(self):
        s, e, r = fixture(targets=((0, 0),))
        r[23]["hands"] = [["FEED"]]
        self.assertEqual(proposals(s, e, r), ())

    def test_coverage_is_conservative_without_wheat(self):
        self.assertEqual(incumbent_feeds([(1, 0)], [{"farmer": ["WEST"]}, {"farmer": ["FEED"]}]), {(0, 0)})

    def test_unfed_but_not_endangered_is_not_a_rescue(self):
        s, e, r = fixture()
        for row in s[0].observation.farms[0]["tiles"]:
            for t in row:
                if isinstance(t, dict): t["consecutive_unfed"] = 0
        self.assertEqual(proposals(s, e, r), ())

    def test_already_fed_is_not_rescued(self):
        s, e, r = fixture()
        for row in s[0].observation.farms[0]["tiles"]:
            for t in row:
                if isinstance(t, dict): t["fed_today"] = True
        self.assertEqual(proposals(s, e, r), ())

    def test_own_cargo_is_the_only_budget(self):
        s, e, r = fixture(wheat=0)
        s[0].observation.private["shed"] = {"WHEAT": 100}
        s[0].observation.farms[0]["money"] = 1000000
        self.assertEqual(proposals(s, e, r), ())

    def test_cargo_bounds_target_count(self):
        s, e, r = fixture(wheat=1)
        self.assertEqual(len(proposals(s, e, r)[0].targets), 1)

    def test_final_day_has_no_reset_credit(self):
        s, e, r = fixture(step=718)
        self.assertEqual(proposals(s, e, r), ())

    def test_full_nonfinal_boundary(self):
        s, e, r = fixture(step=695, targets=((0, 0),))
        self.assertEqual(proposals(s, e, r)[0].end, 696)

    def test_standard_configuration_only(self):
        for name in STANDARD:
            for value in (None, True, float(STANDARD[name]), STANDARD[name] + 1):
                s, e, r = fixture(); e.configuration[name] = value
                self.assertEqual(proposals(s, e, r), (), (name, value))

    def test_unreachable_is_not_a_plan(self):
        s, e, r = fixture(step=23, targets=((1, 0),))
        self.assertEqual(proposals(s, e, r), ())

    def test_no_alias_or_input_mutation(self):
        s, e, r = fixture(); before = digest((s, e, r))
        p = proposals(s, e, r)[0]
        self.assertEqual(digest((s, e, r)), before)
        with self.assertRaises(FrozenInstanceError): p.actor = 5
        r[21]["farmer"][0] = "DROP"
        self.assertEqual(p.commands[0], ("FEED",))

    def test_missing_or_malformed_input_fails_closed(self):
        for field in ("step", "player", "private", "farms"):
            s, e, r = fixture(); del s[0].observation[field]
            self.assertEqual(propose_feed_tails(s[0].observation, r[21], r, e.configuration, enabled=True), ())
        s, e, r = fixture(); s[0].observation.private["inventories"][0]["WHEAT"] = True
        self.assertEqual(proposals(s, e, r), ())

    def test_invalid_search_budget_errors(self):
        s, e, r = fixture()
        for kw in ({"max_targets": 0}, {"max_targets": 4}, {"pool_limit": 7}, {"max_targets": True}):
            with self.assertRaises(ValueError): proposals(s, e, r, **kw)

    def test_declared_pool_truncation(self):
        s, e, r = fixture(step=16, targets=((0, 0), (1, 0), (2, 0)))
        p = proposals(s, e, r, pool_limit=1)[0]
        self.assertTrue(p.truncated_pool)
        self.assertEqual(p.search_pool_size, 1)

    def test_full_interpreter_reset_and_resource_cost(self):
        for seat in (0, 1):
            for actor in (0, 2):
                s, e, r = fixture(seat=seat, actor=actor)
                p = proposals(s, e, r, seat)[0]
                tape = [[pass_action(actor), pass_action(actor)] for _ in range(3)]
                baseline, _, _ = ENGINE.replay((s, e), 21, tape)
                changed, _, receipt = ENGINE.replay((s, e), 21, tape, p)
                self.assertEqual(len(receipt["feeds"]), 2)
                bf, cf = baseline[seat].observation.farms[seat], changed[seat].observation.farms[seat]
                self.assertEqual(cf["farmer"], bf["farmer"])
                self.assertEqual(cf["hands"], [])
                for x, y in p.targets:
                    self.assertNotIn("animal", bf["tiles"][y][x])
                    self.assertEqual(cf["tiles"][y][x]["animal"], "COW")
                self.assertEqual(baseline[seat].observation.private["shed"]["WHEAT"]
                                 - changed[seat].observation.private["shed"]["WHEAT"], 2)

    def test_actual_suffix_drift_rejected_before_displacement(self):
        s, e, r = fixture(); p = proposals(s, e, r)[0]
        tape = [[pass_action(), pass_action()] for _ in range(3)]
        tape[2][0]["farmer"] = ["HARVEST"]
        before = digest((s, e, tape))
        with self.assertRaisesRegex(ValueError, "not idle"):
            ENGINE.replay((s, e), 21, tape, p)
        self.assertEqual(digest((s, e, tape)), before)

    def test_engine_economics_requires_a_real_harvest_and_sale(self):
        for seat in (0, 1):
            for harvest in (False, True):
                s, e, r = fixture(seat=seat, actor=1, targets=((0, 0),))
                s[seat].observation.farms[seat]["tiles"][0][0]["yield_units"] = 3
                p = proposals(s, e, r, seat)[0]
                tape = [[pass_action(1), pass_action(1)] for _ in range(719 - 21)]
                tape[24 - 21][seat]["market"] = [["SELL", "WHEAT", 99]]
                if harvest:
                    from night_feed_frontier import _walk
                    start = tuple(ENGINE.engine._default_spawn(10))
                    commands = [*_walk(start, (0, 0)), ("HARVEST",), *_walk((0, 0), start), ("DROP",)]
                    for off, cmd in enumerate(commands):
                        tape[24 - 21 + off][seat]["farmer"] = list(cmd)
                    tape[24 - 21 + len(commands)][seat]["market"] = [["SELL", "MILK", 99]]
                base, _, _ = ENGINE.replay((s, e), 21, tape)
                alt, _, _ = ENGINE.replay((s, e), 21, tape, p)
                delta = alt[seat].reward - base[seat].reward
                if harvest: self.assertGreater(delta, 0)
                else: self.assertLess(delta, 0)
                self.assertEqual(alt[1-seat].reward, base[1-seat].reward)

    def test_reference_pin_failures_are_not_silently_fetched(self):
        import tempfile
        from night_feed_engine import PINS
        for damaged in PINS:
            for remove in (False, True):
                with tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    for rel in PINS:
                        path = root / rel; path.parent.mkdir(parents=True, exist_ok=True)
                        data = (ENGINE.root / rel).read_bytes()
                        if rel == damaged and remove: continue
                        path.write_bytes(data + (b"\n# changed\n" if rel == damaged else b""))
                    with self.assertRaises((ValueError, FileNotFoundError)):
                        Engine(root)

    def test_randomized_full_interpreter_cases(self):
        rng = random.Random(410721)
        for case in range(80):
            seat, actor = case % 2, (case // 2) % 3
            points = tuple(dict.fromkeys((rng.randrange(4), rng.randrange(3)) for _ in range(4)))
            s, e, r = fixture(seat=seat, step=16, actor=actor, targets=points, wheat=3)
            pp = proposals(s, e, r, seat)
            if not pp: self.fail("constructed reachable pool should engage")
            p = pp[0]
            tape = [[pass_action(actor), pass_action(actor)] for _ in range(8)]
            a, _, receipt = ENGINE.replay((s, e), 16, tape, p)
            self.assertEqual(len(receipt["feeds"]), p.wheat_cost)
            for x, y in p.targets:
                self.assertEqual(a[seat].observation.farms[seat]["tiles"][y][x]["animal"], "COW")
            self.assertEqual(a[seat].observation.private["shed"].get("WHEAT", 0), 3 - p.wheat_cost)


if __name__ == "__main__":
    unittest.main(verbosity=2)
