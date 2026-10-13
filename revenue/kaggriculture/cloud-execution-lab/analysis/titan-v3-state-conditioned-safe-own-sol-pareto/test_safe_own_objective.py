# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import textwrap
import unittest

import own_value_objective as target


FAKE_SOURCE = '''\
from __future__ import annotations
OPTIMIZE_CALLS = 0
RESULTS = []

class MarketPath:
    def __init__(self, item, inventory, params, shops, config, now, end):
        self.config = config
    def score(self, plan, quantity, rival, alignment, terminal=False):
        key = (tuple(tuple(row) for row in plan), repr(rival), alignment, bool(terminal))
        return tuple(self.config['scores'][key])

def optimize_lot(*, item, quantity, inventory, params, shops, config, now, dates,
                 reference, rival_quantity, minimum_now=0, capacity_ok=None, last=718):
    global OPTIMIZE_CALLS
    OPTIMIZE_CALLS += 1
    if OPTIMIZE_CALLS == 2 and config.get('raise_second'):
        raise RuntimeError('candidate pass failed')
    end=dates[-1]
    model=MarketPath(item,inventory,params,shops,config,now,end)
    scenarios=[('no_rival',0,'paired'),('observed_paired',rival_quantity,'paired'),('observed_later_order',rival_quantity,'after')]
    if end>now:
        scenarios.append(('observed_next_turn',((now+1,rival_quantity),),'paired'))
    if end>now+2:
        scenarios.append(('observed_before_delayed_batch',((end-1,rival_quantity),),'paired'))
    baseline=[model.score(reference,quantity,r,a,end==last) for _,r,a in scenarios]
    reference_feasible=(capacity_ok(reference) if capacity_ok else True) and dict(reference).get(now,0)>=minimum_now
    best_plan=tuple(reference); best_key=(0.0,0.0,0.0) if reference_feasible else (-float('inf'),-float('inf'),0.0); best_scores=baseline
    found_feasible=reference_feasible
    candidates={tuple(reference), *[tuple(tuple(row) for row in plan) for plan in config['candidates']]}
    for plan in sorted(candidates):
        if sum(q for _,q in plan)>quantity: continue
        if dict(plan).get(now,0)<minimum_now: continue
        first_score=model.score(plan,quantity,0,'paired',end==last)
        if first_score[0]-baseline[0][0] <= 0: continue
        if capacity_ok and not capacity_ok(plan): continue
        scores=[first_score]
        competitive=True
        for (_,r,a),b in zip(scenarios[1:],baseline[1:]):
            score=model.score(plan,quantity,r,a,end==last)
            if score[0]-b[0] <= 0:
                competitive=False
                break
            scores.append(score)
        if not competitive: continue
        deltas=[s[0]-b[0] for s,b in zip(scores,baseline)]
        key=(round(min(deltas),8),round(sum(deltas),8),float(dict(plan).get(now,0)))
        if key[0]>0 and key>best_key:
            best_key,best_plan,best_scores=key,plan,scores
            found_feasible=True
    accepted=best_key[0]>0
    forced=not reference_feasible and found_feasible
    result = (best_plan, {'plan':[list(row) for row in best_plan], 'reference':[list(row) for row in reference],
        'scenarios':{name:{'reference_relative_value':b[0], 'relative_value':s[0],
                           'own_receipts':s[1], 'rival_receipts':s[2], 'carry_units':s[3]}
                     for (name,_,_),b,s in zip(scenarios,baseline,best_scores)},
        'worst_relative_gain':best_key[0] if found_feasible else 0.0,
        'forced_feasibility':forced, 'feasible':found_feasible,
        'acceptance_rule':config.get('sellAcceptanceRule','strict'), 'accepted':accepted})
    RESULTS.append(result)
    return result
'''


class SafeOwnTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "selected_sell_core.py"
        self.source.write_text(textwrap.dedent(FAKE_SOURCE), encoding="utf-8")
        spec = importlib.util.spec_from_file_location("selected_sell_core_fixture", self.source)
        assert spec is not None and spec.loader is not None
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        data = self.source.read_bytes()
        self.saved = (
            target.EXPECTED_SELECTED_SELL_CORE_BLOB,
            target.EXPECTED_SCORE_NEEDLES,
            target.EXPECTED_OPTIMIZE_NEEDLES,
        )
        target.EXPECTED_SELECTED_SELL_CORE_BLOB = hashlib.sha1(
            b"blob " + str(len(data)).encode("ascii") + b"\0" + data
        ).hexdigest()
        target.EXPECTED_SCORE_NEEDLES = (
            "def score(self, plan, quantity, rival, alignment, terminal=False):",
            "return tuple(self.config['scores'][key])",
        )
        target.EXPECTED_OPTIMIZE_NEEDLES = (
            "baseline=[model.score(reference,quantity,r,a,end==last) for _,r,a in scenarios]",
            "first_score=model.score(plan,quantity,0,'paired',end==last)",
            "'forced_feasibility':forced",
        )

    def tearDown(self):
        (
            target.EXPECTED_SELECTED_SELL_CORE_BLOB,
            target.EXPECTED_SCORE_NEEDLES,
            target.EXPECTED_OPTIMIZE_NEEDLES,
        ) = self.saved
        self.temp.cleanup()

    @staticmethod
    def plans():
        return ((0, 0),), ((0, 1),), ((0, 2),)

    def config(self, *, unsafe=False, rule="strict"):
        reference, control, candidate = self.plans()
        scores = {}
        rivals = ((0, "paired"), (2, "paired"), (2, "after"))
        for index, (rival, alignment) in enumerate(rivals):
            terminal = False
            scores[(reference, repr(rival), alignment, terminal)] = (0, 10, 10, 0)
            scores[(control, repr(rival), alignment, terminal)] = (6, 16, 10, 0)
            relative = -1 if unsafe and index == 2 else 3
            scores[(candidate, repr(rival), alignment, terminal)] = (
                relative,
                20,
                21 if relative == -1 else 17,
                0,
            )
        return {
            "scores": scores,
            "candidates": [control, candidate],
            "sellAcceptanceRule": rule,
        }

    def call(self, config):
        return self.module.optimize_lot(
            item="CARROT", quantity=2, inventory=10, params={}, shops=[],
            config=config, now=0, dates=[0], reference=((0, 0),),
            rival_quantity=2, minimum_now=0, capacity_ok=lambda _plan: True, last=718,
        )

    def test_own_value_tuple_changes_only_element_zero(self):
        original = (3, 20, 17, 0)
        self.assertEqual(target.own_value_tuple(original), (20.0, 20, 17, 0))

    def test_safe_candidate_selected(self):
        receipt = target.install(module=self.module, expected_root=self.root)
        plan, info = self.call(self.config())
        self.assertEqual(plan, ((0, 2),))
        self.assertTrue(info["safe_own_selector"]["selected"])
        self.assertEqual(receipt["changed_field"], "MarketPath.score[0]")
        self.assertEqual(self.module.OPTIMIZE_CALLS, 2)

    def test_relative_regression_falls_back_to_exact_incumbent_object(self):
        target.install(module=self.module, expected_root=self.root)
        result = self.call(self.config(unsafe=True))
        self.assertIs(result, self.module.RESULTS[0])
        plan, info = result
        self.assertEqual(plan, ((0, 1),))
        self.assertNotIn("safe_own_selector", info)
        decision = self.module.__titan_safe_own_last_decision__
        self.assertFalse(decision["selected"])
        self.assertIn("relative_below_reference", decision["reason"])

    def test_non_strict_rule_runs_incumbent_once_and_returns_exact_object(self):
        target.install(module=self.module, expected_root=self.root)
        result = self.call(self.config(rule="expected_downside"))
        self.assertIs(result, self.module.RESULTS[0])
        plan, _info = result
        self.assertEqual(plan, ((0, 1),))
        self.assertEqual(self.module.OPTIMIZE_CALLS, 1)

    def test_candidate_exception_falls_back_to_exact_incumbent_object(self):
        target.install(module=self.module, expected_root=self.root)
        config = self.config()
        config["raise_second"] = True
        result = self.call(config)
        self.assertIs(result, self.module.RESULTS[0])
        self.assertEqual(result[0], ((0, 1),))
        decision = self.module.__titan_safe_own_last_decision__
        self.assertFalse(decision["selected"])
        self.assertEqual(decision["reason"], "candidate_error:RuntimeError")

    def test_idempotent_install(self):
        first = target.install(module=self.module, expected_root=self.root)
        second = target.install(module=self.module, expected_root=self.root)
        self.assertEqual(first, second)

    def test_source_drift_rejected(self):
        target.EXPECTED_SELECTED_SELL_CORE_BLOB = "0" * 40
        with self.assertRaises(target.ObjectiveBindingError):
            target.install(module=self.module, expected_root=self.root)

    def test_pure_gate_rejects_candidate_not_above_control(self):
        reference = {"s": {"own_value": 10.0, "relative_value": 0.0}}
        control = {"s": {"own_value": 20.0, "relative_value": 5.0}}
        candidate = {"s": {"own_value": 19.0, "relative_value": 4.0}}
        admitted, reason, _ = target._admit_candidate(
            reference=reference, control=control, candidate=candidate
        )
        self.assertFalse(admitted)
        self.assertIn("own_not_strictly_above_control", reason)

    def test_pure_gate_accepts_margin_sacrifice_without_reference_regression(self):
        reference = {"s": {"own_value": 10.0, "relative_value": 0.0}}
        control = {"s": {"own_value": 20.0, "relative_value": 10.0}}
        candidate = {"s": {"own_value": 25.0, "relative_value": 1.0}}
        admitted, reason, metrics = target._admit_candidate(
            reference=reference, control=control, candidate=candidate
        )
        self.assertTrue(admitted)
        self.assertEqual(reason, "safe_own_frontier_dominates")
        self.assertEqual(metrics["s"]["own_gain_vs_control"], 5.0)

    def test_malformed_plan_fails_closed(self):
        self.assertRaises(target.ObjectiveScoreError, target._canonical_plan, [(0, 1), (0, 2)], "x")

    def test_nonfinite_gate_rejected(self):
        reference = {"s": {"own_value": 10.0, "relative_value": 0.0}}
        control = {"s": {"own_value": 20.0, "relative_value": 5.0}}
        candidate = {"s": {"own_value": float("nan"), "relative_value": 4.0}}
        with self.assertRaises(target.ObjectiveScoreError):
            target._admit_candidate(reference=reference, control=control, candidate=candidate)


if __name__ == "__main__":
    unittest.main()
