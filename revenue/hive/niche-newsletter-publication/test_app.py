from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile

from http.server import ThreadingHTTPServer

from app import Problem, Store, make_handler

ROOT = Path(__file__).resolve().parent
FIXTURE = json.loads((ROOT / "demo.json").read_text(encoding="utf-8"))
CLOCK = lambda: 1788868500.0


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "northstar.sqlite3"
        self.store = Store(self.db, clock=CLOCK)

    def seed(self):
        return self.store.seed(FIXTURE)

    def subscribe(self, email="reader@example.invalid", topics=None):
        return self.store.subscribe({"email": email, "topics": topics or [], "frequency": "weekly"})["id"]

    def test_seed_builds_three_published_source_linked_issues(self):
        self.seed()
        state = self.store.snapshot()
        self.assertEqual(len(state["archive"]), 3)
        self.assertEqual(len(state["sources"]), 3)
        self.assertTrue(all(issue["source_ids"] for issue in state["issues"]))
        self.assertTrue(all(issue["state"] == "published" for issue in state["issues"]))

    def test_seed_is_idempotent(self):
        first = self.seed()
        second = self.seed()
        self.assertEqual(first, {"sources": 3, "issues": 3, "subscribers": 1})
        self.assertEqual(second, {"sources": 0, "issues": 0, "subscribers": 0})
        self.assertEqual(len(self.store.snapshot()["archive"]), 3)

    def test_reopen_preserves_sources_subscriber_and_archive(self):
        self.seed()
        before = self.store.snapshot()
        reopened = Store(self.db, clock=CLOCK).snapshot()
        self.assertEqual(reopened, before)

    def test_issue_revision_snapshots_old_source_links(self):
        self.store.source({"id":"s1","title":"S1","url":"self-authored:s1","observed_at":"2026-09-01T00:00:00Z","synthetic":True})
        self.store.source({"id":"s2","title":"S2","url":"self-authored:s2","observed_at":"2026-09-02T00:00:00Z","synthetic":True})
        created = self.store.issue({"id":"i1","slug":"first","title":"First","subject":"First","body":"Body one","topic":"ops","scheduled_at":"2026-10-01T12:00:00Z","source_ids":["s1"]})
        self.assertEqual(created["revision"], 1)
        revised = self.store.revise("i1", {"body":"Body two","source_ids":["s2"]})
        self.assertEqual(revised["revision"], 2)
        with self.store.connect() as db:
            history = db.execute("SELECT revision,body,source_ids FROM issue_history WHERE issue_id='i1' ORDER BY revision").fetchall()
        self.assertEqual([(r["revision"], r["body"], json.loads(r["source_ids"])) for r in history],
                         [(1, "Body one", ["s1"]), (2, "Body two", ["s2"])])

    def test_publish_is_idempotent_and_published_issue_is_immutable(self):
        self.store.source({"id":"s","title":"S","url":"self-authored:s","observed_at":"2026-09-01T00:00:00Z","synthetic":True})
        self.store.issue({"id":"i","slug":"immutable","title":"Immutable","subject":"Subject","body":"Body","topic":"ops","scheduled_at":"2026-10-01T12:00:00Z","source_ids":["s"]})
        self.assertEqual(self.store.publish("i"), {"published": True, "replayed": False})
        self.assertEqual(self.store.publish("i"), {"published": True, "replayed": True})
        with self.assertRaisesRegex(Problem, "Published issues are immutable"):
            self.store.revise("i", {"body":"changed"})

    def test_subscribe_welcome_preferences_export_unsubscribe_suppression(self):
        self.seed()
        sid = self.subscribe("flow@example.invalid", ["operations"])
        welcome = json.loads(self.store.welcome(sid))
        self.assertEqual(welcome["delivery_state"], "UNSENT")
        self.assertEqual(welcome["topics"], ["operations"])
        self.store.preferences(sid, {"topics":["automation"], "frequency":"monthly"})
        ops_zip = self.store.issue_export("issue-001")
        with zipfile.ZipFile(io.BytesIO(ops_zip)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        self.assertNotIn("flow@example.invalid", manifest["recipients"])
        auto_zip = self.store.issue_export("issue-003")
        with zipfile.ZipFile(io.BytesIO(auto_zip)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        self.assertIn("flow@example.invalid", manifest["recipients"])
        self.assertFalse(self.store.unsubscribe(sid)["replayed"])
        self.assertTrue(self.store.unsubscribe(sid)["replayed"])
        with self.assertRaisesRegex(Problem, "do not receive exports"):
            self.store.welcome(sid)
        auto_zip = self.store.issue_export("issue-003")
        with zipfile.ZipFile(io.BytesIO(auto_zip)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
        self.assertNotIn("flow@example.invalid", manifest["recipients"])

    def test_unsubscribed_address_does_not_silently_resubscribe(self):
        sid = self.subscribe("stop@example.invalid")
        self.store.unsubscribe(sid)
        with self.assertRaisesRegex(Problem, "explicit resubscription"):
            self.store.subscribe({"email":"STOP@example.invalid", "topics":[], "frequency":"weekly"})

    def test_duplicate_active_subscribe_is_replay(self):
        first = self.store.subscribe({"email":"same@example.invalid", "topics":[], "frequency":"weekly"})
        second = self.store.subscribe({"email":"SAME@example.invalid", "topics":["ops"], "frequency":"monthly"})
        self.assertTrue(second["replayed"])
        self.assertEqual(first["id"], second["id"])
        row = self.store.snapshot()["subscribers"][0]
        self.assertEqual(row["topics"], [])
        self.assertEqual(row["frequency"], "weekly")

    def test_duplicate_subscribe_waits_for_inflight_writer_then_replays(self):
        result = {}
        errors = []
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")

            def retry_same_email():
                try:
                    result.update(self.store.subscribe({
                        "email": "RACE@example.invalid", "topics": [], "frequency": "weekly"
                    }))
                except BaseException as exc:  # Surface raw SQLite races to the test thread.
                    errors.append(exc)

            thread = threading.Thread(target=retry_same_email)
            thread.start()
            time.sleep(0.05)
            db.execute(
                "INSERT INTO subscribers VALUES(?,?,?,?,?,?,?)",
                ("winner", "race@example.invalid", "[]", "weekly", "active",
                 "2026-09-09T00:00:00Z", "2026-09-09T00:00:00Z"),
            )

        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(result, {"id": "winner", "replayed": True})
        self.assertEqual(len(self.store.snapshot()["subscribers"]), 1)

    def test_export_contains_manifest_sources_issue_and_recipient_packets(self):
        self.seed()
        data = self.store.issue_export("issue-003")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = sorted(zf.namelist())
            self.assertIn("manifest.json", names)
            self.assertIn("issue.txt", names)
            self.assertIn("sources.json", names)
            self.assertTrue(any(name.startswith("recipients/") for name in names))
            manifest = json.loads(zf.read("manifest.json"))
            self.assertEqual(manifest["delivery_state"], "UNSENT")
            self.assertEqual([s["id"] for s in manifest["sources"]], ["src-auto-01", "src-ops-02"])
            self.assertEqual(manifest["issue"]["revision"], 1)

    def test_draft_cannot_export(self):
        self.store.source({"id":"s","title":"S","url":"self-authored:s","observed_at":"2026-09-01T00:00:00Z","synthetic":True})
        self.store.issue({"id":"draft","slug":"draft","title":"Draft","subject":"Draft","body":"Body","topic":"ops","scheduled_at":"2026-10-01T12:00:00Z","source_ids":["s"]})
        with self.assertRaisesRegex(Problem, "Only published issues"):
            self.store.issue_export("draft")

    def test_issue_requires_existing_source(self):
        with self.assertRaisesRegex(Problem, "Unknown source ids"):
            self.store.issue({"id":"i","slug":"missing-source","title":"Issue","subject":"Issue","body":"Body","topic":"ops","scheduled_at":"2026-10-01T12:00:00Z","source_ids":["missing"]})

    def test_source_url_contract_rejects_untracked_free_text(self):
        with self.assertRaisesRegex(Problem, "Source URL must"):
            self.store.source({"id":"s","title":"S","url":"notes from memory","observed_at":"2026-09-01T00:00:00Z"})


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "http.sqlite3", clock=CLOCK)
        self.store.seed(FIXTURE)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join, 2)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def request(self, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type":"application/json"} if data else {},
                                     method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=3) as response:
                return response.status, response.headers.get_content_type(), response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get_content_type(), exc.read()

    def test_real_http_subscriber_flow_and_finished_zip(self):
        status, _, body = self.request("/api/subscribers", {"email":"http@example.invalid","topics":["operations"],"frequency":"weekly"})
        self.assertEqual(status, 201)
        sid = json.loads(body)["id"]
        status, content_type, body = self.request(f"/api/subscribers/{sid}/welcome")
        self.assertEqual((status, content_type), (200, "application/json"))
        self.assertEqual(json.loads(body)["delivery_state"], "UNSENT")
        status, content_type, body = self.request("/api/issues/issue-001/export")
        self.assertEqual((status, content_type), (200, "application/zip"))
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            self.assertIn("http@example.invalid", json.loads(zf.read("manifest.json"))["recipients"])
        status, _, _ = self.request(f"/api/subscribers/{sid}/unsubscribe", {})
        self.assertEqual(status, 200)
        status, _, body = self.request("/api/issues/issue-001/export")
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            self.assertNotIn("http@example.invalid", json.loads(zf.read("manifest.json"))["recipients"])

    def test_real_http_draft_export_returns_conflict(self):
        status, _, source = self.request("/api/sources", {"id":"http-source","title":"HTTP source","url":"self-authored:http","observed_at":"2026-09-01T00:00:00Z","synthetic":True})
        self.assertEqual(status, 201)
        status, _, body = self.request("/api/issues", {"id":"http-draft","slug":"http-draft","title":"Draft","subject":"Draft","body":"Body","topic":"ops","scheduled_at":"2026-10-01T00:00:00Z","source_ids":["http-source"]})
        self.assertEqual(status, 201)
        status, content_type, body = self.request("/api/issues/http-draft/export")
        self.assertEqual((status, content_type), (409, "application/json"))
        self.assertIn("Only published issues", json.loads(body)["error"])

    def test_real_http_rejects_non_object_json(self):
        req = urllib.request.Request(self.base + "/api/subscribers", data=b"[]",
                                     headers={"Content-Type":"application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(req, timeout=3)
        self.assertEqual(caught.exception.code, 422)
        self.assertIn("JSON body must be an object", json.loads(caught.exception.read())["error"])


if __name__ == "__main__":
    unittest.main()
