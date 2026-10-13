"""Real SQLite, transaction, HTTP and restart tests for Parts Sourcing Desk."""
import copy
import csv
import io
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from parts_desk import Desk, DeskError, catalog_data, cents, make_server, request_data


def item(**changes):
    result = dict(id="CAT-001", supplier="Fictitious Supplier", supplier_sku="S-100", make="DemoWorks", model="P-1",
                  part_number="P100", aliases=["OLD100"], serial_scope="Serial 1–10: synthetic example",
                  description="Fictitious filter", unit_price="12.50", shipping="4.00", currency="USD",
                  stock_status="in_stock", stock_qty=8, checked_on="2026-09-08", lead_time="Example only",
                  source_url="https://example.invalid/catalog", source_note="Synthetic test reference")
    result.update(changes)
    return result


def job(**changes):
    result = dict(job_ref="JOB-001", make="DemoWorks", model="P-1", serial="6", part_number="OLD100",
                  description="Replace filter", quantity=2, notes="Fictitious workshop")
    result.update(changes)
    return result


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "desk.sqlite3"
        self.desk = Desk(self.path)

    def mutate(self, operation, identity="", **body):
        return self.desk.mutate(operation, identity, {"operation_id": uuid.uuid4().hex, **body})

    def populated(self, fit=False):
        self.mutate("catalog", items=[item()])
        req = self.mutate("request", data=job())
        req = self.mutate("option", req["id"], revision=req["revision"], catalog_id="CAT-001")
        if fit:
            req = self.mutate("review", req["options"][0]["id"], revision=req["revision"], fit="compatible",
                              technician="Demo Technician", note="Synthetic manual: page 4, serial 6")
        return req

    def draft(self, fit=True):
        req = self.populated(fit)
        return self.mutate("draft", req["id"], revision=req["revision"], option_id=req["options"][0]["id"])


class DeskCase(FixtureCase):
    def test_full_manual_workflow_restart_handoff(self):
        req = self.draft()
        order = req["orders"][0]
        self.assertEqual(order["document"]["total_before_tax"], "29.00")
        req = self.mutate("order_edit", order["id"], revision=order["revision"], quantity=3, unit_price="12.25", shipping="0", notes="Collect at counter")
        order = req["orders"][0]
        self.assertEqual(order["document"]["total_before_tax"], "36.75")
        req = self.mutate("placed", order["id"], revision=order["revision"], supplier_reference="DEMO-EXT-23")
        self.assertEqual(req["orders"][0]["status"], "placed")
        fresh = Desk(self.path)
        self.assertEqual(fresh.request(req["id"]), req)
        handoff = fresh.handoff(order["id"])
        for wanted in ("DEMO-EXT-23", "36.75", "https://example.invalid/catalog", "Demo Technician", "Collect at counter", "has not contacted a supplier"):
            self.assertIn(wanted, handoff)

    def test_alias_match_never_implies_fit(self):
        req = self.populated()
        found = self.desk.catalog("old100")
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["match"], "exact part/alias")
        self.assertEqual(req["options"][0]["effective_fit"], "unreviewed")

    def test_catalog_import_all_or_nothing(self):
        with self.assertRaises(DeskError):
            self.mutate("catalog", items=[item(), item(id="CAT-2", source_url="")])
        self.assertEqual(self.desk.catalog(), [])

    def test_catalog_identical_import_does_not_stale_review(self):
        req = self.populated(True)
        result = self.mutate("catalog", items=[item()])
        self.assertEqual(result["changed"], 0)
        self.assertEqual(self.desk.request(req["id"])["options"][0]["effective_fit"], "compatible")

    def test_catalog_update_stales_review_preserves_snapshot(self):
        req = self.populated(True)
        self.mutate("catalog", items=[item(unit_price="14.00")])
        changed = self.desk.request(req["id"])
        option = changed["options"][0]
        self.assertEqual(option["snapshot"]["unit_price"], "12.50")
        self.assertEqual(option["effective_fit"], "stale")
        with self.assertRaises(DeskError):
            self.mutate("review", option["id"], revision=changed["revision"], fit="compatible", technician="D", note="Old source")
        changed = self.mutate("refresh", option["id"], revision=changed["revision"])
        self.assertEqual(changed["options"][0]["snapshot"]["unit_price"], "14.00")
        self.assertEqual(changed["options"][0]["effective_fit"], "unreviewed")
        self.assertTrue(any(e["action"] == "option_review" for e in changed["events"]))

    def test_request_edit_stales_fit_but_keeps_review(self):
        req = self.populated(True)
        changed = self.mutate("request", req["id"], revision=req["revision"], data=job(serial="999"))
        self.assertEqual(changed["options"][0]["effective_fit"], "stale")
        self.assertEqual(changed["options"][0]["review"]["technician"], "Demo Technician")

    def test_other_option_does_not_stale_compatible_review(self):
        req = self.populated(True)
        self.mutate("catalog", items=[item(id="CAT-2")])
        req = self.mutate("option", req["id"], revision=req["revision"], catalog_id="CAT-2")
        self.assertEqual(req["options"][0]["effective_fit"], "compatible")

    def test_fit_review_requires_findings_and_technician(self):
        req = self.populated()
        for extra in ({"technician": "", "note": "Source checked"}, {"technician": "D", "note": ""}):
            with self.subTest(extra=extra), self.assertRaises(DeskError):
                self.mutate("review", req["options"][0]["id"], revision=req["revision"], fit="compatible", **extra)

    def test_uncertain_and_incompatible_survive_export(self):
        for fit in ("uncertain", "incompatible"):
            with self.subTest(fit=fit):
                req = self.populated() if fit == "uncertain" else self.desk.request(req["id"])
                req = self.mutate("review", req["options"][0]["id"], revision=req["revision"], fit=fit, technician="D", note="Serial range differs")
                self.assertEqual(req["options"][0]["effective_fit"], fit)
                saved = json.loads(self.desk.export()["tables"]["options"][0]["review"])
                self.assertEqual(saved["fit"], fit)

    def test_source_urls_are_references_not_script_urls(self):
        for url in ("javascript:alert(1)", "file:///tmp/catalog", "https://user:pass@example.com/p", "https://example.com/a b"):
            with self.subTest(url=url), self.assertRaises(DeskError):
                catalog_data(item(source_url=url))

    def test_dates_and_boolean_quantity_rejected(self):
        for day in ("2026-02-30", "20260908", "yesterday"):
            with self.subTest(day=day), self.assertRaises(DeskError):
                catalog_data(item(checked_on=day))
        with self.assertRaises(DeskError):
            request_data(job(quantity=True))

    def test_money_keeps_cents_exact_and_unknown_distinct(self):
        self.assertEqual(cents("0.01", "price"), 1)
        self.assertEqual(cents("12.10", "price"), 1210)
        self.assertEqual(cents("0", "price"), 0)
        self.assertIsNone(cents("", "price"))
        for value in (True, 0.1, "0.001", "-1", "NaN", "Infinity", "1e3"):
            with self.subTest(value=value), self.assertRaises(DeskError):
                cents(value, "price")

    def test_unknown_shipping_does_not_become_zero_total(self):
        req = self.draft()
        order = req["orders"][0]
        req = self.mutate("order_edit", order["id"], revision=order["revision"], shipping="")
        doc = req["orders"][0]["document"]
        self.assertEqual(doc["subtotal"], "25.00")
        self.assertIsNone(doc["total_before_tax"])
        self.assertIn("total cannot be calculated", " ".join(req["orders"][0]["warnings"]))

    def test_unknown_unit_price_remains_unknown(self):
        req = self.draft()
        order = req["orders"][0]
        req = self.mutate("order_edit", order["id"], revision=order["revision"], unit_price="")
        self.assertIsNone(req["orders"][0]["document"]["subtotal"])
        self.assertIsNone(req["orders"][0]["document"]["total_before_tax"])

    def test_stale_request_update_keeps_current_bytes(self):
        req = self.mutate("request", data=job())
        newer = self.mutate("request", req["id"], revision=req["revision"], data=job(notes="New note"))
        with self.assertRaises(DeskError) as error:
            self.mutate("request", req["id"], revision=req["revision"], data=job(notes="Stale note"))
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(self.desk.request(req["id"]), newer)

    def test_request_retry_returns_original_without_duplicate(self):
        body = {"operation_id": "repeat-create", "data": job()}
        first = self.desk.mutate("request", "", body)
        second = self.desk.mutate("request", "", body)
        self.assertEqual(first, second)
        self.assertEqual(len(self.desk.state()["requests"]), 1)

    def test_operation_id_cannot_represent_different_action(self):
        body = {"operation_id": "unique-action", "data": job()}
        self.desk.mutate("request", "", body)
        body["data"] = job(job_ref="OTHER")
        with self.assertRaises(DeskError) as error:
            self.desk.mutate("request", "", body)
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(len(self.desk.state()["requests"]), 1)

    def test_duplicate_job_reference_casefold(self):
        self.mutate("request", data=job())
        with self.assertRaises(DeskError):
            self.mutate("request", data=job(job_ref="job-001"))

    def test_duplicate_option_is_not_added(self):
        req = self.populated()
        with self.assertRaises(DeskError):
            self.mutate("option", req["id"], revision=req["revision"], catalog_id="CAT-001")
        self.assertEqual(len(self.desk.request(req["id"])["options"]), 1)

    def test_cross_job_option_not_used(self):
        req = self.populated()
        other = self.mutate("request", data=job(job_ref="OTHER"))
        with self.assertRaises(DeskError):
            self.mutate("draft", other["id"], revision=other["revision"], option_id=req["options"][0]["id"])
        self.assertEqual(self.desk.request(other["id"])["orders"], [])

    def test_one_active_order_even_with_new_operation_and_revision(self):
        req = self.draft()
        with self.assertRaises(DeskError) as error:
            self.mutate("draft", req["id"], revision=req["revision"], option_id=req["options"][0]["id"])
        self.assertEqual(error.exception.status, 409)
        self.assertEqual(len(self.desk.request(req["id"])["orders"]), 1)

    def test_concurrent_order_creation_has_one_winner(self):
        req = self.populated(True)
        barrier = threading.Barrier(2)
        def create():
            barrier.wait()
            try:
                self.mutate("draft", req["id"], revision=req["revision"], option_id=req["options"][0]["id"])
                return "created"
            except DeskError as exc:
                return exc.status
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: create(), range(2)))
        self.assertCountEqual(results, ["created", 409])
        self.assertEqual(len(self.desk.request(req["id"])["orders"]), 1)

    def test_concurrent_identical_retry_gets_same_order(self):
        req = self.populated(True)
        body = {"operation_id": "same-draft", "revision": req["revision"], "option_id": req["options"][0]["id"]}
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.desk.mutate("draft", req["id"], body), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.desk.request(req["id"])["orders"]), 1)

    def test_stale_order_edit_preserves_new_amount(self):
        req = self.draft()
        order = req["orders"][0]
        newer = self.mutate("order_edit", order["id"], revision=order["revision"], unit_price="11.00")
        with self.assertRaises(DeskError):
            self.mutate("order_edit", order["id"], revision=order["revision"], unit_price="8.00")
        self.assertEqual(self.desk.request(req["id"]), newer)

    def test_recorded_order_snapshot_not_repriced_by_catalog(self):
        req = self.draft()
        order = req["orders"][0]
        req = self.mutate("placed", order["id"], revision=order["revision"], supplier_reference="ACTUAL-EXAMPLE")
        original = copy.deepcopy(req["orders"][0]["document"])
        self.mutate("catalog", items=[item(unit_price="999.99", stock_status="out_of_stock")])
        fresh = self.desk.request(req["id"])["orders"][0]
        self.assertEqual(fresh["document"], original)
        self.assertIn("Catalog or option changed", " ".join(fresh["warnings"]))
        with self.assertRaises(DeskError):
            self.mutate("order_edit", order["id"], revision=fresh["revision"], quantity=8)

    def test_draft_cancel_permits_replacement_retains_history(self):
        req = self.draft()
        order = req["orders"][0]
        req = self.mutate("cancel", order["id"], revision=order["revision"], note="Need another source")
        req = self.mutate("draft", req["id"], revision=req["revision"], option_id=req["options"][0]["id"])
        self.assertEqual([o["status"] for o in req["orders"]], ["draft", "cancelled"])
        self.assertNotEqual(req["orders"][0]["id"], order["id"])

    def test_placed_cancel_needs_supplier_confirmation(self):
        req = self.draft()
        order = req["orders"][0]
        req = self.mutate("placed", order["id"], revision=order["revision"], supplier_reference="EXT-1")
        revision = req["orders"][0]["revision"]
        with self.assertRaises(DeskError):
            self.mutate("cancel", order["id"], revision=revision, note="Requested cancellation")
        self.assertEqual(self.desk.request(req["id"])["orders"][0]["status"], "placed")
        req = self.mutate("cancel", order["id"], revision=revision, note="Confirmed", supplier_confirmation="Supplier C-1")
        self.assertEqual(req["orders"][0]["status"], "cancelled")

    def test_record_order_requires_actual_reference(self):
        req = self.draft()
        order = req["orders"][0]
        with self.assertRaises(DeskError):
            self.mutate("placed", order["id"], revision=order["revision"], supplier_reference="")
        self.assertEqual(self.desk.request(req["id"])["orders"][0]["status"], "draft")

    def test_unreviewed_handoff_has_explicit_warning(self):
        req = self.draft(False)
        handoff = self.desk.handoff(req["orders"][0]["id"])
        self.assertIn("unreviewed", handoff)
        self.assertNotIn("Fit when drafted: compatible", handoff)

    def test_stock_shortage_is_visible(self):
        req = self.draft()
        order = req["orders"][0]
        req = self.mutate("order_edit", order["id"], revision=order["revision"], quantity=20)
        self.assertIn("below the requested quantity", " ".join(req["orders"][0]["warnings"]))

    def test_csv_import_quotes_unicode_bom_and_aliases(self):
        data = item(description='Fictitious filter, 10" — café', aliases="OLD100;LEGACY")
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=list(data))
        writer.writeheader(); writer.writerow(data)
        result = self.mutate("catalog", format="csv", content="\ufeff" + out.getvalue())
        self.assertEqual(result["changed"], 1)
        self.assertEqual(self.desk.catalog()[0]["description"], data["description"])
        self.assertEqual(self.desk.catalog()[0]["aliases"], ["OLD100", "LEGACY"])

    def test_duplicate_csv_columns_and_catalog_ids_rejected(self):
        with self.assertRaises(DeskError):
            self.mutate("catalog", format="csv", content="id,id\na,b\n")
        with self.assertRaises(DeskError):
            self.mutate("catalog", items=[item(), item()])
        self.assertEqual(self.desk.catalog(), [])

    def test_database_backup_reopens_with_exact_relationships(self):
        req = self.draft()
        restored_path = Path(self.tmp.name) / "restored.sqlite3"
        restored_path.write_bytes(self.desk.backup())
        restored = Desk(restored_path)
        self.assertEqual(restored.request(req["id"]), req)
        with restored.connect() as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_export_preserves_source_and_revisions(self):
        req = self.draft()
        result = self.desk.export()
        self.assertEqual(len(result["tables"]["requests"]), 1)
        self.assertEqual(result["tables"]["requests"][0]["revision"], req["revision"])
        self.assertEqual(json.loads(result["tables"]["catalog"][0]["document"])["source_url"], item()["source_url"])


class HTTPCase(FixtureCase):
    def setUp(self):
        super().setUp()
        self.server = make_server(self.desk, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)

    def http(self, path, body=None, raw=None, content_type="application/json"):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        request = urllib.request.Request(self.base + path, data=data, headers={"Content-Type": content_type})
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            return response.status, response.headers, response.read()

    def test_http_page_state_and_unknown_route(self):
        status, headers, body = self.http("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Parts Desk", body)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertEqual(self.http("/api/state")[0], 200)
        self.assertEqual(self.http("/unknown")[0], 404)

    def test_http_real_create_save_download(self):
        status, _, body = self.http("/api/requests", {"operation_id": "http-create", "data": job()})
        self.assertEqual(status, 200)
        req = json.loads(body)
        self.assertEqual(self.http("/api/requests/" + req["id"])[0], 200)
        self.assertEqual(self.http("/api/export")[0], 200)
        status, headers, backup = self.http("/api/backup")
        self.assertEqual(status, 200)
        self.assertTrue(backup.startswith(b"SQLite format 3"))
        self.assertIn("attachment", headers["Content-Disposition"])

    def test_http_validation_and_conflict(self):
        body = {"operation_id": "http-create", "data": job()}
        self.assertEqual(self.http("/api/requests", body)[0], 200)
        body["data"]["notes"] = "different"
        self.assertEqual(self.http("/api/requests", body)[0], 409)
        for raw in (b"not-json", b"[]", b'{"operation_id":"x","data":NaN}'):
            with self.subTest(raw=raw):
                self.assertEqual(self.http("/api/requests", raw=raw)[0], 400)
        self.assertEqual(self.http("/api/requests", raw=b"{}", content_type="text/plain")[0], 415)

    def test_http_complete_sourcing_to_order_flow(self):
        def post(path, **body):
            status, _, raw = self.http(path, {"operation_id": uuid.uuid4().hex, **body})
            self.assertEqual(status, 200, raw)
            return json.loads(raw)
        post("/api/catalog/import", items=[item()])
        req = post("/api/requests", data=job())
        rid = req["id"]
        req = post(f"/api/requests/{rid}/options", revision=req["revision"], catalog_id="CAT-001")
        opt = req["options"][0]["id"]
        req = post(f"/api/options/{opt}/review", revision=req["revision"], fit="compatible", technician="Test technician", note="Synthetic source and serial reviewed")
        req = post(f"/api/requests/{rid}/orders", revision=req["revision"], option_id=opt)
        order = req["orders"][0]
        req = post(f"/api/orders/{order['id']}", revision=order["revision"], unit_price="11.25", shipping="2.50", quantity=3)
        order = req["orders"][0]
        self.assertEqual(order["document"]["total_before_tax"], "36.25")
        req = post(f"/api/orders/{order['id']}/placed", revision=order["revision"], supplier_reference="SYNTHETIC-HTTP-1")
        self.assertEqual(req["orders"][0]["status"], "placed")
        status, _, handoff = self.http(f"/api/orders/{order['id']}/handoff.txt")
        self.assertEqual(status, 200)
        self.assertIn(b"SYNTHETIC-HTTP-1", handoff)
        self.assertIn(b"36.25", handoff)
        req = post(f"/api/orders/{order['id']}/cancel", revision=req["orders"][0]["revision"], note="Confirmed cancellation", supplier_confirmation="SYNTHETIC-C-1")
        self.assertEqual(req["orders"][0]["status"], "cancelled")
        self.assertEqual(Desk(self.path).request(rid), req)

    def test_http_handoff_exact_download(self):
        req = self.draft()
        oid = req["orders"][0]["id"]
        status, headers, body = self.http(f"/api/orders/{oid}/handoff.txt")
        self.assertEqual(status, 200)
        self.assertEqual(body.decode(), self.desk.handoff(oid))
        self.assertIn("attachment", headers["Content-Disposition"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
