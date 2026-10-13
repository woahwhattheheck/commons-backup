from __future__ import annotations

from copy import deepcopy
import random
import unittest

from terminal_settlement import compose_terminal_settlement

PRODUCTS = ("WHEAT", "MILK", "CARROT", "EGG")


def make_obs(*, positions=None, inventories=None, shed=None, prices=None, step=718):
    positions = positions or [[4, 4]]
    inventories = inventories or [{} for _ in positions]
    shed = shed or {}
    prices = prices or {"WHEAT": 20, "MILK": 50, "CARROT": 10, "EGG": 30}
    tiles = [[None for _ in range(10)] for _ in range(10)]
    farm = {
        "farmer": deepcopy(positions[0]),
        "hands": deepcopy(positions[1:]),
        "tiles": tiles,
        "money": 1000,
    }
    return {
        "step": step,
        "player": 0,
        "farms": [farm, deepcopy(farm)],
        "private": {"shed": deepcopy(shed), "inventories": deepcopy(inventories)},
        "market": {
            "inventory": {item: 100 for item in PRODUCTS},
            "prices": deepcopy(prices),
        },
    }


def action(*, farmer=None, hands=None, market=None):
    return {
        "farmer": ["PASS"] if farmer is None else deepcopy(farmer),
        "hands": [] if hands is None else deepcopy(hands),
        "market": [] if market is None else deepcopy(market),
    }


def project_units(obs, selected, cfg):
    player = int(obs["player"])
    farm = deepcopy(obs["farms"][player])
    private = deepcopy(obs["private"])
    board = int(cfg.get("boardSize", 10))
    half = board // 2
    access = {(half - 1, half - 1), (half, half - 1), (half - 1, half), (half, half)}
    capacity = int(cfg.get("shedCapacity", 100))
    positions = [farm["farmer"], *farm.get("hands", [])]
    actions = [selected["farmer"], *selected["hands"]]
    for index, unit_action in enumerate(actions):
        if unit_action != ["DROP"] or tuple(positions[index]) not in access:
            continue
        cargo = private["inventories"][index]
        for item, raw in list(cargo.items()):
            quantity = int(raw)
            if quantity <= 0:
                del cargo[item]
                continue
            room = max(0, capacity - sum(private["shed"].values()))
            moved = min(quantity, room)
            if moved:
                private["shed"][item] = private["shed"].get(item, 0) + moved
            # Exact engine DROP destroys overflow and clears every cargo key.
            del cargo[item]
    return farm, private


def run(obs, selected, **cfg):
    config = {
        "episodeSteps": 720,
        "boardSize": 10,
        "shedCapacity": 100,
        "maxMarketOrdersPerTurn": 10,
    }
    config.update(cfg)
    return compose_terminal_settlement(obs, config, selected, project_units=project_units)


def totals(market):
    result = {}
    for order in market:
        result[order[1]] = result.get(order[1], 0) + int(order[2])
    return result


def sale_cash(queue, stock, rival_queue, rival_stock, inventory, quote):
    own_cash = 0
    inventory = dict(inventory)
    own_stock = dict(stock)
    rival_stock = dict(rival_stock)
    maximum = max(len(queue), len(rival_queue))
    for index in range(maximum):
        orders = [queue[index] if index < len(queue) else None,
                  rival_queue[index] if index < len(rival_queue) else None]
        remaining = [0, 0]
        for seat, order in enumerate(orders):
            if order is not None:
                remaining[seat] = int(order[2])
        while remaining[0] > 0 or remaining[1] > 0:
            quoted = [None, None]
            for seat, order in enumerate(orders):
                if order is None or remaining[seat] <= 0:
                    continue
                item = order[1]
                stock_map = own_stock if seat == 0 else rival_stock
                if stock_map.get(item, 0) <= 0:
                    remaining[seat] = 0
                    continue
                quoted[seat] = (item, quote(item, inventory[item]))
            if quoted == [None, None]:
                break
            for seat, row in enumerate(quoted):
                if row is None:
                    continue
                item, price = row
                stock_map = own_stock if seat == 0 else rival_stock
                stock_map[item] -= 1
                remaining[seat] -= 1
                if seat == 0:
                    own_cash += price
                if price > 1:
                    inventory[item] += 1
    return own_cash


class TerminalSettlementTests(unittest.TestCase):
    def test_drops_accessible_cargo_and_extends_existing_sell(self):
        obs = make_obs(inventories=[{"WHEAT": 3}], shed={"WHEAT": 2})
        selected = action(market=[["SELL", "WHEAT", 2]])
        result, report = run(obs, selected)
        self.assertEqual(result["farmer"], ["DROP"])
        self.assertEqual(result["market"], [["SELL", "WHEAT", 5]])
        self.assertEqual(report["guaranteed_min_cash_gain"], 3)
        self.assertEqual(report["post_unit_shed_delta"], {"WHEAT": 3})

    def test_appends_missing_product_at_tail(self):
        obs = make_obs(inventories=[{"MILK": 2}])
        result, report = run(obs, action())
        self.assertEqual(result["market"], [["SELL", "MILK", 2]])
        self.assertEqual(report["dropped_actor_indices"], [0])
        self.assertTrue(report["certified"])

    def test_sells_visible_shed_without_changing_units(self):
        obs = make_obs(shed={"CARROT": 4})
        selected = action(market=[["SELL", "CARROT", 1]])
        result, report = run(obs, selected)
        self.assertEqual(result["farmer"], ["PASS"])
        self.assertEqual(result["market"], [["SELL", "CARROT", 4]])
        self.assertEqual(report["guaranteed_min_cash_gain"], 3)

    def test_nonfinal_step_is_unchanged(self):
        obs = make_obs(step=717, inventories=[{"MILK": 2}])
        selected = action()
        result, report = run(obs, selected)
        self.assertEqual(result, selected)
        self.assertEqual(report["reason"], "not_final_executable_step")

    def test_mixed_market_queue_is_rejected(self):
        obs = make_obs(inventories=[{"MILK": 2}])
        selected = action(market=[["HIRE"]])
        result, report = run(obs, selected)
        self.assertEqual(result, selected)
        self.assertEqual(report["reason"], "baseline_not_valid_sale_only_queue")

    def test_underfunded_baseline_sell_is_rejected(self):
        obs = make_obs(shed={"WHEAT": 1})
        selected = action(market=[["SELL", "WHEAT", 2]])
        result, report = run(obs, selected)
        self.assertEqual(result, selected)
        self.assertEqual(report["reason"], "baseline_sell_not_fully_funded")

    def test_actor_away_from_shed_is_not_changed(self):
        obs = make_obs(positions=[[0, 0]], inventories=[{"MILK": 2}])
        selected = action()
        result, report = run(obs, selected)
        self.assertEqual(result, selected)
        self.assertEqual(report["reason"], "no_certified_gain")

    def test_non_sellable_drop_is_rejected(self):
        obs = make_obs(inventories=[{"CHICKEN": 1}])
        selected = action()
        result, report = run(obs, selected)
        self.assertEqual(result, selected)
        self.assertEqual(report["reason"], "no_certified_gain")

    def test_new_early_drop_cannot_displace_baseline_later_drop(self):
        obs = make_obs(
            positions=[[4, 4], [5, 4]],
            inventories=[{"MILK": 2}, {"WHEAT": 2}],
        )
        selected = action(hands=[["DROP"]], market=[["SELL", "WHEAT", 2]])
        result, report = run(obs, selected, shedCapacity=2)
        self.assertEqual(result, selected)
        self.assertEqual(report["reason"], "no_certified_gain")

    def test_higher_value_later_actor_wins_one_slot_without_displacement(self):
        obs = make_obs(
            positions=[[4, 4], [5, 4]],
            inventories=[{"CARROT": 1}, {"MILK": 1}],
            prices={"WHEAT": 20, "MILK": 90, "CARROT": 2, "EGG": 30},
        )
        selected = action(hands=[["PASS"]])
        result, report = run(obs, selected, shedCapacity=1)
        self.assertEqual(result["farmer"], ["PASS"])
        self.assertEqual(result["hands"], [["DROP"]])
        self.assertEqual(result["market"], [["SELL", "MILK", 1]])
        self.assertEqual(report["dropped_actor_indices"], [1])

    def test_full_market_cap_rejects_new_product(self):
        obs = make_obs(inventories=[{"MILK": 1}], shed={"WHEAT": 1})
        selected = action(market=[["SELL", "WHEAT", 1]])
        result, report = run(obs, selected, maxMarketOrdersPerTurn=1)
        self.assertEqual(result, selected)
        self.assertEqual(report["reason"], "no_certified_gain")

    def test_duplicate_product_extends_only_last_order(self):
        obs = make_obs(shed={"WHEAT": 5})
        selected = action(market=[["SELL", "WHEAT", 2], ["SELL", "WHEAT", 1]])
        result, report = run(obs, selected)
        self.assertEqual(result["market"], [["SELL", "WHEAT", 2], ["SELL", "WHEAT", 3]])
        self.assertEqual(report["guaranteed_min_cash_gain"], 2)

    def test_inputs_are_not_mutated(self):
        obs = make_obs(inventories=[{"MILK": 2}])
        selected = action()
        before_obs = deepcopy(obs)
        before_selected = deepcopy(selected)
        run(obs, selected)
        self.assertEqual(obs, before_obs)
        self.assertEqual(selected, before_selected)

    def test_actor_inventory_mismatch_is_rejected(self):
        obs = make_obs(positions=[[4, 4], [5, 4]], inventories=[{}])
        selected = action(hands=[["PASS"]])
        result, report = run(obs, selected)
        self.assertEqual(result, selected)
        self.assertEqual(report["reason"], "actor_action_inventory_mismatch")

    def test_projection_exception_fails_closed(self):
        obs = make_obs(inventories=[{"MILK": 2}])
        selected = action()
        result, report = compose_terminal_settlement(
            obs,
            {"episodeSteps": 720, "boardSize": 10, "maxMarketOrdersPerTurn": 10},
            selected,
            project_units=lambda *_: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        self.assertEqual(result, selected)
        self.assertEqual(report["reason"], "baseline_projection_failed")

    def test_drop_candidate_search_is_bounded_and_value_ordered(self):
        positions = [[4, 4] for _ in range(10)]
        inventories = [{"MILK": index + 1} for index in range(10)]
        obs = make_obs(positions=positions, inventories=inventories)
        selected = action(hands=[["PASS"] for _ in range(9)])
        candidate, report = compose_terminal_settlement(
            obs,
            {
                "episodeSteps": 720,
                "boardSize": 10,
                "shedCapacity": 100,
                "maxMarketOrdersPerTurn": 10,
            },
            selected,
            project_units=project_units,
            max_drop_candidates=3,
        )
        # Highest-value actors 9, 8, and 7 are considered first.
        self.assertEqual(report["dropped_actor_indices"], [9, 8, 7])
        self.assertEqual(report["eligible_actor_count"], 10)
        self.assertEqual(report["considered_actor_count"], 3)
        self.assertEqual(totals(candidate["market"])["MILK"], 27)

    def test_random_lockstep_adversary_preserves_cash_lower_bound(self):
        rng = random.Random(20260909)
        changed = 0
        for _ in range(1000):
            shed = {item: rng.randint(0, 5) for item in PRODUCTS}
            cargo = {item: rng.randint(0, 3) for item in PRODUCTS if rng.random() < 0.45}
            positions = [[4, 4]]
            obs = make_obs(positions=positions, inventories=[cargo], shed=shed)
            baseline_market = []
            for item in PRODUCTS:
                amount = rng.randint(0, shed[item])
                if amount:
                    baseline_market.append(["SELL", item, amount])
            selected = action(market=baseline_market)
            candidate, report = run(obs, selected)
            if not report["certified"]:
                continue
            changed += 1
            _, baseline_private = project_units(
                obs,
                selected,
                {"boardSize": 10, "shedCapacity": 100},
            )
            _, candidate_private = project_units(
                obs,
                candidate,
                {"boardSize": 10, "shedCapacity": 100},
            )
            rival_queue = []
            rival_stock = {}
            for item in PRODUCTS:
                quantity = rng.randint(0, 6)
                rival_stock[item] = quantity
                if quantity:
                    rival_queue.append(["SELL", item, quantity])
            rng.shuffle(rival_queue)
            initial = {item: rng.randint(0, 160) for item in PRODUCTS}

            def quote(_item, market_inventory):
                return max(1, 200 - market_inventory * 3)

            baseline_cash = sale_cash(
                selected["market"], baseline_private["shed"], rival_queue,
                rival_stock, initial, quote,
            )
            candidate_cash = sale_cash(
                candidate["market"], candidate_private["shed"], rival_queue,
                rival_stock, initial, quote,
            )
            self.assertGreaterEqual(
                candidate_cash - baseline_cash,
                report["guaranteed_min_cash_gain"],
            )
        self.assertGreater(changed, 900)


if __name__ == "__main__":
    unittest.main()
