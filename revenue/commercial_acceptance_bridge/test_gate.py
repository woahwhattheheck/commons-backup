from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from revenue.commercial_acceptance_bridge import acceptance as acceptance_module
from revenue.commercial_acceptance_bridge.acceptance import (
    EXPECTED_FIXTURE_RECEIPT_SHA256,
    EXPECTED_QUARANTINES,
    EXPECTED_STATES,
    SNAPSHOT,
    check_acceptance,
    generate_fixture,
    offer_event,
    response_event,
    sha,
)
from revenue.commercial_acceptance_bridge.gate import (
    AcceptanceError,
    canonical_json,
    receipt_self_digest_matches,
    reconcile as reconcile_gate,
    sha256_text,
    verify_receipt,
)


def batch(events, snapshot=SNAPSHOT):
    return {"schema_version": 1, "snapshot_at": snapshot, "events": events}


def reconcile(payload):
    """Deterministic test helper: evaluate exactly at the supplied fixture snapshot."""

    return reconcile_gate(payload, evaluated_at=payload["snapshot_at"])


def self_digest(manifest):
    forged = deepcopy(manifest)
    forged.pop("receipt_sha256", None)
    forged["receipt_sha256"] = sha256_text(canonical_json(forged))
    return forged


class CommercialAcceptanceBridgeTests(unittest.TestCase):
    def assertCode(self, code, fn):
        with self.assertRaises(AcceptanceError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_acceptance_matrix(self):
        result = check_acceptance()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["manifest"]["counts"]["states"], EXPECTED_STATES)
        actual = {}
        for row in result["manifest"]["quarantines"]:
            actual[row["code"]] = actual.get(row["code"], 0) + 1
        self.assertEqual(actual, EXPECTED_QUARANTINES)

    def test_exact_accept_routes_only_to_human_closing_ready_without_authority(self):
        offer = offer_event(90)
        response = response_event(90, "EXACT_ACCEPT")
        manifest = reconcile(batch([offer, response]))
        state = manifest["series"][0]
        self.assertEqual(state["state"], "HUMAN_CLOSING_READY")
        self.assertEqual(state["next_action"], "HUMAN_CLOSING_REVIEW")
        self.assertFalse(state["contract_authority"])
        self.assertFalse(state["payment_authority"])
        self.assertFalse(state["fulfillment_authority"])
        self.assertFalse(state["revenue_authority"])
        self.assertFalse(state["signer_authority_determined"])
        self.assertTrue(all(value is False for value in manifest["authorities"].values()))

    def test_exact_retry_collapses_without_duplicate_effect(self):
        offer = offer_event(90)
        response = response_event(90, "EXACT_ACCEPT")
        manifest = reconcile(batch([offer, response, deepcopy(response)]))
        self.assertEqual(manifest["replay_collapsed"], 1)
        self.assertEqual(manifest["counts"]["responses"], 1)
        self.assertEqual(manifest["counts"]["states"]["HUMAN_CLOSING_READY"], 1)

    def test_changed_event_replay_fails(self):
        response = response_event(90, "EXACT_ACCEPT")
        changed = deepcopy(response)
        changed["price_minor"] += 1
        self.assertCode("IDEMPOTENCY_CONFLICT", lambda: reconcile(batch([offer_event(90), response, changed])))

    def test_provider_message_collision_fails_even_under_distinct_event_ids(self):
        one = response_event(90, "QUESTION")
        two = response_event(90, "DECLINE", suffix="SECOND")
        two["provider_message_id"] = one["provider_message_id"]
        self.assertCode("PROVIDER_MESSAGE_COLLISION", lambda: reconcile(batch([offer_event(90), one, two])))

    def test_exact_accept_content_mismatch_blocks_closing(self):
        offer = offer_event(90)
        response = response_event(90, "EXACT_ACCEPT", mismatch=True)
        manifest = reconcile(batch([offer, response]))
        self.assertEqual(manifest["series"][0]["state"], "HUMAN_REVIEW_REQUIRED")
        self.assertIn("EXACT_ACCEPT_MISMATCH", manifest["series"][0]["blocker_codes"])

    def test_stale_offer_acceptance_is_quarantined_and_does_not_close_current(self):
        v1 = offer_event(1, 1)
        v2 = offer_event(1, 2)
        stale = response_event(1, "EXACT_ACCEPT", version=1, suffix="STALE")
        manifest = reconcile(batch([v1, v2, stale]))
        self.assertEqual(manifest["series"][0]["state"], "AWAITING_RESPONSE")
        self.assertEqual(manifest["quarantines"][0]["code"], "SUPERSEDED_OFFER_VERSION")

    def test_offer_version_gap_fails_closed(self):
        v1 = offer_event(1, 1)
        v3 = offer_event(1, 2)
        v3["version"] = 3
        v3["offer_version_id"] = "OFFER-001-V3"
        v3["event_id"] = "EV-OFFER-001-V3"
        self.assertCode("OFFER_VERSION_GAP", lambda: reconcile(batch([v1, v3])))

    def test_wrong_supersession_parent_fails_closed(self):
        v1 = offer_event(1, 1)
        v2 = offer_event(1, 2)
        v2["supersedes_version_id"] = "OFFER-OTHER"
        self.assertCode("OFFER_LINEAGE_INVALID", lambda: reconcile(batch([v1, v2])))

    def test_offer_lineage_cannot_change_counterparty(self):
        v1 = offer_event(1, 1)
        v2 = offer_event(1, 2)
        v2["counterparty_id"] = "SYNTH-COUNTERPARTY-OTHER"
        self.assertCode("OFFER_LINEAGE_INVALID", lambda: reconcile(batch([v1, v2])))

    def test_offer_lineage_cannot_change_thread(self):
        v1 = offer_event(1, 1)
        v2 = offer_event(1, 2)
        v2["provider_thread_id"] = "SYNTH-THREAD-OTHER"
        self.assertCode("OFFER_LINEAGE_INVALID", lambda: reconcile(batch([v1, v2])))

    def test_response_before_offer_blocks(self):
        offer = offer_event(54)
        response = response_event(54, "EXACT_ACCEPT")
        response["received_at"] = "2026-09-01T12:00:00Z"
        manifest = reconcile(batch([offer, response]))
        self.assertIn("RESPONSE_BEFORE_OFFER", manifest["series"][0]["blocker_codes"])

    def test_response_after_expiry_blocks(self):
        offer = offer_event(90)
        response = response_event(90, "EXACT_ACCEPT")
        response["received_at"] = "2026-09-21T12:00:00Z"
        manifest = reconcile(batch([offer, response], snapshot="2026-09-22T12:00:00Z"))
        self.assertIn("RESPONSE_AFTER_EXPIRY", manifest["series"][0]["blocker_codes"])

    def test_response_after_snapshot_blocks(self):
        offer = offer_event(90)
        response = response_event(90, "EXACT_ACCEPT")
        response["received_at"] = "2026-09-14T12:00:00Z"
        manifest = reconcile(batch([offer, response]))
        self.assertIn("RESPONSE_AFTER_SNAPSHOT", manifest["series"][0]["blocker_codes"])

    def test_thread_mismatch_blocks(self):
        offer = offer_event(90)
        response = response_event(90, "EXACT_ACCEPT")
        response["provider_thread_id"] = "SYNTH-THREAD-WRONG"
        manifest = reconcile(batch([offer, response]))
        self.assertIn("THREAD_MISMATCH", manifest["series"][0]["blocker_codes"])

    def test_counterparty_mismatch_blocks(self):
        offer = offer_event(90)
        response = response_event(90, "EXACT_ACCEPT")
        response["counterparty_id"] = "SYNTH-COUNTERPARTY-WRONG"
        manifest = reconcile(batch([offer, response]))
        self.assertIn("COUNTERPARTY_MISMATCH", manifest["series"][0]["blocker_codes"])

    def test_unknown_offer_response_quarantines_without_fabricating_series(self):
        response = response_event(90, "EXACT_ACCEPT")
        manifest = reconcile(batch([response]))
        self.assertEqual(manifest["counts"]["offer_series"], 0)
        self.assertEqual(manifest["quarantines"][0]["code"], "UNKNOWN_OFFER_VERSION")

    def test_later_counteroffer_supersedes_earlier_exact_accept_for_routing(self):
        offer = offer_event(90)
        exact = response_event(90, "EXACT_ACCEPT", suffix="EARLY")
        exact["received_at"] = "2026-09-11T10:00:00Z"
        counter = response_event(90, "COUNTEROFFER", suffix="LATE")
        counter["received_at"] = "2026-09-11T11:00:00Z"
        counter["price_minor"] += 1
        manifest = reconcile(batch([offer, exact, counter]))
        self.assertEqual(manifest["series"][0]["state"], "COUNTEROFFER_REVIEW")

    def test_same_timestamp_distinct_responses_require_human_review(self):
        offer = offer_event(90)
        exact = response_event(90, "EXACT_ACCEPT", suffix="A")
        question = response_event(90, "QUESTION", suffix="B")
        manifest = reconcile(batch([offer, exact, question]))
        self.assertEqual(manifest["series"][0]["state"], "HUMAN_REVIEW_REQUIRED")
        self.assertEqual(manifest["series"][0]["effective_review_class"], "NONE")

    def test_counteroffer_changed_fields_are_recorded_but_not_accepted(self):
        offer = offer_event(90)
        response = response_event(90, "COUNTEROFFER")
        response["price_minor"] += 1
        response["terms_sha256"] = sha("new-terms")
        manifest = reconcile(batch([offer, response]))
        state = manifest["series"][0]
        self.assertEqual(state["state"], "COUNTEROFFER_REVIEW")
        self.assertEqual(state["changed_fields"], ["terms_sha256", "price_minor"])

    def test_expired_offer_without_response_is_expired_not_accepted(self):
        offer = offer_event(60)
        manifest = reconcile(batch([offer]))
        self.assertEqual(manifest["series"][0]["state"], "EXPIRED_NO_ACCEPTANCE")

    def test_active_offer_without_response_waits(self):
        offer = offer_event(55)
        manifest = reconcile(batch([offer]))
        self.assertEqual(manifest["series"][0]["state"], "AWAITING_RESPONSE")

    def test_raw_message_content_is_rejected(self):
        contaminated = {**offer_event(90), "body": "I accept"}
        self.assertCode("RAW_CONTENT_FORBIDDEN", lambda: reconcile(batch([contaminated])))

    def test_nested_data_is_rejected(self):
        contaminated = {**offer_event(90), "metadata": {"anything": "no"}}
        self.assertCode("NESTED_DATA_FORBIDDEN", lambda: reconcile(batch([contaminated])))

    def test_lowercase_currency_is_rejected(self):
        offer = offer_event(90)
        offer["currency"] = "usd"
        self.assertCode("INVALID_INPUT", lambda: reconcile(batch([offer])))

    def test_boolean_price_is_rejected(self):
        offer = offer_event(90)
        offer["price_minor"] = True
        self.assertCode("INVALID_INPUT", lambda: reconcile(batch([offer])))

    def test_impossible_timestamp_is_rejected(self):
        offer = offer_event(90)
        offer["issued_at"] = "2026-02-30T12:00:00Z"
        self.assertCode("INVALID_INPUT", lambda: reconcile(batch([offer])))

    def test_expiry_must_follow_issue(self):
        offer = offer_event(90)
        offer["expires_at"] = offer["issued_at"]
        self.assertCode("INVALID_OFFER_WINDOW", lambda: reconcile(batch([offer])))

    def test_future_offer_fails_batch(self):
        offer = offer_event(90)
        offer["issued_at"] = "2026-09-14T12:00:00Z"
        offer["expires_at"] = "2026-09-20T12:00:00Z"
        self.assertCode("FUTURE_OFFER", lambda: reconcile(batch([offer])))

    def test_order_invariant_receipt(self):
        offer = offer_event(90)
        response = response_event(90, "EXACT_ACCEPT")
        one = reconcile(batch([offer, response]))
        two = reconcile(batch([response, offer]))
        self.assertEqual(one["receipt_sha256"], two["receipt_sha256"])

    def test_receipt_verification_and_tamper_detection(self):
        source = batch([offer_event(90), response_event(90, "EXACT_ACCEPT")])
        manifest = reconcile(source)
        self.assertTrue(receipt_self_digest_matches(manifest))
        self.assertTrue(
            verify_receipt(manifest, manifest["receipt_sha256"], source, evaluated_at=source["snapshot_at"])
        )
        tampered = deepcopy(manifest)
        tampered["series"][0]["state"] = "PAID"
        self.assertFalse(receipt_self_digest_matches(tampered))
        self.assertFalse(
            verify_receipt(tampered, manifest["receipt_sha256"], source, evaluated_at=source["snapshot_at"])
        )

    def test_fixture_receipt_requires_frozen_out_of_band_commitment_and_source(self):
        source = generate_fixture()
        manifest = check_acceptance(source)["manifest"]
        self.assertEqual(manifest["receipt_sha256"], EXPECTED_FIXTURE_RECEIPT_SHA256)
        self.assertTrue(
            verify_receipt(
                manifest,
                EXPECTED_FIXTURE_RECEIPT_SHA256,
                source,
                evaluated_at=source["snapshot_at"],
            )
        )
        self.assertFalse(
            verify_receipt(manifest, "0" * 64, source, evaluated_at=source["snapshot_at"])
        )
        changed_source = deepcopy(source)
        changed_source["events"][0]["price_minor"] += 1
        self.assertFalse(
            verify_receipt(
                manifest,
                EXPECTED_FIXTURE_RECEIPT_SHA256,
                changed_source,
                evaluated_at=source["snapshot_at"],
            )
        )

    def test_self_digested_unknown_product_is_integrity_only_not_valid_bridge_receipt(self):
        forged = self_digest({"product": "NOT_THE_BRIDGE", "state": "PAID"})
        self.assertTrue(receipt_self_digest_matches(forged))
        self.assertFalse(verify_receipt(forged, forged["receipt_sha256"], batch([]), evaluated_at=SNAPSHOT))

    def test_recomputed_digest_cannot_enable_revenue_or_payment_authority(self):
        source = batch([offer_event(90), response_event(90, "EXACT_ACCEPT")])
        manifest = reconcile(source)
        forged = deepcopy(manifest)
        forged["authorities"]["recognized_revenue"] = True
        forged["authorities"]["payment_or_charge"] = True
        forged = self_digest(forged)
        self.assertTrue(receipt_self_digest_matches(forged))
        self.assertFalse(
            verify_receipt(forged, forged["receipt_sha256"], source, evaluated_at=source["snapshot_at"])
        )

    def test_recomputed_digest_cannot_invent_paid_series_state(self):
        source = batch([offer_event(90), response_event(90, "EXACT_ACCEPT")])
        manifest = reconcile(source)
        forged = deepcopy(manifest)
        forged["series"][0]["state"] = "PAID"
        forged["series"][0]["revenue_authority"] = True
        forged["roots"]["series_state_sha256"] = sha256_text(
            "\n".join(sorted(canonical_json(row) for row in forged["series"]))
        )
        forged = self_digest(forged)
        self.assertTrue(receipt_self_digest_matches(forged))
        self.assertFalse(
            verify_receipt(forged, forged["receipt_sha256"], source, evaluated_at=source["snapshot_at"])
        )

    def test_future_snapshot_is_rejected_against_trusted_evaluation_time(self):
        source = batch([offer_event(90)])
        self.assertCode(
            "FUTURE_SNAPSHOT",
            lambda: reconcile_gate(source, evaluated_at="2026-09-13T11:59:59Z"),
        )

    def test_snapshot_older_than_five_minutes_fails_closed(self):
        source = batch([offer_event(90)])
        self.assertCode(
            "STALE_SNAPSHOT",
            lambda: reconcile_gate(source, evaluated_at="2026-09-13T12:05:01Z"),
        )

    def test_exact_accept_loses_closing_ready_after_offer_expires_at_evaluation(self):
        source = batch(
            [offer_event(90), response_event(90, "EXACT_ACCEPT")],
            snapshot="2026-09-20T12:01:00Z",
        )
        manifest = reconcile_gate(source, evaluated_at=source["snapshot_at"])
        state = manifest["series"][0]
        self.assertEqual(state["state"], "HUMAN_REVIEW_REQUIRED")
        self.assertEqual(state["effective_review_class"], "NONE")
        self.assertEqual(state["blocker_codes"], ["OFFER_EXPIRED_AT_EVALUATION"])

    def test_historical_closing_receipt_fails_current_verification_after_offer_expiry(self):
        source = batch(
            [offer_event(90), response_event(90, "EXACT_ACCEPT")],
            snapshot="2026-09-20T11:59:00Z",
        )
        manifest = reconcile_gate(source, evaluated_at=source["snapshot_at"])
        self.assertEqual(manifest["series"][0]["state"], "HUMAN_CLOSING_READY")
        self.assertFalse(
            verify_receipt(
                manifest,
                manifest["receipt_sha256"],
                source,
                evaluated_at="2026-09-20T12:01:00Z",
            )
        )

    def test_acceptance_cli_default_path_executes(self):
        output = StringIO()
        with redirect_stdout(output):
            status = acceptance_module.main([])
        self.assertEqual(status, 0)
        parsed = json.loads(output.getvalue())
        self.assertEqual(parsed["status"], "PASS")

    def test_trusted_verify_cli_requires_source_and_executes_current_receipt(self):
        source = generate_fixture()
        manifest = reconcile(source)
        with TemporaryDirectory() as temp:
            temp_path = Path(temp)
            receipt_path = temp_path / "receipt.json"
            source_path = temp_path / "source.json"
            receipt_path.write_text(canonical_json({"manifest": manifest}) + "\n", encoding="utf-8")
            source_path.write_text(canonical_json(source) + "\n", encoding="utf-8")
            now = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)
            output = StringIO()
            with patch("revenue.commercial_acceptance_bridge.gate._utcnow", return_value=now), redirect_stdout(output):
                status = acceptance_module.main(
                    [
                        "--verify-receipt",
                        str(receipt_path),
                        "--source-batch",
                        str(source_path),
                        "--expected-receipt-sha256",
                        manifest["receipt_sha256"],
                    ]
                )
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue()), {"valid": True})

    def test_trusted_verify_cli_rejects_stale_receipt(self):
        source = generate_fixture()
        manifest = reconcile(source)
        with TemporaryDirectory() as temp:
            temp_path = Path(temp)
            receipt_path = temp_path / "receipt.json"
            source_path = temp_path / "source.json"
            receipt_path.write_text(canonical_json({"manifest": manifest}) + "\n", encoding="utf-8")
            source_path.write_text(canonical_json(source) + "\n", encoding="utf-8")
            stale_now = datetime(2026, 9, 13, 12, 5, 1, tzinfo=timezone.utc)
            output = StringIO()
            with patch("revenue.commercial_acceptance_bridge.gate._utcnow", return_value=stale_now), redirect_stdout(output):
                status = acceptance_module.main(
                    [
                        "--verify-receipt",
                        str(receipt_path),
                        "--source-batch",
                        str(source_path),
                        "--expected-receipt-sha256",
                        manifest["receipt_sha256"],
                    ]
                )
            self.assertEqual(status, 2)
            self.assertEqual(json.loads(output.getvalue()), {"valid": False})

    def test_unknown_review_class_is_rejected(self):
        response = response_event(90, "QUESTION")
        response["review_class"] = "AUTO_ACCEPT_FROM_TEXT"
        self.assertCode("INVALID_REVIEW_CLASS", lambda: reconcile(batch([offer_event(90), response])))


if __name__ == "__main__":
    unittest.main()
