# SPDX-License-Identifier: Apache-2.0
"""Discriminating mechanics/strategy cases, independent of the runtime hooks."""
import unittest
from pathlib import Path
from build import entry_bytes
from selective_carrot import CropChoice, absorption, crop_lot


def timeline(harvest=74, feed=None, drop=None, skip_water=None):
    events = []
    for t in range(96):
        action = ['PASS']; pos = (2, 2)
        if t == 0: action = ['PLANT', 'WHEAT']
        if t in (1, 25, 49, 73) and t != skip_water: action = ['WATER']
        if t == harvest: action = ['HARVEST']
        if t == feed: action = ['FEED']
        if t == drop: action = ['DROP']; pos = (4, 4)
        events.append((t, [(0, pos, action)]))
    return events


def observation():
    farm = {'farmer': [2,2], 'hands': [[3,3]], 'tiles': [[None]*10 for _ in range(10)],
            'money': 10000, 'hires_today': 1, 'unlocked_quadrants': ['NW']}
    return {'step': 241, 'player': 0, 'day': 10, 'hour': 1,
            'farms': [farm, {'tiles': [[None]*10 for _ in range(10)]}],
            'private': {'seeds': {'CARROT': 1, 'WHEAT': 1}, 'shed': {}, 'inventories': [{},{}]},
            'town': {'unlocked_shops': ['PET_CAFE']},
            'market': {'inventory': {'CARROT': 9500, 'WHEAT': 9900}}}


class StrategyCases(unittest.TestCase):
    def test_capacity_profile_changes_only_constructor_argument(self):
        original = (Path(__file__).parent/'choice_entry.py').read_bytes()
        self.assertEqual(entry_bytes(4), original)
        for capacity in (8,12):
            transformed = entry_bytes(capacity)
            self.assertEqual(transformed.replace(f'CropChoice(market_price, max_active={capacity})'.encode(),
                                                b'CropChoice(market_price)'), original)

    def test_age_three_equal_output_and_early_drop(self):
        p = crop_lot(timeline(drop=80), 0, 0, (2,2))
        self.assertEqual((p['quantity'], p['harvest_step'], p['sale_step']), (3,74,80))

    def test_age_four_harvest_is_ineligible(self):
        self.assertIsNone(crop_lot(timeline(harvest=None)+[(96,[(0,(2,2),['HARVEST'])])],0,0,(2,2)))

    def test_unwatered_planting_day_dies(self):
        self.assertIsNone(crop_lot(timeline(skip_water=1),0,0,(2,2)))

    def test_direct_carried_feed_excludes_site(self):
        self.assertIsNone(crop_lot(timeline(feed=76, drop=80),0,0,(2,2)))
        self.assertIsNotNone(crop_lot(timeline(feed=82, drop=80),0,0,(2,2)))

    def test_shop_duplicates_and_sale_before_consumption(self):
        self.assertEqual(absorption('CARROT', 4, 8, ['PET_CAFE','PET_CAFE'], {}), 4)
        self.assertEqual(absorption('WHEAT', 24, 25, ['PIZZA_SHOP','BRUNCH_SPOT'], {}), 3)

    def test_seed_receipt_and_atomic_same_crop_demand(self):
        obs = observation(); choice = CropChoice(lambda *args: 50)
        lot = {'plant_step':241,'worker':0,'site':[2,2],'planted_day':10,
               'harvest_step':314,'quantity':3,'sale_step':320}
        choice.pending = {'plant_step':241,'route':'R','seed_floor':0,'lots':[lot]}
        selected = {'farmer':['PLANT','WHEAT'], 'hands':[['PLANT','CARROT']], 'market':[]}
        self.assertEqual(choice.units(obs, {}, selected, 'R'), selected)
        obs['step'] = 242; obs['private']['seeds']['CARROT'] = 2
        lot['plant_step'] = 242
        choice.pending = {'plant_step':242,'route':'R','seed_floor':0,'lots':[lot]}
        changed = choice.units(obs, {}, selected, 'R')
        self.assertEqual(changed['farmer'], ['PLANT','CARROT'])
        self.assertEqual(selected['farmer'], ['PLANT','WHEAT'])

    def test_supply_depresses_choice_value(self):
        obs = observation(); choice = CropChoice(lambda p,i,params: max(1,11000-i))
        lot = {'sale_step':320,'quantity':3}
        first = choice.value(obs, {}, lot)
        obs['farms'][1]['tiles'][0][0] = {'kind':'PLANT','crop':'CARROT'}
        second = choice.value(obs, {}, lot)
        self.assertLess(second['edge'], first['edge'])
        self.assertEqual(second['extra_seed_cost'], 20)


if __name__ == '__main__':
    unittest.main()
