"""Exact finite enumeration and source-schedule correspondence; no game calls."""
from __future__ import annotations
import copy
from collections import Counter
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
import unittest

from arrival_law import buyer_arrivals
from town_demand import DemandRules, build_schedule

RULES = None


def observed(step=226, shops=('BAKERY','PIZZA_SHOP','BRUNCH_SPOT')):
    return {'step':step,'town':{'unlocked_shops':list(shops)}}


def cfg(**extra):
    return dict(episodeSteps=720,turnsPerDay=24,townShopUnlockInterval=3,
                townShopSellInterval=4,**extra)


def fraction(row):
    return Fraction(row['numerator'],row['denominator'])


class ArrivalTests(unittest.TestCase):
    def call(self, obs=None, config=None, **extra):
        return buyer_arrivals(observed() if obs is None else obs,
                              {} if config is None else config, RULES,
                              buyers=extra.pop('buyers',('YARN_STORE',)), **extra)

    def test_default_support_and_no_implicit_probabilities(self):
        r=self.call()
        self.assertEqual([x['first_visible_step'] for x in r['first_arrivals']],
                         [288,360,432,504,576])
        self.assertEqual(r['full_identity_paths'],32768)
        self.assertTrue(all(x['first_buyer_mass'] is None for x in r['first_arrivals']))
        self.assertIsNone(r['no_future_buyer_mass'])

    def test_exact_first_arrival_mass_by_complete_identity_enumeration(self):
        names=tuple(x for x,_ in RULES.shops)
        counts=Counter(next((i for i,s in enumerate(path) if s=='YARN_STORE'),None)
                       for path in product(names,repeat=5))
        r=self.call(model='independent_uniform')
        for i,row in enumerate(r['first_arrivals']):
            self.assertEqual(fraction(row['first_buyer_mass']),Fraction(counts[i],8**5))
        self.assertEqual(fraction(r['no_future_buyer_mass']),Fraction(counts[None],8**5))
        self.assertEqual(sum(fraction(x['first_buyer_mass']) for x in r['first_arrivals'])+
                         fraction(r['no_future_buyer_mass']),1)

    def test_two_buyer_types_identity_enumeration(self):
        targets=('BAKERY','BRUNCH_SPOT')
        r=self.call(observed(70,('PIZZA_SHOP',)*5),buyers=targets,model='independent_uniform')
        names=tuple(x for x,_ in RULES.shops)
        counts=Counter(next((i for i,s in enumerate(path) if s in targets),None)
                       for path in product(names,repeat=3))
        for i,row in enumerate(r['first_arrivals']):
            self.assertEqual(fraction(row['first_buyer_mass']),Fraction(counts[i],8**3))

    def test_buyer_everywhere_has_first_draw_mass_one(self):
        r=self.call(buyers=tuple(x for x,_ in RULES.shops),model='independent_uniform')
        self.assertEqual(fraction(r['first_arrivals'][0]['first_buyer_mass']),1)
        self.assertTrue(all(fraction(x['first_buyer_mass'])==0 for x in r['first_arrivals'][1:]))

    def test_already_observed_buyer_is_separate(self):
        r=self.call(observed(226,('YARN_STORE',)*3),model='independent_uniform')
        self.assertEqual(r['observed_buyer_instances'],3)
        self.assertEqual(fraction(r['first_arrivals'][0]['first_buyer_mass']),Fraction(1,8))

    def test_cap_full_means_no_future_draws(self):
        r=self.call(observed(226,('YARN_STORE',)*8),model='independent_uniform')
        self.assertEqual(r['remaining_draws'],0)
        self.assertEqual(fraction(r['no_future_buyer_mass']),1)
        self.assertEqual(fraction(r['at_least_one_future_buyer_mass']),0)

    def test_one_slot_at_cap(self):
        r=self.call(observed(70,('BAKERY',)*7),model='independent_uniform')
        self.assertEqual(r['remaining_draws'],1)
        self.assertEqual(fraction(r['at_least_one_future_buyer_mass']),Fraction(1,8))

    def test_marginal_single_buyer_demand_matches_existing_schedule(self):
        obs=observed(); queries=(288,289,360,361,718)
        r=self.call(market_steps=queries)
        baseline=build_schedule(obs,{},RULES,future_shops=('BAKERY',)*5)
        for i,row in enumerate(r['first_arrivals']):
            path=['BAKERY']*5; path[i]='YARN_STORE'
            candidate=build_schedule(obs,{},RULES,future_shops=path)
            for step in queries:
                expected=baseline.before_market(step)['WOOL']-candidate.before_market(step)['WOOL']
                self.assertEqual(row['one_instance_removed_before_market']['YARN_STORE'][str(step)]['WOOL'],expected)

    def test_same_turn_demand_is_not_in_market_quote(self):
        row=self.call(market_steps=(288,289))['first_arrivals'][0]
        self.assertEqual(row['one_instance_removed_before_market']['YARN_STORE']['288']['WOOL'],0)
        self.assertEqual(row['one_instance_removed_before_market']['YARN_STORE']['289']['WOOL'],2)

    def test_terminal_draw_has_no_remaining_market(self):
        r=self.call(observed(286,()),{'episodeSteps':289},market_steps=(287,),model='independent_uniform')
        self.assertFalse(r['first_arrivals'][0]['has_remaining_market'])
        self.assertEqual(r['first_arrivals'][0]['one_instance_removed_before_market']['YARN_STORE']['287']['WOOL'],0)

    def test_custom_ticks(self):
        r=self.call(observed(8,()),{'episodeSteps':22,'turnsPerDay':5,
                    'townShopUnlockInterval':2,'townShopSellInterval':3},market_steps=(9,12,13,20))
        first=r['first_arrivals'][0]
        self.assertEqual(first['first_visible_step'],10)
        self.assertEqual(first['one_instance_removed_before_market']['YARN_STORE']['12']['WOOL'],0)
        self.assertEqual(first['one_instance_removed_before_market']['YARN_STORE']['13']['WOOL'],2)

    def test_no_payoff_or_ranker_weights_inferred(self):
        r=self.call(model='independent_uniform')
        self.assertIsNone(r['scenario_weights_for_ranker'])
        self.assertFalse(r['draw_categories_are_complete_economic_scenarios'])
        self.assertFalse(r['model_is_hidden_seed_posterior'])
        self.assertFalse(r['model_is_empirically_calibrated'])

    def test_invalid_model_or_buyer(self):
        for value in ['uniform-posterior',False,1]:
            with self.assertRaises(ValueError): self.call(model=value)
        for buyers in [(),('YARN_STORE','YARN_STORE'),('UNKNOWN',)]:
            with self.assertRaises(ValueError): self.call(buyers=buyers)

    def test_market_queries_and_terminal_validation(self):
        for steps in [(225,),(719,),(True,),(288.0,)]:
            with self.assertRaises(ValueError): self.call(market_steps=steps)
        with self.assertRaises(ValueError): self.call(observed(719))

    def test_read_only_mapping_configuration(self):
        from types import MappingProxyType
        r=self.call(config=MappingProxyType({'episodeSteps':300,'townShopSellInterval':3}),
                    market_steps=(289,))
        self.assertEqual(r['end_step'],298)
        self.assertEqual(r['remaining_draws'],1)
        self.assertEqual(r['first_arrivals'][0]['one_instance_removed_before_market']['YARN_STORE']['289']['WOOL'],2)

    def test_public_inputs_unchanged_and_no_private_fields_needed(self):
        obs=observed(); config={}; before=copy.deepcopy((obs,config))
        self.call(obs,config,model='independent_uniform')
        self.assertEqual((obs,config),before)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(); parser.add_argument('--rules',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True); args=parser.parse_args()
    raw=json.loads(args.rules.read_text()); r=raw.get('rules',raw)
    RULES=DemandRules(tuple((a,tuple(b)) for a,b in r['shops']),tuple(r['products']),
                      tuple(r['center_products']),r['max_instances'])
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ArrivalTests))
    report={'methods':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
            'passed':result.wasSuccessful(),'enumerated_complete_identity_paths':32768+512,
            'new_engine_transitions':0,'new_game_calls':0,
            'example':buyer_arrivals(observed(),{},RULES,buyers=('YARN_STORE',),
                      market_steps=(288,289,360,361,432,504,576,718),model='independent_uniform')}
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
