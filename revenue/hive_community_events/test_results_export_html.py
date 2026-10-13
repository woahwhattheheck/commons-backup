"""Focused current-contract tests for Lantern printable HTML results."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import app
import results_export_html as printable

ROOT = Path(__file__).resolve().parent


class PrintableResultsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "events.sqlite3"
        self.now = 1000.0
        self.store = app.Store(self.db, clock=lambda: self.now)
        self.event = self.store.create({
            "title": '<Final & "Round">', "room": "Café <room>", "opens": 900, "ends": 2000,
            "questions": [
                {"prompt": "SECRET QUESTION 1", "choices": ["A", "B"], "correct": 0, "points": 100},
                {"prompt": "SECRET QUESTION 2", "choices": ["A", "B"], "correct": 1, "points": 200},
            ],
        })["id"]

    def player(self, name, choices=()):
        member = self.store.join(self.event, {"name": name})["id"]
        self.now += 0.001
        for index, choice in enumerate(choices):
            self.store.answer(self.event, {"member_id": member, "question": index, "choice": choice})
        return member

    def finish(self):
        self.store.finish(self.event)

    def test_native_competition_ranks_and_empty_players(self):
        self.player("First", (0, 1)); self.player("Second", (0, 1)); self.player("Third", (1,)); self.player("No answers")
        self.finish()
        text = printable.export_html(self.store, self.event).decode()
        self.assertIn('<td>1</td><th scope="row">First</th><td>300</td><td>2 / 2</td>', text)
        self.assertIn('<td>1</td><th scope="row">Second</th><td>300</td><td>2 / 2</td>', text)
        self.assertIn('<td>3</td><th scope="row">Third</th><td>0</td><td>1 / 2</td>', text)
        self.assertIn('<td>3</td><th scope="row">No answers</th><td>0</td><td>0 / 2</td>', text)

    def test_html_escapes_user_text_and_excludes_private_fields(self):
        member = self.player('<img src=x onerror="bad">', (0,))
        self.finish()
        text = printable.export_html(self.store, self.event).decode()
        self.assertIn('&lt;Final &amp; &quot;Round&quot;&gt;', text)
        self.assertIn('Café &lt;room&gt;', text)
        self.assertIn('&lt;img src=x onerror=&quot;bad&quot;&gt;', text)
        self.assertNotIn('<img src=x', text)
        self.assertNotIn(member, text)
        self.assertNotIn('SECRET QUESTION', text)
        self.assertNotIn('member_id', text)
        self.assertNotIn('\"correct\"', text)
        self.assertNotIn('<script', text.lower())
        self.assertNotIn('http://', text.lower())
        self.assertNotIn('https://', text.lower())

    def test_finished_output_is_byte_deterministic_across_clock_changes(self):
        self.player("Player", (0,)); self.finish()
        first = printable.export_html(self.store, self.event)
        self.now += 5000
        self.assertEqual(printable.export_html(self.store, self.event), first)

    def test_unfinished_event_is_rejected(self):
        self.player("Player", (0,))
        with self.assertRaises(app.Problem) as error:
            printable.export_html(self.store, self.event)
        self.assertEqual(error.exception.status, 409)

    def test_empty_finished_event_is_printable(self):
        self.finish()
        text = printable.export_html(self.store, self.event).decode()
        self.assertIn('0 participants', text)
        self.assertIn('No participants joined this event.', text)

    def test_readonly_cli_preserves_database_and_refuses_overwrite(self):
        self.player("CLI", (0, 1)); self.finish()
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        output = self.root / "results.html"
        args = [sys.executable, "-B", str(ROOT / "results_export_html.py"), "--db", str(self.db), "--event", self.event, "--output", str(output)]
        first = subprocess.run(args, capture_output=True, text=True, timeout=15)
        self.assertEqual(first.returncode, 0, first.stderr)
        expected = printable.export_html(self.store, self.event)
        self.assertEqual(output.read_bytes(), expected)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)
        retry = subprocess.run(args, capture_output=True, text=True, timeout=15)
        self.assertEqual(retry.returncode, 2)
        self.assertEqual(output.read_bytes(), expected)
        self.assertEqual(list(self.root.glob('.lantern-results-*')), [])

    def test_cli_refuses_dangling_destination_symlink(self):
        self.finish()
        target, link = self.root / "target.html", self.root / "link.html"
        link.symlink_to(target)
        result = subprocess.run([sys.executable, "-B", str(ROOT / "results_export_html.py"), "--db", str(self.db), "--event", self.event, "--output", str(link)], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertTrue(link.is_symlink())
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
