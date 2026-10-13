"""Synthetic real-SQLite/loopback-HTTP consumer regressions for PO reuse.

No browser automation, external network, accounting posting or draft sending.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import http.client
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile

import desk
from test_purchasing_po_reuse import INVOICE, PO


def csv_bytes(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def payload(*, duplicate=True, request_id="synthetic-create"):
    rows = [{**INVOICE}]
    if duplicate:
        rows.append({**INVOICE, "invoice_number": "INV-B"})
    data = {
        "vendors": csv_bytes([{"supplier_id": "SUP-1", "canonical_name": "Acme", "aliases": "Acme Industrial"}]),
        "purchase_orders": csv_bytes([PO]),
        "invoices": csv_bytes(rows),
    }
    return {"title": "Synthetic PO reuse acceptance", "request_id": request_id,
            "sources": {kind: {"name": kind + ".csv", "data": base64.b64encode(raw).decode("ascii")}
                        for kind, raw in data.items()}, "draft_edits": {}, "attachments": []}


class DeskPOReuseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.database = Path(self.tmp.name) / "workspace.sqlite3"
        self.store = desk.Store(self.database)

    def assert_held(self, packet):
        self.assertEqual([], packet["accounting"])
        self.assertEqual(2, len(packet["drafts"]))
        self.assertEqual(0, packet["report"]["summary"]["matched_lines"])
        for draft in packet["drafts"]:
            self.assertEqual("DRAFT_NOT_SENT", draft["status"])
            self.assertIn("po_line_reused_in_batch:count=2", draft["issues"])
            self.assertEqual(64, len(draft["basis_sha256"]))

    def test_prepare_uses_repaired_engine_without_adapter_changes(self):
        self.assert_held(desk.prepare(payload()))

    def test_new_packet_survives_sqlite_reopen(self):
        saved = self.store.save(payload())
        reopened = desk.Store(self.database).get(saved["id"])
        self.assertEqual(saved, reopened)
        self.assert_held(reopened)

    def test_draft_edit_and_retry_remain_unsent_and_idempotent(self):
        saved = self.store.save(payload())
        self.assert_held(saved)
        edit = payload(request_id="synthetic-edit")
        edit["expected_revision"] = 1
        edit["draft_edits"] = {saved["drafts"][0]["basis_sha256"]:
                               {"subject": "Review both source invoices", "body": "Synthetic internal edit."}}
        updated = self.store.save(edit, saved["id"])
        retry = self.store.save(edit, saved["id"])
        self.assertEqual(updated, retry)
        self.assertEqual(2, updated["revision"])
        self.assertTrue(updated["drafts"][0]["edited"])
        self.assertFalse(updated["drafts"][1]["edited"])
        self.assert_held(updated)

    def test_corrected_revision_releases_one_row_preserving_history(self):
        first = self.store.save(payload())
        self.assert_held(first)
        corrected = payload(duplicate=False, request_id="synthetic-correct")
        corrected["expected_revision"] = 1
        corrected["draft_edits"] = {first["drafts"][0]["basis_sha256"]:
                                    {"subject": "Old issue", "body": "Do not carry to corrected source."}}
        second = self.store.save(corrected, first["id"])
        self.assertEqual(2, second["revision"])
        self.assertEqual(1, len(second["accounting"]))
        self.assertEqual("50.00", second["accounting"][0]["line_total"])
        self.assertEqual([], second["drafts"])
        self.assertEqual([first["drafts"][0]["basis_sha256"]], second["discarded_stale_edits"])
        historical = self.store.get(first["id"], 1)
        self.assert_held(historical)
        self.assertEqual(first["sources"], historical["sources"])
        self.assertEqual(2, historical["current_revision"])

    def test_bundle_has_no_duplicate_accounting_rows_and_exact_source_bytes(self):
        supplied = payload()
        packet = self.store.save(supplied)
        self.assert_held(packet)
        with zipfile.ZipFile(io.BytesIO(desk.bundle(packet))) as archive:
            rows = list(csv.DictReader(io.StringIO(archive.read("accounting_import.csv").decode())))
            self.assertEqual([], rows)
            self.assertEqual(2, len(json.loads(archive.read("exception_drafts.json"))["drafts"]))
            for item in json.loads(archive.read("manifest.json"))["files"]:
                raw = archive.read(item["path"])
                self.assertEqual(item["bytes"], len(raw))
                self.assertEqual(item["sha256"], hashlib.sha256(raw).hexdigest())
            for kind, item in supplied["sources"].items():
                self.assertEqual(base64.b64decode(item["data"]), archive.read("sources/" + kind + ".csv"))

    def test_loopback_http_create_reopen_source_csv_and_bundle(self):
        server = desk.make_server(self.store, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def cleanup():
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
        self.addCleanup(cleanup)
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        self.addCleanup(connection.close)
        supplied = payload()
        connection.request("POST", "/api/packets", json.dumps(supplied), {"Content-Type": "application/json"})
        response = connection.getresponse()
        self.assertEqual(200, response.status)
        packet = json.loads(response.read())
        self.assert_held(packet)
        for suffix in ("", "/accounting.csv", "/bundle", "/sources/invoices"):
            connection.request("GET", "/api/packets/" + packet["id"] + suffix)
            response = connection.getresponse()
            self.assertEqual(200, response.status)
            self.assertEqual("no-store", response.getheader("Cache-Control"))
            raw = response.read()
            if not suffix:
                self.assert_held(json.loads(raw))
            elif suffix == "/accounting.csv":
                self.assertEqual([], list(csv.DictReader(io.StringIO(raw.decode()))))
            elif suffix == "/bundle":
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    self.assertEqual(2, json.loads(archive.read("reconciliation.json"))["summary"]["exception_lines"])
            else:
                self.assertEqual(base64.b64decode(supplied["sources"]["invoices"]["data"]), raw)

    def test_stale_revision_does_not_overwrite_corrected_result(self):
        first = self.store.save(payload())
        corrected = payload(duplicate=False, request_id="synthetic-correct")
        corrected["expected_revision"] = 1
        second = self.store.save(corrected, first["id"])
        stale = payload(request_id="synthetic-stale")
        stale["expected_revision"] = 1
        with self.assertRaises(desk.DeskError) as result:
            self.store.save(stale, first["id"])
        self.assertEqual(409, result.exception.status)
        self.assertEqual(second, self.store.get(first["id"]))

    def test_unrelated_saved_packets_do_not_become_cross_batch_ledger(self):
        one = self.store.save(payload(duplicate=False, request_id="synthetic-one"))
        two = self.store.save(payload(duplicate=False, request_id="synthetic-two"))
        self.assertNotEqual(one["id"], two["id"])
        self.assertEqual(1, len(one["accounting"]))
        self.assertEqual(1, len(two["accounting"]))

    def test_exact_old_retry_returns_historical_revision_not_new_head(self):
        original = payload()
        first = self.store.save(original)
        self.assert_held(first)
        corrected = payload(duplicate=False, request_id="synthetic-correct")
        corrected["expected_revision"] = 1
        second = self.store.save(corrected, first["id"])
        replay = self.store.save(original)
        self.assertEqual(1, replay["revision"])
        self.assertEqual(2, replay["current_revision"])
        self.assert_held(replay)
        self.assertEqual(second, self.store.get(first["id"]))


if __name__ == "__main__":
    unittest.main()
