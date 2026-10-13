import contextlib
import io
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from queue_cancel import CancellationError, cancel_request, main

SCHEMA = """
CREATE TABLE workspaces(id TEXT PRIMARY KEY,name TEXT NOT NULL,brand TEXT NOT NULL,version INTEGER NOT NULL);
CREATE TABLE requests(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id),title TEXT NOT NULL,brief TEXT NOT NULL,priority INTEGER NOT NULL,status TEXT NOT NULL,version INTEGER NOT NULL,created TEXT NOT NULL);
CREATE UNIQUE INDEX one_active_request ON requests(workspace_id) WHERE status IN ('production','review','revision');
CREATE TABLE events(id INTEGER PRIMARY KEY,request_id TEXT NOT NULL REFERENCES requests(id),kind TEXT NOT NULL,note TEXT NOT NULL,created TEXT NOT NULL);
CREATE TABLE assets(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id),request_id TEXT REFERENCES requests(id),revision INTEGER NOT NULL,name TEXT NOT NULL,sha256 TEXT NOT NULL,content BLOB NOT NULL,created TEXT NOT NULL);
"""

R1 = "1" * 32
R2 = "2" * 32
R3 = "3" * 32
W1 = "a" * 32


class QueueCancelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "desk.sqlite3"
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("INSERT INTO workspaces VALUES(?,?,?,1)", (W1, "Demo", "{}"))

    def tearDown(self):
        self.temp.cleanup()

    @contextlib.contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path)
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, rid, status, priority, version=1, created="2026-09-08T12:00:00Z"):
        with self.connect() as db:
            db.execute(
                "INSERT INTO requests VALUES(?,?,?,?,?,?,?,?)",
                (rid, W1, "Request " + rid[0], "brief", priority, status, version, created),
            )
            db.execute(
                "INSERT INTO events(request_id,kind,note,created) VALUES(?,?,?,?)",
                (rid, "submitted", "seed", created),
            )

    def rows(self):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            return {row["id"]: dict(row) for row in db.execute("SELECT * FROM requests")}

    def events(self, rid):
        with self.connect() as db:
            return list(db.execute("SELECT kind,note FROM events WHERE request_id=? ORDER BY id", (rid,)))

    def test_active_cancel_advances_lowest_priority_queue_item(self):
        self.add(R1, "production", 100)
        self.add(R2, "queued", 20, created="2026-09-08T12:01:00Z")
        self.add(R3, "queued", 10, created="2026-09-08T12:02:00Z")
        result = cancel_request(self.db_path, R1, 1, "Customer withdrew this request")
        rows = self.rows()
        self.assertTrue(result["cancelled"])
        self.assertEqual(R3, result["advanced_request_id"])
        self.assertEqual(("cancelled", 2), (rows[R1]["status"], rows[R1]["version"]))
        self.assertEqual(("production", 2), (rows[R3]["status"], rows[R3]["version"]))
        self.assertEqual("queued", rows[R2]["status"])
        self.assertEqual("cancelled", self.events(R1)[-1][0])
        self.assertIn("no delivery acceptance is implied", self.events(R1)[-1][1])
        self.assertEqual("started", self.events(R3)[-1][0])

    def test_queued_cancel_does_not_disturb_active_request(self):
        self.add(R1, "review", 100)
        self.add(R2, "queued", 1)
        result = cancel_request(self.db_path, R2, 1, "Duplicate request")
        rows = self.rows()
        self.assertIsNone(result["advanced_request_id"])
        self.assertEqual("review", rows[R1]["status"])
        self.assertEqual("cancelled", rows[R2]["status"])

    def test_cancelled_and_approved_terminal_states_remain_distinct(self):
        self.add(R1, "production", 100)
        self.add(R2, "complete", 200)
        cancel_request(self.db_path, R1, 1, "Withdrawn")
        rows = self.rows()
        self.assertEqual("cancelled", rows[R1]["status"])
        self.assertEqual("complete", rows[R2]["status"])

    def test_stale_version_refuses_without_mutation(self):
        self.add(R1, "production", 100, version=3)
        with self.assertRaises(CancellationError) as caught:
            cancel_request(self.db_path, R1, 2, "Stale operator view")
        self.assertEqual(409, caught.exception.status)
        self.assertEqual(("production", 3), (self.rows()[R1]["status"], self.rows()[R1]["version"]))
        self.assertEqual(1, len(self.events(R1)))

    def test_terminal_request_refuses_without_second_event(self):
        self.add(R1, "complete", 100, version=4)
        with self.assertRaises(CancellationError) as caught:
            cancel_request(self.db_path, R1, 4, "Too late")
        self.assertEqual(409, caught.exception.status)
        self.assertEqual(1, len(self.events(R1)))

    def test_cancelled_request_refuses_without_second_event(self):
        self.add(R1, "cancelled", 100, version=4)
        with self.assertRaises(CancellationError) as caught:
            cancel_request(self.db_path, R1, 4, "Too late")
        self.assertEqual(409, caught.exception.status)
        self.assertEqual(1, len(self.events(R1)))

    def test_repeat_cancel_refuses_via_terminal_state(self):
        self.add(R1, "production", 100)
        cancel_request(self.db_path, R1, 1, "Cancelled once")
        with self.assertRaises(CancellationError) as caught:
            cancel_request(self.db_path, R1, 2, "Cancelled twice")
        self.assertEqual(409, caught.exception.status)
        self.assertEqual(1, [kind for kind, _ in self.events(R1)].count("cancelled"))

    def test_two_concurrent_operators_advance_queue_once(self):
        self.add(R1, "revision", 100)
        self.add(R2, "queued", 5)
        barrier = threading.Barrier(3)
        results = []
        lock = threading.Lock()

        def worker(label):
            barrier.wait()
            try:
                value = ("ok", cancel_request(self.db_path, R1, 1, label))
            except CancellationError as exc:
                value = ("error", exc.status)
            with lock:
                results.append(value)

        threads = [threading.Thread(target=worker, args=("operator-a",)), threading.Thread(target=worker, args=("operator-b",))]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()
        self.assertEqual(["error", "ok"], sorted(kind for kind, _ in results))
        self.assertEqual(1, [kind for kind, _ in self.events(R1)].count("cancelled"))
        self.assertEqual(1, [kind for kind, _ in self.events(R2)].count("started"))
        self.assertEqual("production", self.rows()[R2]["status"])
        self.assertEqual("cancelled", self.rows()[R1]["status"])

    def test_missing_database_is_not_created(self):
        missing = Path(self.temp.name) / "missing.sqlite3"
        with self.assertRaises(CancellationError) as caught:
            cancel_request(missing, R1, 1, "Nothing to cancel")
        self.assertEqual(404, caught.exception.status)
        self.assertFalse(missing.exists())

    def test_cli_requires_exact_request_id_confirmation(self):
        self.add(R1, "production", 100)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main([R1, "--db", str(self.db_path), "--expected-version", "1", "--reason", "obsolete", "--confirm-request-id", R2])
        self.assertEqual(2, code)
        self.assertIn("does not match", output.getvalue())
        self.assertEqual("production", self.rows()[R1]["status"])


if __name__ == "__main__":
    unittest.main()
