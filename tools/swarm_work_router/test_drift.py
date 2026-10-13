import copy
import json
import unittest

import tools.swarm_work_router.drift as drift
from tools.swarm_work_router.drift import (
    DriftError,
    compile_audit,
    expected_snapshot,
    loads_census_strict,
    render_markdown,
    validate_census,
    verify_audit_receipt,
)
from tools.swarm_work_router.router import MUSE_DM_ID, _CHANNELS


def clean_census():
    rows = [
        {"id": channel_id, "name": name, "archived": False, "is_member": True, "conversation_type": "public_channel"}
        for channel_id, name in _CHANNELS.values()
    ]
    rows.append({"id": MUSE_DM_ID, "name": "muse-assistant", "archived": False, "is_member": True, "conversation_type": "im"})
    return {"schema": "swarm-slack-channel-census/v1", "generation": "20260915T044600Z", "source": "slack_list_user_channels", "channels": rows}


class DriftTests(unittest.TestCase):
    def test_clean_census_passes(self):
        receipt = compile_audit(clean_census())
        self.assertEqual(receipt["state"], "PASS")
        self.assertEqual(receipt["findings"], [])
        self.assertEqual(receipt["counts"]["resolved_route_targets"], receipt["counts"]["route_targets"])
        self.assertTrue(verify_audit_receipt(receipt))

    def test_input_order_invariant(self):
        a = clean_census()
        b = clean_census()
        b["channels"].reverse()
        self.assertEqual(compile_audit(a), compile_audit(b))

    def test_missing_expected_channel_holds(self):
        census = clean_census()
        census["channels"] = [row for row in census["channels"] if row["id"] != _CHANNELS["products"][0]]
        receipt = compile_audit(census)
        self.assertEqual(receipt["state"], "HOLD")
        self.assertIn("MISSING_EXPECTED_CHANNEL", {row["code"] for row in receipt["findings"]})

    def test_archived_expected_channel_holds(self):
        census = clean_census()
        next(row for row in census["channels"] if row["id"] == _CHANNELS["products"][0])["archived"] = True
        self.assertIn("ARCHIVED_EXPECTED_CHANNEL", {row["code"] for row in compile_audit(census)["findings"]})

    def test_inaccessible_expected_channel_holds(self):
        census = clean_census()
        next(row for row in census["channels"] if row["id"] == _CHANNELS["products"][0])["is_member"] = False
        self.assertIn("INACCESSIBLE_EXPECTED_CHANNEL", {row["code"] for row in compile_audit(census)["findings"]})

    def test_rename_reviews_but_route_stays_resolved(self):
        census = clean_census()
        next(row for row in census["channels"] if row["id"] == _CHANNELS["products"][0])["name"] = "products-renamed"
        receipt = compile_audit(census)
        self.assertEqual(receipt["state"], "REVIEW")
        self.assertIn("RENAMED_EXPECTED_CHANNEL", {row["code"] for row in receipt["findings"]})
        self.assertEqual(receipt["counts"]["resolved_route_targets"], receipt["counts"]["route_targets"])

    def test_duplicate_observed_id_holds(self):
        census = clean_census()
        census["channels"].append(copy.deepcopy(census["channels"][0]))
        receipt = compile_audit(census)
        self.assertEqual(receipt["state"], "HOLD")
        self.assertIn("DUPLICATE_OBSERVED_ID", {row["code"] for row in receipt["findings"]})

    def test_duplicate_observed_name_reviews(self):
        census = clean_census()
        census["channels"].append({"id": "C0ZZZZZZZZZ", "name": "products", "archived": False, "is_member": True, "conversation_type": "public_channel"})
        receipt = compile_audit(census)
        self.assertEqual(receipt["state"], "REVIEW")
        self.assertIn("DUPLICATE_OBSERVED_NAME", {row["code"] for row in receipt["findings"]})

    def test_missing_muse_holds(self):
        census = clean_census()
        census["channels"] = [row for row in census["channels"] if row["id"] != MUSE_DM_ID]
        receipt = compile_audit(census)
        self.assertIn("MISSING_MUSE_DM", {row["code"] for row in receipt["findings"]})

    def test_muse_must_be_im(self):
        census = clean_census()
        next(row for row in census["channels"] if row["id"] == MUSE_DM_ID)["conversation_type"] = "public_channel"
        self.assertIn("MUSE_DM_UNAVAILABLE", {row["code"] for row in compile_audit(census)["findings"]})

    def test_unknown_route_target_holds(self):
        original = drift._ROUTES
        try:
            drift._ROUTES = dict(original)
            drift._ROUTES["broken"] = ("not-a-registry-key", ())
            receipt = compile_audit(clean_census())
            self.assertIn("UNKNOWN_ROUTE_TARGET", {row["code"] for row in receipt["findings"]})
        finally:
            drift._ROUTES = original

    def test_central_queue_primary_violation_holds(self):
        original = drift._ROUTES
        try:
            drift._ROUTES = dict(original)
            drift._ROUTES["bad_lane"] = ("delegations", ())
            receipt = compile_audit(clean_census())
            self.assertIn("CENTRAL_QUEUE_PRIMARY_VIOLATION", {row["code"] for row in receipt["findings"]})
        finally:
            drift._ROUTES = original

    def test_strict_json_rejects_nested_duplicate_key(self):
        text = json.dumps(clean_census(), separators=(",", ":"))
        text = text.replace('"archived":false', '"archived":false,"archived":false', 1)
        with self.assertRaises(DriftError):
            loads_census_strict(text)

    def test_unknown_and_missing_fields_rejected(self):
        raw = clean_census()
        raw["extra"] = True
        with self.assertRaises(DriftError):
            validate_census(raw)
        raw = clean_census()
        del raw["source"]
        with self.assertRaises(DriftError):
            validate_census(raw)

    def test_bool_fields_are_exact_bool(self):
        raw = clean_census()
        raw["channels"][0]["is_member"] = 1
        with self.assertRaises(DriftError):
            validate_census(raw)

    def test_census_size_bound(self):
        row = {"id": "C0ZZZZZZZZZ", "name": "x", "archived": False, "is_member": True, "conversation_type": "public_channel"}
        raw = clean_census()
        raw["channels"] = [copy.deepcopy(row) for _ in range(1001)]
        with self.assertRaises(DriftError):
            validate_census(raw)

    def test_receipt_tamper_detected(self):
        receipt = compile_audit(clean_census())
        receipt["state"] = "HOLD"
        self.assertFalse(verify_audit_receipt(receipt))

    def test_semantic_state_tamper_detected_even_with_rehash(self):
        receipt = compile_audit(clean_census())
        receipt["state"] = "REVIEW"
        body = dict(receipt)
        body.pop("receipt_sha256")
        receipt["receipt_sha256"] = drift._sha256_obj(body)
        self.assertFalse(verify_audit_receipt(receipt))

    def test_markdown_is_deterministic_and_no_authority(self):
        receipt = compile_audit(clean_census())
        report = render_markdown(receipt)
        self.assertEqual(report, render_markdown(copy.deepcopy(receipt)))
        self.assertIn("Side effects authorized: **false**", report)

    def test_expected_snapshot_is_stable_and_explicit(self):
        snap = expected_snapshot()
        self.assertEqual(snap["schema"], "swarm-work-channel-expectation/v1")
        self.assertEqual(snap["muse_dm_id"], MUSE_DM_ID)
        self.assertEqual(snap["non_default_primary"], ["awaiting-merge", "delegations"])
        self.assertTrue(any(row["key"] == "coordination" for row in snap["channels"]))
        self.assertTrue(any(row["key"] == "todo" for row in snap["channels"]))


if __name__ == "__main__":
    unittest.main()
