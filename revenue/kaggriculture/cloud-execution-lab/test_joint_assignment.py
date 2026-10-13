# SPDX-License-Identifier: Apache-2.0
import copy
import unittest

from joint_assignment import JointAssignmentError, propose_pair_swap

MOVES = {"NORTH": (0, -1), "SOUTH": (0, 1), "EAST": (1, 0), "WEST": (-1, 0)}


class FakeMechanics:
    def _farmer_position(self, farm, idx):
        return farm["farmer"] if idx == 0 else farm["hands"][idx - 1]

    def _set_pos(self, farm, idx, pos):
        if idx == 0:
            farm["farmer"] = list(pos)
        else:
            farm["hands"][idx - 1] = list(pos)

    def _apply_unit_action(self, farm, private, idx, action, board, day, turns_per_day, shed_capacity=100):
        op = action[0] if action else "PASS"
        pos = tuple(self._farmer_position(farm, idx))
        if op in MOVES:
            dx, dy = MOVES[op]
            nxt = (pos[0] + dx, pos[1] + dy)
            if 0 <= nxt[0] < board and 0 <= nxt[1] < board:
                self._set_pos(farm, idx, nxt)
            return
        if op == "PASS":
            return
        inv = private["inventories"][idx]
        if op == "PICKUP":
            if pos not in {tuple(x) for x in private["shed_access"]} or len(action) < 2:
                return
            item = action[1]
            n = int(action[2]) if len(action) >= 3 else 1
            n = min(max(n, 0), private["shed"].get(item, 0))
            if n:
                private["shed"][item] -= n
                if private["shed"][item] == 0:
                    del private["shed"][item]
                inv[item] = inv.get(item, 0) + n
            return
        if op == "DROP":
            if pos not in {tuple(x) for x in private["shed_access"]}:
                return
            for item, n in list(inv.items()):
                room = shed_capacity - sum(private["shed"].values())
                moved = min(n, max(room, 0))
                if moved:
                    private["shed"][item] = private["shed"].get(item, 0) + moved
                    inv[item] -= moved
                    if inv[item] == 0:
                        del inv[item]
            return
        x, y = pos
        tile = farm["tiles"][y][x]
        if op == "FERTILIZE":
            if tile.get("kind") != "PLANT" or inv.get("FERTILIZER", 0) < 1:
                return
            inv["FERTILIZER"] -= 1
            if inv["FERTILIZER"] == 0:
                del inv["FERTILIZER"]
            tile["fertilized"] = tile.get("fertilized", 0) + 1
            return
        if op == "FEED":
            if "animal" not in tile or inv.get("WHEAT", 0) < 1:
                return
            inv["WHEAT"] -= 1
            if inv["WHEAT"] == 0:
                del inv["WHEAT"]
            tile["fed"] = tile.get("fed", 0) + 1
            return
        if op == "WATER":
            if tile.get("kind") != "PLANT" or tile.get("watered_today"):
                return
            tile["watered_today"] = True
            return

    def _decay_plants(self, farm, step):
        return


def blank_board(n=5):
    return [[{} for _ in range(n)] for _ in range(n)]


def row(a=("PASS",), b=("PASS",), market=None):
    out = {"farmer": list(a), "hands": [list(b)]}
    if market:
        out["market"] = copy.deepcopy(market)
    return out


def crossing_fixture(*, aligned=False, stock=None):
    """Two crossed shed bundles with inherited task events at offsets 4, 7, 10."""
    mechanics = FakeMechanics()
    tiles = blank_board()
    tiles[2][0] = {"kind": "PLANT", "fertilized": 0}
    tiles[2][4] = {"animal": "COW", "fed": 0}
    if aligned:
        farmer, hand = [0, 0], [4, 0]
    else:
        farmer, hand = [4, 0], [0, 0]
    farm = {"farmer": farmer, "hands": [hand], "tiles": tiles}
    private = {
        "shed": dict(stock or {"FERTILIZER": 2, "WHEAT": 2}),
        "inventories": [{}, {}],
        "shed_access": [[0, 0], [4, 0]],
    }
    obs = {"player": 0, "farms": [farm], "private": private}

    # Worker 0 bundle A: access (0,0) -> PLANT (0,2) -> access (0,0), then rejoin (4,0).
    # Worker 1 bundle B: access (4,0) -> COW (4,2) -> access (4,0), then rejoin (0,0).
    seq_a = [
        ("WEST",), ("WEST",), ("WEST",), ("WEST",),
        ("PICKUP", "FERTILIZER", 2),
        ("SOUTH",), ("SOUTH",), ("FERTILIZE",),
        ("NORTH",), ("NORTH",), ("DROP",),
        ("EAST",), ("EAST",), ("EAST",), ("EAST",),
    ]
    seq_b = [
        ("EAST",), ("EAST",), ("EAST",), ("EAST",),
        ("PICKUP", "WHEAT", 2),
        ("SOUTH",), ("SOUTH",), ("FEED",),
        ("NORTH",), ("NORTH",), ("DROP",),
        ("WEST",), ("WEST",), ("WEST",), ("WEST",),
    ]
    if aligned:
        # Same bundles from already-compatible starts/ends: remove crossed endpoint travel.
        seq_a = [
            ("PASS",), ("PASS",), ("PASS",), ("PASS",),
            ("PICKUP", "FERTILIZER", 2),
            ("SOUTH",), ("SOUTH",), ("FERTILIZE",),
            ("NORTH",), ("NORTH",), ("DROP",),
            ("PASS",), ("PASS",), ("PASS",), ("PASS",),
        ]
        seq_b = [
            ("PASS",), ("PASS",), ("PASS",), ("PASS",),
            ("PICKUP", "WHEAT", 2),
            ("SOUTH",), ("SOUTH",), ("FEED",),
            ("NORTH",), ("NORTH",), ("DROP",),
            ("PASS",), ("PASS",), ("PASS",), ("PASS",),
        ]
    route = [row(seq_a[i], seq_b[i]) for i in range(15)]
    return mechanics, obs, route


class JointAssignmentTests(unittest.TestCase):
    def test_crossed_complete_bundles_are_swapped_atomically(self):
        m, obs, route = crossing_fixture()
        result = propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=14)
        self.assertTrue(result.changed, result.reason)
        self.assertEqual(result.reason, "accepted_exact_joint_swap")
        plan = result.plan
        self.assertEqual(plan.owner_key, "joint:0-1:0-14")
        self.assertEqual(plan.workers, (0, 1))
        self.assertEqual(plan.inherited_from, (1, 0))
        self.assertEqual(plan.original_travel, 24)
        self.assertEqual(plan.replacement_travel, 8)
        self.assertEqual(plan.travel_saved, 16)
        self.assertEqual(len(plan.patches()), 15)
        self.assertTrue(all(set(p["units"]) == {"0", "1"} for p in plan.patches()))

    def test_inherited_events_keep_original_global_steps(self):
        m, obs, route = crossing_fixture()
        plan = propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=14).plan
        stream0, stream1 = plan.replacement
        self.assertEqual(stream0[4], ("PICKUP", "WHEAT", 2))
        self.assertEqual(stream0[7], ("FEED",))
        self.assertEqual(stream0[10], ("DROP",))
        self.assertEqual(stream1[4], ("PICKUP", "FERTILIZER", 2))
        self.assertEqual(stream1[7], ("FERTILIZE",))
        self.assertEqual(stream1[10], ("DROP",))

    def test_collision_trace_records_both_same_step_pickups_and_services(self):
        m, obs, route = crossing_fixture()
        plan = propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=14).plan
        rows = [(x["step"], x["worker"], x["action"][0]) for x in plan.collision_trace]
        self.assertEqual(rows, [
            (4, 0, "PICKUP"), (4, 1, "PICKUP"),
            (7, 0, "FEED"), (7, 1, "FERTILIZE"),
            (10, 0, "DROP"), (10, 1, "DROP"),
        ])

    def test_original_and_candidate_end_state_match_including_actor_positions(self):
        m, obs, route = crossing_fixture()
        plan = propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=14).plan
        patches = plan.patches()
        candidate = copy.deepcopy(route)
        for patch in patches:
            step = patch["step"]
            candidate[step]["farmer"] = patch["units"]["0"]
            candidate[step]["hands"][0] = patch["units"]["1"]
        # Re-certifying the already swapped route should not find a further travel gain.
        second = propose_pair_swap(m, obs, candidate, 0, 1, start_step=0, end_step=14)
        self.assertFalse(second.changed)

    def test_partial_pickup_rejects_shared_stock_contention(self):
        m, obs, route = crossing_fixture(stock={"FERTILIZER": 1, "WHEAT": 2})
        result = propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=14)
        self.assertFalse(result.changed)
        self.assertIn("partial_pickup", result.reason)

    def test_same_resource_pickups_reconcile_in_exact_worker_order(self):
        m, obs, route = crossing_fixture(stock={"WHEAT": 5})
        obs["farms"][0]["tiles"][2][0] = {"animal": "SHEEP", "fed": 0}
        route[4]["farmer"] = ["PICKUP", "WHEAT", 3]
        route[7]["farmer"] = ["FEED"]
        route[4]["hands"][0] = ["PICKUP", "WHEAT", 2]
        result = propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=14)
        self.assertTrue(result.changed, result.reason)
        self.assertEqual(result.plan.travel_saved, 16)
        pickups = [x for x in result.plan.collision_trace if x["action"][0] == "PICKUP"]
        self.assertEqual(pickups[0]["shed_before"].get("WHEAT"), 5)
        self.assertEqual(pickups[0]["shed_after"].get("WHEAT"), 3)
        self.assertEqual(pickups[1]["shed_before"].get("WHEAT"), 3)
        self.assertNotIn("WHEAT", pickups[1]["shed_after"])

    def test_unrelated_third_actor_is_preserved(self):
        m, obs, route = crossing_fixture()
        obs["farms"][0]["hands"].append([2, 4])
        obs["private"]["inventories"].append({})
        for r in route:
            r["hands"].append(["PASS"])
        result = propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=14)
        self.assertTrue(result.changed, result.reason)
        self.assertTrue(all(set(p["units"]) == {"0", "1"} for p in result.plan.patches()))

    def test_preexisting_actor_cargo_rejects_swap(self):
        m, obs, route = crossing_fixture()
        obs["private"]["inventories"][0]["WHEAT"] = 1
        result = propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=14)
        self.assertEqual((result.changed, result.reason), (False, "starting_cargo_not_empty"))

    def test_market_mutation_is_a_hard_boundary(self):
        m, obs, route = crossing_fixture()
        route[6]["market"] = [["SELL", "WHEAT", 1]]
        result = propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=14)
        self.assertEqual((result.changed, result.reason), (False, "market_boundary"))

    def test_end_of_day_is_a_hard_boundary(self):
        m, obs, route = crossing_fixture()
        route = {20 + i: r for i, r in enumerate(route)}
        result = propose_pair_swap(m, obs, route, 0, 1, start_step=20, end_step=34)
        self.assertEqual((result.changed, result.reason), (False, "day_boundary"))

    def test_checkpoint_is_a_hard_boundary(self):
        m, obs, route = crossing_fixture()
        result = propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=14, checkpoints=(7,))
        self.assertEqual((result.changed, result.reason), (False, "checkpoint_boundary"))

    def test_no_swap_when_existing_assignment_is_already_shorter(self):
        m, obs, route = crossing_fixture(aligned=True)
        result = propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=14)
        self.assertEqual((result.changed, result.reason), (False, "no_travel_gain"))

    def test_candidate_must_fit_inherited_event_deadline(self):
        m = FakeMechanics()
        tiles = blank_board()
        tiles[1][0] = {"kind": "PLANT", "fertilized": 0}
        tiles[1][4] = {"animal": "COW", "fed": 0}
        farm = {"farmer": [0, 0], "hands": [[4, 0]], "tiles": tiles}
        private = {
            "shed": {"FERTILIZER": 2, "WHEAT": 2},
            "inventories": [{}, {}],
            "shed_access": [[0, 0], [4, 0]],
        }
        obs = {"player": 0, "farms": [farm], "private": private}

        # Both baseline owners are already at their offset-1 PICKUP sites. Each
        # complete bundle then services locally and crosses the board only to its
        # own continuation endpoint. A swap would save that tail travel, but the
        # opposite actor is four moves from the inherited offset-1 PICKUP, so it
        # must fail the exact event deadline rather than moving the event later.
        seq_a = [
            ("PASS",), ("PICKUP", "FERTILIZER", 2), ("SOUTH",),
            ("FERTILIZE",), ("NORTH",), ("DROP",),
            ("EAST",), ("EAST",), ("EAST",), ("EAST",),
        ]
        seq_b = [
            ("PASS",), ("PICKUP", "WHEAT", 2), ("SOUTH",),
            ("FEED",), ("NORTH",), ("DROP",),
            ("WEST",), ("WEST",), ("WEST",), ("WEST",),
        ]
        route = [row(seq_a[i], seq_b[i]) for i in range(10)]
        result = propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=9)
        self.assertFalse(result.changed)
        self.assertIn("event_deadline_unreachable", result.reason)

    def test_noop_service_is_rejected(self):
        m, obs, route = crossing_fixture()
        obs["farms"][0]["tiles"][2][0] = {"kind": "WEED"}
        result = propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=14)
        self.assertFalse(result.changed)
        self.assertIn("fertilize_noop", result.reason)

    def test_malformed_worker_indices_fail_closed(self):
        m, obs, route = crossing_fixture()
        with self.assertRaises(JointAssignmentError):
            propose_pair_swap(m, obs, route, 0, 9, start_step=0, end_step=14)

    def test_same_worker_is_invalid(self):
        m, obs, route = crossing_fixture()
        with self.assertRaises(JointAssignmentError):
            propose_pair_swap(m, obs, route, 0, 0, start_step=0, end_step=14)

    def test_missing_route_row_is_invalid(self):
        m, obs, route = crossing_fixture()
        del route[5]
        with self.assertRaises(JointAssignmentError):
            propose_pair_swap(m, obs, route, 0, 1, start_step=0, end_step=14)


if __name__ == "__main__":
    unittest.main()
