# SPDX-License-Identifier: Apache-2.0
"""Real SQLite, source-file, relationship, rollback and HTTP workflow checks."""
from __future__ import annotations

from contextlib import closing
import http.client
import io
import json
import shutil
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

from desk import server_for
from intake import MigrationError, canonical, digest, record_id
from migrate import apply_plan, edit_record, export_workspace, make_plan, read_state, rollback


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        shutil.copytree(Path(__file__).parent / "examples", self.source)
        self.database = self.root / "destination" / "crm.sqlite"
        self.assets = self.root / "destination" / "assets"

    def plan(self, operation="import-001"):
        return make_plan(self.source, "mapping.json", self.database, operation)

    def apply(self, operation="import-001"):
        plan = self.plan(operation)
        return apply_plan(plan, self.source, self.database, self.assets)

    def customer(self):
        return record_id("customers", "demo-workshop", "001")

    def task(self):
        return record_id("tasks", "demo-workshop", "T-01")

    def source_bytes(self):
        return {str(p.relative_to(self.source)): p.read_bytes() for p in self.source.rglob("*") if p.is_file()}

    def change(self, path, before, after):
        file = self.source / path
        file.write_text(file.read_text().replace(before, after), encoding="utf-8")

    def test_trial_does_not_create_destination_or_change_sources(self):
        source = self.source_bytes()
        plan = self.plan()
        self.assertFalse(self.database.parent.exists())
        self.assertEqual(source, self.source_bytes())
        self.assertEqual(plan["counts"], {"customers": 2, "tasks": 2, "attachments": 1})
        self.assertEqual([c["action"] for c in plan["changes"]], ["create"] * 5)

    def test_real_cutover_keeps_leading_zero_ids_relationships_and_attachment(self):
        source = self.source_bytes()
        result = self.apply()
        state = read_state(self.database)
        self.assertEqual(result["changed"], 5)
        self.assertEqual(state[self.customer()]["external_id"], "001")
        self.assertEqual(state[self.task()]["data"]["customer_id"], self.customer())
        asset = next(r for r in state.values() if r["kind"] == "attachments")
        self.assertEqual(asset["data"]["customer_id"], self.customer())
        self.assertEqual((self.assets / asset["data"]["sha256"]).read_bytes(), source["files/work-order.txt"])
        self.assertEqual(source, self.source_bytes())

    def test_exact_apply_retry_is_idempotent(self):
        plan = self.plan()
        first = apply_plan(plan, self.source, self.database, self.assets)
        state = read_state(self.database)
        second = apply_plan(plan, self.source, self.database, self.assets)
        self.assertFalse(first["repeated"])
        self.assertTrue(second["repeated"])
        self.assertEqual(state, read_state(self.database))
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM runs").fetchone()[0], 1)

    def test_reused_operation_for_another_plan_is_rejected(self):
        self.apply()
        self.change("customers.csv", "Example Workshop", "Changed Workshop")
        with self.assertRaisesRegex(MigrationError, "different plan"):
            apply_plan(self.plan(), self.source, self.database, self.assets)

    def test_unchanged_new_import_has_no_changes(self):
        self.apply()
        result = self.apply("import-002")
        self.assertEqual(result["changed"], 0)
        rollback(self.database, "import-002")
        self.assertEqual(len(read_state(self.database)), 5)

    def test_source_change_after_trial_is_rejected_before_destination_creation(self):
        plan = self.plan()
        self.change("customers.csv", "Example Workshop", "Changed Workshop")
        with self.assertRaisesRegex(MigrationError, "Source export changed"):
            apply_plan(plan, self.source, self.database, self.assets)
        self.assertFalse(self.database.exists())

    def test_attachment_change_after_trial_is_rejected(self):
        plan = self.plan()
        (self.source / "files/work-order.txt").write_bytes(b"changed")
        with self.assertRaisesRegex(MigrationError, "Source export changed"):
            apply_plan(plan, self.source, self.database, self.assets)
        self.assertFalse(self.database.exists())

    def test_missing_parent_rejects_the_entire_trial(self):
        self.change("tasks.csv", "T-01,001", "T-01,999")
        with self.assertRaisesRegex(MigrationError, "customer reference"):
            self.plan()
        self.assertFalse(self.database.exists())

    def test_duplicate_source_id_rejected(self):
        with (self.source / "customers.csv").open("a") as out:
            out.write("001,Duplicate,other@example.invalid,555-0102\n")
        with self.assertRaisesRegex(MigrationError, "Duplicate source identity"):
            self.plan()

    def test_duplicate_email_requires_explicit_decision_without_merging(self):
        self.change("customers.csv", "garden@example.invalid", "WORKSHOP@example.invalid")
        with self.assertRaisesRegex(MigrationError, "Duplicate customer email"):
            self.plan()
        self.change("mapping.json", '"duplicate_email": "error"', '"duplicate_email": "keep_separate"')
        plan = self.plan()
        self.assertEqual(len(plan["duplicate_decisions"]), 1)
        apply_plan(plan, self.source, self.database, self.assets)
        self.assertEqual(sum(r["kind"] == "customers" for r in read_state(self.database).values()), 2)

    def test_missing_column_rejected(self):
        self.change("mapping.json", '"name": "Customer"', '"name": "Missing column"')
        with self.assertRaisesRegex(MigrationError, "missing columns"):
            self.plan()

    def test_duplicate_csv_headers_rejected(self):
        self.change("customers.csv", "Contact Email,Phone", "Phone,Phone")
        with self.assertRaisesRegex(MigrationError, "repeated column headers"):
            self.plan()

    def test_unknown_mapping_field_rejected(self):
        self.change("mapping.json", '"phone": "Phone"', '"secret_guess": "Phone"')
        with self.assertRaisesRegex(MigrationError, "expected fields"):
            self.plan()

    def test_task_status_and_date_are_not_guessed(self):
        self.change("tasks.csv", "in_progress", "probably done")
        with self.assertRaisesRegex(MigrationError, "Task status"):
            self.plan()
        self.change("tasks.csv", "probably done", "in_progress")
        self.change("tasks.csv", "2026-09-15", "09/15/2026")
        with self.assertRaisesRegex(MigrationError, "YYYY-MM-DD"):
            self.plan()

    def test_parent_path_and_symbolic_link_sources_rejected(self):
        self.change("attachments.csv", "files/work-order.txt", "../outside.txt")
        (self.root / "outside.txt").write_text("outside")
        with self.assertRaisesRegex(MigrationError, "relative"):
            self.plan()
        self.change("attachments.csv", "../outside.txt", "files/link.txt")
        (self.source / "files/link.txt").symlink_to(self.root / "outside.txt")
        with self.assertRaisesRegex(MigrationError, "symbolic link"):
            self.plan()

    def test_plan_tampering_and_inconsistent_actions_rejected(self):
        plan = self.plan()
        plan["changes"][0]["action"] = "unchanged"
        with self.assertRaisesRegex(MigrationError, "Plan content changed"):
            apply_plan(plan, self.source, self.database, self.assets)
        plan["plan_id"] = digest(canonical({k: v for k, v in plan.items() if k != "plan_id"}).encode())
        with self.assertRaisesRegex(MigrationError, "Plan action differs"):
            apply_plan(plan, self.source, self.database, self.assets)

    def test_destination_edit_after_trial_prevents_stale_import(self):
        self.apply()
        self.change("customers.csv", "Example Workshop", "CSV Workshop")
        plan = self.plan("import-002")
        edit_record(self.database, self.customer(), 1, {"name": "Later local edit"})
        state = read_state(self.database)
        with self.assertRaisesRegex(MigrationError, "Destination changed"):
            apply_plan(plan, self.source, self.database, self.assets)
        self.assertEqual(read_state(self.database), state)

    def test_update_and_rollback_restore_exact_before_images(self):
        self.apply()
        before = read_state(self.database)
        self.change("customers.csv", "Example Workshop", "Updated Workshop")
        result = self.apply("import-002")
        self.assertEqual(result["changed"], 1)
        self.assertEqual(read_state(self.database)[self.customer()]["data"]["name"], "Updated Workshop")
        rollback(self.database, "import-002")
        self.assertEqual(read_state(self.database), before)

    def test_original_import_rollback_retains_source_and_attachment_copy(self):
        self.apply()
        originals = self.source_bytes()
        blobs = {p.name: p.read_bytes() for p in self.assets.iterdir()}
        result = rollback(self.database, "import-001")
        self.assertEqual(result["restored_records"], 5)
        self.assertEqual(read_state(self.database), {})
        self.assertEqual(self.source_bytes(), originals)
        self.assertEqual(blobs, {p.name: p.read_bytes() for p in self.assets.iterdir()})
        self.assertTrue(rollback(self.database, "import-001")["repeated"])

    def test_rollback_does_not_overwrite_later_task_work(self):
        self.apply()
        edit_record(self.database, self.task(), 1, {"status": "done"})
        state = read_state(self.database)
        with self.assertRaisesRegex(MigrationError, "Later edit"):
            rollback(self.database, "import-001")
        self.assertEqual(read_state(self.database), state)

    def test_rollback_cannot_orphan_later_related_task(self):
        self.apply()
        mapping = json.loads((self.source / "mapping.json").read_text())
        mapping.pop("customers")
        mapping.pop("attachments")
        (self.source / "mapping.json").write_text(json.dumps(mapping))
        with (self.source / "tasks.csv").open("a") as stream:
            stream.write("T-03,001,Later customer work,open,2026-09-20\n")
        self.apply("import-002")
        state = read_state(self.database)
        with self.assertRaisesRegex(MigrationError, "customer reference"):
            rollback(self.database, "import-001")
        self.assertEqual(read_state(self.database), state)

    def test_edit_preserves_links_and_rejects_stale_revision(self):
        self.apply()
        updated = edit_record(self.database, self.task(), 1, {"status": "done"})
        self.assertEqual(updated["data"]["customer_id"], self.customer())
        self.assertEqual(updated["revision"], 2)
        with self.assertRaisesRegex(MigrationError, "Record changed"):
            edit_record(self.database, self.task(), 1, {"status": "open"})
        with self.assertRaisesRegex(MigrationError, "displayed"):
            edit_record(self.database, self.task(), 2, {"customer_id": "invented"})

    def test_failed_asset_copy_does_not_partially_change_records(self):
        plan = self.plan()
        attachment = next(r for r in plan["source"]["records"] if r["kind"] == "attachments")
        self.assets.mkdir(parents=True)
        (self.assets / attachment["data"]["sha256"]).write_bytes(b"wrong existing bytes")
        with self.assertRaisesRegex(MigrationError, "content address"):
            apply_plan(plan, self.source, self.database, self.assets)
        self.assertEqual(read_state(self.database), {})
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM runs").fetchone()[0], 0)

    def test_workspace_export_keeps_relationships_and_exact_bytes(self):
        self.apply()
        export = self.root / "export"
        result = export_workspace(self.database, self.assets, export)
        self.assertEqual((result["records"], result["attachments"]), (5, 1))
        manifest = json.loads((export / "MANIFEST.json").read_text())
        for name, meta in manifest.items():
            raw = (export / name).read_bytes()
            self.assertEqual((digest(raw), len(raw)), (meta["sha256"], meta["bytes"]))
        task = json.loads((export / "tasks.json").read_text())[0]
        self.assertIn(task["data"]["customer_id"], {r["id"] for r in json.loads((export / "customers.json").read_text())})
        with self.assertRaisesRegex(MigrationError, "existing exports"):
            export_workspace(self.database, self.assets, export)

    def test_corrupt_asset_export_leaves_no_partial_export(self):
        self.apply()
        next(self.assets.iterdir()).write_bytes(b"corrupted")
        output = self.root / "export"
        with self.assertRaisesRegex(MigrationError, "Attachment hash"):
            export_workspace(self.database, self.assets, output)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.root.glob(".export-*")))

    def test_non_ascii_customer_and_binary_attachment_are_preserved(self):
        self.change("customers.csv", "Example Workshop", "Taller Ñandú 東京")
        raw = b"\x00\x01\xff\xfe\x00binary attachment\r\n"
        (self.source / "files/work-order.txt").write_bytes(raw)
        self.apply()
        self.assertEqual(read_state(self.database)[self.customer()]["data"]["name"], "Taller Ñandú 東京")
        self.assertEqual((self.assets / digest(raw)).read_bytes(), raw)

    def test_live_http_read_edit_download_and_export(self):
        self.apply()
        server = server_for(self.database, self.assets, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: thread.join(timeout=2))
        self.addCleanup(server.shutdown)
        conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(conn.close)

        def request(method, path, body=None, content_type="application/json"):
            conn.request(method, path, body=body, headers={"Content-Type": content_type} if body else {})
            response = conn.getresponse()
            return response.status, response.read(), response.getheaders()

        status, html, _ = request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Migration Desk", html)
        status, rows, _ = request("GET", "/api/records")
        self.assertEqual(len(json.loads(rows)), 5)
        body = json.dumps({"id": self.task(), "revision": 1, "fields": {"status": "done"}})
        status, output, _ = request("POST", "/api/edit", body)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(output)["data"]["status"], "done")
        self.assertEqual(request("POST", "/api/edit", body)[0], 409)
        self.assertEqual(request("POST", "/api/edit", "status=done", "application/x-www-form-urlencoded")[0], 415)
        asset = next(r for r in read_state(self.database).values() if r["kind"] == "attachments")
        status, raw, headers = request("GET", "/files/" + asset["id"])
        self.assertEqual(status, 200)
        self.assertEqual(digest(raw), asset["data"]["sha256"])
        self.assertTrue(dict(headers)["Content-Disposition"].startswith("attachment;"))
        status, bundle, _ = request("POST", "/api/export", "{}")
        self.assertEqual(status, 200)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            self.assertIn("MANIFEST.json", archive.namelist())
            tasks = json.loads(archive.read("tasks.json"))
            self.assertEqual(next(r for r in tasks if r["id"] == self.task())["data"]["status"], "done")
        status, runs, _ = request("GET", "/api/runs")
        self.assertEqual(json.loads(runs)[0]["operation"], "import-001")


if __name__ == "__main__":
    unittest.main(verbosity=2)
