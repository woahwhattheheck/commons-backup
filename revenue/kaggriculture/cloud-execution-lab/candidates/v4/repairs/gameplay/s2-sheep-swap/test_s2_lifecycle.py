# SPDX-License-Identifier: Apache-2.0
"""Explicit offline tests; no missing-source skip or network fallback.

S2_NATIVE_ROOT supplies the authenticated native package (including
checks/reference/{engine,evaluator}); S2_SOURCE supplies current donor bytes.
Both default to the sole canonical repository paths when run there.
"""
from __future__ import annotations
import copy
import importlib.util
import itertools
import os
from pathlib import Path
import random
import sys
import types
import unittest

import build_s2_lifecycle as builder

HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = HERE.parents[4] if len(HERE.parents) > 4 else HERE
ROOT = Path(os.environ.get("S2_NATIVE_ROOT", DEFAULT_ROOT))
SOURCE = Path(os.environ.get("S2_SOURCE", ROOT / "candidates/v4/donor/overlay/r04_s2_sheep_swap.py"))
PARENT_BYTES = SOURCE.read_bytes()
MECHANICS_BYTES = (ROOT / "mechanics.py").read_bytes()
if builder.git_blob(MECHANICS_BYTES) != builder.MECHANICS_BLOB:
    raise RuntimeError("unvalidated native mechanics")
sys.path.insert(0, str(ROOT))


def module(raw, name):
    out = types.ModuleType(name)
    exec(compile(raw, name, "exec"), out.__dict__)
    return out


PARENT = module(PARENT_BYTES, "s2_exact_parent")
CANDIDATE_BYTES = builder.compose(PARENT_BYTES, MECHANICS_BYTES)
CANDIDATE = module(CANDIDATE_BYTES, "s2_candidate")
LOADER_PIN = '23948e10cfc3d32f46c9abb1321b0d8fc8db21d5'
if builder.git_blob((ROOT / "checks/reference/evaluator/loader.py").read_bytes()) != LOADER_PIN:
    raise RuntimeError("offline loader source changed")
loader_spec = importlib.util.spec_from_file_location(
    "s2_official_loader", ROOT / "checks/reference/evaluator/loader.py")
LOADER = importlib.util.module_from_spec(loader_spec)
loader_spec.loader.exec_module(LOADER)
ENGINE_PATH = ROOT / "checks/reference/engine"
ENGINE_PINS = {
    "kaggriculture.py": "3c202c7ee921da239356789e266b694635103fc4",
    "kaggriculture.json": "b354d06b742fe48402513792253f1a5c29366b20",
    "utils.py": "91c8822ee6201ba4a5a8416c7dbe34f95dd61c87",
}
for filename, pin in ENGINE_PINS.items():
    if builder.git_blob((ENGINE_PATH / filename).read_bytes()) != pin:
        raise RuntimeError("official engine fixture changed: " + filename)
ENGINE, _ = LOADER.get_engine(ENGINE_PATH)
ENGINE_CALLS = 0
ENGINE_INITIALIZATIONS = 0
WITNESSES = []


def action(farmer=None, hands=None, market=None):
    return {"farmer": ["PASS"] if farmer is None else farmer,
            "hands": [] if hands is None else hands,
            "market": [] if market is None else market}


def world(seat=0, step=100, inventories=None, shed=None, tile=None, positions=None):
    global ENGINE_CALLS, ENGINE_INITIALIZATIONS
    cfg = LOADER.Struct({k: v.get("default") if isinstance(v, dict) else v
                         for k, v in ENGINE.specification["configuration"].items()})
    cfg.update(seed=31, weedSpawnChance=0)
    env = LOADER.Struct(configuration=cfg, done=False, info={})
    states = [LOADER.Struct(observation=LOADER.Struct(), action=action(),
                           status="ACTIVE", reward=0) for _ in range(2)]
    ENGINE.interpreter(states, env); ENGINE_CALLS += 1; ENGINE_INITIALIZATIONS += 1
    inventories = copy.deepcopy([{}, {}] if inventories is None else inventories)
    positions = positions or [[4, 4] for _ in inventories]
    farm = states[seat].observation.farms[seat]
    farm.update(money=3000, farmer=list(positions[0]), hands=copy.deepcopy(positions[1:]))
    farm["tiles"] = [[None for _ in range(10)] for _ in range(10)]
    for x, y in positions:
        farm["tiles"][y][x] = copy.deepcopy(tile)
    private = states[seat].observation.private
    private.update(shed=copy.deepcopy(shed or {}), seeds={}, inventories=inventories)
    states[0].observation.town["unlocked_shops"] = ["YARN_STORE"]
    for state in states:
        state.observation.step = step
        state.observation.day = step // 24
        state.observation.hour = step % 24
    return states, env


def advance(states, env, seat, returned):
    global ENGINE_CALLS
    for state in states:
        state.action = action()
    states[seat].action = copy.deepcopy(returned)
    ENGINE.interpreter(states, env); ENGINE_CALLS += 1
    for state in states:
        state.observation.step += 1
    return states[seat].observation


def invoke(mod, observation, cfg, parent, state=None, enabled=True, tape=None):
    state = mod.new_state() if state is None else state
    native = [action() for _ in range(720)] if tape is None else tape
    return mod.apply_s2_swap(observation, parent, state, enabled=enabled,
                            configuration=cfg, native_tape=native), state


def positive_stock(stock):
    return {k: v for k, v in stock.items() if v}


class LifecycleTests(unittest.TestCase):
    def test_parent_and_mechanics_pins(self):
        self.assertEqual(builder.git_blob(PARENT_BYTES), builder.PARENT_BLOB)
        self.assertEqual(builder.git_blob(MECHANICS_BYTES), builder.MECHANICS_BLOB)

    def test_source_drift_fails_closed(self):
        for parent, mechanics in ((PARENT_BYTES + b"\n", MECHANICS_BYTES),
                                  (PARENT_BYTES, MECHANICS_BYTES + b"\n")):
            with self.assertRaises(ValueError):
                builder.compose(parent, mechanics)

    def test_already_composed_input_rejected(self):
        with self.assertRaises(ValueError):
            builder.compose(CANDIDATE_BYTES, MECHANICS_BYTES)

    def test_unrelated_gates_byte_preserved(self):
        # Compare ASTs because exec-created modules have no inspectable source file.
        import ast
        before = {n.name: ast.dump(n) for n in ast.parse(PARENT_BYTES).body
                  if isinstance(n, ast.FunctionDef)}
        after = {n.name: ast.dump(n) for n in ast.parse(CANDIDATE_BYTES).body
                 if isinstance(n, ast.FunctionDef)}
        for name in ("new_state", "_exact_standard", "_valid_observation",
                     "_beside_shed", "_future_purchase_conflict", "_owned_current_cow_buy"):
            self.assertEqual(before[name], after[name])

    def test_disabled_exact_identity_no_state_mutation(self):
        states, env = world()
        state = CANDIDATE.new_state(); state["reserved"] = 3
        saved = copy.deepcopy(state); parent = action(market=[["BUY_ANIMAL", "COW", 1]])
        returned, _ = invoke(CANDIDATE, states[0].observation, env.configuration,
                             parent, state, enabled=False)
        self.assertIs(returned, parent); self.assertEqual(state, saved)

    def test_invalid_config_and_parent_do_not_consume_state(self):
        states, env = world()
        for parent, cfg in ((action(), dict(env.configuration, shedCapacity=99)),
                            ({"market": None}, env.configuration),
                            (None, env.configuration)):
            state = CANDIDATE.new_state(); saved = copy.deepcopy(state)
            returned, _ = invoke(CANDIDATE, states[0].observation, cfg, parent, state)
            self.assertIs(returned, parent); self.assertEqual(state, saved)

    def test_gap_clears_owned_animals(self):
        states, env = world(step=102, shed={"SHEEP": 1})
        state = CANDIDATE.new_state(); state.update(last=100, reserved=1)
        returned, state = invoke(CANDIDATE, states[0].observation, env.configuration,
                                 action(["PICKUP", "COW", 1]), state)
        self.assertEqual(returned["farmer"], ["PICKUP", "COW", 1])
        self.assertEqual(state["reserved"], 0)

    def test_truncated_day_still_vetoes_buy(self):
        states, env = world()
        returned, state = invoke(CANDIDATE, states[0].observation, env.configuration,
                                 action(market=[["BUY_ANIMAL", "COW", 1]]), tape=[action()] * 101)
        self.assertEqual(returned["market"][0][1], "COW")
        self.assertIsNone(state["pending_buy"])

    def test_raw_market_prefix_still_excludes_dead_buy(self):
        states, env = world()
        returned, state = invoke(CANDIDATE, states[0].observation, env.configuration,
                                 action(market=[[]] * 10 + [["BUY_ANIMAL", "COW", 1]]))
        self.assertEqual(returned["market"], [[]] * 10)
        self.assertIsNone(state["pending_buy"])

    def test_successful_purchase_requires_next_observation(self):
        for seat in (0, 1):
            states, env = world(seat=seat)
            result, state = invoke(CANDIDATE, states[seat].observation, env.configuration,
                                   action(market=[["BUY_ANIMAL", "COW", 1]]))
            self.assertEqual(state["confirmed"], 0)
            observation = advance(states, env, seat, result)
            result, state = invoke(CANDIDATE, observation, env.configuration,
                                   action(["PICKUP", "COW", 1]), state)
            self.assertEqual(state["confirmed"], 1)
            self.assertEqual(result["farmer"], ["PICKUP", "SHEEP", 1])
            advance(states, env, seat, result)
            self.assertEqual(state["carrying"].get(0), 1)

    def test_failed_full_shed_purchase_never_hijacks_pickup(self):
        states, env = world(shed={"FERTILIZER": 100})
        result, state = invoke(CANDIDATE, states[0].observation, env.configuration,
                               action(market=[["BUY_ANIMAL", "COW", 1]]))
        observation = advance(states, env, 0, result)
        result, state = invoke(CANDIDATE, observation, env.configuration,
                               action(["PICKUP", "COW", 1]), state)
        self.assertEqual(result["farmer"], ["PICKUP", "COW", 1])
        self.assertEqual(state["failed_purchase_units"], 1)

    def test_animal_shed_fallback_prevents_phantom_wool_sale(self):
        for seat in (0, 1):
            states, env = world(seat, inventories=[{"SHEEP": 1}, {"WOOL": 2}],
                                shed={"FERTILIZER": 98, "WOOL": 1})
            parent = action(["PLACE", "SHEEP"], [["DROP"]], [["SELL", "WOOL", 1]])
            observation = states[seat].observation
            old = PARENT.new_state(); old.update(wool_credit=2, carrying={0: 1})
            new = copy.deepcopy(old)
            bad, old = invoke(PARENT, observation, env.configuration, parent, old)
            good, new = invoke(CANDIDATE, observation, env.configuration, parent, new)
            self.assertEqual(bad["market"], [["SELL", "WOOL", 2]])
            self.assertEqual(good["market"], [["SELL", "WOOL", 1]])
            self.assertEqual(new["wool_credit"], 2)
            self.assertEqual(new["reserved"], 1)
            self.assertEqual(new["carrying"].get(0), 0)
            after = advance(states, env, seat, good)
            self.assertEqual(after.private["shed"].get("WOOL", 0), 0)
            self.assertEqual(after.private["shed"].get("SHEEP", 0), 1)

    def test_successful_place_leaves_capacity_for_real_topup(self):
        for seat in (0, 1):
            states, env = world(seat, inventories=[{"SHEEP": 1}, {"WOOL": 2}],
                                shed={"FERTILIZER": 98, "WOOL": 1}, tile={"kind": "PASTURE"})
            state = CANDIDATE.new_state(); state.update(wool_credit=2, carrying={0: 1})
            parent = action(["PLACE", "COW"], [["DROP"]], [["SELL", "WOOL", 1]])
            result, state = invoke(CANDIDATE, states[seat].observation, env.configuration,
                                   parent, state)
            self.assertEqual(result["farmer"], ["PLACE", "SHEEP"])
            self.assertEqual(result["market"], [["SELL", "WOOL", 2]])
            observation = advance(states, env, seat, result)
            self.assertEqual(observation.private["shed"].get("WOOL", 0), 0)
            _, state = invoke(CANDIDATE, observation, env.configuration, action(), state)
            self.assertEqual(state["placed"], 1)
            self.assertEqual(state["carrying"].get(0), 0)

    def test_earlier_native_pickup_cannot_mint_second_carry(self):
        for seat in (0, 1):
            states, env = world(seat, shed={"SHEEP": 1})
            parent = action(["PICKUP", "SHEEP", 1], [["PICKUP", "COW", 1]])
            state = CANDIDATE.new_state(); state["reserved"] = 1
            result, state = invoke(CANDIDATE, states[seat].observation, env.configuration,
                                   parent, state)
            self.assertEqual(result["hands"], [["PICKUP", "COW", 1]])
            observation = advance(states, env, seat, result)
            self.assertEqual(sum(state["carrying"].values()), 1)
            self.assertEqual(state["carrying"].get(1), 0)
            self.assertEqual(observation.private["inventories"][0]["SHEEP"], 1)

    def test_pickup_has_no_invented_carry_capacity(self):
        states, env = world(inventories=[{"WOOL": 100}, {}], shed={"SHEEP": 2})
        state = CANDIDATE.new_state(); state["reserved"] = 2
        result, state = invoke(CANDIDATE, states[0].observation, env.configuration,
                               action(["PICKUP", "COW", 2]), state)
        observation = advance(states, env, 0, result)
        self.assertEqual(observation.private["inventories"][0]["SHEEP"], 2)
        self.assertEqual(state["carrying"][0], 2)

    def test_drop_follows_partial_and_discarded_custody(self):
        for room in range(4):
            states, env = world(inventories=[{"SHEEP": 2, "WOOL": 1}, {}],
                                shed={"FERTILIZER": 100 - room})
            state = CANDIDATE.new_state(); state["carrying"] = {0: 2}
            result, state = invoke(CANDIDATE, states[0].observation, env.configuration,
                                   action(["DROP"]), state)
            observation = advance(states, env, 0, result)
            self.assertEqual(state["reserved"], min(2, room))
            self.assertEqual(sum(state["carrying"].values()), 0)
            self.assertEqual(observation.private["shed"].get("SHEEP", 0), min(2, room))

    def test_eod_hands_retired_and_real_sheep_rejoin(self):
        for seat, room in itertools.product((0, 1), range(5)):
            states, env = world(seat, step=119,
                                inventories=[{}, {"WOOL": 1, "SHEEP": 2}],
                                shed={"FERTILIZER": 100 - room})
            state = CANDIDATE.new_state(); state.update(last=118, carrying={1: 2})
            result, state = invoke(CANDIDATE, states[seat].observation, env.configuration,
                                   action(hands=[["PASS"]]), state)
            observation = advance(states, env, seat, result)
            self.assertEqual(state["carrying"], {})
            self.assertEqual(state["reserved"], min(2, max(0, room - 1)))
            self.assertEqual(observation.farms[seat]["hands"], [])
            next_parent = action(["PICKUP", "COW", 1])
            result, state = invoke(CANDIDATE, observation, env.configuration, next_parent, state)
            expected = "SHEEP" if room >= 2 else "COW"
            self.assertEqual(result["farmer"][1], expected)

    def test_eod_market_deposit_conservative_lower_bound(self):
        for seat in (0, 1):
            states, env = world(seat, step=119, inventories=[{}, {"SHEEP": 1}],
                                shed={"FERTILIZER": 99})
            state = CANDIDATE.new_state(); state["carrying"] = {1: 1}
            result, state = invoke(CANDIDATE, states[seat].observation, env.configuration,
                                   action(market=[["BUY_PRODUCT", "WHEAT", 1]]), state)
            observation = advance(states, env, seat, result)
            self.assertEqual(state["reserved"], 0)
            self.assertEqual(observation.private["shed"].get("SHEEP", 0), 0)
            self.assertEqual(state["carrying"], {})

    def test_eod_sale_released_room_not_speculatively_credited(self):
        states, env = world(step=119, inventories=[{}, {"SHEEP": 1}], shed={"WOOL": 100})
        state = CANDIDATE.new_state(); state["carrying"] = {1: 1}
        result, state = invoke(CANDIDATE, states[0].observation, env.configuration,
                               action(market=[["SELL", "WOOL", 1]]), state)
        observation = advance(states, env, 0, result)
        self.assertEqual(state["reserved"], 0)
        self.assertEqual(observation.private["shed"].get("SHEEP", 0), 1)

    def test_harvest_credit_matches_real_multi_actor_output(self):
        for seat, first in itertools.product((0, 1), (["HARVEST"], ["HARVEST", "ignored"])):
            tile = ENGINE._new_animal("SHEEP", 1); tile["yield_units"] = 6
            states, env = world(seat, tile=tile)
            state = CANDIDATE.new_state(); state["sites"] = {(4, 4): 1}
            result, state = invoke(CANDIDATE, states[seat].observation, env.configuration,
                                   action(first, [["HARVEST"]]), state)
            observation = advance(states, env, seat, result)
            harvested = sum(inv.get("WOOL", 0) for inv in observation.private["inventories"])
            self.assertEqual(harvested, 6)
            self.assertEqual(state["wool_credit"], harvested)
            self.assertEqual(state["extra_wool_harvested"], harvested)

    def test_unowned_site_has_no_harvest_credit(self):
        tile = ENGINE._new_animal("SHEEP", 1); tile["yield_units"] = 6
        states, env = world(tile=tile)
        result, state = invoke(CANDIDATE, states[0].observation, env.configuration,
                               action(["HARVEST"]))
        advance(states, env, 0, result)
        self.assertEqual(state["wool_credit"], 0)

    def test_owned_native_sheep_place_confirmed_once(self):
        states, env = world(inventories=[{"SHEEP": 2}, {}], tile={"kind": "PASTURE"})
        state = CANDIDATE.new_state(); state["carrying"] = {0: 2}
        result, state = invoke(CANDIDATE, states[0].observation, env.configuration,
                               action(["PLACE", "SHEEP"]), state)
        observation = advance(states, env, 0, result)
        self.assertEqual(state["carrying"][0], 1)
        _, state = invoke(CANDIDATE, observation, env.configuration, action(), state)
        self.assertEqual(state["placed"], 1)
        self.assertEqual(state["carrying"][0], 1)

    def test_proposal_does_not_mutate_live_state(self):
        states, env = world()
        state = CANDIDATE.new_state(); before = copy.deepcopy(state)
        proposal = CANDIDATE.propose_s2_swap(states[0].observation,
            action(market=[["BUY_ANIMAL", "COW", 1]]), state, enabled=True,
            configuration=env.configuration, native_tape=[action()] * 720)
        self.assertEqual(state, before)
        returned = proposal.action
        self.assertEqual(returned["market"], [["BUY_ANIMAL", "SHEEP", 1]])
        self.assertTrue(proposal.commit(state, returned))
        self.assertEqual(state["pending_buy"]["quantity"], 1)
        self.assertFalse(proposal.commit(state, returned))

    def test_rejected_final_action_cannot_create_purchase_receipt(self):
        states, env = world()
        state = CANDIDATE.new_state(); before = copy.deepcopy(state)
        parent = action(market=[["BUY_ANIMAL", "COW", 1]])
        proposal = CANDIDATE.propose_s2_swap(states[0].observation, parent, state,
            enabled=True, configuration=env.configuration, native_tape=[action()] * 720)
        self.assertFalse(proposal.commit(state, parent))
        self.assertEqual(state, before)
        self.assertFalse(proposal.commit(state, proposal.action))

    def test_proposal_rejects_state_drift(self):
        states, env = world()
        state = CANDIDATE.new_state()
        proposal = CANDIDATE.propose_s2_swap(states[0].observation, action(), state,
            enabled=True, configuration=env.configuration, native_tape=[action()] * 720)
        state["requested"] += 1; before = copy.deepcopy(state)
        self.assertFalse(proposal.commit(state, proposal.action))
        self.assertEqual(state, before)

    def test_proposal_action_cannot_mutate_receipt(self):
        states, env = world()
        state = CANDIDATE.new_state(); before = copy.deepcopy(state)
        proposal = CANDIDATE.propose_s2_swap(states[0].observation,
            action(market=[["BUY_ANIMAL", "COW", 1]]), state, enabled=True,
            configuration=env.configuration, native_tape=[action()] * 720)
        first = proposal.action; first["market"][0][2] = 99
        self.assertEqual(proposal.action["market"][0][2], 1)
        self.assertFalse(proposal.commit(state, first))
        self.assertEqual(state, before)

    def test_proposal_rejects_bool_float_quantity_aliases(self):
        for quantity in (True, 1.0):
            states, env = world()
            state = CANDIDATE.new_state()
            proposal = CANDIDATE.propose_s2_swap(states[0].observation,
                action(market=[["BUY_ANIMAL", "COW", 1]]), state, enabled=True,
                configuration=env.configuration, native_tape=[action()] * 720)
            result = proposal.action; result["market"][0][2] = quantity
            self.assertFalse(proposal.commit(state, result))
            self.assertIsNone(state["pending_buy"])

    def test_ghost_plant_demand_changes_structure_prefix(self):
        for seat in (0, 1):
            states, env = world(seat, inventories=[{}, {}, {"SHEEP": 1}, {"WOOL": 2}],
                                shed={"FERTILIZER": 99})
            observation = states[seat].observation
            observation.private["seeds"] = {"WHEAT": 1}
            parent = action(["PLANT", "WHEAT"], [["BUILD_PASTURE"],
                            ["PLACE", "SHEEP"], ["DROP"], ["PLANT", "WHEAT"]])
            predicted = CANDIDATE._projected_shed(parent, observation)
            after = advance(states, env, seat, parent)
            self.assertEqual(positive_stock(predicted), positive_stock(after.private["shed"]))
            self.assertEqual(predicted.get("WOOL"), 1)
            self.assertEqual(after.farms[seat]["tiles"][4][4].get("animal"), "SHEEP")

    def test_constructed_eod_rejoin_economic_segment(self):
        # Identical reachable-type midgame inventories and authored actions.
        # This is asset recovery, NOT a natural-game activation or field gate.
        for seat in (0, 1):
            outcomes = []
            for mod in (PARENT, CANDIDATE):
                states, env = world(seat, step=119, inventories=[{}, {"SHEEP": 1}],
                                    shed={"WHEAT": 30}, tile={"kind": "PASTURE"})
                state = mod.new_state(); state.update(last=118, carrying={1: 1},
                                                      confirmed=1, requested=1)
                for step in range(119, 367):
                    hour = step % 24
                    unit = {0: ["PICKUP", "COW", 1], 1: ["PLACE", "COW"],
                            2: ["PICKUP", "WHEAT", 1], 3: ["FEED"], 4: ["CARE"],
                            5: ["HARVEST"], 6: ["DROP"]}.get(hour, ["PASS"])
                    market = [["SELL", "WOOL", 1]] if hour == 6 else []
                    if step == 366:
                        unit = ["DROP"]
                        market = [["SELL", "WOOL", 100], ["SELL", "WHEAT", 100]]
                    result, state = invoke(mod, states[seat].observation, env.configuration,
                                           action(unit, market=market), state)
                    after = advance(states, env, seat, result)
                outcomes.append({"cash": after.farms[seat]["money"],
                                 "shed": positive_stock(after.private["shed"]),
                                 "placed": state["placed"],
                                 "harvested": state["extra_wool_harvested"]})
            self.assertEqual(outcomes[0]["placed"], 0)
            self.assertEqual(outcomes[1]["placed"], 1)
            self.assertGreater(outcomes[1]["cash"], outcomes[0]["cash"])
            self.assertNotIn("WHEAT", outcomes[0]["shed"])
            self.assertNotIn("WHEAT", outcomes[1]["shed"])
            WITNESSES.append({"seat": seat, "callbacks_per_arm": 248,
                              "parent": outcomes[0], "candidate": outcomes[1],
                              "cash_delta": outcomes[1]["cash"] - outcomes[0]["cash"]})

    def test_primitive_projection_matches_full_interpreter_matrix(self):
        actions = [["PASS"], ["DROP"], ["PICKUP", "WOOL", 2],
                   ["PLACE", "SHEEP"], ["PLACE", "GOOSE"], ["PLACE", "WOOL", 2],
                   ["BUILD_PASTURE"], ["BUILD_COOP"], ["DIG"], ["HARVEST"],
                   ["PLANT", "WHEAT"], ["NORTH"], ["PLACE", "COW", 0]]
        tiles = [None, "LOCKED", {"kind": "PASTURE"}, {"kind": "COOP"},
                 ENGINE._new_animal("SHEEP", 1), ENGINE._new_plant("WHEAT", 0, 24)]
        rng = random.Random(90426)
        for seat, index in itertools.product((0, 1), range(360)):
            inventories = [{"SHEEP": rng.randrange(3), "WOOL": rng.randrange(4),
                            "GOOSE": rng.randrange(2), "COW": 1} for _ in range(3)]
            states, env = world(seat, inventories=inventories,
                                shed={"FERTILIZER": rng.choice((0, 95, 98, 99, 100)),
                                      "WOOL": 0, "SHEEP": 0}, tile=tiles[index % len(tiles)])
            observation = states[seat].observation
            observation.private["seeds"] = {"WHEAT": 1}
            selected = [copy.deepcopy(rng.choice(actions)) for _ in range(3)]
            # A ghost request changes atomic PLANT validation but is never applied.
            if index % 3 == 0:
                selected.append(["PLANT", "WHEAT"])
            parent = action(selected[0], selected[1:])
            before = copy.deepcopy(observation)
            projected = CANDIDATE._projected_shed(parent, observation)
            self.assertEqual(observation, before)
            after = advance(states, env, seat, parent)
            self.assertEqual(positive_stock(projected), positive_stock(after.private["shed"]),
                             (seat, index, parent))

    def test_custody_and_sale_conservation_matrix(self):
        rng = random.Random(1882)
        for seat, index in itertools.product((0, 1), range(240)):
            step = 119 if index % 3 == 0 else 100
            inventories = [{"SHEEP": rng.randrange(3), "WOOL": rng.randrange(4)}
                           for _ in range(3)]
            states, env = world(seat, step=step, inventories=inventories,
                                shed={"SHEEP": rng.randrange(3),
                                      "FERTILIZER": rng.choice((0, 90, 95))},
                                tile=rng.choice((None, {"kind": "PASTURE"})))
            observation = states[seat].observation
            choices = [["PASS"], ["DROP"], ["PICKUP", "COW", 1],
                       ["PICKUP", "SHEEP", 1], ["PLACE", "COW"],
                       ["PLACE", "SHEEP"], ["BUILD_PASTURE"], ["DIG"]]
            selected = [copy.deepcopy(rng.choice(choices)) for _ in range(3)]
            market = [["BUY_PRODUCT", "WHEAT", rng.randrange(3)]] if index % 5 == 0 else []
            state = CANDIDATE.new_state()
            state["reserved"] = observation.private["shed"]["SHEEP"]
            state["carrying"] = {i: inv["SHEEP"] for i, inv in enumerate(inventories)}
            owned_before = state["reserved"] + sum(state["carrying"].values())
            parent = action(selected[0], selected[1:], market)
            before = copy.deepcopy(observation); before_parent = copy.deepcopy(parent)
            result, state = invoke(CANDIDATE, observation, env.configuration, parent, state)
            self.assertEqual(observation, before); self.assertEqual(parent, before_parent)
            after = advance(states, env, seat, result)
            self.assertLessEqual(state["reserved"], after.private["shed"].get("SHEEP", 0))
            for actor, n in state["carrying"].items():
                self.assertLessEqual(n, after.private["inventories"][actor].get("SHEEP", 0))
            after_tokens = (state["reserved"] + sum(state["carrying"].values())
                            + len(state["pending_places"]))
            self.assertLessEqual(after_tokens, owned_before)
            for pending in state["pending_places"]:
                x, y = pending["site"]
                self.assertEqual(after.farms[seat]["tiles"][y][x].get("animal"), "SHEEP")


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LifecycleTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("ENGINE_CALLS", ENGINE_CALLS)
    print("ENGINE_INITIALIZATIONS", ENGINE_INITIALIZATIONS)
    print("ENGINE_TRANSITIONS", ENGINE_CALLS - ENGINE_INITIALIZATIONS)
    print("CONSTRUCTED_WITNESSES", __import__("json").dumps(WITNESSES, sort_keys=True))
    print("PARENT", builder.git_blob(PARENT_BYTES))
    print("CANDIDATE", builder.git_blob(CANDIDATE_BYTES))
    raise SystemExit(not result.wasSuccessful())
