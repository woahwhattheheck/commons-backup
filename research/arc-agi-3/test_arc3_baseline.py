from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from arc3_baseline import NoveltyExplorer, grid_signature, normalize_actions, normalize_grid


class T(unittest.TestCase):
    def test_latest(self):
        self.assertEqual(normalize_grid([[[0, 0], [0, 0]], [[1, 0], [0, 0]]]), ((1, 0), (0, 0)))

    def test_invalid(self):
        for frame in ([[0] * 2 for _ in range(65)], [[16]], [[0], [0, 1]]):
            with self.assertRaises(ValueError):
                normalize_grid(frame)

    def test_actions(self):
        self.assertEqual(normalize_actions([7, 2, 2, 9, 0, "3"]), (2, 3, 7))

    def test_reset(self):
        policy = NoveltyExplorer()
        self.assertEqual(policy.choose([[0]], [1], state="NOT_PLAYED").action_id, 0)
        self.assertEqual(policy.choose([[0]], [1], state="GAME_OVER").action_id, 0)

    def test_available_only(self):
        self.assertEqual(NoveltyExplorer().choose([[0]], [4], state="NOT_FINISHED").action_id, 4)

    def test_deterministic_explore(self):
        policy = NoveltyExplorer()
        frame = [[0, 0], [0, 0]]
        self.assertEqual(
            [policy.choose(frame, [1, 2, 3], state="NOT_FINISHED").action_id for _ in range(3)],
            [1, 2, 3],
        )

    def test_action6_salient(self):
        grid = [[0] * 5 for _ in range(5)]
        grid[4][1] = 9
        decision = NoveltyExplorer().choose(grid, [6], state="NOT_FINISHED")
        self.assertEqual((decision.action_id, decision.x, decision.y), (6, 1, 4))

    def test_change_reward(self):
        policy = NoveltyExplorer()
        a = [[0, 0], [0, 0]]
        b = [[1, 0], [0, 0]]
        decision = policy.choose(a, [1], state="NOT_FINISHED")
        signature = grid_signature(normalize_grid(a))
        policy.choose(b, [1], state="NOT_FINISHED")
        stat = policy.stats[(signature, decision.key)]
        self.assertEqual(stat.changed_cells, 1)
        self.assertGreater(stat.mean_reward, 0)

    def test_level_bonus(self):
        policy = NoveltyExplorer()
        frame = [[0]]
        decision = policy.choose(frame, [1], state="NOT_FINISHED", levels_completed=0)
        signature = grid_signature(normalize_grid(frame))
        policy.choose(frame, [1], state="NOT_FINISHED", levels_completed=1)
        self.assertGreater(policy.stats[(signature, decision.key)].mean_reward, 7)

    def test_frontier_routes_to_untried_state(self):
        policy = NoveltyExplorer()
        a = [[0, 0]]
        b = [[1, 0]]
        self.assertEqual(policy.choose(a, [1, 2], state="NOT_FINISHED").action_id, 1)
        self.assertEqual(policy.choose(b, [1, 2], state="NOT_FINISHED").action_id, 1)
        self.assertEqual(policy.choose(a, [1, 2], state="NOT_FINISHED").action_id, 2)
        routed = policy.choose(a, [1, 2], state="NOT_FINISHED")
        self.assertEqual(routed.action_id, 1)
        self.assertIn("frontier-route", routed.reason)
        self.assertEqual(policy.frontier_routes, 1)
        at_b = policy.choose(b, [1, 2], state="NOT_FINISHED")
        self.assertEqual(at_b.action_id, 2)
        self.assertEqual(at_b.reason, "untried-frontier")

    def test_self_loop_not_used_as_route(self):
        policy = NoveltyExplorer()
        a = [[0, 0]]
        for _ in range(3):
            policy.choose(a, [1], state="NOT_FINISHED")
        self.assertEqual(policy.frontier_routes, 0)
        self.assertGreaterEqual(policy.diagnostics()["self_loop_observations"], 2)

    def test_repeatable(self):
        sequence = [
            ([[0, 0], [0, 0]], [1, 2, 6]),
            ([[1, 0], [0, 0]], [1, 2, 6]),
            ([[1, 0], [0, 2]], [1, 2, 6]),
            ([[1, 0], [0, 2]], [1, 2, 6]),
        ]

        def run():
            policy = NoveltyExplorer()
            return [
                (decision.action_id, decision.x, decision.y)
                for frame, actions in sequence
                for decision in [policy.choose(frame, actions, state="NOT_FINISHED")]
            ]

        self.assertEqual(run(), run())

    def test_json_diag(self):
        policy = NoveltyExplorer()
        policy.choose([[0]], [1], state="NOT_FINISHED")
        policy.choose([[1]], [1], state="NOT_FINISHED")
        diagnostics = policy.diagnostics()
        self.assertEqual(diagnostics["policy"], "deterministic-frontier-model-v2")
        self.assertIn("known_edges", diagnostics)
        self.assertIn("unique_states", json.dumps(diagnostics))


if __name__ == "__main__":
    unittest.main(verbosity=2)
