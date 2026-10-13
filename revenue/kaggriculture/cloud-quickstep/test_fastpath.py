# SPDX-License-Identifier: Apache-2.0
"""Real frozen observer, canonical checkpoint, and optimizer-equivalence tests.

Usage: python test_fastpath.py --package /path/to/extracted/current
No private game input or network access is used by this test suite.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import itertools
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from seller_snapshot import seller_public_observation

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument('--package', required=True, type=Path)
args, remaining = parser.parse_known_args()
sys.path.insert(0, str(args.package.resolve()))
import scheduler
import selected_sell_core
import titan_runtime


def observation(player: int = 0, step: int = 20) -> dict:
    def tiles():
        return [
            [None, 'LOCKED', {'kind': 'PLANT', 'crop': 'CARROT', 'yield_units': 8,
                              'metadata': {'values': [1, 2]}}],
            [{'kind': 'ANIMAL', 'animal': 'COW', 'yield_units': 3},
             {'kind': 'PLANT', 'crop': 'WHEAT', 'yield_units': 4}, None],
        ]
    return {'step': step, 'player': player, 'farms': [
        {'tiles': tiles(), 'money': 900}, {'tiles': tiles(), 'money': 1100}],
        'private': {'shed': {'WOOL': 13}, 'seeds': {'CARROT': 2}},
        'market': {'inventory': {'MILK': 20}}, 'town': {'unlocked_shops': []}}


class SnapshotTests(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(seller_public_observation(None))

    def test_both_seats_match_existing_checkpoint_projection(self):
        for player in (0, 1):
            with self.subTest(player=player):
                obs = observation(player)
                result = seller_public_observation(obs)
                self.assertEqual(result, titan_runtime.TitanAgent._seller_public_observation(obs))
                self.assertEqual(set(result), {'step', 'player', 'farms'})
                self.assertEqual(result['farms'][player], {'tiles': []})
                self.assertEqual(result['farms'][1-player]['tiles'], obs['farms'][1-player]['tiles'])

    def test_metadata_normalization(self):
        obs = observation()
        obs.update(player='0', step='20')
        result = seller_public_observation(obs)
        self.assertIs(type(result['player']), int)
        self.assertIs(type(result['step']), int)

    def test_live_source_mutation_cannot_change_snapshot(self):
        obs = observation()
        result = seller_public_observation(obs)
        obs['farms'][1]['tiles'][0][2]['metadata']['values'].append(9)
        obs['farms'][1]['tiles'][1][0]['yield_units'] = 0
        obs['farms'][1]['tiles'].append([])
        self.assertEqual(result['farms'][1]['tiles'][0][2]['metadata']['values'], [1, 2])
        self.assertEqual(result['farms'][1]['tiles'][1][0]['yield_units'], 3)
        self.assertEqual(len(result['farms'][1]['tiles']), 2)

    def test_snapshot_mutation_cannot_change_live_source(self):
        obs = observation()
        original = deepcopy(obs)
        result = seller_public_observation(obs)
        result['farms'][1]['tiles'][0][2]['metadata']['values'].clear()
        self.assertEqual(obs, original)

    def test_completed_snapshot_can_be_retained_without_recopied_tiles(self):
        snapshot = seller_public_observation(observation())
        result = seller_public_observation(snapshot, copy_tiles=False)
        self.assertIsNot(result, snapshot)
        self.assertIs(result['farms'][1]['tiles'], snapshot['farms'][1]['tiles'])

    def test_unused_private_and_own_farm_bytes_are_not_copied(self):
        class Uncopyable:
            def __deepcopy__(self, memo):
                raise AssertionError('Unused observation field was copied')
        obs = observation()
        obs['private'] = Uncopyable()
        obs['farms'][0]['tiles'] = Uncopyable()
        obs['market'] = Uncopyable()
        obs['other_unused_field'] = Uncopyable()
        self.assertEqual(seller_public_observation(obs)['step'], 20)

    def test_real_observer_matches_full_history_for_both_seats(self):
        for player in (0, 1):
            with self.subTest(player=player):
                full = scheduler.SellScheduler()
                compact = scheduler.SellScheduler()
                for step in (20, 21, 22, 30, 31):
                    obs = observation(player, step)
                    rival = obs['farms'][1-player]['tiles']
                    if step >= 21:
                        rival[0][2]['yield_units'] = 3
                        rival[1][0]['yield_units'] = 0
                    if step >= 22:
                        rival[0][2] = None
                    full.observe(obs)
                    compact.observe(obs)
                    self.assertEqual(full.observed_harvests, compact.observed_harvests)
                    full.previous = deepcopy(obs)
                    compact.previous = seller_public_observation(obs)
                    self.assertEqual(titan_runtime.TitanAgent._seller_state(full),
                                     titan_runtime.TitanAgent._seller_state(compact))
                self.assertTrue(all(not rows for rows in compact.observed_harvests.values()))

    def test_checkpoint_restore_and_completed_fallback_observation(self):
        agent = titan_runtime.TitanAgent()
        agent._initialize()
        first = observation()
        agent.consumer.previous = seller_public_observation(first)
        agent.consumer.planned = {'CARROT': [(23, 4)]}
        agent.consumer.pending = {'CARROT': 4}
        agent._commit_seller_state()
        checkpoint = deepcopy(agent._completed_seller_state)
        skipped = observation(step=21)
        skipped['farms'][1]['tiles'][0][2]['yield_units'] = 3
        agent._remember_seller_fallback(skipped)
        # Completed snapshots are immutable by contract; a later in-progress
        # transform replaces previous rather than mutating the committed grid.
        first['farms'][1]['tiles'][0][2]['yield_units'] = 999
        agent.consumer.previous = seller_public_observation(first)
        self.assertEqual(agent._completed_seller_state, checkpoint)
        # Restore into a fresh consumer, as the canonical cancellation path does.
        agent.consumer = scheduler.SellScheduler()
        agent._restore_seller_state()
        self.assertEqual(agent.consumer.planned, checkpoint['planned'])
        self.assertEqual(agent.consumer.pending, checkpoint['pending'])
        self.assertEqual(agent.consumer.observed_harvests['CARROT'], [(21, 5)])
        self.assertEqual(agent.consumer.previous, seller_public_observation(skipped))


class CachedOptimizerTests(unittest.TestCase):
    def models(self, item='CARROT', inventory=30, now=20, end=25):
        shops = list(scheduler.m.SHOPS)[:3]
        config = {'townShopSellInterval': 4, 'townCenterSellInterval': 24}
        return tuple(cls(item, inventory, None, list(shops), dict(config), now, end)
                     for cls in (scheduler.MarketPath, selected_sell_core.MarketPath))

    def test_exact_scores_across_products_inventory_and_scenarios(self):
        count = 0
        for item, inventory, quantity in itertools.product(scheduler.PRODUCTS, (-20, 0, 50, 5000), (0, 1, 7)):
            baseline, cached = self.models(item=item, inventory=inventory)
            for plan, rival, alignment, terminal in itertools.product(
                ((), ((20, quantity),), ((21, quantity//2), (25, quantity-quantity//2))),
                (0, 5, ((21, 3), (24, 2))), ('paired', 'after', 'before'), (False, True)):
                self.assertEqual(baseline.score(plan, quantity, rival, alignment, terminal),
                                 cached.score(plan, quantity, rival, alignment, terminal))
                count += 1
        self.assertGreater(count, 1000)
        self.score_cases = count

    def test_cache_invalidates_after_shop_and_interval_mutations(self):
        baseline, cached = self.models()
        def compare():
            args = (((21, 4), (25, 3)), 9, ((22, 8),), 'paired')
            self.assertEqual(baseline.score(*args), cached.score(*args))
        compare()
        for model in (baseline, cached):
            model.shops[:] = list(scheduler.m.SHOPS)
        compare()
        for model in (baseline, cached):
            model.config['townShopSellInterval'] = 3
        compare()
        for model in (baseline, cached):
            model.config['townCenterSellInterval'] = 7
        compare()
        for model in (baseline, cached):
            model.now = 22
            model.end = 28
        compare()

    def test_empty_horizon_and_repeated_plan_keys(self):
        baseline, cached = self.models(now=30, end=29)
        for terminal in (False, True):
            args = (((30, 4), (30, 2)), 7, ((31, 3), (31, 4)), 'paired', terminal)
            self.assertEqual(baseline.score(*args), cached.score(*args))

    def test_cached_schedule_reused_by_actual_score(self):
        _, cached = self.models()
        with patch.object(selected_sell_core, 'absorption', wraps=selected_sell_core.absorption) as absorb:
            cached.score(((20, 4),), 7, 5, 'paired')
            initial = absorb.call_count
            self.assertEqual(initial, 6)
            cached.score(((21, 2), (25, 5)), 7, ((22, 3),), 'after')
            self.assertEqual(absorb.call_count, initial)
            cached.config['townShopSellInterval'] = 3
            cached.score(((20, 4),), 7, 5, 'paired')
            self.assertEqual(absorb.call_count, initial+6)

    def test_optimizer_plan_and_diagnostics_exact(self):
        for item, quantity, rival in itertools.product(('CARROT', 'MILK', 'WOOL'), (1, 7, 18), (0, 5)):
            kwargs = dict(item=item, quantity=quantity, inventory=30, params=None,
                          shops=list(scheduler.m.SHOPS)[:2], config={}, now=20,
                          dates=[20, 21, 23], reference=((20, quantity//2),),
                          rival_quantity=rival, minimum_now=0, last=718)
            self.assertEqual(scheduler.optimize_lot(**kwargs), selected_sell_core.optimize_lot(**kwargs))


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
