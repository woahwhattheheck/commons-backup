import copy
import importlib.util
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("terminal_labor_surge", HERE / "terminal_labor_surge.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FakeMechanics:
    CROPS = {
        "WHEAT": {"first_yield_day": 2},
        "MELON": {"first_yield_day": 10},
    }
    ANIMALS = {"COW": {"product": "MILK"}}
    PRODUCTS = ["WHEAT", "MELON", "MILK"]

    @staticmethod
    def _fib(n):
        a, b = 1, 1
        for _ in range(n):
            a, b = b, a + b
        return a

    @classmethod
    def _hire_cost(cls, n, mult=1):
        return mult * cls._fib(n)

    @staticmethod
    def _shed_tiles(board):
        h = board // 2
        return [(h - 1, h - 1), (h, h - 1), (h - 1, h), (h, h)]

    @classmethod
    def _spawn_hand(cls, farm, board):
        spots = cls._shed_tiles(board)
        occ = {p: 0 for p in spots}
        for p in [tuple(farm["farmer"]), *map(tuple, farm["hands"])]:
            if p in occ:
                occ[p] += 1
        return list(min(spots, key=lambda p: (occ[p], spots.index(p))))

    @classmethod
    def _do_hire(cls, farm, private, board, mult=1):
        cost = cls._hire_cost(farm["hires_today"], mult)
        if farm["money"] < cost:
            return
        farm["money"] -= cost
        farm["hires_today"] += 1
        farm["hands"].append(cls._spawn_hand(farm, board))
        private["inventories"].append({})

    @staticmethod
    def _apply_unit_action(farm, private, idx, action, board, day, day_len, cap):
        if not isinstance(action, list) or not action:
            return
        if idx == 0:
            pos = farm["farmer"]
        elif idx - 1 < len(farm["hands"]):
            pos = farm["hands"][idx - 1]
        else:
            return
        if action[0] in m.MOVES:
            dx, dy = m.MOVES[action[0]]
            nx, ny = pos[0] + dx, pos[1] + dy
            if 0 <= nx < board and 0 <= ny < board:
                pos[:] = [nx, ny]

    @staticmethod
    def market_price(item, inventory, params=None):
        # High enough for several cheap terminal workers; monotonically declines
        # with this proposal's own planned volume so volume accounting is tested.
        base = {"WHEAT": 8, "MELON": 20, "MILK": 14}[item]
        return max(1, base - max(0, inventory - 10000))


class FakeTerminal:
    @staticmethod
    def assign_routes(farm, inventories, start, final, day, prices, cap):
        # Each hand creates up to 20 current-quote value; farmer baseline contributes 5.
        positions = [farm["farmer"], *farm["hands"]]
        evaluations = []
        for i, _ in enumerate(positions):
            value = 5 if i == 0 else 20
            evaluations.append((value, 1, [["PASS"]], {}))
        return [[] for _ in positions], evaluations


def plant(crop="WHEAT", quantity=1, x=None):
    return {
        "kind": "PLANT",
        "crop": crop,
        "planted_day": 20 if crop == "WHEAT" else 10,
        "yield_units": quantity,
        "max_lifespan_step": 999,
    }


def base_world(step=698, money=3000, hires_today=1, market=None):
    board = 10
    tiles = [[None for _ in range(board)] for _ in range(board)]
    # Distinct profitable targets around the four shed-access spawn tiles.
    for (x, y) in [(3,4),(4,3),(5,3),(6,4),(3,5),(4,6),(5,6),(6,5),(2,4),(7,4),(2,5),(7,5)]:
        tiles[y][x] = plant("WHEAT", 1)
    farm = {
        "money": float(money),
        "tiles": tiles,
        "farmer": [4,4],
        "hands": [],
        "hires_today": hires_today,
    }
    obs = {
        "step": step,
        "day": 29,
        "player": 0,
        "farms": [farm, copy.deepcopy(farm)],
        "private": {"shed": {"WHEAT":0,"MELON":0,"MILK":0}, "inventories":[{}]},
        "market": {"inventory": {"WHEAT":10000,"MELON":10000,"MILK":10000}},
    }
    selected = {"farmer":["PASS"], "hands":[], "market": copy.deepcopy(market or [])}
    route = [{"farmer":["PASS"], "hands":[], "market":[]} for _ in range(719)]
    route[step] = copy.deepcopy(selected)
    snapshots = [
        {"step": t, "post_unit_shed": {"WHEAT":0,"MELON":0,"MILK":0},
         "admission": "actual-current" if t == step else "conditional-reference-sales"}
        for t in range(step, 719)
    ]
    cfg = {"boardSize":10,"turnsPerDay":24,"episodeSteps":720,"shedCapacity":100,
           "maxMarketOrdersPerTurn":10,"farmHandCostMult":1}
    return obs, cfg, selected, route, snapshots


class TerminalLaborSurgeTests(unittest.TestCase):
    def call(self, *args, **kwargs):
        obs, cfg, selected, route, snapshots = base_world(*args, **kwargs)
        return m.propose_terminal_labor_surge(FakeMechanics, obs, cfg, selected,
            route=route, snapshots=snapshots, route_id="T05", max_extra_hires=9,
            min_quote_surplus=1)

    def test_profitable_jobs_append_hires_and_same_turn_sells(self):
        out, route, report = self.call()
        self.assertTrue(report["changed"])
        self.assertGreaterEqual(report["extra_hires"], 3)
        self.assertLessEqual(len(out["market"]), 10)
        self.assertEqual(report["cumulative_wage"], sum(j["wage"] for j in report["jobs"]))
        self.assertGreater(report["current_quote_value"], report["cumulative_wage"])
        self.assertEqual(len({tuple(j["target"]) for j in report["jobs"]}), report["extra_hires"])
        for job in report["jobs"]:
            self.assertIn(["SELL", job["item"], job["quantity"]], route[job["drop_and_sell_step"]]["market"])

    def test_exact_fibonacci_marginal_wages_start_after_existing_hire(self):
        _, _, report = self.call()
        wages = [j["wage"] for j in report["jobs"]]
        # hires_today=1 means the added sequence begins at Fib(1)=1.
        self.assertEqual(wages[:5], [1, 2, 3, 5, 8][:len(wages[:5])])

    def test_only_appends_to_free_raw_slots_never_replaces_parent_orders(self):
        parent = [["SELL", "WHEAT", 0]] * 9
        out, _, report = self.call(market=parent)
        self.assertEqual(out["market"][:9], parent)
        self.assertLessEqual(report["extra_hires"], 1)
        self.assertLessEqual(len(out["market"]), 10)

    def test_no_raw_capacity_is_identity(self):
        parent = [["SELL", "WHEAT", 0]] * 10
        out, route, report = self.call(market=parent)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "no_current_raw_market_capacity")
        self.assertEqual(out["market"], parent)
        self.assertEqual(route[698]["market"], parent)

    def test_outside_terminal_owner_window_is_identity(self):
        obs, cfg, selected, route, snapshots = base_world(step=697)
        # snapshots need only exist for this identity path.
        out, r, report = m.propose_terminal_labor_surge(FakeMechanics, obs, cfg, selected,
            route=route, snapshots=snapshots, route_id="T05")
        self.assertFalse(report["changed"])
        self.assertEqual(out, selected)
        self.assertEqual(r, route)

    def test_final_callback_cannot_buy_useless_hand(self):
        obs, cfg, selected, route, snapshots = base_world(step=718)
        out, _, report = m.propose_terminal_labor_surge(FakeMechanics, obs, cfg, selected,
            route=route, snapshots=snapshots, route_id="T05")
        self.assertFalse(report["changed"])
        self.assertEqual(out["market"], [])

    def test_full_shed_snapshot_blocks_deposit(self):
        obs, cfg, selected, route, snapshots = base_world()
        for s in snapshots:
            s["post_unit_shed"]["WHEAT"] = 100
        out, _, report = m.propose_terminal_labor_surge(FakeMechanics, obs, cfg, selected,
            route=route, snapshots=snapshots, route_id="T05")
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "no_profitable_executable_job")
        self.assertEqual(out["market"], [])

    def test_parent_harvest_target_is_reserved(self):
        obs, cfg, selected, route, snapshots = base_world()
        # Farmer starts [4,4], parent harvests that tile after one WEST move -> [3,4].
        route[699]["farmer"] = ["WEST"]
        route[700]["farmer"] = ["HARVEST"]
        _, _, report = m.propose_terminal_labor_surge(FakeMechanics, obs, cfg, selected,
            route=route, snapshots=snapshots, route_id="T05")
        self.assertGreaterEqual(report.get("parent_harvest_targets_reserved", 0), 1)
        self.assertNotIn([3,4], [j["target"] for j in report.get("jobs", [])])

    def test_future_hire_fails_closed_without_worker_reindex_guess(self):
        obs, cfg, selected, route, snapshots = base_world()
        route[702]["market"] = [["HIRE"]]
        out, r, report = m.propose_terminal_labor_surge(FakeMechanics, obs, cfg, selected,
            route=route, snapshots=snapshots, route_id="T05")
        self.assertFalse(report["changed"])
        self.assertTrue(report["reason"].startswith("fail_closed:ValueError:future executable HIRE"))
        self.assertEqual(out, selected)
        self.assertEqual(r[702]["market"], [["HIRE"]])

    def test_existing_current_hire_is_preserved_and_new_workers_follow_it(self):
        obs, cfg, selected, route, snapshots = base_world(hires_today=0, market=[["HIRE"]])
        out, _, report = m.propose_terminal_labor_surge(FakeMechanics, obs, cfg, selected,
            route=route, snapshots=snapshots, route_id="T05")
        self.assertEqual(out["market"][0], ["HIRE"])
        self.assertTrue(all(job["worker"] >= 2 for job in report["jobs"]))

    def test_missing_snapshot_fails_closed(self):
        obs, cfg, selected, route, snapshots = base_world()
        snapshots.pop()
        out, _, report = m.propose_terminal_labor_surge(FakeMechanics, obs, cfg, selected,
            route=route, snapshots=snapshots, route_id="T05")
        self.assertFalse(report["changed"])
        self.assertTrue(report["reason"].startswith("fail_closed:ValueError:complete terminal"))
        self.assertEqual(out, selected)

    def test_unprofitable_wage_tail_stops_instead_of_blind_mass_hiring(self):
        obs, cfg, selected, route, snapshots = base_world(hires_today=6)
        # Next wage = 13, while one WHEAT sells for 8: no terminal hire.
        out, _, report = m.propose_terminal_labor_surge(FakeMechanics, obs, cfg, selected,
            route=route, snapshots=snapshots, route_id="T05")
        self.assertFalse(report["changed"])
        self.assertEqual(out["market"], [])

    def test_current_cash_spending_order_fails_closed(self):
        obs, cfg, selected, route, snapshots = base_world(market=[["BUY_SEED", "WHEAT", 1]])
        out, r, report = m.propose_terminal_labor_surge(FakeMechanics, obs, cfg, selected,
            route=route, snapshots=snapshots, route_id="T05")
        self.assertFalse(report["changed"])
        self.assertTrue(report["reason"].startswith("fail_closed:ValueError:current terminal prefix"))
        self.assertEqual(out, selected)
        self.assertEqual(r[698]["market"], selected["market"])

    def test_parent_terminal_sale_volume_is_charged_against_quote(self):
        obs, cfg, selected, route, snapshots = base_world()
        # A large parent WHEAT sale makes the conservative future quote hit the floor.
        route[710]["market"] = [["SELL", "WHEAT", 100]]
        out, _, report = m.propose_terminal_labor_surge(FakeMechanics, obs, cfg, selected,
            route=route, snapshots=snapshots, route_id="T05")
        self.assertFalse(report["changed"])
        self.assertEqual(out["market"], [])


    def test_preterminal_frontier_consumes_superseded_12762_seam(self):
        obs, cfg, selected, route, snapshots = base_world(step=697, hires_today=0)
        obs["market"]["prices"] = {"WHEAT":8,"MELON":20,"MILK":14}
        out, report = m.propose_preterminal_hire_frontier(
            FakeMechanics, FakeTerminal, obs, cfg, selected,
            enabled=True, min_quote_surplus=1, max_extra_hires=10)
        self.assertTrue(report["changed"])
        self.assertGreater(report["chosen"]["net_current_quote_gain"], 0)
        self.assertLessEqual(len(out["market"]), 10)
        self.assertEqual(report["donor"], "superseded PR #12762 / ASTRA-FRONTIERWIDE")

    def test_preterminal_frontier_exact_first_ten_cost_is_143(self):
        obs, cfg, selected, route, snapshots = base_world(step=697, hires_today=0)
        obs["market"]["prices"] = {"WHEAT":8,"MELON":20,"MILK":14}
        _, report = m.propose_preterminal_hire_frontier(
            FakeMechanics, FakeTerminal, obs, cfg, selected,
            enabled=True, min_quote_surplus=0, max_extra_hires=10)
        self.assertEqual(report["frontier"][-1]["extra_hires"], 10)
        self.assertEqual(report["frontier"][-1]["cumulative_hire_cost"], 143)

    def test_preterminal_frontier_refuses_sell_or_buy_prefix(self):
        for order in (["SELL","WHEAT",1], ["BUY_SEED","WHEAT",1]):
            obs, cfg, selected, route, snapshots = base_world(step=697, market=[order])
            obs["market"]["prices"] = {"WHEAT":8,"MELON":20,"MILK":14}
            out, report = m.propose_preterminal_hire_frontier(
                FakeMechanics, FakeTerminal, obs, cfg, selected,
                enabled=True, min_quote_surplus=0)
            self.assertFalse(report["changed"])
            self.assertEqual(report["reason"], "nonhire_market_prefix")
            self.assertIs(out, selected)

    def test_preterminal_frontier_disabled_is_exact_identity(self):
        obs, cfg, selected, route, snapshots = base_world(step=697)
        out, report = m.propose_preterminal_hire_frontier(
            FakeMechanics, FakeTerminal, obs, cfg, selected, enabled=False)
        self.assertIs(out, selected)
        self.assertFalse(report["changed"])
        self.assertEqual(report["reason"], "disabled")


if __name__ == "__main__":
    unittest.main()
