from __future__ import annotations

import copy
import random
import unittest

from revenue.mrhd_impact_match.fixture import (
    FIXTURE_EVENT_COUNT,
    build_acceptance_fixture,
)
from revenue.mrhd_impact_match.rail import (
    ELIGIBLE_GEOGRAPHIES,
    FOCUS_CATEGORIES,
    EvidenceInputError,
    reconcile,
    verify_manifest_signature,
)

KEY = b"synthetic-test-key-not-a-production-secret"


def award_event(
    *,
    award_id: str = "A1",
    sequence: int = 1,
    award_cents: int = 100_000 * 100,
    geography: str | None = None,
    category: str | None = None,
):
    return {
        "event_id": f"e-{sequence}",
        "sequence": sequence,
        "event_type": "AWARD_APPROVED",
        "award_id": award_id,
        "payload": {
            "applicant_id": "AP1",
            "project_id": "P1",
            "cycle_id": "C1",
            "category": category or FOCUS_CATEGORIES[0],
            "geography": geography or ELIGIBLE_GEOGRAPHIES[0],
            "award_cents": award_cents,
            "required_match_cents": award_cents // 4,
        },
    }


def commitment(
    *,
    event_id: str,
    sequence: int,
    award_id: str,
    commitment_id: str,
    kind: str,
    cents: int,
):
    p = {
        "commitment_id": commitment_id,
        "kind": kind,
        "committed_cents": cents,
        "source_id": f"source-{commitment_id}",
    }
    if kind == "in_kind":
        p["valuation_method"] = "approved-rate-card"
        p["evidence_hash"] = f"sha256:{commitment_id}"
    return {
        "event_id": event_id,
        "sequence": sequence,
        "event_type": "MATCH_COMMITMENT",
        "award_id": award_id,
        "payload": p,
    }


def verified(
    *,
    event_id: str,
    sequence: int,
    award_id: str,
    commitment_id: str,
    cents: int,
):
    return {
        "event_id": event_id,
        "sequence": sequence,
        "event_type": "CONTRIBUTION_VERIFIED",
        "award_id": award_id,
        "payload": {
            "commitment_id": commitment_id,
            "realized_cents": cents,
            "evidence_hash": f"sha256:{event_id}",
            "reviewer_id": "MRHD-reviewer",
        },
    }


class EvidenceRailTests(unittest.TestCase):
    def test_exact_25_percent_match_and_complete_cash_inkind(self):
        records = [award_event()]
        records += [
            commitment(
                event_id="e2",
                sequence=2,
                award_id="A1",
                commitment_id="cash",
                kind="cash",
                cents=15_000 * 100,
            ),
            commitment(
                event_id="e3",
                sequence=3,
                award_id="A1",
                commitment_id="inkind",
                kind="in_kind",
                cents=10_000 * 100,
            ),
            verified(
                event_id="e4",
                sequence=4,
                award_id="A1",
                commitment_id="cash",
                cents=15_000 * 100,
            ),
            verified(
                event_id="e5",
                sequence=5,
                award_id="A1",
                commitment_id="inkind",
                cents=10_000 * 100,
            ),
        ]
        manifest = reconcile(records, signing_key=KEY)
        award = manifest["awards"][0]
        self.assertEqual(award["required_match_cents"], 25_000 * 100)
        self.assertEqual(award["max_in_kind_cents"], 12_500 * 100)
        self.assertEqual(award["countable_match_cents"], 25_000 * 100)
        self.assertTrue(award["match_complete"])
        self.assertEqual(manifest["disposition"], "PASS")

    def test_unverified_commitment_never_counts_as_realized(self):
        records = [
            award_event(),
            commitment(
                event_id="e2",
                sequence=2,
                award_id="A1",
                commitment_id="cash",
                kind="cash",
                cents=25_000 * 100,
            ),
        ]
        manifest = reconcile(records, signing_key=KEY)
        award = manifest["awards"][0]
        self.assertEqual(award["countable_match_cents"], 0)
        self.assertFalse(award["match_complete"])
        self.assertIn("MATCH_SHORTFALL", {h["code"] for h in manifest["holds"]})

    def test_in_kind_above_cap_is_visible_but_not_counted(self):
        records = [award_event()]
        records += [
            commitment(
                event_id="e2",
                sequence=2,
                award_id="A1",
                commitment_id="inkind",
                kind="in_kind",
                cents=20_000 * 100,
            ),
            verified(
                event_id="e3",
                sequence=3,
                award_id="A1",
                commitment_id="inkind",
                cents=20_000 * 100,
            ),
        ]
        manifest = reconcile(records, signing_key=KEY)
        award = manifest["awards"][0]
        self.assertEqual(award["in_kind_verified_cents"], 20_000 * 100)
        self.assertEqual(award["countable_in_kind_cents"], 12_500 * 100)
        self.assertIn("IN_KIND_CAP_EXCEEDED", {h["code"] for h in manifest["holds"]})

    def test_exact_retry_is_idempotent(self):
        event = award_event()
        manifest = reconcile([event, copy.deepcopy(event)], signing_key=KEY)
        self.assertEqual(manifest["cycle"]["award_count"], 1)
        self.assertEqual(manifest["event_receipt"]["replay_event_count"], 1)

    def test_conflicting_retry_freezes(self):
        first = award_event()
        second = copy.deepcopy(first)
        second["payload"]["project_id"] = "CHANGED"
        manifest = reconcile([first, second], signing_key=KEY)
        self.assertIn("IDEMPOTENCY_CONFLICT", {h["code"] for h in manifest["holds"]})
        conflict = next(h for h in manifest["holds"] if h["code"] == "IDEMPOTENCY_CONFLICT")
        self.assertEqual(conflict["action"], "FREEZE")

    def test_sequence_collision_freezes_second_event(self):
        first = award_event()
        second = award_event(award_id="A2")
        second["event_id"] = "different"
        manifest = reconcile([first, second], signing_key=KEY)
        self.assertIn("SEQUENCE_COLLISION", {h["code"] for h in manifest["holds"]})
        self.assertEqual(manifest["cycle"]["award_count"], 1)

    def test_amendment_preserves_prior_approved_state(self):
        records = [
            award_event(),
            {
                "event_id": "e2",
                "sequence": 2,
                "event_type": "AMENDMENT_APPROVED",
                "award_id": "A1",
                "payload": {
                    "amendment_id": "AM1",
                    "approver_id": "reviewer",
                    "new_award_cents": 120_000 * 100,
                    "new_required_match_cents": 30_000 * 100,
                },
            },
        ]
        manifest = reconcile(records, signing_key=KEY)
        lineage = manifest["awards"][0]["amendments"]
        self.assertEqual(len(lineage), 2)
        self.assertEqual(lineage[0]["award_cents"], 100_000 * 100)
        self.assertEqual(lineage[1]["prior_award_cents"], 100_000 * 100)
        self.assertEqual(lineage[1]["award_cents"], 120_000 * 100)

    def test_return_preserves_lineage_and_balance(self):
        records = [
            award_event(),
            {
                "event_id": "e2",
                "sequence": 2,
                "event_type": "RETURN_RECORDED",
                "award_id": "A1",
                "payload": {
                    "return_id": "R1",
                    "amount_cents": 5_000 * 100,
                    "evidence_hash": "sha256:return",
                },
            },
        ]
        manifest = reconcile(records, signing_key=KEY)
        award = manifest["awards"][0]
        self.assertEqual(award["returned_cents"], 5_000 * 100)
        self.assertEqual(award["net_unreturned_award_cents"], 95_000 * 100)
        self.assertEqual(award["returns"][0]["return_id"], "R1")

    def test_return_cannot_exceed_award(self):
        records = [
            award_event(),
            {
                "event_id": "e2",
                "sequence": 2,
                "event_type": "RETURN_RECORDED",
                "award_id": "A1",
                "payload": {
                    "return_id": "R1",
                    "amount_cents": 100_001 * 100,
                    "evidence_hash": "sha256:return",
                },
            },
        ]
        manifest = reconcile(records, signing_key=KEY)
        self.assertIn("RETURN_EXCEEDS_AWARD", {h["code"] for h in manifest["holds"]})
        self.assertEqual(manifest["awards"][0]["returned_cents"], 0)

    def test_late_milestone_stays_visible_for_review(self):
        records = [
            award_event(),
            {
                "event_id": "e2",
                "sequence": 2,
                "event_type": "MILESTONE_RECORDED",
                "award_id": "A1",
                "payload": {
                    "milestone_id": "M1",
                    "due_on": "2027-01-01",
                    "observed_on": "2027-01-02",
                    "status": "complete",
                    "evidence_hash": "sha256:m1",
                },
            },
        ]
        manifest = reconcile(records, signing_key=KEY)
        self.assertIn("MILESTONE_REVIEW_REQUIRED", {h["code"] for h in manifest["holds"]})
        self.assertEqual(manifest["awards"][0]["milestones"][0]["milestone_id"], "M1")

    def test_unknown_award_fails_closed(self):
        event = {
            "event_id": "e1",
            "sequence": 1,
            "event_type": "CLOSEOUT_REQUESTED",
            "award_id": "NOPE",
            "payload": {"closeout_id": "C1", "evidence_hash": "sha256:c1"},
        }
        manifest = reconcile([event], signing_key=KEY)
        self.assertEqual(manifest["cycle"]["award_count"], 0)
        self.assertIn("UNKNOWN_AWARD", {h["code"] for h in manifest["holds"]})

    def test_invalid_geography_is_not_admitted(self):
        event = award_event(geography="IA:NotEligible")
        manifest = reconcile([event], signing_key=KEY)
        self.assertEqual(manifest["cycle"]["award_count"], 0)
        self.assertIn("INVALID_AWARD_APPROVAL", {h["code"] for h in manifest["holds"]})

    def test_invalid_category_is_not_admitted(self):
        event = award_event(category="not_a_focus_area")
        manifest = reconcile([event], signing_key=KEY)
        self.assertEqual(manifest["cycle"]["award_count"], 0)
        self.assertIn("INVALID_AWARD_APPROVAL", {h["code"] for h in manifest["holds"]})

    def test_malformed_event_envelope_raises_before_reconciliation(self):
        bad = award_event()
        bad["sequence"] = True
        with self.assertRaisesRegex(EvidenceInputError, "sequence must be an integer"):
            reconcile([bad], signing_key=KEY)

    def test_empty_signing_key_rejected(self):
        with self.assertRaisesRegex(EvidenceInputError, "signing_key"):
            reconcile([], signing_key=b"")

    def test_manifest_signature_verifies_and_detects_tamper(self):
        manifest = reconcile([award_event()], signing_key=KEY)
        self.assertTrue(verify_manifest_signature(manifest, signing_key=KEY))
        tampered = copy.deepcopy(manifest)
        tampered["cycle"]["award_cents"] += 1
        self.assertFalse(verify_manifest_signature(tampered, signing_key=KEY))

    def test_fixture_is_exactly_180_events(self):
        fixture = build_acceptance_fixture()
        self.assertEqual(len(fixture), FIXTURE_EVENT_COUNT)
        self.assertEqual(len(fixture), 180)

    def test_fixture_spans_all_focus_categories_and_geographies(self):
        fixture = build_acceptance_fixture()
        approvals = [e for e in fixture if e["event_type"] == "AWARD_APPROVED"]
        seen_categories = {
            e["payload"]["category"]
            for e in approvals
            if e["payload"]["category"] in FOCUS_CATEGORIES
        }
        seen_geos = {
            e["payload"]["geography"]
            for e in approvals
            if e["payload"]["geography"] in ELIGIBLE_GEOGRAPHIES
        }
        self.assertEqual(seen_categories, set(FOCUS_CATEGORIES))
        self.assertEqual(seen_geos, set(ELIGIBLE_GEOGRAPHIES))

    def test_fixture_exercises_promised_hostile_cases(self):
        manifest = reconcile(build_acceptance_fixture(), signing_key=KEY)
        codes = {h["code"] for h in manifest["holds"]}
        expected = {
            "IDEMPOTENCY_CONFLICT",
            "SEQUENCE_COLLISION",
            "UNKNOWN_AWARD",
            "DUPLICATE_AWARD",
            "INVALID_AWARD_APPROVAL",
            "IN_KIND_CAP_EXCEEDED",
            "MILESTONE_REVIEW_REQUIRED",
            "UNMATCHED_CONTRIBUTION",
            "RETURN_EXCEEDS_AWARD",
            "OVER_REALIZED_COMMITMENT",
            "MATCH_SHORTFALL",
        }
        self.assertTrue(expected <= codes, expected - codes)
        self.assertGreaterEqual(manifest["event_receipt"]["replay_event_count"], 2)

    def test_clean_room_replay_is_byte_deterministic(self):
        fixture = build_acceptance_fixture()
        first = reconcile(fixture, signing_key=KEY)
        shuffled = copy.deepcopy(fixture)
        random.Random(913452).shuffle(shuffled)
        second = reconcile(shuffled, signing_key=KEY)
        self.assertEqual(first, second)
        self.assertEqual(first["manifest_sha256"], second["manifest_sha256"])
        self.assertEqual(first["manifest_hmac_sha256"], second["manifest_hmac_sha256"])

    def test_cycle_totals_equal_sum_of_per_award_state(self):
        manifest = reconcile(build_acceptance_fixture(), signing_key=KEY)
        self.assertEqual(
            manifest["cycle"]["award_cents"],
            sum(a["award_cents"] for a in manifest["awards"]),
        )
        self.assertEqual(
            manifest["cycle"]["returned_cents"],
            sum(a["returned_cents"] for a in manifest["awards"]),
        )
        self.assertEqual(
            manifest["cycle"]["required_match_cents"],
            sum(a["required_match_cents"] for a in manifest["awards"]),
        )
        self.assertEqual(
            manifest["cycle"]["countable_match_cents"],
            sum(a["countable_match_cents"] for a in manifest["awards"]),
        )

    def test_closeout_with_shortfall_holds(self):
        records = [
            award_event(),
            {
                "event_id": "e2",
                "sequence": 2,
                "event_type": "CLOSEOUT_REQUESTED",
                "award_id": "A1",
                "payload": {
                    "closeout_id": "C1",
                    "evidence_hash": "sha256:c1",
                },
            },
        ]
        manifest = reconcile(records, signing_key=KEY)
        self.assertIn("MATCH_INCOMPLETE_AT_CLOSEOUT", {h["code"] for h in manifest["holds"]})

    def test_over_realized_contribution_does_not_mutate_totals(self):
        records = [
            award_event(),
            commitment(
                event_id="e2",
                sequence=2,
                award_id="A1",
                commitment_id="cash",
                kind="cash",
                cents=1_000 * 100,
            ),
            verified(
                event_id="e3",
                sequence=3,
                award_id="A1",
                commitment_id="cash",
                cents=2_000 * 100,
            ),
        ]
        manifest = reconcile(records, signing_key=KEY)
        self.assertIn("OVER_REALIZED_COMMITMENT", {h["code"] for h in manifest["holds"]})
        self.assertEqual(manifest["awards"][0]["cash_verified_cents"], 0)


if __name__ == "__main__":
    unittest.main()
