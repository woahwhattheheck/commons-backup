from __future__ import annotations

import datetime as dt
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import desk
import merchant_auth


ORDERS = """order_ref,status,eta,delivered_on,returnable
1001,delivered,Delivered,2026-09-01,true
1002,shipped,Carrier update pending,,false
"""
ACCESS = """order_ref,support_code
1001,31415926
1002,27182818
"""
POLICY = {
    "shop_name": "Fixture Shop",
    "shipping_text": "Fixture shipping policy.",
    "return_days": 30,
    "staff_phone": "",
}


class MerchantAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "desk.sqlite3"
        self.today = lambda: dt.date(2026, 9, 9)
        base = desk.Store(self.db, today=self.today)
        base.import_csv(ORDERS)
        base.update_policy(POLICY)
        self.gate = merchant_auth.MerchantGate(self.db, today=self.today)
        self.assertEqual(self.gate.import_access_csv(ACCESS), {"provisioned": 2})

    def tearDown(self):
        self.temp.cleanup()

    def enter_ref(self, call_id: str, ref: str):
        self.gate.turn(call_id, 0)
        return self.gate.turn(call_id, 1, digits=ref)

    def verify(self, call_id: str, ref: str = "1001", code: str = "31415926"):
        prompt = self.enter_ref(call_id, ref)
        self.assertIsNone(prompt["order_ref"])
        return self.gate.turn(call_id, 2, digits=code)

    def test_known_and_unknown_refs_have_same_preverification_response(self):
        known = self.enter_ref("known-call", "1001")
        unknown = self.enter_ref("unknown-call", "9999")
        for field in ("message", "state", "order_ref", "next_turn"):
            self.assertEqual(known[field], unknown[field])
        self.assertEqual(known["state"], "verify")
        self.assertIsNone(known["order_ref"])

    def test_known_wrong_and_unknown_valid_code_use_same_kdf_shape(self):
        original_pbkdf2 = merchant_auth.hashlib.pbkdf2_hmac
        observations = []

        def traced_pbkdf2(hash_name, password, salt, iterations, *args, **kwargs):
            observations.append((hash_name, len(password), len(salt), iterations))
            return original_pbkdf2(hash_name, password, salt, iterations, *args, **kwargs)

        with mock.patch.object(
            merchant_auth.hashlib, "pbkdf2_hmac", side_effect=traced_pbkdf2
        ):
            self.enter_ref("known-work", "1001")
            start = len(observations)
            known = self.gate.turn("known-work", 2, digits="99999999")
            known_calls = observations[start:]

            self.enter_ref("unknown-work", "9999")
            start = len(observations)
            unknown = self.gate.turn("unknown-work", 2, digits="99999999")
            unknown_calls = observations[start:]

        self.assertEqual(known["state"], "ended")
        self.assertEqual(unknown["state"], "ended")
        self.assertEqual(known["message"], unknown["message"])
        self.assertEqual(known_calls, [("sha256", 8, 16, merchant_auth.PBKDF2_ROUNDS)])
        self.assertEqual(unknown_calls, known_calls)

    def test_wrong_blank_and_cross_order_codes_disclose_nothing_and_mutate_no_return(self):
        cases = (
            ("wrong", "1001", "99999999"),
            ("cross", "1001", "27182818"),
            ("blank", "1001", ""),
            ("unknown", "9999", "31415926"),
        )
        for call_id, ref, code in cases:
            with self.subTest(call_id=call_id):
                self.enter_ref(call_id, ref)
                denied = self.gate.turn(call_id, 2, digits=code)
                self.assertEqual(denied["state"], "ended")
                self.assertIsNone(denied["order_ref"])
                self.assertNotIn("delivered", denied["message"].lower())
                self.assertNotIn("shipped", denied["message"].lower())
                self.assertNotIn(ref, denied["message"])
        snap = self.gate.base.snapshot()
        self.assertEqual(snap["returns"], [])
        self.assertEqual(snap["calls"], [])

    def test_exact_verifier_unlocks_existing_status_and_return_state_machine(self):
        verified = self.verify("status-call")
        self.assertEqual(verified["state"], "menu")
        self.assertEqual(verified["order_ref"], "1001")
        self.assertIn("Order 1001 found", verified["message"])
        status = self.gate.turn("status-call", 3, speech="status")
        self.assertIn("Order 1001 is delivered", status["message"])

        self.verify("return-call")
        reason_prompt = self.gate.turn("return-call", 3, speech="return")
        self.assertEqual(reason_prompt["state"], "reason")
        confirm = self.gate.turn("return-call", 4, digits="1")
        self.assertEqual(confirm["state"], "confirm")
        created = self.gate.turn("return-call", 5, digits="1")
        self.assertIn("Return request", created["message"])
        snapshot = self.gate.base.snapshot()
        self.assertEqual(len(snapshot["returns"]), 1)
        self.assertEqual(snapshot["returns"][0]["order_ref"], "1001")

    def test_restart_replays_verified_outer_turn_without_reusing_support_code(self):
        self.enter_ref("restart-call", "1001")
        first = self.gate.turn("restart-call", 2, digits="31415926")
        restarted = merchant_auth.MerchantGate(self.db, today=self.today)
        replay = restarted.turn("restart-call", 2, digits="31415926")
        self.assertEqual(first, replay)
        with self.assertRaisesRegex(desk.Conflict, "different input"):
            restarted.turn("restart-call", 2, digits="99999999")
        snapshot = restarted.base.snapshot()
        self.assertEqual(len(snapshot["calls"]), 1)

    def test_verifier_material_is_separate_from_order_snapshot_and_export(self):
        snapshot = self.gate.base.snapshot(include_audit=True)
        self.assertNotIn("merchant_access", snapshot)
        exported = self.gate.base.export().decode("utf-8")
        self.assertNotIn("31415926", exported)
        self.assertNotIn("27182818", exported)
        with self.gate.base.connection() as db:
            row = db.execute(
                "SELECT salt,verifier,rounds FROM merchant_access WHERE order_ref='1001'"
            ).fetchone()
        self.assertEqual(len(row["salt"]), 16)
        self.assertEqual(len(row["verifier"]), 32)
        self.assertEqual(row["rounds"], merchant_auth.PBKDF2_ROUNDS)
        self.assertNotEqual(row["verifier"], b"31415926")

    def test_access_import_is_atomic_and_requires_existing_orders(self):
        before = self.gate.import_access_csv("order_ref,support_code\n1001,11112222\n")
        self.assertEqual(before, {"provisioned": 1})
        with self.assertRaisesRegex(ValueError, "unknown order"):
            self.gate.import_access_csv(
                "order_ref,support_code\n1001,33334444\nNO-SUCH,55556666\n"
            )
        # The rejected two-row import must not replace 1001's previously valid code.
        call = "atomic-call"
        self.enter_ref(call, "1001")
        allowed = self.gate.turn(call, 2, digits="11112222")
        self.assertEqual(allowed["state"], "menu")

    def test_merchant_edge_rejects_nonloopback_bind(self):
        for value in ("127.0.0.1", "127.0.0.42", "::1", "localhost"):
            with self.subTest(value=value):
                self.assertTrue(merchant_auth._loopback(value))
        for value in ("0.0.0.0", "::", "192.168.1.4", "8.8.8.8", "example.com"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(Exception, "loopback"):
                    merchant_auth._loopback(value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
