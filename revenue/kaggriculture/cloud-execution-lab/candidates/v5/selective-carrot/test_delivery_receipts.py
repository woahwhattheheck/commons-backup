import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from delivery_choice import DeliveryChoice


def observation(step, wheat=10):
    farm = {'farmer': [4, 4], 'hands': [], 'money': 5000,
            'tiles': [[None] * 10 for _ in range(10)]}
    return {'step': step, 'player': 0, 'farms': [farm, farm],
            'private': {'shed': {'WHEAT': wheat}, 'seeds': {}, 'inventories': [{}]},
            'market': {'inventory': {'WHEAT': 10000}}}


class Receipts(unittest.TestCase):
    def prepare(self, step=100):
        choice = DeliveryChoice(lambda *args: 10)
        obs = observation(step)
        choice.observe(obs)
        choice.debts = [{'due': 100, 'quantity': 3}, {'due': 100, 'quantity': 3}]
        return choice, obs

    def test_returned_order_does_not_discharge_until_observed(self):
        choice, obs = self.prepare()
        action = choice.market(obs, {}, {}, [], 'MAIN', obs)
        choice.commit(obs, action)
        self.assertEqual(sum(d['quantity'] for d in choice.debts), 6)
        choice.observe(observation(101, 12))
        self.assertEqual(sum(d['quantity'] for d in choice.debts), 4)

    def test_unfilled_buy_retries(self):
        choice, obs = self.prepare()
        action = choice.market(obs, {}, {}, [], 'MAIN', obs)
        choice.commit(obs, action)
        later = observation(101, 10)
        choice.observe(later)
        self.assertEqual(choice.market(later, {}, {}, [], 'MAIN', later)['market'],
                         [['BUY_PRODUCT', 'WHEAT', 6]])

    def test_fallback_does_not_create_purchase(self):
        choice, obs = self.prepare()
        choice.market(obs, {}, {}, [], 'MAIN', obs)
        choice.commit(obs, {})
        choice.observe(observation(101, 16))
        self.assertEqual(sum(d['quantity'] for d in choice.debts), 6)

    def test_eod_defers_ambiguous_autodrop(self):
        choice, obs = self.prepare(119)
        self.assertEqual(choice.market(obs, {}, {}, [], 'MAIN', obs), {})

    def test_authored_wheat_buy_keeps_receipt_unambiguous(self):
        choice, obs = self.prepare()
        selected = {'market': [['BUY_PRODUCT', 'WHEAT', 2]]}
        self.assertEqual(choice.market(obs, {}, selected, [], 'MAIN', obs), selected)

    def test_prior_sell_accounted_before_purchase_receipt(self):
        choice, obs = self.prepare()
        action = choice.market(obs, {}, {'market': [['SELL', 'WHEAT', 4]]}, [], 'MAIN', obs)
        choice.commit(obs, action)
        choice.observe(observation(101, 12))
        self.assertEqual(choice.debts, [])


if __name__ == '__main__':
    unittest.main()
