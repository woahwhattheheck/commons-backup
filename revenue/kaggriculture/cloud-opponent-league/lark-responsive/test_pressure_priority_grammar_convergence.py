"""Cross-helper SELL grammar convergence for pressure priority."""
import copy
import unittest

from pressure_priority import transform


BASE = {
    'CARROT': 1000,
    'TOMATO': 1000,
    'MILK': 1000,
    'WOOL': 1000,
}


def curve(item, stock, params=None):
    return max(1, BASE[item] - stock)


def observation(step=10):
    return {
        'step': step,
        'market': {
            'inventory': dict.fromkeys(BASE, 0),
            'prices': BASE.copy(),
        },
    }


class PressureGrammarConvergenceTests(unittest.TestCase):
    def test_prefix_compaction_accepts_engine_valid_trailing_fields_byte_exact(self):
        sale = ['SELL', 'MILK', 2, 'engine-ignored', {'metadata': True}]
        action = {'market': [[], copy.deepcopy(sale)]}
        before = copy.deepcopy(action)

        result = transform(
            action, observation(), {'maxMarketOrdersPerTurn': 2}, quote=curve
        )

        self.assertEqual(result['market'], [sale, []])
        self.assertEqual(result['market'][0], sale)
        self.assertEqual(action, before)

    def test_prefix_compaction_accepts_engine_int_quantity_coercions(self):
        for quantity in (True, 2.0, 2.9, '2'):
            with self.subTest(quantity=quantity):
                sale = ['SELL', 'MILK', quantity]
                result = transform(
                    {'market': [[], copy.deepcopy(sale)]},
                    observation(),
                    {'maxMarketOrdersPerTurn': 2},
                    quote=curve,
                )
                self.assertEqual(result['market'], [sale, []])

    def test_nonpositive_sell_remains_barrier_not_empty_slot(self):
        action = {
            'market': [
                [],
                ['SELL', 'MILK', 0],
                ['SELL', 'CARROT', 1],
            ]
        }
        self.assertEqual(
            transform(
                action,
                observation(),
                {'maxMarketOrdersPerTurn': 3},
                quote=curve,
            ),
            action,
        )

    def test_terminal_suffix_promotion_uses_same_engine_grammar(self):
        sale = ['SELL', 'MILK', '2', 'engine-ignored']
        action = {
            'market': [
                [],
                ['SELL', 'CARROT', 1],
                copy.deepcopy(sale),
            ]
        }

        result = transform(
            action,
            observation(step=718),
            {'maxMarketOrdersPerTurn': 2, 'episodeSteps': 720},
            quote=curve,
        )

        self.assertIn(sale, result['market'][:2])
        self.assertEqual(result['market'][2], [])
        self.assertCountEqual(map(repr, result['market']), map(repr, action['market']))

    def test_public_rival_supply_applies_to_trailing_field_sell(self):
        carrot = ['SELL', 'CARROT', 14, 'engine-ignored']
        tomato = ['SELL', 'TOMATO', 8]
        action = {'market': [copy.deepcopy(carrot), copy.deepcopy(tomato)]}

        result = transform(
            action,
            observation(),
            quote=curve,
            rival_supply={'CARROT': 0, 'TOMATO': 20},
        )

        self.assertEqual(result['market'], [tomato, carrot])


if __name__ == '__main__':
    unittest.main(verbosity=2)
