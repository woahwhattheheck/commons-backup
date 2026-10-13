import copy
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from acceptance import generate
from rail import RailError, receipt_for, reconcile, verify_receipt


def tiny():
    return {
        "review_owner_role": "Highgate guest-operations reviewer",
        "events": [
            {"event_id":"R1","type":"resource","sequence":1,"surface":"ROOM","resource_id":"ROOM-001","state":"AVAILABLE"},
            {"event_id":"P1","type":"promise","sequence":2,"promise_id":"P-1","journey_id":"J-1","expected_surfaces":["ROOM"]},
            {"event_id":"B1","type":"booking","sequence":3,"operation_id":"OP-B1","promise_id":"P-1","surface":"ROOM","resource_id":"ROOM-001","slot_id":"S-1","action":"RESERVE","outcome":"APPLIED"},
            {"event_id":"M1","type":"money","sequence":4,"operation_id":"OP-M1","promise_id":"P-1","account_type":"FOLIO","account_id":"F-1","kind":"CHARGE","amount_cents":10000,"related_operation_id":None,"outcome":"APPLIED"},
        ],
    }


class RailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.acceptance = generate(15000)
        cls.acceptance_manifest = reconcile(cls.acceptance)

    def test_15000_journey_acceptance(self):
        m = self.acceptance_manifest
        self.assertEqual(m["journey_count"], 15000)
        self.assertEqual(m["promise_count"], 15000)
        self.assertEqual(len([r for r in m["resources"] if r["surface"] == "ROOM"]), 143)
        self.assertEqual(m["overbook_collision_count"], 0)
        self.assertEqual(m["unknown_effect_count"], 3)
        self.assertEqual(len([h for h in m["review_holds"] if h["reason"] == "UNKNOWN_EFFECT"]), 3)
        self.assertEqual(len([a for a in m["accounts"] if a["unknown_operation_ids"]]), 3)
        self.assertEqual(len([h for h in m["review_holds"] if h["reason"] == "RECOVERY_NOT_RESOLVED"]), 3)
        self.assertEqual(len([h for h in m["review_holds"] if h["reason"] == "EXPECTED_SURFACE_UNACCOUNTED"]), 0)

    def test_small_order_invariant(self):
        payload = generate(200)
        expected = reconcile(payload)
        shuffled = copy.deepcopy(payload)
        random.Random(913).shuffle(shuffled["events"])
        self.assertEqual(reconcile(shuffled), expected)

    def test_operation_retry_is_exactly_once(self):
        p = tiny()
        retry = copy.deepcopy(p["events"][2]); retry["event_id"] = "B1-RETRY"; retry["sequence"] = 9
        p["events"].append(retry)
        m = reconcile(p)
        self.assertEqual(m["operation_retry_count"], 1)
        self.assertEqual(m["booking_operation_count"], 1)

    def test_conflicting_operation_retry_fails(self):
        p = tiny()
        retry = copy.deepcopy(p["events"][2]); retry["event_id"] = "B1-RETRY"; retry["sequence"] = 9; retry["resource_id"] = "ROOM-002"
        p["events"].append(retry)
        with self.assertRaisesRegex(RailError, "conflicting duplicate operation_id"):
            reconcile(p)

    def test_overbook_becomes_named_hold(self):
        p = tiny()
        p["events"].append({"event_id":"P2","type":"promise","sequence":5,"promise_id":"P-2","journey_id":"J-2","expected_surfaces":["ROOM"]})
        p["events"].append({"event_id":"B2","type":"booking","sequence":6,"operation_id":"OP-B2","promise_id":"P-2","surface":"ROOM","resource_id":"ROOM-001","slot_id":"S-1","action":"RESERVE","outcome":"APPLIED"})
        m = reconcile(p)
        self.assertEqual(m["overbook_collision_count"], 1)
        self.assertIn("OVERBOOK_COLLISION", {h["reason"] for h in m["review_holds"]})

    def test_room_hold_is_visible(self):
        p = tiny()
        p["events"].insert(1, {"event_id":"RH","type":"resource","sequence":2,"surface":"ROOM","resource_id":"ROOM-001","state":"HOLD"})
        p["events"][2]["sequence"] = 3
        p["events"][3]["sequence"] = 4
        p["events"][4]["sequence"] = 5
        m = reconcile(p)
        self.assertIn("BOOKING_ON_UNAVAILABLE_RESOURCE", {h["reason"] for h in m["review_holds"]})

    def test_unknown_effect_must_be_visible(self):
        p = tiny(); p["events"][3]["outcome"] = "UNKNOWN"
        m = reconcile(p)
        self.assertEqual(m["unknown_effect_count"], 1)
        self.assertEqual(m["unknown_effects"][0]["operation_id"], "OP-M1")

    def test_resolution_reconciles_unknown(self):
        p = tiny(); p["events"][3]["outcome"] = "UNKNOWN"
        p["events"].append({"event_id":"X1","type":"resolution","sequence":5,"resolution_id":"RES-1","operation_id":"OP-M1","resolved_outcome":"APPLIED","reason_code":"PROVIDER_READBACK"})
        self.assertEqual(reconcile(p)["unknown_effect_count"], 0)

    def test_resolution_of_known_effect_fails(self):
        p = tiny(); p["events"].append({"event_id":"X1","type":"resolution","sequence":5,"resolution_id":"RES-1","operation_id":"OP-M1","resolved_outcome":"APPLIED","reason_code":"BAD"})
        with self.assertRaisesRegex(RailError, "non-UNKNOWN"):
            reconcile(p)

    def test_folio_reversal_cannot_exceed_source(self):
        p = tiny(); p["events"].append({"event_id":"V1","type":"money","sequence":5,"operation_id":"OP-V1","promise_id":"P-1","account_type":"FOLIO","account_id":"F-1","kind":"REFUND","amount_cents":10001,"related_operation_id":"OP-M1","outcome":"APPLIED"})
        with self.assertRaisesRegex(RailError, "reversals exceed"):
            reconcile(p)

    def test_gift_redeem_cannot_overdraw(self):
        p = tiny(); p["events"].append({"event_id":"G1","type":"money","sequence":5,"operation_id":"OP-G1","promise_id":"P-1","account_type":"GIFT_CARD","account_id":"G-1","kind":"REDEEM","amount_cents":1,"related_operation_id":None,"outcome":"APPLIED"})
        with self.assertRaisesRegex(RailError, "redeem exceeds"):
            reconcile(p)

    def test_missing_expected_surface_is_held(self):
        p = tiny(); p["events"][1]["expected_surfaces"] = ["ROOM", "SPA"]
        self.assertIn("EXPECTED_SURFACE_UNACCOUNTED", {h["reason"] for h in reconcile(p)["review_holds"]})

    def test_open_recovery_is_held(self):
        p = tiny(); p["events"].append({"event_id":"RC1","type":"recovery","sequence":5,"recovery_id":"REC-1","promise_id":"P-1","state":"OPEN","reason_code":"SERVICE_RECOVERY"})
        self.assertIn("RECOVERY_NOT_RESOLVED", {h["reason"] for h in reconcile(p)["review_holds"]})

    def test_guest_pii_rejected(self):
        p = tiny(); p["events"][1]["guest_name"] = "Forbidden Guest"
        with self.assertRaisesRegex(RailError, "PII field forbidden"):
            reconcile(p)

    def test_float_money_rejected(self):
        p = tiny(); p["events"][3]["amount_cents"] = 1.5
        with self.assertRaisesRegex(RailError, "integer"):
            reconcile(p)

    def test_receipt_detects_tamper(self):
        m = reconcile(tiny()); r = receipt_for(m)
        self.assertTrue(verify_receipt(m, r))
        bad = copy.deepcopy(m); bad["journey_count"] += 1
        with self.assertRaisesRegex(RailError, "manifest hash mismatch"):
            verify_receipt(bad, r)

    def test_authority_all_false(self):
        self.assertEqual(set(self.acceptance_manifest["authority"].values()), {False})

    def test_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            payload = Path(td)/"payload.json"; manifest = Path(td)/"manifest.json"; receipt = Path(td)/"receipt.json"
            payload.write_text(json.dumps(generate(50)))
            b = subprocess.run([sys.executable, str(HERE/"rail.py"), "build", str(payload), "--manifest", str(manifest), "--receipt", str(receipt)], text=True, capture_output=True)
            self.assertEqual(b.returncode, 0, b.stdout+b.stderr)
            v = subprocess.run([sys.executable, str(HERE/"rail.py"), "verify", str(manifest), str(receipt)], text=True, capture_output=True)
            self.assertEqual(v.returncode, 0, v.stdout+v.stderr)
            self.assertEqual(json.loads(v.stdout), {"ok": True})

    def test_optimized_mode_keeps_validation(self):
        code = "import sys; sys.path.insert(0,sys.argv[1]); from test_rail import tiny; from rail import reconcile,RailError; p=tiny(); p['events'][3]['amount_cents']=1.25;\ntry: reconcile(p)\nexcept RailError: raise SystemExit(0)\nraise SystemExit(9)"
        r = subprocess.run([sys.executable, "-O", "-c", code, str(HERE)])
        self.assertEqual(r.returncode, 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)
