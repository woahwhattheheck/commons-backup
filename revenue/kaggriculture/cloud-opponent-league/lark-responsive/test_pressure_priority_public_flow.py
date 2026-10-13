"""E01 contracts for explicit public rival-flow quantities in pressure scoring."""
import copy
import unittest

from pressure_priority import lot_pressure, transform

BASE = {
    'CARROT': 1000,
    'TOMATO': 1000,
    'MILK': 1000,
}


def curve(item, stock, params=None):
    slope = (params or {}).get('slope', 1)
    return max(1, BASE[item] - slope * stock)


def obs():
    return {
        'market': {
            'inventory': dict.fromkeys(BASE, 0),
            'prices': BASE.copy(),
        }
    }


class PublicFlowPressureTests(unittest.TestCase):
    def test_default_same_lot_proxy_is_retained_exactly(self):
        carrot = ['SELL', 'CARROT', 14]
        tomato = ['SELL', 'TOMATO', 8]
        market = obs()['market']
        self.assertEqual(lot_pressure(carrot, market, curve), 196)
        self.assertEqual(lot_pressure(tomato, market, curve), 64)
        action = {'market': [carrot, tomato]}
        self.assertEqual(transform(action, obs(), quote=curve), action)

    def test_public_flow_quantity_can_reverse_proxy_ranking(self):
        carrot = ['SELL', 'CARROT', 14]
        tomato = ['SELL', 'TOMATO', 8]
        action = {'market': [carrot, tomato]}
        flow = {'CARROT': 0, 'TOMATO': 20}
        market = obs()['market']
        self.assertEqual(lot_pressure(carrot, market, curve, 0), 0)
        self.assertEqual(lot_pressure(tomato, market, curve, 20), 160)
        self.assertEqual(
            transform(action, obs(), quote=curve, rival_supply=flow)['market'],
            [tomato, carrot],
        )

    def test_missing_product_keeps_proxy_but_explicit_zero_does_not(self):
        carrot = ['SELL', 'CARROT', 14]
        tomato = ['SELL', 'TOMATO', 8]
        action = {'market': [carrot, tomato]}
        result = transform(
            action,
            obs(),
            quote=curve,
            rival_supply={'CARROT': 0},
        )
        # CARROT uses real zero flow; TOMATO has no public estimate and therefore
        # retains the documented same-lot fallback stress (64).
        self.assertEqual(result['market'], [tomato, carrot])

    def test_malformed_explicit_quantity_is_barrier_not_guess(self):
        action = {
            'market': [
                ['SELL', 'CARROT', 14],
                ['SELL', 'TOMATO', 8],
            ]
        }
        for bad in (None, True, -1, 1.5, '20', 257):
            self.assertIsNone(lot_pressure(action['market'][0], obs()['market'], curve, bad))
            self.assertEqual(
                transform(
                    action,
                    obs(),
                    quote=curve,
                    rival_supply={'CARROT': bad, 'TOMATO': 20},
                ),
                action,
            )
        self.assertEqual(transform(action, obs(), quote=curve, rival_supply=[]), action)

    def test_unhashable_malformed_item_is_barrier_with_public_flow(self):
        carrot = ['SELL', 'CARROT', 14]
        tomato = ['SELL', 'TOMATO', 8]
        bad = ['SELL', [], 1]
        flow = {'CARROT': 0, 'TOMATO': 20}
        split = {'market': [carrot, bad, tomato]}
        self.assertEqual(
            transform(split, obs(), quote=curve, rival_supply=flow)['market'],
            [carrot, bad, tomato],
        )
        trailing = {'market': [bad, carrot, tomato]}
        self.assertEqual(
            transform(trailing, obs(), quote=curve, rival_supply=flow)['market'],
            [bad, tomato, carrot],
        )

    def test_explicit_flow_does_not_mutate_parent_or_observation(self):
        action = {'farmer': ['PASS'], 'market': [['SELL', 'CARROT', 14], ['SELL', 'TOMATO', 8]]}
        observation = obs()
        before = copy.deepcopy((action, observation))
        result = transform(
            action,
            observation,
            quote=curve,
            rival_supply={'CARROT': 0, 'TOMATO': 20},
        )
        self.assertEqual((action, observation), before)
        self.assertNotEqual(result['market'], action['market'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
