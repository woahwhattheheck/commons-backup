"""Additional boundary coverage; compose with LINDEN's existing consumer suite."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import app as lantern
import knight_pack as pack

ROOT = Path(__file__).resolve().parent


class LanternKnightBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.database = self.directory / "events.sqlite3"
        self.store = lantern.Store(self.database, clock=lambda: 1000.0)

    def payload(self, questions):
        return {"title": "Knight challenge", "room": "Community",
                "opens": 900, "ends": 2000, "questions": questions}

    def test_real_cli_file_imports_and_preserves_a_second_invocation(self):
        output = self.directory / "new-week.json"
        command = [sys.executable, "-B", str(ROOT / "knight_pack.py"),
                   "--seed", "community-knight-week-3", "--count", "12",
                   "--answer-key", "correct", "--omit-explanation",
                   "--output", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        original = output.read_bytes()
        questions = json.loads(original)
        event = self.store.create(self.payload(questions))["id"]
        self.assertEqual(self.store.state(event)["question_count"], 12)
        expected = pack.adapt(pack.generate("community-knight-week-3", 12),
                              answer_key="correct", explanation_key=None)
        self.assertEqual(questions, expected)
        repeated = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(repeated.returncode, 2)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(len(self.store.listing()), 1)

    def test_oversized_import_keeps_existing_event_and_generator_capacity(self):
        self.assertEqual(len(pack.generate(count=64)), 64)
        questions = pack.adapt(pack.generate(count=50), answer_key="correct",
                               explanation_key=None)
        event = self.store.create(self.payload(questions))["id"]
        before = self.store.state(event)
        listing_before = self.store.listing()
        oversized = pack.adapt(pack.generate(count=51), answer_key="correct",
                                explanation_key=None)
        with self.assertRaises(lantern.Problem) as error:
            self.store.create(self.payload(oversized))
        self.assertEqual(error.exception.status, 422)
        self.assertEqual(self.store.listing(), listing_before)
        reopened = lantern.Store(self.database, clock=lambda: 1000.0)
        self.assertEqual(reopened.state(event), before)
        self.assertEqual(reopened.state(event)["question_count"], 50)


if __name__ == "__main__":
    unittest.main(verbosity=2)
