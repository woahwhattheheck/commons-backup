# SPDX-License-Identifier: Apache-2.0
"""E18 acceptance-rule contracts; pure optimizer comparisons, no game execution."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

# The production runtime flattens these attributed sibling modules into its
# archive root. A clean repository checkout keeps their source in sibling labs,
# so make that same import contract explicit for this standalone test.
KAGGRICULTURE = Path(__file__).resolve().parent.parent
for sibling in ('cloud-runtime-pulse', 'cloud-quickstep'):
    sys.path.insert(0, str(KAGGRICULTURE / sibling))

from selected_sell_core import optimize_lot
from frozen_selected import seller_choice_rank


REFERENCE = ((0, 2),)
RISKY = ((0, 1), (3, 1))
NO_RIVAL_ONLY = ((0, 0), (3, 2))


class FakeMarketPath:
    """Deterministic scenario surface for comparing admission rules only."""
    def __init__(self, item, inventory, params, shops, config, now, end):
        self.now = now
        self.end = end

    @staticmethod
    def _scenario(rival, alignment):
        if rival == 0 and alignment == 'paired':
            return 'no_rival'
        if rival == 1 and alignment == 'paired':
            return 'observed_paired'
        if rival == 1 and alignment == 'after':
            return 'observed_later_order'
        if rival == ((1, 1),) and alignment == 'paired':
            return 'observed_next_turn'
        if rival == ((2, 1),) and alignment == 'paired':
            return 'observed_before_delayed_batch'
        raise AssertionError((rival, alignment))

    def score(self, plan, quantity, rival, alignment, terminal=False):
        plan = tuple(plan)
        scenario = self._scenario(rival, alignment)
        if plan == REFERENCE:
            relative = 0.0
        elif plan == RISKY:
            relative = -1.0 if scenario == 'no_rival' else 4.0
        elif plan == NO_RIVAL_ONLY:
            relative = 2.0 if scenario == 'no_rival' else 0.0
        else:
            relative = -6.0
        return relative, relative, 0.0, 0


def run(rule='strict', extra=None):
    config = {'sellAcceptanceRule': rule}
    config.update(extra or {})
    with patch('selected_sell_core.MarketPath', FakeMarketPath):
        return optimize_lot(
            item='MILK',
            quantity=2,
            inventory=100,
            params=None,
            shops=[],
            config=config,
            now=0,
            dates=[0, 3],
            reference=REFERENCE,
            rival_quantity=1,
            minimum_now=0,
            capacity_ok=lambda _plan: True,
            last=718,
        )


class AcceptanceRuleTests(unittest.TestCase):
    def test_strict_default_keeps_reference(self):
        plan, info = run()
        self.assertEqual(plan, REFERENCE)
        self.assertEqual(info['acceptance_rule'], 'strict')
        self.assertFalse(info['accepted'])
        self.assertEqual(info['worst_relative_gain'], 0.0)

    def test_expected_downside_accepts_positive_expectation_with_bounded_loss(self):
        plan, info = run('expected_downside', {'sellDownsideBound': 1})
        self.assertEqual(plan, RISKY)
        self.assertTrue(info['accepted'])
        self.assertEqual(info['worst_relative_gain'], -1.0)
        self.assertEqual(info['weighted_expected_gain'], 3.0)
        self.assertEqual(info['acceptance_score'], 3.0)
        self.assertEqual(info['downside_bound'], 1.0)

    def test_expected_weights_are_explicit_and_change_choice(self):
        plan, info = run('expected_downside', {
            'sellDownsideBound': 1,
            'sellScenarioWeights': {'no_rival': 1.0},
        })
        self.assertEqual(plan, NO_RIVAL_ONLY)
        self.assertEqual(info['scenario_weights']['no_rival'], 1.0)
        self.assertEqual(
            sum(v for k, v in info['scenario_weights'].items() if k != 'no_rival'),
            0.0,
        )
        self.assertEqual(info['weighted_expected_gain'], 2.0)

    def test_minimax_regret_requires_strict_regret_reduction(self):
        plan, info = run('minimax_regret')
        self.assertEqual(plan, RISKY)
        self.assertTrue(info['accepted'])
        self.assertEqual(info['reference_max_regret'], 4.0)
        self.assertEqual(info['max_regret'], 3.0)
        self.assertEqual(info['acceptance_score'], 1.0)
        self.assertEqual(info['scenario_regrets']['no_rival'], 3.0)

    def test_unknown_rule_falls_back_to_strict(self):
        plan, info = run('not-a-rule')
        self.assertEqual(plan, REFERENCE)
        self.assertEqual(info['acceptance_rule'], 'strict')
        self.assertFalse(info['accepted'])

    def test_frozen_selector_can_admit_non_strict_candidate_by_acceptance_score(self):
        eligible, rank = seller_choice_rank({
            'accepted': True,
            'forced_feasibility': False,
            'worst_relative_gain': -1.0,
            'acceptance_score': 3.0,
        })
        self.assertTrue(eligible)
        self.assertEqual(rank, (False, 3.0))


if __name__ == '__main__':
    unittest.main()
