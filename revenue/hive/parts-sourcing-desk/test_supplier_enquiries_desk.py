"""New exporter composition tests against the actual canonical Desk, not a mock."""
import copy
from datetime import date
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

import supplier_enquiries as se
from test_supplier_enquiries import row, request

CORE = Path(os.environ.get("PARTS_DESK_SOURCE_DIR", Path(__file__).parent)) / "parts_desk.py"
if not CORE.is_file():
    raise RuntimeError("Set PARTS_DESK_SOURCE_DIR to a checkout containing the canonical parts_desk.py")
expected = os.environ.get("PARTS_DESK_EXPECTED_SHA256")
actual = hashlib.sha256(CORE.read_bytes()).hexdigest()
if expected and actual != expected:
    raise RuntimeError("The explicitly frozen canonical core hash does not match")
spec = importlib.util.spec_from_file_location("spruce_parts_desk_reference", CORE)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class DeskCompositionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.desk = core.Desk(Path(self.temp.name)/"real.sqlite3")
        self.sequence = 0
        self.desk.mutate("catalog", "", {"operation_id": "import",
                                      "items": [row(),row(id="offer-2",supplier="OtherSupplierPrivate",unit_price="999.00")]})
        r = request()
        data = {k:r[k] for k in ("job_ref","make","model","serial","quantity","notes")}
        data.update(part_number=r["requested_part"],description="Synthetic repair only")
        saved=self.desk.mutate("request","",{"operation_id":"create","data":data})
        self.rid=saved["id"]
        for cid in ("offer-1","offer-2"):
            saved=self.desk.mutate("option",self.rid,{"operation_id":"option-"+cid,
                                                  "catalog_id":cid,"revision":saved["revision"]})
        self.oid=saved["options"][0]["id"]

    def mutate(self,operation,identity,body):
        self.sequence += 1
        return self.desk.mutate(operation,identity,{"operation_id":str(self.sequence),**body})

    def build(self,saved=None,ids=None):
        return se.build_from_desk_request(saved or self.desk.request(self.rid),
                                         ids or [self.oid],as_of=date(2026,9,8))

    def review(self, fit="compatible"):
        saved=self.desk.request(self.rid)
        return self.mutate("review",self.oid,{"revision":saved["revision"],"fit":fit,
                                            "technician":"Synthetic technician",
                                            "note":"Synthetic recorded review; not real fit evidence"})

    def test_actual_catalog_validator_and_request_mapping(self):
        self.assertEqual(core.catalog_data(row())["unit_price"],"32.45")
        result=self.build()
        self.assertEqual(result["request"]["requested_part"],"000-BELT")
        self.assertEqual(result["enquiries"][0]["options"][0]["line_amount"],"97.35")
        self.assertEqual(result["request"]["source_request_revision"],3)
        self.assertNotIn("OtherSupplierPrivate",json.dumps(result))
        self.assertNotIn("999.00",json.dumps(result))

    def test_existing_compatible_review_is_preserved_not_reclassified(self):
        saved=self.review()
        result=self.build(saved)
        opt=result["enquiries"][0]["options"][0]["catalog"]["desk_option"]
        self.assertEqual(opt["effective_fit"],"compatible")
        self.assertEqual(opt["review"],saved["options"][0]["review"])
        self.assertIn("records compatibility",result["enquiries"][0]["text"])
        self.assertIn("Saved desk fit state: compatible",result["enquiries"][0]["text"])

    def test_catalog_change_retains_historical_quote_and_stale_review(self):
        self.review()
        self.mutate("catalog","",{"items":[row(unit_price="33.50",checked_on="2026-09-09")]})
        saved=self.desk.request(self.rid)
        self.assertEqual(saved["options"][0]["effective_fit"],"stale")
        result=self.build(saved)
        opt=result["enquiries"][0]["options"][0]
        self.assertEqual(opt["catalog"]["unit_price"],"32.45")
        self.assertIn("stale_desk_review",{q["code"] for q in opt["questions"]})
        self.assertIn("Saved desk fit state: stale",result["enquiries"][0]["text"])

    def test_request_change_maps_new_quantity_and_preserves_review_warning(self):
        saved=self.review()
        self.mutate("request",self.rid,{"revision":saved["revision"],
                                      "data":{**saved["data"],"quantity":4,"serial":"changed"}})
        result=self.build()
        self.assertEqual(result["request"]["quantity"],4)
        self.assertEqual(result["enquiries"][0]["options"][0]["line_amount"],"129.80")
        self.assertIn("stale_desk_review",{q["code"] for q in result["enquiries"][0]["options"][0]["questions"]})

    def test_incompatible_review_stays_explicit(self):
        result=self.build(self.review("incompatible"))
        self.assertIn("Do not ship this SKU",result["enquiries"][0]["text"])
        self.assertEqual(result["enquiries"][0]["options"][0]["catalog"]["desk_option"]["effective_fit"],"incompatible")

    def test_draft_and_placed_existing_order_do_not_create_duplicate(self):
        saved=self.desk.request(self.rid)
        saved=self.mutate("draft",self.rid,{"revision":saved["revision"],"option_id":self.oid})
        for action in ("draft","placed"):
            if action=="placed":
                order=saved["orders"][0]
                saved=self.mutate("placed",order["id"],{"revision":order["revision"],
                                                      "supplier_reference":"SYNTHETIC-NOT-A-PURCHASE"})
            before=self.desk.export()["tables"]
            result=self.build(saved)
            self.assertEqual(result["request"]["existing_order_count"],1)
            self.assertIn("Do not ship or duplicate",result["enquiries"][0]["text"])
            se.write_pack(result,Path(self.temp.name)/action)
            self.assertEqual(self.desk.export()["tables"],before)
        self.assertEqual(len(self.desk.request(self.rid)["orders"]),1)

    def test_cancellation_remains_in_core_without_active_order_warning(self):
        saved=self.desk.request(self.rid)
        saved=self.mutate("draft",self.rid,{"revision":saved["revision"],"option_id":self.oid})
        order=saved["orders"][0]
        saved=self.mutate("cancel",order["id"],{"revision":order["revision"],"note":"Synthetic draft cancelled"})
        result=self.build(saved)
        self.assertEqual(result["request"]["existing_order_count"],0)
        self.assertNotIn("EXISTING ORDER/DRAFT",result["enquiries"][0]["text"])
        self.assertEqual(len(self.desk.request(self.rid)["orders"]),1)

    def test_cross_request_and_unknown_selection_not_silently_exported(self):
        saved=self.desk.request(self.rid)
        wrong=copy.deepcopy(saved)
        wrong["options"][0]["request_id"]="another-request"
        with self.assertRaises(se.EnquiryError): self.build(wrong)
        with self.assertRaises(se.EnquiryError): self.build(saved,["missing-option"])
        wrong=copy.deepcopy(saved)
        wrong["options"][0]["catalog_id"]="wrong-catalog"
        with self.assertRaises(se.EnquiryError): self.build(wrong)

    def test_real_http_saved_request_to_real_cli_files(self):
        server=core.make_server(self.desk,port=0)
        thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":0.01},daemon=True)
        thread.start()
        try:
            base=f"http://127.0.0.1:{server.server_port}"
            with urlopen(base+"/api/requests/"+self.rid,timeout=5) as response:
                self.assertEqual(response.status,200)
                raw=response.read()
            request_path=Path(self.temp.name)/"saved-request.json"
            request_path.write_bytes(raw)
            out=Path(self.temp.name)/"enquiry-pack"
            before=self.desk.export()["tables"]
            run=subprocess.run([sys.executable,"-S","-B",str(Path(se.__file__)),
                                "--desk-request",str(request_path),"--option-id",self.oid,
                                "--out",str(out),"--as-of","2026-09-08"],
                               text=True,capture_output=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            result=se.read_json(out/"enquiries.json")
            self.assertEqual(result["request"]["id"],self.rid)
            self.assertEqual(result["enquiries"][0]["options"][0]["line_amount"],"97.35")
            self.assertNotIn("OtherSupplierPrivate",json.dumps(result))
            self.assertEqual(self.desk.export()["tables"],before)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
        self.assertFalse(thread.is_alive())

if __name__=="__main__":
    print("Canonical core SHA256:",actual)
    unittest.main()
