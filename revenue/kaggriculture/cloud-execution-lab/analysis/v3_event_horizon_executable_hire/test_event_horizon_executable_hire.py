#!/usr/bin/env python3
"""Contracts for the source-bound event-horizon executable-HIRE carrier."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
LAB = HERE.parent.parent
CANONICAL_SOURCE = LAB / "frozen_selected.py"
MATERIALIZER_PATH = HERE / "materialize_event_horizon_executable_hire.py"

spec = importlib.util.spec_from_file_location("hire_materializer", MATERIALIZER_PATH)
assert spec and spec.loader
carrier = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = carrier
spec.loader.exec_module(carrier)


def _minimal_source() -> str:
    """Build a source-shaped fixture whose Git identity can be test-patched."""
    return """def apply_represented_market(farm, private, orders, size):
    for order in orders or ():
        if not order:
            continue
        if order[0]=='SELL' and len(order)>2:
            private['shed'][order[1]]=max(0,private['shed'].get(order[1],0)-max(0,int(order[2])))
        elif order[0] in ('BUY_PRODUCT','BUY_ANIMAL') and len(order)>2:
            private['shed'][order[1]]=private['shed'].get(order[1],0)+max(0,int(order[2]))
        elif order[0]=='HIRE':
            farm['hands'].append(m._spawn_hand(farm,size))
            private['inventories'].append({})


def represented_shed_event(now, baseline_end, hard_end, route, farm, private, config,
                           current_market=None):
    if hard_end<=baseline_end:
        return None
    f,p=copy.deepcopy(farm),copy.deepcopy(private)
    size=len(f['tiles'])
    apply_represented_market(f,p,current_market,size)
    turns_per_day=int(config.get('turnsPerDay',24))
    for t in range(now+1,hard_end+1):
        action=route[t] if t<len(route) else parent.PASS
        before=sum(p['shed'].values())
        acts=[action.get('farmer',['PASS']),*action.get('hands',[])]
        for i,a in enumerate(acts):
            m._apply_unit_action(f,p,i,a,size,t//turns_per_day,turns_per_day,10**6)
        after=sum(p['shed'].values())
        if t>baseline_end and after>before:
            return t
        apply_represented_market(f,p,action.get('market',[]),size)
    return None


def _score_reach():
    unit_event=(represented_shed_event(
        0, 0, 0, [], {}, {}, {}, []))
    end=0
    if unit_event is not None:
        end=max(end,unit_event)
    return end
"""


def _extract_functions(source: str, name: str):
    """Execute the two audited functions with a deterministic mechanics stub."""
    start = source.index("def apply_represented_market")
    reach = source.index("def represented_shed_event", start)
    next_def = source.find("\ndef ", reach + len("def represented_shed_event"))
    next_class = source.find("\nclass ", reach + len("def represented_shed_event"))
    ends = [value for value in (next_def, next_class) if value != -1]
    end = min(ends) if ends else len(source)
    function_text = source[start:end]

    module = types.ModuleType(name)
    module.copy = copy
    module.parent = types.SimpleNamespace(
        PASS={"farmer": ["PASS"], "hands": [], "market": []}
    )

    def spawn_hand(farm, size):
        return {
            "identifier": f"sim-hand-{len(farm['hands'])}",
            "location": {"vertical": 0, "horizontal": 0},
        }

    def unit_action(farm, private, actor, action, *_args):
        # Actor zero is the farmer; hired hands begin at one.
        if actor >= 1 + len(farm["hands"]):
            return
        if not action:
            return
        inventory = private["inventories"][actor]
        verb = action[0]
        if verb == "PICKUP" and len(action) > 2:
            item, requested = action[1], max(0, int(action[2]))
            quantity = min(requested, max(0, int(private["shed"].get(item, 0))))
            private["shed"][item] = private["shed"].get(item, 0) - quantity
            inventory[item] = inventory.get(item, 0) + quantity
        elif verb == "DROP" and len(action) > 2:
            item, requested = action[1], max(0, int(action[2]))
            quantity = min(requested, max(0, int(inventory.get(item, 0))))
            inventory[item] = inventory.get(item, 0) - quantity
            private["shed"][item] = private["shed"].get(item, 0) + quantity

    module.m = types.SimpleNamespace(
        _spawn_hand=spawn_hand,
        _apply_unit_action=unit_action,
    )
    exec(function_text, module.__dict__)
    return module.apply_represented_market, module.represented_shed_event


def _phantom_hire_route():
    empty = {"farmer": ["PASS"], "hands": [], "market": []}
    return [
        copy.deepcopy(empty),
        {"farmer": ["PASS"], "hands": [], "market": [["HIRE", 0, 0]]},
        {"farmer": ["PASS"], "hands": [["PICKUP", "WHEAT", 1]], "market": []},
        {"farmer": ["PASS"], "hands": [["DROP", "WHEAT", 1]], "market": []},
    ]


class CarrierTests(unittest.TestCase):
    def _candidate_for(self, source: str) -> str:
        actual = carrier.git_blob_sha1(source.encode())
        with mock.patch.object(carrier, "SOURCE_GIT_BLOB_SHA1", actual):
            return carrier.materialize(source)

    def test_git_blob_identity_uses_git_header(self):
        payload = b"abc"
        expected = hashlib.sha1(b"blob 3\0abc").hexdigest()
        self.assertEqual(carrier.git_blob_sha1(payload), expected)

    def test_fails_closed_on_source_drift(self):
        with self.assertRaisesRegex(ValueError, "source drift"):
            carrier.materialize("not the pinned source")

    def test_replacement_is_unique_and_non_hire_actions_are_byte_exact(self):
        source = _minimal_source()
        candidate = self._candidate_for(source)
        self.assertEqual(candidate.count(carrier.NEW_HIRE_BRANCH), 1)
        self.assertNotIn(carrier.OLD_HIRE_BRANCH, candidate)
        before_prefix, before_suffix = source.split(carrier.OLD_HIRE_BRANCH)
        after_prefix, after_suffix = candidate.split(carrier.NEW_HIRE_BRANCH)
        self.assertEqual((before_prefix, before_suffix), (after_prefix, after_suffix))

    def test_zero_cash_hire_intent_no_longer_invents_actor(self):
        source = _minimal_source()
        candidate = self._candidate_for(source)
        predecessor_fn, _ = _extract_functions(source, "predecessor")
        candidate_fn, _ = _extract_functions(candidate, "candidate")
        order = [["HIRE", 0, 0]]

        pred_farm = {"money": 0, "hands": [], "tiles": [[{}]]}
        pred_private = {"shed": {}, "inventories": [{}]}
        predecessor_fn(pred_farm, pred_private, order, 1)
        self.assertEqual(len(pred_farm["hands"]), 1)
        self.assertEqual(len(pred_private["inventories"]), 2)

        cand_farm = {"money": 0, "hands": [], "tiles": [[{}]]}
        cand_private = {"shed": {}, "inventories": [{}]}
        candidate_fn(cand_farm, cand_private, order, 1)
        self.assertEqual(cand_farm["hands"], [])
        self.assertEqual(cand_private["inventories"], [{}])

    def test_phantom_hire_reaches_score_facing_horizon_extension(self):
        source = _minimal_source()
        candidate = self._candidate_for(source)
        _, predecessor_event = _extract_functions(source, "predecessor_event")
        _, candidate_event = _extract_functions(candidate, "candidate_event")
        farm = {"money": 0, "hands": [], "tiles": [[{}]]}
        private = {"shed": {"WHEAT": 1}, "inventories": [{}]}
        route = _phantom_hire_route()

        self.assertEqual(
            predecessor_event(0, 2, 3, route, farm, private, {"turnsPerDay": 24}, []),
            3,
        )
        self.assertIsNone(
            candidate_event(0, 2, 3, route, farm, private, {"turnsPerDay": 24}, [])
        )

    def test_existing_actor_control_preserves_real_event(self):
        source = _minimal_source()
        candidate = self._candidate_for(source)
        _, predecessor_event = _extract_functions(source, "predecessor_control_event")
        _, candidate_event = _extract_functions(candidate, "candidate_control_event")
        route = _phantom_hire_route()
        route[1]["market"] = []
        farm = {"money": 0, "hands": [{"identifier": "existing"}], "tiles": [[{}]]}
        private = {"shed": {"WHEAT": 1}, "inventories": [{}, {}]}
        args = (0, 2, 3, route, farm, private, {"turnsPerDay": 24}, [])
        self.assertEqual(predecessor_event(*args), 3)
        self.assertEqual(candidate_event(*args), 3)

    def test_sell_and_buy_simulation_remain_identical(self):
        source = _minimal_source()
        candidate = self._candidate_for(source)
        predecessor_fn, _ = _extract_functions(source, "predecessor_market_control")
        candidate_fn, _ = _extract_functions(candidate, "candidate_market_control")
        orders = [["SELL", "WHEAT", 2], ["BUY_PRODUCT", "FERTILIZER", 3]]
        states = []
        for fn in (predecessor_fn, candidate_fn):
            farm = {"money": 0, "hands": [], "tiles": [[{}]]}
            private = {"shed": {"WHEAT": 5}, "inventories": [{}]}
            fn(farm, private, orders, 1)
            states.append((farm, private))
        self.assertEqual(states[0], states[1])
        self.assertEqual(states[0][1]["shed"], {"WHEAT": 3, "FERTILIZER": 3})

    def test_materialized_file_round_trip(self):
        source = _minimal_source()
        candidate = self._candidate_for(source)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "candidate.py"
            path.write_text(candidate, encoding="utf-8")
            self.assertEqual(path.read_text(encoding="utf-8"), candidate)

    @unittest.skipUnless(CANONICAL_SOURCE.exists(), "canonical source is available in repository CI")
    def test_real_canonical_blob_materializes_and_runs_witness(self):
        source = CANONICAL_SOURCE.read_text(encoding="utf-8")
        self.assertEqual(
            carrier.git_blob_sha1(source.encode("utf-8")), carrier.SOURCE_GIT_BLOB_SHA1
        )
        candidate = carrier.materialize(source)
        _, predecessor_event = _extract_functions(source, "real_predecessor_event")
        _, candidate_event = _extract_functions(candidate, "real_candidate_event")
        farm = {"money": 0, "hands": [], "tiles": [[{}]]}
        private = {"shed": {"WHEAT": 1}, "inventories": [{}]}
        args = (0, 2, 3, _phantom_hire_route(), farm, private, {"turnsPerDay": 24}, [])
        self.assertEqual(predecessor_event(*args), 3)
        self.assertIsNone(candidate_event(*args))


if __name__ == "__main__":
    unittest.main()
