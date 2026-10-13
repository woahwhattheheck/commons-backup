import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("extra_hand_overlay", HERE / "overlay-v1.py")
mod = importlib.util.module_from_spec(spec)
mod.agent = lambda obs: {"farmer": ["PASS"], "hands": [], "market": []}
mod.MAX_ORDERS = 10
mod.SHED_CAP = 100
spec.loader.exec_module(mod)


class OverlayEconomicsTest(unittest.TestCase):
    def test_floor_units_carry_revenue_without_supply(self):
        obs = {"step": 10, "market": {"inventory": {p: 50000 for p in mod._EH_PARAMS}, "params": {}},
               "town": {"unlocked_shops": []}, "player": 0, "day": 0,
               "farms": [{"tiles": [[None]], "farmer": [0,0], "hands": []}]}
        plan = {"product": "WHEAT", "quantity": 3, "sale_step": 11, "target": (0,0)}
        original = mod._eh_price
        mod._eh_price = lambda *args: 1
        try:
            self.assertEqual(mod._eh_receipt(obs, plan, False), 3)
        finally:
            mod._eh_price = original

    def test_hire_cost_matches_engine_sequence(self):
        self.assertEqual([mod._eh_hire_cost(i) for i in range(7)], [1,1,2,3,5,8,13])

    def test_spawn_matches_engine_tie_order(self):
        farm = {"farmer": [4,4], "hands": [[5,4],[4,5]]}
        self.assertEqual(mod._eh_spawn(farm, 10), (5,5))

    def test_spawn_uses_post_action_positions_and_prior_hires(self):
        tiles = [[None] * 10 for _ in range(10)]
        obs = {"player": 0, "farms": [{"farmer": [4,4], "hands": [[5,4]], "tiles": tiles}]}
        base = {"farmer": ["WEST"], "hands": [["SOUTH"]], "market": [["HIRE"]]}
        # After moves, 4,4 is empty; the base hire takes it and the overlay gets 5,4.
        self.assertEqual(mod._eh_spawn_after_base(obs, base), (5,4))

    def test_reserved_cash_does_not_credit_sales(self):
        products = {p: 10000 for p in mod._EH_PARAMS}
        obs = {"player": 0, "farms": [{"money": 100, "hires_today": 0, "unlocked_land": ["NW"]}],
               "market": {"inventory": products, "params": {}}}
        cash, hires = mod._eh_reserved_cash(obs, [["SELL","WHEAT",9],["BUY_SEED","WHEAT",2],["HIRE"]])
        self.assertEqual((cash, hires), (79, 1))


if __name__ == "__main__":
    unittest.main()
