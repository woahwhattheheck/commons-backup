"""Actual Lantern Store, SQLite/WAL, CLI and filesystem acceptance for exports."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import contextlib
import csv
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

import app
import results_export as exports

ROOT = Path(__file__).resolve().parent


class ResultsExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.database = self.root / "events ?# café.sqlite3"
        self.now = 1000.0
        self.store = app.Store(self.database, clock=lambda: self.now)
        self.event = self.make_event()

    def make_event(self, **changes):
        payload = {"title": "Community, round 1", "room": "Café room", "opens": 900, "ends": 2000,
                   "questions": [{"prompt": "Choose A", "choices": ["A", "B"], "correct": 0},
                                 {"prompt": "Choose B", "choices": ["A", "B"], "correct": 1}]}
        payload.update(changes)
        return self.store.create(payload)["id"]

    def player(self, name, choices=(), event=None):
        event = event or self.event
        member = self.store.join(event, {"name": name})["id"]
        self.now += 0.001  # Stable native tie ordering, no synthetic ranks.
        for index, choice in enumerate(choices):
            self.store.answer(event, {"member_id": member, "question": index, "choice": choice})
        return member

    def finished(self):
        self.store.finish(self.event)
        return exports.results_document(self.store, self.event)

    def test_native_ranking_ties_and_unanswered_players_are_preserved(self):
        for name, choices in (("First", (0, 1)), ("Second", (0, 1)), ("Third", (1,)), ("No answers", ())):
            self.player(name, choices)
        document = self.finished()
        self.assertEqual([r["rank"] for r in document["leaderboard"]], [1, 1, 3, 3])
        self.assertEqual([r["points"] for r in document["leaderboard"]], [200, 200, 0, 0])
        self.assertEqual([r["answered"] for r in document["leaderboard"]], [2, 2, 1, 0])
        self.assertEqual(document["participants"], 4)
        self.assertEqual(document["leaderboard"], [{k: r[k] for k in ("rank", "name", "points", "answered")}
                                                 for r in self.store.state(self.event)["leaderboard"]])

    def test_export_excludes_reconnect_references_and_question_answers(self):
        reference = self.player("Nickname", (0,))
        self.finished()
        data = exports.export_bytes(self.store, self.event)
        self.assertNotIn(reference.encode(), data)
        for excluded in (b'"correct"', b'"questions"', b'"answers"', b'"member"', b'"joined"'):
            self.assertNotIn(excluded, data)
        self.assertEqual(json.loads(data)["schema"], "lantern.results.v1")
        self.assertEqual(json.loads(data)["event"]["question_count"], 2)

    def test_json_unicode_commas_quotes_and_multiline_names_remain_exact(self):
        name = 'Zoë, "雨"\nsecond line'
        self.player(name)
        document = self.finished()
        self.assertEqual(json.loads(exports.export_bytes(self.store, self.event))["leaderboard"][0]["name"], name)
        self.assertEqual(document["event"]["room"], "Café room")

    def test_csv_unicode_quotes_newlines_and_metadata_round_trip(self):
        name = 'Zoë, "雨"\nsecond line'
        self.player(name, (0,))
        self.finished()
        data = exports.export_bytes(self.store, self.event, "csv")
        self.assertTrue(data.startswith(b"\xef\xbb\xbf"))
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"), newline="")))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], dict(zip(exports.COLUMNS,
                         [self.event, "Community, round 1", "Café room", "1", name, "100", "1"])))

    def test_csv_formula_prefixes_are_text_and_json_is_lossless(self):
        names = ["=1+1", "+2", "-3", "@sum", "\x00=1+1", "Ordinary"]
        for name in names:
            self.player(name)
        document = self.finished()
        rows = list(csv.DictReader(io.StringIO(exports.export_bytes(self.store, self.event, "csv").decode("utf-8-sig"))))
        self.assertEqual([r["display_name"] for r in rows], ["'" + n for n in names[:-1]] + ["Ordinary"])
        self.assertEqual([r["name"] for r in document["leaderboard"]], names)

    def test_formula_like_event_metadata_is_neutralized_in_csv(self):
        self.event = self.make_event(title="=1+1", room="@room")
        self.player("Player")
        self.finished()
        row = next(csv.DictReader(io.StringIO(exports.export_bytes(self.store, self.event, "csv").decode("utf-8-sig"))))
        self.assertEqual((row["event_title"], row["room"]), ("'=1+1", "'@room"))

    def test_empty_event_has_json_metadata_and_csv_header_only(self):
        document = self.finished()
        self.assertEqual(document["participants"], 0)
        self.assertEqual(document["leaderboard"], [])
        data = exports.export_bytes(self.store, self.event, "csv").decode("utf-8-sig")
        self.assertEqual(list(csv.reader(io.StringIO(data))), [list(exports.COLUMNS)])

    def test_open_event_rejected_without_revealing_scores(self):
        self.player("Active", (0,))
        with self.assertRaises(app.Problem) as error:
            exports.export_bytes(self.store, self.event)
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.store.state(self.event)["phase"], "open")

    def test_scheduled_event_rejected(self):
        self.now = 899
        with self.assertRaises(app.Problem) as error:
            exports.export_bytes(self.store, self.event, "csv")
        self.assertEqual(error.exception.status, 409)

    def test_natural_end_uses_the_native_exclusive_boundary(self):
        self.player("Player", (0,))
        self.now = 1999.999
        with self.assertRaises(app.Problem):
            exports.results_document(self.store, self.event)
        self.now = 2000
        self.assertEqual(exports.results_document(self.store, self.event)["leaderboard"][0]["points"], 100)

    def test_unknown_event_preserves_native_404(self):
        with self.assertRaises(app.Problem) as error:
            exports.results_document(self.store, "missing")
        self.assertEqual(error.exception.status, 404)

    def test_other_event_participants_are_not_exported(self):
        other = self.make_event(title="Another event")
        self.player("DO_NOT_EXPORT", (0, 1), other)
        self.player("This event", (0,))
        self.finished()
        self.assertNotIn(b"DO_NOT_EXPORT", exports.export_bytes(self.store, self.event))

    def test_finished_exports_are_deterministic_across_clock_changes(self):
        self.player("Player", (0,))
        self.finished()
        for format in ("csv", "json"):
            first = exports.export_bytes(self.store, self.event, format)
            self.now += 500
            self.assertEqual(exports.export_bytes(self.store, self.event, format), first)

    def test_reopened_readonly_store_preserves_results_and_database_bytes(self):
        self.player("Player", (0, 1))
        self.finished()
        before = hashlib.sha256(self.database.read_bytes()).hexdigest()
        reader = exports.ReadOnlyStore(self.database, clock=lambda: self.now)
        self.assertEqual(exports.export_bytes(reader, self.event), exports.export_bytes(self.store, self.event))
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(), before)
        with reader.connect() as db:
            with self.assertRaises(sqlite3.OperationalError):
                db.execute("UPDATE events SET title='no' WHERE id=?", (self.event,))

    def test_readonly_snapshot_sees_committed_wal_but_not_pending_changes(self):
        self.player("Committed", (0,))
        self.finished()
        connection = sqlite3.connect(self.database)
        self.addCleanup(connection.close)
        connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("UPDATE members SET name='Committed WAL' WHERE event=?", (self.event,))
        connection.commit()
        self.assertTrue(Path(str(self.database) + "-wal").exists())
        connection.execute("UPDATE members SET name='Pending' WHERE event=?", (self.event,))
        reader = exports.ReadOnlyStore(self.database, clock=lambda: self.now)
        self.assertEqual(exports.results_document(reader, self.event)["leaderboard"][0]["name"], "Committed WAL")
        connection.rollback()

    def test_missing_database_is_never_created(self):
        path = self.root / "missing.sqlite3"
        with self.assertRaises(FileNotFoundError):
            exports.ReadOnlyStore(path)
        self.assertFalse(path.exists())

    def test_directory_is_not_a_database(self):
        with self.assertRaises(ValueError):
            exports.ReadOnlyStore(self.root)

    def test_wrong_database_is_not_initialized(self):
        path = self.root / "wrong.sqlite3"
        with contextlib.closing(sqlite3.connect(path)) as db:
            db.execute("CREATE TABLE unrelated(value TEXT)")
            db.commit()
        before = path.read_bytes()
        with self.assertRaises(sqlite3.DatabaseError):
            exports.export_bytes(exports.ReadOnlyStore(path), self.event)
        self.assertEqual(path.read_bytes(), before)

    def test_invalid_format_is_rejected(self):
        with self.assertRaises(ValueError):
            exports.export_bytes(self.store, self.event, "xml")

    def cli(self, *arguments):
        return subprocess.run([sys.executable, "-B", str(ROOT / "results_export.py"), *arguments],
                              capture_output=True, text=True, timeout=15)

    def test_actual_cli_exports_csv_and_json_then_refuses_overwrite(self):
        self.player("CLI participant", (0,))
        self.finished()
        for format in ("json", "csv"):
            output = self.root / ("results." + format)
            args = ["--db", str(self.database), "--event", self.event, "--format", format, "--output", str(output)]
            result = self.cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(output.read_bytes(), exports.export_bytes(self.store, self.event, format))
            before = output.read_bytes()
            retry = self.cli(*args)
            self.assertEqual(retry.returncode, 2)
            self.assertEqual(output.read_bytes(), before)
            self.assertNotIn("Traceback", retry.stderr)

    def test_cli_error_does_not_create_output_or_database(self):
        database, output = self.root / "missing.db", self.root / "nothing.json"
        result = self.cli("--db", str(database), "--event", "missing", "--output", str(output))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())
        self.assertFalse(database.exists())
        self.assertNotIn("Traceback", result.stderr)

    def test_cli_refuses_unfinished_event_without_creating_output(self):
        self.now = time.time()
        event = self.make_event(opens=self.now + 600, ends=self.now + 3600)
        output = self.root / "not-ready.json"
        result = self.cli("--db", str(self.database), "--event", event, "--output", str(output))
        self.assertEqual(result.returncode, 2)
        self.assertIn("only after the event finishes", result.stderr)
        self.assertFalse(output.exists())
        self.assertEqual(self.store.state(event)["phase"], "scheduled")

    def test_database_cannot_be_replaced_by_export_output(self):
        self.player("Player")
        self.finished()
        before = self.database.read_bytes()
        result = self.cli("--db", str(self.database), "--event", self.event, "--output", str(self.database))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.database.read_bytes(), before)
        self.assertEqual(list(self.root.glob(".lantern-results-*")), [])

    def test_atomic_competing_writers_publish_one_complete_output(self):
        output = self.root / "race.json"
        payloads = [(str(i) * 10000).encode() for i in range(16)]
        def publish(data):
            try:
                exports.write_new_output(output, data)
                return data
            except FileExistsError:
                return None
        with ThreadPoolExecutor(max_workers=16) as pool:
            winners = [result for result in pool.map(publish, payloads) if result is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(output.read_bytes(), winners[0])
        self.assertEqual(list(self.root.glob(".lantern-results-*")), [])

    def test_dangling_destination_symlink_is_not_followed_or_replaced(self):
        target, link = self.root / "target.json", self.root / "link.json"
        link.symlink_to(target)
        with self.assertRaises(FileExistsError):
            exports.write_new_output(link, b"results")
        self.assertTrue(link.is_symlink())
        self.assertFalse(target.exists())
        self.assertEqual(list(self.root.glob(".lantern-results-*")), [])

    def test_existing_directory_is_not_replaced(self):
        output = self.root / "folder"
        output.mkdir()
        with self.assertRaises(OSError):
            exports.write_new_output(output, b"results")
        self.assertTrue(output.is_dir())
        self.assertEqual(list(self.root.glob(".lantern-results-*")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
