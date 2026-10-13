import tempfile, unittest
from pathlib import Path
from resale_workspace import *

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(); self.db=Path(self.t.name)/"w.db"; self.w=ResaleWorkspace(self.db)
        self.base=dict(item_id="I1",sku="S1",title="Meter",photo_ref="photos/I1/original.jpg",
                       photo_sha256="a"*64,condition_notes="Calibration unknown")
        self.w.add_item(**self.base,request_id="add")
    def tearDown(self): self.t.cleanup()

    def test_retry_and_immutable_photo(self):
        self.assertEqual("FOR_SALE",self.w.add_item(**self.base,request_id="add")["state"])
        with self.assertRaises(ImmutablePhotoError):
            self.w.add_item(**{**self.base,"photo_sha256":"b"*64},request_id="add2")
        self.assertEqual("a"*64,self.w.item_snapshot("I1")["photo"]["sha256"])

    def test_request_payload_conflict(self):
        with self.assertRaises(RequestConflict):
            self.w.add_item(**{**self.base,"title":"Other"},request_id="add")

    def test_request_id_must_be_nonblank_text_and_does_not_mutate(self):
        before=self.w.item_snapshot("I1")
        for rid in (None, b"", 0):
            with self.subTest(request_id=rid):
                with self.assertRaises(WorkspaceError):
                    self.w.save_draft(item_id="I1",channel="a",title="x",body="y",request_id=rid)
        self.assertEqual(before,self.w.item_snapshot("I1"))

    def test_explicit_uncertainty(self):
        self.w.edit_item(item_id="I1",title="Meter",condition_notes="used",
          attributes={"brand":"A","model":"M7"},uncertain_attributes=["model"],request_id="edit")
        s=self.w.item_snapshot("I1")
        self.assertFalse(s["attributes"]["brand"]["uncertain"]); self.assertTrue(s["attributes"]["model"]["uncertain"])
        with self.assertRaises(WorkspaceError):
            self.w.edit_item(item_id="I1",title="x",condition_notes="",attributes={"brand":"A"},
                             uncertain_attributes=["model"],request_id="bad")

    def test_editable_draft_preserves_photo(self):
        self.w.save_draft(item_id="I1",channel="a",title="One",body="v1",request_id="d1")
        self.w.save_draft(item_id="I1",channel="a",title="Two",body="v2",request_id="d2")
        s=self.w.item_snapshot("I1"); self.assertEqual("Two",s["drafts"]["a"]["title"])
        self.assertEqual("a"*64,s["photo"]["sha256"])

    def test_price_reference_only(self):
        self.w.add_price_reference(item_id="I1",source_url="https://example.test/a",note="asking 125",request_id="p")
        s=self.w.item_snapshot("I1"); self.assertEqual(1,len(s["price_references"])); self.assertNotIn("recommended_price",s)
        with self.assertRaises(InvalidReference):
            self.w.add_price_reference(item_id="I1",source_url="file:///x",note="bad",request_id="p2")

    def test_active_export_preserves_photo_and_uncertainty(self):
        self.w.edit_item(item_id="I1",title="Meter",condition_notes="used",
          attributes={"model":"M7"},uncertain_attributes=["model"],request_id="e2")
        self.w.record_listing(item_id="I1",channel="a",remote_url="https://market.test/i1",request_id="l")
        r=self.w.active_channel_export("a")[0]
        self.assertEqual("photos/I1/original.jpg",r["photo_ref"]); self.assertEqual(["model"],r["uncertain_attributes"])

    def test_sold_is_atomic_local_removal_plus_pending_tasks(self):
        for n,ch in enumerate(("a","b")):
            self.w.record_listing(item_id="I1",channel=ch,remote_url=f"https://{ch}.test/i1",request_id=f"l{n}")
        r=self.w.mark_sold(item_id="I1",sold_at="2026-09-09T17:00:00Z",request_id="sold")
        self.assertEqual([],self.w.active_channel_export("a")); self.assertEqual([],self.w.active_channel_export("b"))
        self.assertEqual(2,len(r["close_tasks"])); self.assertEqual({"PENDING"},{x["status"] for x in r["close_tasks"]})
        self.assertFalse(r["remote_changed"])

    def test_sold_retries_do_not_duplicate_close_tasks(self):
        self.w.record_listing(item_id="I1",channel="a",remote_url="https://a.test/i1",request_id="l")
        a=self.w.mark_sold(item_id="I1",sold_at="t1",request_id="s1")
        self.assertEqual(a,self.w.mark_sold(item_id="I1",sold_at="t1",request_id="s1"))
        b=self.w.mark_sold(item_id="I1",sold_at="t2",request_id="s2")
        self.assertEqual(1,len(b["close_tasks"])); self.assertEqual("t1",b["sold_at"])

    def test_sold_item_cannot_reactivate(self):
        self.w.mark_sold(item_id="I1",sold_at="t",request_id="s")
        with self.assertRaises(WorkspaceError):
            self.w.record_listing(item_id="I1",channel="a",remote_url="https://a.test/i1",request_id="late")

    def test_remote_change_requires_explicit_confirmation(self):
        self.w.record_listing(item_id="I1",channel="a",remote_url="https://a.test/i1",request_id="l")
        task=self.w.mark_sold(item_id="I1",sold_at="t",request_id="s")["close_tasks"][0]
        self.assertEqual("PENDING",task["status"])
        r=self.w.confirm_remote_close(task_id=task["task_id"],confirmation_note="operator removed listing",request_id="c")
        self.assertEqual("HUMAN_CONFIRMED",r["remote_changed"]); self.assertEqual("CONFIRMED",r["status"])

    def test_confirmation_requires_exact_positive_integer_task_id(self):
        self.w.record_listing(item_id="I1",channel="a",remote_url="https://a.test/i1",request_id="l")
        task=self.w.mark_sold(item_id="I1",sold_at="t",request_id="s")["close_tasks"][0]
        self.assertEqual(1,task["task_id"])
        before=self.w.item_snapshot("I1")
        for rid,bad in (("true",True),("false",False),("str","1"),("float",1.0),("none",None),("zero",0),("neg",-1)):
            with self.subTest(task_id=bad):
                with self.assertRaises(WorkspaceError):
                    self.w.confirm_remote_close(task_id=bad,confirmation_note="operator removed listing",request_id=rid)
                self.assertEqual(before,self.w.item_snapshot("I1"))
        first=self.w.confirm_remote_close(task_id=task["task_id"],confirmation_note="operator removed listing",request_id="valid")
        self.assertEqual("CONFIRMED",first["status"])
        self.assertEqual(first,self.w.confirm_remote_close(task_id=task["task_id"],confirmation_note="operator removed listing",request_id="valid"))

    def test_confirmation_requires_nonblank_text_and_is_one_way(self):
        self.w.record_listing(item_id="I1",channel="a",remote_url="https://a.test/i1",request_id="l")
        task=self.w.mark_sold(item_id="I1",sold_at="t",request_id="s")["close_tasks"][0]
        before=self.w.item_snapshot("I1")
        for rid,note in (("none",None),("bytes",b"operator"),("int",123),("blank","  ")):
            with self.subTest(confirmation_note=note):
                with self.assertRaises(WorkspaceError):
                    self.w.confirm_remote_close(task_id=task["task_id"],confirmation_note=note,request_id=rid)
                self.assertEqual(before,self.w.item_snapshot("I1"))
        first=self.w.confirm_remote_close(task_id=task["task_id"],confirmation_note="operator removed listing",request_id="confirm-first")
        self.assertEqual(first,self.w.confirm_remote_close(task_id=task["task_id"],confirmation_note="operator removed listing",request_id="confirm-first"))
        confirmed=self.w.item_snapshot("I1")
        with self.assertRaises(WorkspaceError):
            self.w.confirm_remote_close(task_id=task["task_id"],confirmation_note="replacement note",request_id="confirm-second")
        self.assertEqual(confirmed,self.w.item_snapshot("I1"))
        self.assertEqual("operator removed listing",confirmed["close_tasks"][0]["confirmation_note"])

    def test_restart_persistence(self):
        self.w.record_listing(item_id="I1",channel="a",remote_url="https://a.test/i1",request_id="l")
        self.w.mark_sold(item_id="I1",sold_at="t",request_id="s")
        self.assertEqual("SOLD",ResaleWorkspace(self.db).item_snapshot("I1")["state"])

class DemoTests(unittest.TestCase):
    def test_fixture_demo(self):
        f=Path(__file__).parent/"fixtures"/"sample_inventory.json"
        with tempfile.TemporaryDirectory() as t: r=run_demo(f,Path(t)/"d.db")
        self.assertEqual({"market-a":1,"market-b":1},r["before_active_counts"])
        self.assertEqual({"market-a":0,"market-b":0},r["after_active_counts"])
        self.assertEqual(2,r["close_task_count"]); self.assertEqual(["PENDING","PENDING"],r["close_task_statuses"])
        self.assertEqual(["model"],r["uncertain_attributes"]); self.assertFalse(r["remote_changed"])

if __name__=="__main__": unittest.main()
