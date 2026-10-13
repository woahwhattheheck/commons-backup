"""Real matcher, SQLite, export and HTTP coverage for the browser consumer."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import copy
import csv
from decimal import Decimal
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

import desk


def encoded(raw: bytes, name: str) -> dict:
    return {"name": name, "data": base64.b64encode(raw).decode("ascii")}


def sample() -> dict:
    return {"title": "Fictional sample", "sources": {
        kind: encoded((Path(__file__).parent / "examples" / f"{kind}.csv").read_bytes(), f"{kind}.csv")
        for kind in desk.KINDS}, "attachments": [], "draft_edits": {}}


def inputs(packet: dict) -> dict:
    return {key: copy.deepcopy(packet[key]) for key in ("title", "sources", "attachments", "draft_edits")}


def change_invoice(payload: dict, old: bytes, new: bytes) -> None:
    item = payload["sources"]["invoices"]
    payload["sources"]["invoices"] = encoded(base64.b64decode(item["data"]).replace(old, new), item["name"])


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "packets.sqlite3"
        self.store = desk.Store(self.database)

    def test_real_matching_and_review_totals(self):
        packet = self.store.save(sample())
        self.assertEqual(packet["revision"], 1)
        summary = packet["report"]["summary"]
        self.assertEqual((summary["invoice_lines"], summary["matched_lines"], summary["exception_lines"]), (3, 2, 1))
        self.assertEqual(sum(Decimal(row["line_total"]) for row in packet["accounting"]), Decimal("74.00"))
        self.assertEqual(summary["accounting_rows_posted"], 0)
        self.assertEqual(summary["drafts_sent"], 0)
        self.assertEqual(packet["drafts"][0]["status"], "DRAFT_NOT_SENT")
        self.assertEqual(packet["drafts"][0]["issues"], ["quantity_mismatch:invoice=3,po=2"])

    def test_database_reopen_keeps_exact_packet(self):
        packet = self.store.save(sample())
        self.assertEqual(desk.Store(self.database).get(packet["id"]), packet)
        self.assertEqual(self.store.list()[0]["id"], packet["id"])

    def test_source_links_hashes_and_original_bytes(self):
        payload = sample()
        original = b"\xef\xbb\xbf" + base64.b64decode(payload["sources"]["vendors"]["data"]).replace(b"\n", b"\r\n")
        payload["sources"]["vendors"] = encoded(original, "Original vendor directory.csv")
        packet = self.store.save(payload)
        item = packet["sources"]["vendors"]
        self.assertEqual(base64.b64decode(item["data"]), original)
        self.assertEqual(item["sha256"], desk.sha(original))
        self.assertEqual(packet["report"]["sources"]["vendors"], {"path": "sources/vendors.csv", "sha256": desk.sha(original)})
        self.assertEqual(packet["report"]["records"][1]["invoice_source"]["line"], 3)

    def test_bundle_contains_linked_originals_and_exact_accounting(self):
        payload = sample()
        raw = b"fictional original bytes\x00\xff\n"
        payload["attachments"] = [encoded(raw, "../../original.bin")]
        packet = self.store.save(payload)
        with zipfile.ZipFile(io.BytesIO(desk.bundle(packet))) as archive:
            self.assertEqual(archive.read("attachments/01.bin"), raw)
            self.assertFalse(any(".." in path for path in archive.namelist()))
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["files"][-1]["name"], "../../original.bin")
            for item in manifest["files"]:
                self.assertEqual(desk.sha(archive.read(item["path"])), item["sha256"])
            self.assertEqual(archive.read("accounting_import.csv"), desk.accounting_csv(packet))
            self.assertEqual(json.loads(archive.read("reconciliation.json")), packet["report"])
            rows = list(csv.DictReader(io.StringIO(archive.read("accounting_import.csv").decode())))
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["status"] == "REVIEW_READY_NOT_POSTED" for row in rows))

    def test_attachment_extension_is_preserved_without_paths(self):
        payload = sample()
        payload["attachments"] = [encoded(b"original text", "../folder/Invoice.TXT"), encoded(b"original", "no extension")]
        packet = self.store.save(payload)
        self.assertEqual([item["path"] for item in packet["attachments"]], ["attachments/01.txt", "attachments/02.bin"])

    def test_edit_unsent_draft_then_reopen(self):
        packet = self.store.save(sample())
        payload = inputs(packet)
        key = packet["drafts"][0]["basis_sha256"]
        payload["draft_edits"][key] = {"subject": "Please confirm quantity", "body": "Our PO lists two belts; please confirm the third."}
        payload["expected_revision"] = 1
        revised = self.store.save(payload, packet["id"])
        self.assertEqual(revised["revision"], 2)
        self.assertEqual(revised["drafts"][0]["subject"], "Please confirm quantity")
        self.assertTrue(revised["drafts"][0]["edited"])
        self.assertEqual(self.store.get(packet["id"])["drafts"], revised["drafts"])
        self.assertFalse(self.store.get(packet["id"], 1)["drafts"][0]["edited"])

    def test_changed_issue_resets_old_draft(self):
        first = self.store.save(sample())
        payload = inputs(first)
        key = first["drafts"][0]["basis_sha256"]
        payload["draft_edits"][key] = {"subject": "old quantity", "body": "three belts"}
        change_invoice(payload, b"Belt B,3,20.00", b"Belt B,4,20.00")
        payload["expected_revision"] = 1
        updated = self.store.save(payload, first["id"])
        self.assertFalse(updated["drafts"][0]["edited"])
        self.assertIn("invoice=4", updated["drafts"][0]["body"])
        self.assertEqual(updated["discarded_stale_edits"], [key])

    def test_corrected_invoice_resolves_exception_in_new_revision(self):
        first = self.store.save(sample())
        payload = inputs(first)
        change_invoice(payload, b"Belt B,3,20.00", b"Belt B,2,20.00")
        payload["expected_revision"] = 1
        second = self.store.save(payload, first["id"])
        self.assertEqual(second["report"]["summary"]["matched_lines"], 3)
        self.assertEqual(second["drafts"], [])
        self.assertEqual(self.store.get(first["id"], 1)["report"]["summary"]["exception_lines"], 1)
        self.assertNotEqual(first["sources"]["invoices"]["sha256"], second["sources"]["invoices"]["sha256"])

    def test_idempotent_create_retry_after_reopen(self):
        payload = sample()
        payload["request_id"] = "create-1"
        first = self.store.save(payload)
        self.assertEqual(desk.Store(self.database).save(payload), first)
        self.assertEqual(len(self.store.list()), 1)

    def test_idempotent_update_retry_after_newer_revision(self):
        first = self.store.save(sample())
        payload = inputs(first)
        payload.update(expected_revision=1, request_id="edit-1", title="Edited")
        second = self.store.save(payload, first["id"])
        third_input = inputs(second)
        third_input.update(expected_revision=2, title="Third")
        self.store.save(third_input, first["id"])
        retry = self.store.save(payload, first["id"])
        self.assertEqual(retry["revision"], 2)
        self.assertEqual(retry["current_revision"], 3)
        self.assertEqual(retry["title"], "Edited")

    def test_different_input_cannot_reuse_request_id(self):
        payload = sample()
        payload["request_id"] = "once"
        self.store.save(payload)
        payload["title"] = "changed"
        with self.assertRaises(desk.DeskError) as raised:
            self.store.save(payload)
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(len(self.store.list()), 1)

    def test_stale_revision_does_not_overwrite(self):
        first = self.store.save(sample())
        payload = inputs(first)
        payload.update(expected_revision=1, title="One tab")
        self.store.save(payload, first["id"])
        payload["title"] = "Other tab"
        with self.assertRaises(desk.DeskError) as raised:
            self.store.save(payload, first["id"])
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(self.store.get(first["id"])["title"], "One tab")

    def test_concurrent_update_has_one_winner(self):
        first = self.store.save(sample())
        def save(label):
            payload = inputs(first)
            payload.update(expected_revision=1, title=label)
            try:
                return self.store.save(payload, first["id"])["revision"]
            except desk.DeskError as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = sorted(pool.map(save, ["Left", "Right"]))
        self.assertEqual(results, [2, 409])

    def test_invalid_csv_shapes_leave_no_saved_record(self):
        for raw in [b"a,a\n1,2\n", b"a,b\n1,2,3\n", b"a,b\n1\n", b"a,b\n\"unterminated", b"a,b\n1,\xff\n", b"a,b\n1,\x00\n"]:
            with self.subTest(raw=raw):
                payload = sample()
                payload["sources"]["invoices"] = encoded(raw, "bad.csv")
                with self.assertRaises(desk.DeskError):
                    self.store.save(payload)
                self.assertEqual(self.store.list(), [])

    def test_missing_required_columns_report_diagnostic(self):
        payload = sample()
        payload["sources"]["invoices"] = encoded(b"invoice_number\nINV-1\n", "missing.csv")
        with self.assertRaisesRegex(desk.DeskError, "missing columns"):
            self.store.save(payload)

    def test_shape_and_file_bounds(self):
        for update in [{"title": []}, {"sources": []}, {"attachments": {}}, {"draft_edits": []}]:
            payload = sample()
            payload.update(update)
            with self.subTest(update=update), self.assertRaises(desk.DeskError):
                self.store.save(payload)
        payload = sample()
        payload["sources"]["vendors"]["data"] = "not base64!"
        with self.assertRaisesRegex(desk.DeskError, "base64"):
            self.store.save(payload)
        with self.assertRaises(desk.DeskError):
            desk.file_record(encoded(b"x" * (desk.MAX_FILE + 1), "large.bin"), "file")

    def test_boolean_revision_and_missing_packet(self):
        first = self.store.save(sample())
        payload = inputs(first)
        payload["expected_revision"] = True
        with self.assertRaisesRegex(desk.DeskError, "positive integer"):
            self.store.save(payload, first["id"])
        with self.assertRaises(desk.DeskError) as raised:
            self.store.get("absent")
        self.assertEqual(raised.exception.status, 404)

    def test_invalid_update_preserves_prior_snapshot(self):
        first = self.store.save(sample())
        payload = inputs(first)
        change_invoice(payload, b"Belt B,3,20.00", b"Belt B,NaN,20.00")
        payload["expected_revision"] = 1
        with self.assertRaises(desk.DeskError):
            self.store.save(payload, first["id"])
        self.assertEqual(self.store.get(first["id"]), first)

    def test_nonfinite_json_is_rejected(self):
        payload = sample()
        payload["extra"] = float("nan")
        with self.assertRaisesRegex(desk.DeskError, "JSON values"):
            self.store.save(payload)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = desk.Store(Path(self.temp.name) / "packets.sqlite3")
        self.server = desk.make_server(self.store, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)
        self.temp.cleanup()

    def request(self, path, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        req = Request(self.base + path, data=body, headers={"Content-Type": "application/json"})
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, response.read(), response.headers

    def test_complete_http_save_reopen_download(self):
        status, raw, _ = self.request("/api/packets", sample())
        self.assertEqual(status, 200)
        packet = json.loads(raw)
        path = "/api/packets/" + packet["id"]
        status, raw, _ = self.request(path)
        self.assertEqual(json.loads(raw), packet)
        status, raw, headers = self.request(path + "/bundle?revision=1")
        self.assertEqual((status, headers["Content-Type"]), (200, "application/zip"))
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertIn("sources/invoices.csv", archive.namelist())
        status, raw, _ = self.request(path + "/sources/invoices?revision=1")
        self.assertEqual(raw, base64.b64decode(packet["sources"]["invoices"]["data"]))
        self.assertEqual(self.request(path + "/accounting.csv")[1], desk.accounting_csv(packet))

    def test_http_revision_conflict_and_history(self):
        first = json.loads(self.request("/api/packets", sample())[1])
        path = "/api/packets/" + first["id"]
        payload = inputs(first)
        payload.update(expected_revision=1, title="Revision two")
        self.assertEqual(self.request(path, payload)[0], 200)
        self.assertEqual(self.request(path, payload)[0], 409)
        historic = json.loads(self.request(path + "?revision=1")[1])
        self.assertEqual((historic["revision"], historic["current_revision"]), (1, 2))
        self.assertEqual(self.request(path + "?revision=-1")[0], 422)
        self.assertEqual(self.request(path + "?revision=")[0], 422)

    def test_http_example_and_html_shell(self):
        status, raw, _ = self.request("/api/example")
        self.assertEqual(status, 200)
        self.assertEqual(set(json.loads(raw)["sources"]), set(desk.KINDS))
        status, raw, headers = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        class Parser(HTMLParser):
            def __init__(self):
                super().__init__(); self.ids = []
            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                if "id" in values: self.ids.append(values["id"])
        parser = Parser()
        parser.feed(raw.decode())
        self.assertEqual(len(parser.ids), len(set(parser.ids)))
        for ident in ("save", "records", "drafts", "bundle", "saved", "revision"):
            self.assertIn(ident, parser.ids)

    def test_http_errors_are_structured(self):
        self.assertEqual(self.request("/api/unknown")[0], 404)
        self.assertEqual(self.request("/api/packets", [1])[0], 422)
        req = Request(self.base + "/api/packets", data=b"{", headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as raised:
            urlopen(req, timeout=5)
        with raised.exception as response:
            self.assertEqual(response.code, 400)
            self.assertIn("error", json.loads(response.read()))


if __name__ == "__main__":
    unittest.main()
