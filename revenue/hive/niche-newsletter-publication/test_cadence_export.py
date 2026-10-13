from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import zipfile

from cadence_export import ExportError, build_cadence_export, main


class CadenceExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / "northstar.sqlite3"
        with sqlite3.connect(self.db) as db:
            db.executescript("""
            CREATE TABLE sources(
              id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
              observed_at TEXT NOT NULL, notes TEXT NOT NULL, synthetic INTEGER NOT NULL,
              created_at TEXT NOT NULL);
            CREATE TABLE issues(
              id TEXT PRIMARY KEY, slug TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
              subject TEXT NOT NULL, body TEXT NOT NULL, topic TEXT NOT NULL,
              scheduled_at TEXT NOT NULL, state TEXT NOT NULL,
              revision INTEGER NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE issue_sources(
              issue_id TEXT NOT NULL, source_id TEXT NOT NULL,
              PRIMARY KEY(issue_id,source_id));
            CREATE TABLE subscribers(
              id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, topics TEXT NOT NULL,
              frequency TEXT NOT NULL, status TEXT NOT NULL,
              created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            """)
            db.execute(
                "INSERT INTO sources VALUES(?,?,?,?,?,?,?)",
                ("src-1", "Source", "self-authored:test", "2026-09-01T00:00:00Z", "", 1, "2026-09-01T00:00:00Z"),
            )
            issue = (
                "issue-pub", "published-issue", "Published", "Northstar update", "Body", "operations",
                "2026-09-12T14:00:00Z", "published", 2, "2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z",
            )
            db.execute("INSERT INTO issues VALUES(?,?,?,?,?,?,?,?,?,?,?)", issue)
            draft = (
                "issue-draft", "draft-issue", "Draft", "Draft", "Body", "operations",
                "2026-09-19T14:00:00Z", "draft", 1, "2026-09-01T00:00:00Z", "2026-09-01T00:00:00Z",
            )
            db.execute("INSERT INTO issues VALUES(?,?,?,?,?,?,?,?,?,?,?)", draft)
            db.execute("INSERT INTO issue_sources VALUES(?,?)", ("issue-pub", "src-1"))
            db.execute("INSERT INTO issue_sources VALUES(?,?)", ("issue-draft", "src-1"))
            rows = [
                ("w-ops", "weekly-ops@example.invalid", '["operations"]', "weekly", "active"),
                ("w-all", "weekly-all@example.invalid", '[]', "weekly", "active"),
                ("w-other", "weekly-other@example.invalid", '["automation"]', "weekly", "active"),
                ("m-ops", "monthly-ops@example.invalid", '["operations"]', "monthly", "active"),
                ("m-stop", "monthly-stop@example.invalid", '["operations"]', "monthly", "unsubscribed"),
            ]
            db.executemany(
                "INSERT INTO subscribers VALUES(?,?,?,?,?,?,?)",
                [(sid, email, topics, frequency, status, "2026-09-01T00:00:00Z", "2026-09-01T00:00:00Z")
                 for sid, email, topics, frequency, status in rows],
            )

    def manifest(self, payload: bytes) -> dict:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return json.loads(archive.read("manifest.json"))

    def test_weekly_export_isolates_weekly_and_topic_matches(self):
        manifest = self.manifest(build_cadence_export(self.db, "issue-pub", "weekly"))
        self.assertEqual(manifest["cadence"], "weekly")
        self.assertEqual(
            manifest["recipients"],
            ["weekly-all@example.invalid", "weekly-ops@example.invalid"],
        )
        self.assertEqual(manifest["recipient_count"], 2)

    def test_monthly_export_excludes_weekly_and_unsubscribed(self):
        manifest = self.manifest(build_cadence_export(self.db, "issue-pub", "monthly"))
        self.assertEqual(manifest["recipients"], ["monthly-ops@example.invalid"])
        self.assertEqual(manifest["recipient_count"], 1)

    def test_every_recipient_packet_is_unsent_and_cadence_bound(self):
        payload = build_cadence_export(self.db, "issue-pub", "weekly")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            packets = [json.loads(archive.read(name)) for name in archive.namelist() if name.startswith("recipients/")]
        self.assertEqual(len(packets), 2)
        self.assertTrue(all(packet["delivery_state"] == "UNSENT" for packet in packets))
        self.assertTrue(all(packet["cadence"] == "weekly" for packet in packets))
        self.assertEqual({packet["issue_id"] for packet in packets}, {"issue-pub"})

    def test_export_is_byte_deterministic(self):
        first = build_cadence_export(self.db, "issue-pub", "weekly")
        second = build_cadence_export(self.db, "issue-pub", "weekly")
        self.assertEqual(first, second)
        self.assertEqual(hashlib.sha256(first).digest(), hashlib.sha256(second).digest())

    def test_export_is_read_only(self):
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        build_cadence_export(self.db, "issue-pub", "weekly")
        after = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_draft_issue_is_rejected(self):
        with self.assertRaisesRegex(ExportError, "Only published"):
            build_cadence_export(self.db, "issue-draft", "weekly")

    def test_missing_issue_is_rejected(self):
        with self.assertRaisesRegex(ExportError, "Issue not found"):
            build_cadence_export(self.db, "missing", "weekly")

    def test_invalid_requested_cadence_is_rejected(self):
        with self.assertRaisesRegex(ExportError, "weekly or monthly"):
            build_cadence_export(self.db, "issue-pub", "daily")

    def test_invalid_persisted_frequency_is_rejected(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE subscribers SET frequency='daily' WHERE id='w-ops'")
        with self.assertRaisesRegex(ExportError, "invalid frequency"):
            build_cadence_export(self.db, "issue-pub", "weekly")

    def test_invalid_persisted_status_is_rejected(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE subscribers SET status='paused' WHERE id='w-ops'")
        with self.assertRaisesRegex(ExportError, "invalid status"):
            build_cadence_export(self.db, "issue-pub", "weekly")

    def test_invalid_topics_json_is_rejected(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE subscribers SET topics='{}' WHERE id='w-ops'")
        with self.assertRaisesRegex(ExportError, "JSON array"):
            build_cadence_export(self.db, "issue-pub", "weekly")

    def test_cli_refuses_to_overwrite_existing_output(self):
        output = self.root / "weekly.zip"
        self.assertEqual(main(["--db", str(self.db), "--issue", "issue-pub", "--cadence", "weekly", "--output", str(output)]), 0)
        first = output.read_bytes()
        self.assertEqual(main(["--db", str(self.db), "--issue", "issue-pub", "--cadence", "weekly", "--output", str(output)]), 2)
        self.assertEqual(output.read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
