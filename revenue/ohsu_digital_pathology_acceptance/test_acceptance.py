import hashlib
import io
import unittest

from acceptance import AcceptanceError, AcceptanceSession, parse_jsonl


H64_A = hashlib.sha256(b"artifact").hexdigest()
H64_I = hashlib.sha256(b"input").hexdigest()


def order(event_id="e1", seq=1, case="CASE-001", slide="SLIDE-001"):
    return {"type":"order","event_id":event_id,"seq":seq,"message":"OML^O21","case_id":case,"slide_id":slide,"order_id":f"ORD-{slide}"}


def status(event_id="e2", seq=2, status_name="IMAGE_AVAILABLE", case="CASE-001", slide="SLIDE-001"):
    return {"type":"status","event_id":event_id,"seq":seq,"message":"SSU^U03","case_id":case,"slide_id":slide,"status":status_name}


def link(event_id="e3", seq=3, case="CASE-001", slide="SLIDE-001"):
    return {"type":"link","event_id":event_id,"seq":seq,"case_id":case,"slide_id":slide,"scope":"slide","linked_id":slide,"url":f"https://viewer.example.test/slides/{slide}"}


def ai(event_id="e4", seq=4, case="CASE-001", slide="SLIDE-001"):
    return {"type":"ai_provenance","event_id":event_id,"seq":seq,"case_id":case,"slide_id":slide,"adapter":"adapter-v1","model_name":"model-a","model_version":"v1","artifact_sha256":H64_A,"input_sha256":H64_I,"purpose":"synthetic routing evidence only","authority":"decision_support_only"}


class AcceptanceTests(unittest.TestCase):
    def test_happy_path_receipt_is_deterministic(self):
        s = AcceptanceSession()
        for e in [order(), status(), link(), ai(), {"type":"case_close","event_id":"e5","seq":5,"message":"ORU^R01","case_id":"CASE-001"}]:
            s.apply(e)
        r1 = s.receipt()
        r2 = s.receipt()
        self.assertEqual(r1, r2)
        self.assertEqual(r1["slide_count"], 1)
        self.assertEqual(r1["linked_slide_count"], 1)
        self.assertEqual(r1["ai_provenance_count"], 1)
        self.assertFalse(r1["clinical_decision_authority"])
        self.assertFalse(r1["phi_accepted"])

    def test_exact_duplicate_is_idempotent(self):
        s = AcceptanceSession(); e = order()
        s.apply(e); s.apply(dict(e))
        self.assertEqual(s.receipt()["unique_event_count"], 1)
        self.assertEqual(s.receipt()["duplicate_replay_count"], 1)

    def test_changed_duplicate_conflicts(self):
        s = AcceptanceSession(); s.apply(order())
        changed = order(); changed["slide_id"] = "SLIDE-999"
        with self.assertRaises(AcceptanceError): s.apply(changed)

    def test_status_requires_prior_order(self):
        with self.assertRaises(AcceptanceError): AcceptanceSession().apply(status())

    def test_status_requires_ssu_u03(self):
        s = AcceptanceSession(); s.apply(order())
        e = status(); e["message"] = "ORU^R01"
        with self.assertRaises(AcceptanceError): s.apply(e)

    def test_per_slide_status_is_independent(self):
        s = AcceptanceSession()
        s.apply(order("o1", 1, slide="SLIDE-001")); s.apply(order("o2", 2, slide="SLIDE-002"))
        s.apply(status("s1", 3, slide="SLIDE-001"))
        receipt = s.receipt()
        states = {x["slide_id"]: x["status"] for x in receipt["slides"]}
        self.assertEqual(states, {"SLIDE-001":"IMAGE_AVAILABLE", "SLIDE-002":"ORDERED"})

    def test_status_regression_fails(self):
        s = AcceptanceSession(); s.apply(order()); s.apply(status()); s.apply(status("e3", 3, "QC_COMPLETE"))
        with self.assertRaises(AcceptanceError): s.apply(status("e4", 4, "IMAGE_AVAILABLE"))

    def test_non_https_link_fails(self):
        s = AcceptanceSession(); s.apply(order()); e = link(); e["url"] = "http://viewer.example.test/x"
        with self.assertRaises(AcceptanceError): s.apply(e)

    def test_cross_slide_link_identity_fails(self):
        s = AcceptanceSession(); s.apply(order()); e = link(); e["linked_id"] = "SLIDE-OTHER"
        with self.assertRaises(AcceptanceError): s.apply(e)

    def test_ai_cannot_claim_autonomous_clinical_authority(self):
        s = AcceptanceSession(); s.apply(order()); e = ai(); e["authority"] = "autonomous_diagnosis"
        with self.assertRaises(AcceptanceError): s.apply(e)

    def test_ai_hashes_are_strict(self):
        s = AcceptanceSession(); s.apply(order()); e = ai(); e["artifact_sha256"] = "abc"
        with self.assertRaises(AcceptanceError): s.apply(e)

    def test_phi_like_fields_are_rejected_anywhere(self):
        s = AcceptanceSession(); e = order(); e["meta"] = {"mrn":"123"}
        with self.assertRaises(AcceptanceError): s.apply(e)

    def test_case_close_requires_every_slide_available(self):
        s = AcceptanceSession(); s.apply(order())
        with self.assertRaises(AcceptanceError): s.apply({"type":"case_close","event_id":"c1","seq":2,"message":"ORU^R01","case_id":"CASE-001"})

    def test_jsonl_duplicate_keys_fail(self):
        text = '{"type":"order","type":"order","event_id":"e1","seq":1,"message":"OML^O21","case_id":"CASE-001","slide_id":"SLIDE-001","order_id":"ORD-1"}\n'
        with self.assertRaises(AcceptanceError): parse_jsonl(io.StringIO(text))

    def test_unknown_fields_fail_closed(self):
        s = AcceptanceSession(); e = order(); e["surprise"] = 1
        with self.assertRaises(AcceptanceError): s.apply(e)

    def test_case_link_must_bind_case_id(self):
        s = AcceptanceSession(); s.apply(order()); e = link(); e["scope"] = "case"; e["linked_id"] = "SLIDE-001"
        with self.assertRaises(AcceptanceError): s.apply(e)


if __name__ == "__main__":
    unittest.main()
