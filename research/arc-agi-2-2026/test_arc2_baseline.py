import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from arc2_baseline import build_submission, solve_task, validate_grid


def task(inp, out, test):
    return {"train": [{"input": inp, "output": out}], "test": [{"input": test}]}


class Arc2BaselineTests(unittest.TestCase):
    def test_rejects_ragged_grid(self):
        with self.assertRaises(ValueError):
            validate_grid([[1, 2], [3]])

    def test_rotation_is_learned(self):
        t = task([[1, 0], [2, 3]], [[2, 1], [3, 0]], [[4, 5], [0, 6]])
        solved = solve_task(t)[0]
        self.assertEqual(solved["attempt_1"], [[0, 4], [6, 5]])

    def test_recolor_is_learned_globally(self):
        t = task([[1, 0], [1, 2]], [[7, 0], [7, 4]], [[2, 1], [0, 2]])
        self.assertEqual(solve_task(t)[0]["attempt_1"], [[4, 7], [0, 4]])

    def test_rotation_plus_recolor(self):
        t = task([[1, 0], [2, 1]], [[9, 8], [8, 7]], [[2, 1], [0, 2]])
        # rot90(test) -> [[0,2],[2,1]], then 0->7, 2->9, 1->8
        self.assertEqual(solve_task(t)[0]["attempt_1"], [[7, 9], [9, 8]])

    def test_mirror_quadrants(self):
        t = task(
            [[1, 2], [3, 4]],
            [[1, 2, 2, 1], [3, 4, 4, 3], [3, 4, 4, 3], [1, 2, 2, 1]],
            [[5, 6], [7, 8]],
        )
        self.assertEqual(
            solve_task(t)[0]["attempt_1"],
            [[5, 6, 6, 5], [7, 8, 8, 7], [7, 8, 8, 7], [5, 6, 6, 5]],
        )

    def test_latin_square_zero_completion(self):
        t = task(
            [[0, 2, 3, 4], [2, 3, 4, 1], [3, 4, 1, 2], [4, 1, 2, 0]],
            [[1, 2, 3, 4], [2, 3, 4, 1], [3, 4, 1, 2], [4, 1, 2, 3]],
            [[1, 0, 3, 4], [0, 3, 4, 1], [3, 4, 0, 2], [4, 1, 2, 0]],
        )
        self.assertEqual(
            solve_task(t)[0]["attempt_1"],
            [[1, 2, 3, 4], [2, 3, 4, 1], [3, 4, 1, 2], [4, 1, 2, 3]],
        )

    def test_panel_overlap_vertical(self):
        t = task(
            [[1, 1, 0, 5, 0, 1, 0], [0, 0, 1, 5, 1, 1, 1], [1, 1, 0, 5, 0, 1, 0]],
            [[0, 2, 0], [0, 0, 2], [0, 2, 0]],
            [[1, 0, 1, 5, 1, 0, 1], [0, 1, 0, 5, 1, 0, 1], [1, 0, 1, 5, 0, 1, 0]],
        )
        self.assertEqual(solve_task(t)[0]["attempt_1"], [[2, 0, 2], [0, 0, 0], [0, 0, 0]])

    def test_fill_enclosed_zero_regions_with_yellow(self):
        t = task(
            [
                [0, 0, 0, 0, 0, 0],
                [0, 3, 3, 3, 3, 0],
                [0, 3, 0, 0, 3, 0],
                [0, 3, 0, 0, 3, 0],
                [0, 3, 3, 3, 3, 0],
                [0, 0, 0, 0, 0, 0],
            ],
            [
                [0, 0, 0, 0, 0, 0],
                [0, 3, 3, 3, 3, 0],
                [0, 3, 4, 4, 3, 0],
                [0, 3, 4, 4, 3, 0],
                [0, 3, 3, 3, 3, 0],
                [0, 0, 0, 0, 0, 0],
            ],
            [
                [0, 0, 0, 0, 0],
                [0, 8, 8, 8, 0],
                [0, 8, 0, 8, 0],
                [0, 8, 8, 8, 0],
                [0, 0, 0, 0, 0],
            ],
        )
        self.assertEqual(
            solve_task(t)[0]["attempt_1"],
            [
                [0, 0, 0, 0, 0],
                [0, 8, 8, 8, 0],
                [0, 8, 4, 8, 0],
                [0, 8, 8, 8, 0],
                [0, 0, 0, 0, 0],
            ],
        )

    def test_reflected_tile3x3(self):
        t = task(
            [[7, 9], [4, 3]],
            [
                [7, 9, 7, 9, 7, 9],
                [4, 3, 4, 3, 4, 3],
                [9, 7, 9, 7, 9, 7],
                [3, 4, 3, 4, 3, 4],
                [7, 9, 7, 9, 7, 9],
                [4, 3, 4, 3, 4, 3],
            ],
            [[3, 2], [7, 8]],
        )
        self.assertEqual(
            solve_task(t)[0]["attempt_1"],
            [
                [3, 2, 3, 2, 3, 2],
                [7, 8, 7, 8, 7, 8],
                [2, 3, 2, 3, 2, 3],
                [8, 7, 8, 7, 8, 7],
                [3, 2, 3, 2, 3, 2],
                [7, 8, 7, 8, 7, 8],
            ],
        )

    def test_self_mask_expand(self):
        t = task(
            [[4, 0, 4], [0, 0, 0], [0, 4, 0]],
            [
                [4, 0, 4, 0, 0, 0, 4, 0, 4],
                [0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 4, 0, 0, 0, 0, 0, 4, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 4, 0, 4, 0, 0, 0],
                [0, 0, 0, 0, 0, 0, 0, 0, 0],
                [0, 0, 0, 0, 4, 0, 0, 0, 0],
            ],
            [[7, 0, 7], [7, 0, 7], [7, 7, 0]],
        )
        expected = [
            [7, 0, 7, 0, 0, 0, 7, 0, 7],
            [7, 0, 7, 0, 0, 0, 7, 0, 7],
            [7, 7, 0, 0, 0, 0, 7, 7, 0],
            [7, 0, 7, 0, 0, 0, 7, 0, 7],
            [7, 0, 7, 0, 0, 0, 7, 0, 7],
            [7, 7, 0, 0, 0, 0, 7, 7, 0],
            [7, 0, 7, 7, 0, 7, 0, 0, 0],
            [7, 0, 7, 7, 0, 7, 0, 0, 0],
            [7, 7, 0, 7, 7, 0, 0, 0, 0],
        ]
        self.assertEqual(solve_task(t)[0]["attempt_1"], expected)

    def test_crop_background_parameter_nonzero(self):
        t = task(
            [[8, 8, 8, 8], [8, 2, 3, 8], [8, 4, 5, 8], [8, 8, 8, 8]],
            [[2, 3], [4, 5]],
            [[8, 8, 8], [8, 6, 8], [8, 7, 8]],
        )
        self.assertEqual(solve_task(t)[0]["attempt_1"], [[6], [7]])

    def test_component_crops_search_background_parameter(self):
        largest = task(
            [[8, 2, 2, 8, 8], [8, 2, 8, 8, 3], [8, 8, 8, 8, 8]],
            [[2, 2], [2, 8]],
            [[8, 4, 4, 8, 5], [8, 4, 8, 8, 8], [8, 8, 8, 8, 8]],
        )
        self.assertEqual(solve_task(largest)[0]["attempt_1"], [[4, 4], [4, 8]])

        smallest = task(
            [[8, 2, 2, 8, 8], [8, 2, 8, 8, 3], [8, 8, 8, 8, 8]],
            [[3]],
            [[8, 4, 4, 8, 5], [8, 4, 8, 8, 8], [8, 8, 8, 8, 8]],
        )
        self.assertEqual(solve_task(smallest)[0]["attempt_1"], [[5]])

    def test_crop_nonzero(self):
        t = task(
            [[0, 0, 0, 0], [0, 2, 3, 0], [0, 4, 5, 0], [0, 0, 0, 0]],
            [[2, 3], [4, 5]],
            [[0, 0, 0], [0, 6, 0], [0, 7, 0]],
        )
        self.assertEqual(solve_task(t)[0]["attempt_1"], [[6], [7]])

    def test_upscale2(self):
        t = task([[1, 2]], [[1, 1, 2, 2], [1, 1, 2, 2]], [[3, 4]])
        self.assertEqual(solve_task(t)[0]["attempt_1"], [[3, 3, 4, 4], [3, 3, 4, 4]])

    def test_multiple_train_pairs_enforce_one_hypothesis(self):
        t = {
            "train": [
                {"input": [[1, 2]], "output": [[2, 1]]},
                {"input": [[3, 4]], "output": [[4, 3]]},
            ],
            "test": [{"input": [[5, 6]]}],
        }
        self.assertEqual(solve_task(t)[0]["attempt_1"], [[6, 5]])

    def test_two_attempts_always_present(self):
        t = task([[1]], [[1]], [[2]])
        result = solve_task(t)[0]
        self.assertEqual(set(result), {"attempt_1", "attempt_2"})
        self.assertEqual(result["attempt_1"], [[2]])
        self.assertEqual(result["attempt_2"], [[2]])

    def test_submission_keeps_all_task_ids_and_test_order(self):
        challenges = {
            "a": {"train": [{"input": [[1]], "output": [[1]]}], "test": [{"input": [[2]]}, {"input": [[3]]}]},
            "b": {"train": [{"input": [[4]], "output": [[4]]}], "test": [{"input": [[5]]}]},
        }
        submission = build_submission(challenges)
        self.assertEqual(list(submission), ["a", "b"])
        self.assertEqual(len(submission["a"]), 2)
        self.assertEqual(len(submission["b"]), 1)

    def test_cli_writes_compact_submission_json(self):
        challenges = {
            "demo": {"train": [{"input": [[1, 2]], "output": [[2, 1]]}], "test": [{"input": [[3, 4]]}]}
        }
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            source = td / "challenges.json"
            output = td / "submission.json"
            source.write_text(json.dumps(challenges), encoding="utf-8")
            subprocess.run([sys.executable, str(Path(__file__).with_name("arc2_baseline.py")), str(source), "--output", str(output)], check=True)
            parsed = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(parsed["demo"][0]["attempt_1"], [[4, 3]])


if __name__ == "__main__":
    unittest.main()
