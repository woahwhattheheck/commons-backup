"""Exercise file intake against the real canonical Desk, not a replacement store."""
import contextlib
import copy
import csv
import io
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.request import Request, urlopen

from catalog_file import CatalogFileError, parse_bytes
from catalog_intake import PROVENANCE_LABEL, main, prepare_import
from parts_desk import Desk, catalog_data, make_server


def row(**changes):
    data = {"id": "DEMO-SKU-0007", "supplier": "Synthetic supplier", "supplier_sku": "0007",
            "part_number": "000070", "make": "ExampleCo", "model": "DEMO-M1",
            "description": "Synthetic pump example; not a real fit recommendation",
            "source_url": "https://example.invalid/catalog/demo-0007", "checked_on": "2026-09-08",
            "currency": "USD", "unit_price": "32.45", "shipping": "7.50",
            "stock_status": "unknown", "aliases": ["DEMO-P7"], "source_note": "Original supplier note"}
    return {**data, **changes}


def parsed(*rows, name="supplier.json"):
    return parse_bytes(json.dumps(list(rows), ensure_ascii=False).encode(), name)


class CatalogIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dbpath = self.root / "desk.sqlite3"
        self.desk = Desk(self.dbpath)

    def test_payload_uses_canonical_schema_and_preserves_extra_evidence(self):
        source = parsed(row(vendor_extension={"shelf": "A07"}))
        before = copy.deepcopy(source.document())
        preview = prepare_import(source)
        item = preview["payload"]["items"][0]
        self.assertEqual(item, catalog_data(item))
        self.assertEqual(item["part_number"], "000070")
        self.assertEqual(item["unit_price"], "32.45")
        self.assertTrue(item["source_note"].startswith("Original supplier note\n"))
        evidence = json.loads(item["source_note"].split(PROVENANCE_LABEL, 1)[1])
        self.assertEqual(evidence["extra_fields"], {"vendor_extension": {"shelf": "A07"}})
        self.assertEqual(evidence["sha256"], source.source["sha256"])
        self.assertEqual(evidence["json_pointer"], "/0")
        self.assertEqual(source.document(), before)
        self.assertFalse(preview["applied"])
        self.assertEqual(preview["compatibility"], "not_inferred")

    def test_mapped_csv_import_real_desk_and_unknown_values(self):
        raw = b'SKU,Part,Text,Price,Notes\r\n0007,000070,"Pump, example",,"first\nsecond"\r\n'
        defaults = row(unit_price="", shipping="", aliases="DEMO-P7;DEMO-P8")
        for key in ("supplier_sku", "part_number", "description", "unit_price", "source_note"):
            defaults.pop(key)
        preview = prepare_import(parse_bytes(raw, "supplier.csv"),
                                 {"SKU": "supplier_sku", "Part": "part_number", "Text": "description",
                                  "Price": "unit_price", "Notes": "source_note"}, defaults)
        self.assertEqual(self.desk.mutate("catalog", "", preview["payload"]), {"rows": 1, "changed": 1})
        actual = self.desk.catalog("DEMO-P8")[0]
        self.assertEqual(actual["supplier_sku"], "0007")
        self.assertIsNone(actual["unit_price"])
        self.assertIsNone(actual["shipping"])
        self.assertEqual(actual["match"], "exact part/alias")
        self.assertIn('"line_start":2', actual["source_note"])
        self.assertIn('"line_end":3', actual["source_note"])
        self.assertIn("first\nsecond", actual["source_note"])

    def test_invalid_later_row_applies_nothing(self):
        with self.assertRaisesRegex(CatalogFileError, "record 2.*checked_on"):
            prepare_import(parsed(row(), row(id="DEMO-2", checked_on="2026-02-30")))
        self.assertEqual(self.desk.state()["catalog_count"], 0)
        self.assertEqual(self.desk.export()["tables"]["operations"], [])

    def test_duplicate_normalized_ids_are_visible(self):
        with self.assertRaisesRegex(CatalogFileError, "record 2: duplicate catalog id"):
            prepare_import(parsed(row(), row(id=" DEMO-SKU-0007 ")))

    def test_required_observations_and_identifiers_are_never_inferred(self):
        for field in ("id", "checked_on", "currency", "source_url"):
            data = row()
            data.pop(field)
            with self.subTest(field=field), self.assertRaisesRegex(CatalogFileError, field):
                prepare_import(parsed(data))
        with self.assertRaisesRegex(CatalogFileError, "part_number must be text"):
            prepare_import(parsed(row(part_number=70)))

    def test_exact_retry_after_restart_retains_one_operation_and_version(self):
        payload = prepare_import(parsed(row()))["payload"]
        first = self.desk.mutate("catalog", "", payload)
        restored = Desk(self.dbpath)
        self.assertEqual(restored.mutate("catalog", "", payload), first)
        self.assertEqual(restored.catalog()[0]["version"], 1)
        self.assertEqual(len(restored.export()["tables"]["operations"]), 1)

    def test_changed_file_marks_review_stale_and_old_retry_cannot_roll_back(self):
        old = prepare_import(parsed(row()))["payload"]
        self.desk.mutate("catalog", "", old)
        req = self.desk.mutate("request", "", {"operation_id": "create-job", "data": {
            "job_ref": "DEMO-JOB", "make": "ExampleCo", "model": "DEMO-M1",
            "description": "Synthetic integration example", "quantity": 3}})
        req = self.desk.mutate("option", req["id"], {"operation_id": "add-option", "revision": req["revision"],
                                                    "catalog_id": "DEMO-SKU-0007"})
        oid = req["options"][0]["id"]
        req = self.desk.mutate("review", oid, {"operation_id": "review-option", "revision": req["revision"],
                                             "fit": "compatible", "technician": "Synthetic test operator",
                                             "note": "Synthetic-only review"})
        self.assertEqual(req["options"][0]["effective_fit"], "compatible")
        newer = prepare_import(parsed(row(unit_price="33.00")))["payload"]
        self.assertNotEqual(newer["operation_id"], old["operation_id"])
        self.desk.mutate("catalog", "", newer)
        self.desk.mutate("catalog", "", old)
        self.assertEqual(self.desk.catalog()[0]["unit_price"], "33.00")
        self.assertEqual(self.desk.catalog()[0]["version"], 2)
        current = self.desk.request(req["id"])["options"][0]
        self.assertEqual(current["effective_fit"], "stale")
        self.assertEqual(current["snapshot"]["unit_price"], "32.45")
        self.assertIn(old["items"][0]["source_note"], current["snapshot"]["source_note"])

    def test_concurrent_same_payload_uses_existing_transaction_deduplication(self):
        payload = prepare_import(parsed(row()))["payload"]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.desk.mutate("catalog", "", payload), range(16)))
        self.assertEqual(results, [{"rows": 1, "changed": 1}] * 16)
        self.assertEqual(self.desk.catalog()[0]["version"], 1)
        self.assertEqual(len(self.desk.export()["tables"]["operations"]), 1)

    def test_original_filename_or_explicit_defaults_change_operation_id(self):
        first = prepare_import(parsed(row()))["payload"]
        renamed = prepare_import(parsed(row(), name="other.json"))["payload"]
        alternate = prepare_import(parsed(row()), defaults={"serial_scope": "Explicit range"})["payload"]
        self.assertNotEqual(first["operation_id"], renamed["operation_id"])
        self.assertNotEqual(first["operation_id"], alternate["operation_id"])
        self.assertEqual(first, prepare_import(parsed(row()))["payload"])

    def test_existing_http_import_road_consumes_payload_and_exports_handoff(self):
        server = make_server(self.desk, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            def post(path, body):
                request = Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
                with urlopen(request, timeout=5) as response:
                    return json.load(response)
            preview = prepare_import(parsed(row()))
            self.assertEqual(post("/api/catalog/import", preview["payload"]), {"rows": 1, "changed": 1})
            req = post("/api/requests", {"operation_id": "http-job", "data": {"job_ref": "HTTP-DEMO",
                "make": "ExampleCo", "model": "DEMO-M1", "description": "Synthetic pump", "quantity": 3}})
            req = post(f"/api/requests/{req['id']}/options", {"operation_id": "http-option",
                "revision": req["revision"], "catalog_id": "DEMO-SKU-0007"})
            req = post(f"/api/requests/{req['id']}/orders", {"operation_id": "http-draft", "revision": req["revision"],
                "option_id": req["options"][0]["id"]})
            order = req["orders"][0]
            self.assertEqual(order["status"], "draft")
            self.assertEqual(order["document"]["subtotal"], "97.35")
            self.assertEqual(order["document"]["total_before_tax"], "104.85")
            with urlopen(base + f"/api/orders/{order['id']}/handoff.txt", timeout=5) as response:
                handoff = response.read().decode()
            self.assertIn(preview["source"]["sha256"], handoff)
            self.assertIn("Original supplier note", handoff)
            self.assertIn("Fit when drafted: unreviewed", handoff)
            self.assertIn("https://example.invalid/catalog/demo-0007", handoff)
            self.assertIn("has not contacted a supplier", handoff)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_canonical_row_and_http_payload_bounds(self):
        source = parsed(*(row(id=f"DEMO-{i}") for i in range(2001)))
        with self.assertRaisesRegex(CatalogFileError, "1-2000"):
            prepare_import(source)
        source = parsed(*(row(id=f"DEMO-{i}", description="x" * 4000) for i in range(500)))
        with self.assertRaisesRegex(CatalogFileError, "body limit"):
            prepare_import(source)

    def test_provenance_never_silently_truncates_note(self):
        with self.assertRaisesRegex(CatalogFileError, "source_note is too long"):
            prepare_import(parsed(row(source_note="x" * 3990)))
        self.assertEqual(self.desk.state()["catalog_count"], 0)

    def test_cli_preview_and_actual_apply_subprocess_roundtrip(self):
        source = self.root / "supplier.json"
        source.write_text(json.dumps([row()]))
        output = self.root / "preview.json"
        command = [sys.executable, str(Path(__file__).with_name("catalog_intake.py")), str(source)]
        result = subprocess.run(command + ["--output", str(output)], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, "")
        self.assertEqual(self.desk.state()["catalog_count"], 0)
        preview = json.loads(output.read_text())
        result = subprocess.run(command + ["--apply", "--db", str(self.dbpath)], capture_output=True, text=True, check=True)
        receipt = json.loads(result.stdout)
        self.assertTrue(receipt["applied"])
        self.assertEqual(receipt["operation_id"], preview["payload"]["operation_id"])
        self.assertEqual(receipt["result"], {"rows": 1, "changed": 1})
        second = subprocess.run(command + ["--apply", "--db", str(self.dbpath)], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(second.stdout), receipt)
        self.assertEqual(self.desk.catalog()[0]["version"], 1)

    def test_cli_existing_preview_or_missing_database_leaves_data_unchanged(self):
        source = self.root / "supplier.json"
        source.write_text(json.dumps([row()]))
        output = self.root / "preview.json"
        output.write_text("KEEP THIS FILE")
        for extra in (["--output", str(output), "--apply", "--db", str(self.dbpath)],
                      ["--apply", "--db", str(self.root / "absent.sqlite3")], ["--db", str(self.dbpath)]):
            with self.subTest(extra=extra), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                main([str(source), *extra])
            self.assertEqual(exc.exception.code, 2)
        self.assertEqual(output.read_text(), "KEEP THIS FILE")
        self.assertFalse((self.root / "absent.sqlite3").exists())
        self.assertEqual(self.desk.state()["catalog_count"], 0)

    def test_cli_configuration_ambiguities_are_errors(self):
        source = self.root / "supplier.json"
        source.write_text(json.dumps([row()]))
        config = self.root / "mapping.json"
        for value in ('[]', '{"id":"id","id":"part_number"}', '{"id":NaN}'):
            config.write_text(value)
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                main([str(source), "--mapping", str(config)])
            self.assertEqual(exc.exception.code, 2)
        self.assertEqual(self.desk.state()["catalog_count"], 0)


if __name__ == "__main__":
    unittest.main()
