"""Real puzzle-generation, exhaustive board geometry, and CLI regression tests."""
from collections import Counter, deque
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest

import knight_pack as pack


def reference_neighbors(value):
    x, y = ord(value[0]) - 97, int(value[1]) - 1
    # Independent implementation: inspect every destination, not production deltas.
    return tuple(sorted(candidate for candidate in pack.SQUARES
                        if sorted((abs(ord(candidate[0]) - 97 - x), abs(int(candidate[1]) - 1 - y))) == [1, 2]))


def reference_distances(origin):
    distances = {origin: 0}
    queue = deque([origin])
    while queue:
        node = queue.popleft()
        for neighbor in reference_neighbors(node):
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)
    return distances


class GeometryTests(unittest.TestCase):
    def test_legal_moves_all_64_squares(self):
        for origin in pack.SQUARES:
            with self.subTest(origin=origin):
                self.assertEqual(pack.legal_moves(origin), reference_neighbors(origin))

    def test_shortest_routes_all_4096_pairs(self):
        for origin in pack.SQUARES:
            expected = reference_distances(origin)
            self.assertEqual(len(expected), 64)
            for target in pack.SQUARES:
                with self.subTest(origin=origin, target=target):
                    route = pack.shortest_route(origin, target)
                    self.assertEqual(route[0], origin)
                    self.assertEqual(route[-1], target)
                    self.assertEqual(len(route) - 1, expected[target])
                    self.assertEqual(pack.validate_route(route, origin, target), route)

    def test_corner_and_center_move_counts(self):
        self.assertEqual(len(pack.legal_moves("a1")), 2)
        self.assertEqual(len(pack.legal_moves("d4")), 8)

    def test_zero_move_route(self):
        self.assertEqual(pack.shortest_route("a1", "a1"), ("a1",))

    def test_known_long_corner_route(self):
        self.assertEqual(pack.distance("a1", "h8"), 6)

    def test_invalid_squares(self):
        for value in (None, 1, True, "A1", "a0", "a9", "i1", " a1", "a1\n", "a11"):
            with self.subTest(value=value), self.assertRaises(pack.PuzzleError):
                pack.square(value)

    def test_illegal_routes(self):
        for route in ("a1 b3", [], ["a1", "a2", "b3"], ["c2", "b3"], ["a1", "c2"], ["a1"] * 66):
            with self.subTest(route=route), self.assertRaises(pack.PuzzleError):
                pack.validate_route(route, "a1", "b3")

    def test_route_can_be_legal_but_nonminimal(self):
        self.assertEqual(pack.validate_route(["a1", "b3", "a1", "b3"], "a1", "b3"),
                         ("a1", "b3", "a1", "b3"))


class GeneratorTests(unittest.TestCase):
    def test_default_pack(self):
        questions = pack.generate()
        self.assertEqual(len(questions), 12)
        self.assertEqual([q.kind for q in questions], ["move", "distance"] * 6)

    def test_exact_repeat_is_deterministic(self):
        self.assertEqual(pack.dumps(pack.adapt(pack.generate("same"))), pack.dumps(pack.adapt(pack.generate("same"))))

    def test_seed_changes_content(self):
        self.assertNotEqual(pack.generate("week-1"), pack.generate("week-2"))

    def test_pack_has_unique_origins_and_prompts(self):
        questions = pack.generate("full", 64)
        self.assertEqual(len({q.origin for q in questions}), 64)
        self.assertEqual(len({q.prompt for q in questions}), 64)

    def test_one_correct_move_for_every_origin_and_16_variants(self):
        for origin in pack.SQUARES:
            legal = reference_neighbors(origin)
            for variant in range(16):
                question = pack.move_question(origin, str(variant))
                self.assertEqual(len(question.choices), 4)
                self.assertEqual(len(set(question.choices)), 4)
                self.assertEqual(sum(choice in legal for choice in question.choices), 1)
                self.assertIn(question.choices[question.answer], legal)

    def test_distance_answers_against_reference_all_pairs(self):
        for origin in pack.SQUARES:
            expected = reference_distances(origin)
            for target in pack.SQUARES:
                if origin == target:
                    continue
                question = pack.distance_question(origin, target, "distance-battery")
                self.assertEqual(len(question.choices), 4)
                self.assertEqual(len(set(question.choices)), 4)
                self.assertEqual(int(question.choices[question.answer]), expected[target])

    def test_same_square_distance_puzzle_rejected(self):
        with self.assertRaises(pack.PuzzleError):
            pack.distance_question("a1", "a1", "x")

    def test_default_answer_positions_are_balanced(self):
        self.assertEqual(Counter(q.answer for q in pack.generate()), {0: 3, 1: 3, 2: 3, 3: 3})

    def test_answer_position_balance_for_every_supported_size(self):
        for count in range(1, 65):
            counts = Counter(q.answer for q in pack.generate("position-balance", count))
            self.assertLessEqual(max(counts.values()) - min(counts.get(i, 0) for i in range(4)), 1)

    def test_invalid_seeds(self):
        for seed in (None, 42, "", "   ", "x" * 201):
            with self.subTest(seed=seed), self.assertRaises(pack.PuzzleError):
                pack.generate(seed)

    def test_invalid_counts(self):
        for count in (None, True, 0, -1, 65, 1.0, "12"):
            with self.subTest(count=count), self.assertRaises(pack.PuzzleError):
                pack.generate(count=count)

    def test_generated_explanations_are_nonempty(self):
        for question in pack.generate():
            self.assertTrue(question.explanation)
            self.assertIn(question.choices[question.answer], question.explanation)

    def test_as_dict_matches_canonical_adapter(self):
        questions = pack.generate()
        self.assertEqual([q.as_dict() for q in questions], pack.adapt(questions))


class AdapterAndCliTests(unittest.TestCase):
    def test_custom_consumer_schema(self):
        question = pack.generate(count=1)[0]
        row = pack.adapt([question], prompt_key="question", choices_key="options", answer_key="correct",
                         explanation_key=None, answer_base=1)[0]
        self.assertEqual(set(row), {"question", "options", "correct"})
        self.assertEqual(row["correct"], question.answer + 1)

    def test_adapter_does_not_mutate_questions(self):
        questions = pack.generate()
        before = list(questions)
        result = pack.adapt(questions)
        result[0]["choices"].append("new")
        self.assertEqual(questions, before)
        self.assertEqual(len(questions[0].choices), 4)

    def test_duplicate_fields_rejected(self):
        with self.assertRaises(pack.PuzzleError):
            pack.adapt([], prompt_key="answer")

    def test_invalid_field_names(self):
        for key in ("", "a b", "a-b", None, 123):
            with self.subTest(key=key), self.assertRaises(pack.PuzzleError):
                pack.adapt([], prompt_key=key)

    def test_invalid_answer_base(self):
        for base in (True, -1, 2, "0"):
            with self.subTest(base=base), self.assertRaises(pack.PuzzleError):
                pack.adapt([], answer_base=base)

    def test_stdout_is_complete_json(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(pack.main(["--count", "4"]), 0)
        data = json.loads(output.getvalue())
        self.assertEqual(len(data), 4)
        self.assertTrue(output.getvalue().endswith("\n"))

    def test_cli_writes_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.json"
            pack.main(["--output", str(path), "--choices-key", "options", "--omit-explanation"])
            rows = json.loads(path.read_text())
            self.assertEqual(len(rows), 12)
            self.assertEqual(set(rows[0]), {"prompt", "options", "answer"})

    def test_cli_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "questions.json"
            path.write_bytes(b"existing peer bytes")
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                pack.main(["--output", str(path)])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(path.read_bytes(), b"existing peer bytes")

    def test_cli_invalid_count_is_diagnostic(self):
        output = io.StringIO()
        with redirect_stderr(output), self.assertRaises(SystemExit) as error:
            pack.main(["--count", "0"])
        self.assertEqual(error.exception.code, 2)
        self.assertIn("1–64", output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
