import copy
import hashlib
import unittest

import dependent_animal_rebind as f


def action(market=None, farmer=None, hands=None):
    return {
        "farmer": ["PASS"] if farmer is None else farmer,
        "hands": [] if hands is None else hands,
        "market": [] if market is None else market,
    }


class Mechanics:
    CROPS = {
        "WHEAT": {"seed": 10},
        "STRAWBERRY": {"seed": 100},
    }
    ANIMALS = {"SHEEP": {"cost": 500}}
    FARM_HAND_COST_MULT = 1

    @staticmethod
    def _hire_cost(hires_today, multiplier):
        # Eight new hires starting at zero cost 54 in this exact fixture.
        table = [4, 5, 6, 7, 7, 8, 8, 9]
        if hires_today < len(table):
            return table[hires_today] * multiplier
        return 10 * multiplier

    @staticmethod
    def _apply_unit_action(farm, private, index, action, board, day, tpd, capacity):
        # Fixtures use PASS-only current units; reject accidental scope broadening.
        if action != ["PASS"]:
            raise ValueError("fixture only supports PASS unit stage")


def make_route():
    route = [action() for _ in range(240)]
    market216 = [
        ["BUY_SEED", "WHEAT", 4],
        ["BUY_SEED", "STRAWBERRY", 4],
        *([["HIRE"]] * 8),
    ]
    route[216] = action(market216)
    route[217] = action([
        ["SELL", "FERTILIZER", 2],
        ["HIRE"],
        ["BUY_ANIMAL", "SHEEP", 0],
    ])
    route[219] = action(farmer=["PICKUP", "SHEEP"])
    route[223] = action(farmer=["PLACE", "SHEEP"])
    route[224] = action([["SELL", "EGG", 1]])
    route[225] = action([["SELL", "MILK", 1]])
    route[226] = action([["SELL", "WOOL", 1]])
    route[227] = action([])
    route[228] = action(farmer=["PLANT", "WHEAT"])
    return route


def obs(cash, step=216):
    return {
        "step": step,
        "player": 0,
        "farms": [{
            "money": cash,
            "hires_today": 0,
            "tiles": [],
        }],
        "private": {
            "shed": {"SHEEP": 0, "WHEAT": 0, "STRAWBERRY": 0, "FERTILIZER": 0},
            "seeds": {"WHEAT": 0, "STRAWBERRY": 0},
            "inventories": [],
        },
    }


CFG = {
    "maxMarketOrdersPerTurn": 10,
    "turnsPerDay": 24,
    "boardSize": 10,
    "shedCapacity": 100,
    "farmHandCostMult": 1,
}


class FlockbindTests(unittest.TestCase):
    def propose(self, cash=711, route=None, **kw):
        route = make_route() if route is None else route
        selected = copy.deepcopy(route[216])
        before = copy.deepcopy(selected)
        out, obligation, report = f.propose_dependent_sheep_rebind(
            Mechanics, obs(cash), CFG, selected, route,
            enabled=True, source_bound=True, **kw
        )
        self.assertEqual(before, selected)
        return out, obligation, report

    def test_seed17_preserves_one_strawberry_and_all_hires(self):
        out, obligation, report = self.propose(711)
        self.assertTrue(report["changed"])
        self.assertEqual(["BUY_ANIMAL", "SHEEP", 1], out["market"][0])
        self.assertEqual(["BUY_SEED", "STRAWBERRY", 1], out["market"][1])
        self.assertEqual([["HIRE"]] * 8, out["market"][2:])
        self.assertEqual(10, len(out["market"]))
        self.assertEqual(4, obligation["quantity"])
        self.assertEqual(228, obligation["deadline_step"])
        self.assertEqual([227], report["eligible_empty_steps"])

    def test_seed101_preserves_three_strawberries(self):
        out, obligation, report = self.propose(903)
        self.assertTrue(report["changed"])
        self.assertEqual(["BUY_SEED", "STRAWBERRY", 3], out["market"][1])
        self.assertEqual(1, report["strawberry_trimmed"])
        self.assertIsNotNone(obligation)

    def test_no_future_sell_credit(self):
        route = make_route()
        route[217]["market"].insert(0, ["SELL", "WOOL", 99])
        selected = copy.deepcopy(route[216])
        out, obligation, report = f.propose_dependent_sheep_rebind(
            Mechanics, obs(600), CFG, selected, route,
            enabled=True, source_bound=True,
        )
        self.assertFalse(report["changed"])
        self.assertEqual("observed_cash_insufficient", report["reason"])
        self.assertIsNone(obligation)
        self.assertEqual(route[216], out)

    def test_requires_downstream_zero_buy_pickup_place_and_wheat_plant(self):
        for mutate in (
            lambda r: r[217].update(market=[["SELL", "FERTILIZER", 2], ["HIRE"]]),
            lambda r: r.__setitem__(219, action()),
            lambda r: r.__setitem__(223, action()),
            lambda r: r.__setitem__(228, action()),
        ):
            route = make_route()
            mutate(route)
            out, obligation, report = self.propose(711, route=route)
            self.assertFalse(report["changed"])
            self.assertEqual("dependent_route_not_proved", report["reason"])
            self.assertIsNone(obligation)

    def test_positive_sheep_buy_before_pickup_disables_rebind(self):
        route = make_route()
        route[218] = action([["BUY_ANIMAL", "SHEEP", 1]])
        _, obligation, report = self.propose(711, route=route)
        self.assertFalse(report["changed"])
        self.assertEqual("dependent_route_not_proved", report["reason"])
        self.assertIsNone(obligation)

    def test_parent_market_must_be_exactly_full_prefix(self):
        route = make_route()
        route[216]["market"].pop()
        selected = copy.deepcopy(route[216])
        out, obligation, report = f.propose_dependent_sheep_rebind(
            Mechanics, obs(711), CFG, selected, route,
            enabled=True, source_bound=True,
        )
        self.assertFalse(report["changed"])
        self.assertEqual("requires_full_executable_market", report["reason"])
        self.assertIsNone(obligation)
        self.assertEqual(selected, out)

    def test_current_parent_drift_fails_closed(self):
        route = make_route()
        selected = copy.deepcopy(route[216])
        selected["market"][1] = ["BUY_SEED", "STRAWBERRY", 3]
        before = copy.deepcopy(selected)
        out, obligation, report = f.propose_dependent_sheep_rebind(
            Mechanics, obs(711), CFG, selected, route,
            enabled=True, source_bound=True,
        )
        self.assertEqual("parent_action_drift", report["reason"])
        self.assertEqual(before, out)
        self.assertIsNone(obligation)

    def test_shed_capacity_or_existing_sheep_blocks(self):
        route = make_route()
        observation = obs(711)
        observation["private"]["shed"]["SHEEP"] = 1
        selected = copy.deepcopy(route[216])
        _, obligation, report = f.propose_dependent_sheep_rebind(
            Mechanics, observation, CFG, selected, route,
            enabled=True, source_bound=True,
        )
        self.assertEqual("sheep_capacity_or_stock_not_clean", report["reason"])
        self.assertIsNone(obligation)

    def test_disabled_and_unbound_are_identity(self):
        route = make_route()
        selected = copy.deepcopy(route[216])
        out, obligation, report = f.propose_dependent_sheep_rebind(
            Mechanics, obs(711), CFG, selected, route,
            enabled=False, source_bound=True,
        )
        self.assertIs(out, selected)
        self.assertEqual("disabled", report["reason"])
        self.assertIsNone(obligation)
        out, obligation, report = f.propose_dependent_sheep_rebind(
            Mechanics, obs(711), CFG, selected, route,
            enabled=True, source_bound=False,
        )
        self.assertIs(out, selected)
        self.assertEqual("source_unbound", report["reason"])
        self.assertIsNone(obligation)

    def test_backfill_only_exact_empty_callback_with_observed_cash(self):
        _, obligation, _ = self.propose(711)
        selected = action([])
        out, updated, report = f.apply_wheat_backfill(
            Mechanics, obs(40, step=227), CFG, selected, obligation,
            enabled=True, source_bound=True,
        )
        self.assertTrue(report["changed"])
        self.assertEqual([["BUY_SEED", "WHEAT", 4]], out["market"])
        self.assertEqual("fulfilled", updated["status"])
        self.assertEqual([], selected["market"])

    def test_backfill_rejects_cash39_nonempty_drift_and_deadline(self):
        _, obligation, _ = self.propose(711)
        for step, cash, selected, reason in (
            (227, 39, action([]), "observed_cash_insufficient"),
            (227, 40, action([["HIRE"]]), "parent_market_not_empty"),
            (228, 40, action([]), "outside_backfill_window"),
        ):
            out, updated, report = f.apply_wheat_backfill(
                Mechanics, obs(cash, step=step), CFG, selected, obligation,
                enabled=True, source_bound=True,
            )
            self.assertFalse(report["changed"])
            self.assertEqual(reason, report["reason"])
            self.assertEqual(obligation, updated)

    def test_backfill_nonmarket_signature_drift_rejected(self):
        _, obligation, _ = self.propose(711)
        selected = action([], farmer=["NORTH"])
        _, _, report = f.apply_wheat_backfill(
            Mechanics, obs(40, step=227), CFG, selected, obligation,
            enabled=True, source_bound=True,
        )
        self.assertEqual("parent_callback_drift", report["reason"])

    def test_source_binding_uses_git_blob_identity(self):
        data = b"abc"
        blob = f.git_blob_sha1(data)
        expected = hashlib.sha1(b"blob 3\0abc").hexdigest()
        self.assertEqual(expected, blob)
        report = f.source_binding_report(data, data)
        self.assertFalse(report["bound"])
        self.assertEqual(blob, report["engine_git_blob"])


if __name__ == "__main__":
    unittest.main()
