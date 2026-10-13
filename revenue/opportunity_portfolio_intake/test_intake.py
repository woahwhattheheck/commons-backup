from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
import unittest
from unittest import mock

from revenue.opportunity_portfolio_intake.cli import _pairs
from revenue.opportunity_portfolio_intake import intake as fw
from revenue.opportunity_portfolio_intake.intake import (
    IntakeError,
    SNAPSHOT_AUTHORITY_KEY_ENV,
    SNAPSHOT_AUTHORITY_SCHEMA,
    compile_intake,
    issue_host_snapshot_authority,
    normalize_intake,
    verify_receipt,
)


def h(text: str) -> str:
    return sha256(text.encode()).hexdigest()


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def source(ref: str, at: str, token: str | None = None) -> dict[str, str]:
    return {"ref": ref, "digestSha256": h(token or ref), "observedAt": at}


def event(event_id: str, kind: str, at: str, **extra: object) -> dict[str, object]:
    return {"eventId": event_id, "kind": kind, "source": source(f"slack:{event_id}", at, event_id), **extra}


def facts() -> dict[str, object]:
    return {
        "source": source("issue:123", "2026-09-14T00:40:00Z", "facts"),
        "freshUntil": "2026-09-15T00:00:00Z",
        "deadline": "2026-09-16T00:00:00Z",
        "eligibility": {"status": "ELIGIBLE", "evidenceSha256": h("eligible")},
        "value": {"currency": "USD", "amountMinor": 250000, "probabilityBps": 5000,
                  "probabilityEvidenceSha256": h("probability")},
        "capacity": {"engineering": 1},
        "blockers": [],
        "dependsOn": [],
        "exclusiveGroup": None,
        "labels": ["revenue"],
    }


def packet(events: list[dict[str, object]] | None = None, *, custody: bool = True,
           status: bool = True) -> dict[str, object]:
    return {
        "schema": "commons-opportunity-portfolio-intake/v1",
        "actorSeat": "ZEP-B4N8",
        "capacities": {"engineering": 4},
        "currencyPriority": ["USD"],
        "snapshot": {
            "custodyComplete": custody,
            "statusComplete": status,
            "source": source("snapshot:1", "2026-09-14T01:00:00Z", "snapshot"),
        },
        "opportunities": [{"id": "opp-1", "title": "Paid lane", "facts": facts(),
                           "events": events or []}],
    }


TEST_HOST_KEY = "4b" * 32
os.environ[SNAPSHOT_AUTHORITY_KEY_ENV] = TEST_HOST_KEY
AUTHORITY_ISSUED = "2026-09-14T01:00:30Z"

def trusted_authority(payload: dict[str, object], *, authority_id: str = "test-authority",
                      generation: str = "g1") -> dict[str, object]:
    return issue_host_snapshot_authority(
        payload,
        authority_id=authority_id,
        generation=generation,
        issued_at_utc=AUTHORITY_ISSUED,
    )


TRUSTED = "2026-09-14T01:01:00Z"


class IntakeTests(unittest.TestCase):
    def compile(self, events=None, **kwargs):
        p = packet(events, **kwargs)
        return compile_intake(p, trusted_as_of=TRUSTED,
                              trusted_snapshot_authority=trusted_authority(p))

    def item(self, receipt):
        return receipt["portfolioInput"]["opportunities"][0]

    def blockers(self, receipt):
        return {b["code"]: b["status"] for b in self.item(receipt)["blockers"]}

    def test_available_without_claim_with_trusted_complete_snapshot(self):
        receipt = self.compile()
        self.assertEqual(self.item(receipt)["owner"], {"status": "AVAILABLE", "seat": None})
        self.assertTrue(receipt["snapshotAuthority"]["trusted"])

    def test_packet_completeness_without_authority_fails_closed(self):
        receipt = compile_intake(packet(), trusted_as_of=TRUSTED)
        self.assertEqual(self.item(receipt)["owner"], {"status": "UNKNOWN", "seat": None})
        self.assertEqual(self.blockers(receipt)["CUSTODY-INCOMPLETE"], "OPEN")
        self.assertEqual(self.blockers(receipt)["STATUS-INCOMPLETE"], "OPEN")
        self.assertFalse(receipt["snapshotAuthority"]["trusted"])
        self.assertFalse(receipt["snapshotAuthority"]["effectiveCustodyComplete"])
        self.assertFalse(receipt["snapshotAuthority"]["effectiveStatusComplete"])

    def test_plain_second_mapping_cannot_self_authenticate(self):
        p = packet()
        forged = trusted_authority(p)
        forged["macSha256"] = "0" * 64
        with self.assertRaisesRegex(IntakeError, "MAC does not match host capability"):
            compile_intake(p, trusted_as_of=TRUSTED, trusted_snapshot_authority=forged)

    def test_missing_host_capability_cannot_consume_valid_authority(self):
        p = packet()
        authority = trusted_authority(p)
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(IntakeError, "capability is not provisioned"):
                compile_intake(p, trusted_as_of=TRUSTED, trusted_snapshot_authority=authority)

    def test_wrong_host_capability_cannot_consume_valid_authority(self):
        p = packet()
        authority = trusted_authority(p)
        with mock.patch.dict(os.environ, {SNAPSHOT_AUTHORITY_KEY_ENV: "5c" * 32}, clear=False):
            with self.assertRaisesRegex(IntakeError, "MAC does not match host capability"):
                compile_intake(p, trusted_as_of=TRUSTED, trusted_snapshot_authority=authority)


    def test_actor_identity_transplant_cannot_relabel_foreign_take(self):
        p = packet([event("e1", "TAKE", "2026-09-14T00:50:00Z", actorSeat="OTHER-1")])
        p["actorSeat"] = "REAL-1"
        authority = trusted_authority(p)
        transplanted = deepcopy(p)
        transplanted["actorSeat"] = "OTHER-1"
        with self.assertRaisesRegex(IntakeError, "actorSeat does not match"):
            compile_intake(transplanted, trusted_as_of=TRUSTED, trusted_snapshot_authority=authority)

    def test_stale_complete_snapshot_cannot_manufacture_current_available(self):
        p = packet()
        authority = trusted_authority(p)
        with self.assertRaisesRegex(IntakeError, "older than 300 seconds"):
            compile_intake(p, trusted_as_of="2026-09-14T01:10:00Z", trusted_snapshot_authority=authority)

    def test_module_authority_rebinding_and_mutation_cannot_widen_receipt(self):
        injected = {"sendAuthorized": True}
        fw._AUTHORITY = injected
        try:
            injected["contactAuthorized"] = True
            p = packet()
            authority = trusted_authority(p)
            receipt = compile_intake(p, trusted_as_of=TRUSTED, trusted_snapshot_authority=authority)
            self.assertFalse(any(receipt["authority"].values()))
            self.assertEqual(
                verify_receipt(receipt, trusted_snapshot_authority=authority)["receiptDigestSha256"],
                receipt["receiptDigestSha256"],
            )
        finally:
            del fw._AUTHORITY

    def test_this_seat_take(self):
        r = self.compile([event("e1", "TAKE", "2026-09-14T00:50:00Z", actorSeat="ZEP-B4N8")])
        self.assertEqual(self.item(r)["owner"], {"status": "OWNED_BY_THIS_SEAT", "seat": "ZEP-B4N8"})

    def test_other_seat_take(self):
        r = self.compile([event("e1", "TAKE", "2026-09-14T00:50:00Z", actorSeat="OTHER-1")])
        self.assertEqual(self.item(r)["owner"], {"status": "OWNED_BY_OTHER", "seat": "OTHER-1"})

    def test_take_then_release_becomes_available(self):
        r = self.compile([
            event("e1", "TAKE", "2026-09-14T00:49:00Z", actorSeat="A-1"),
            event("e2", "RELEASE", "2026-09-14T00:51:00Z", actorSeat="A-1"),
        ])
        self.assertEqual(self.item(r)["owner"]["status"], "AVAILABLE")

    def test_owner_collision_fails_closed(self):
        r = self.compile([
            event("e1", "TAKE", "2026-09-14T00:49:00Z", actorSeat="A-1"),
            event("e2", "TAKE", "2026-09-14T00:51:00Z", actorSeat="B-1"),
        ])
        self.assertEqual(self.item(r)["owner"]["status"], "UNKNOWN")
        self.assertEqual(self.blockers(r)["OWNER-COLLISION"], "OPEN")

    def test_same_timestamp_take_release_fails_closed(self):
        r = self.compile([
            event("a-release", "RELEASE", "2026-09-14T00:50:00Z", actorSeat="A-1"),
            event("z-take", "TAKE", "2026-09-14T00:50:00Z", actorSeat="A-1"),
        ])
        self.assertEqual(self.item(r)["owner"]["status"], "UNKNOWN")
        self.assertEqual(self.blockers(r)["CUSTODY-HISTORY-CONFLICT"], "OPEN")

    def test_unmatched_release_marks_conflict(self):
        r = self.compile([event("e1", "RELEASE", "2026-09-14T00:51:00Z", actorSeat="A-1")])
        self.assertEqual(self.blockers(r)["CUSTODY-HISTORY-CONFLICT"], "OPEN")

    def test_exact_event_replay_collapses(self):
        e = event("e1", "TAKE", "2026-09-14T00:50:00Z", actorSeat="A-1")
        r = self.compile([e, deepcopy(e)])
        self.assertEqual(r["folds"][0]["eventIds"], ["e1"])

    def test_changed_event_id_payload_rejected(self):
        a = event("e1", "TAKE", "2026-09-14T00:50:00Z", actorSeat="A-1")
        b = event("e1", "TAKE", "2026-09-14T00:50:00Z", actorSeat="B-1")
        with self.assertRaisesRegex(IntakeError, "changed payload reused eventId"):
            p = packet([a, b])
            compile_intake(p, trusted_as_of=TRUSTED, trusted_snapshot_authority=trusted_authority(p))

    def test_dnr_survives_internal_take(self):
        r = self.compile([
            event("e1", "DNR", "2026-09-14T00:45:00Z", origin="BUYER"),
            event("e2", "TAKE", "2026-09-14T00:50:00Z", actorSeat="ZEP-B4N8"),
        ])
        self.assertEqual(self.blockers(r)["DNR"], "OPEN")

    def test_only_buyer_reopen_clears_dnr(self):
        r = self.compile([
            event("e1", "DNR", "2026-09-14T00:45:00Z", origin="BUYER"),
            event("e2", "BUYER_REOPEN", "2026-09-14T00:55:00Z", origin="BUYER"),
        ])
        self.assertEqual(self.blockers(r)["DNR"], "RESOLVED")

    def test_buyer_reopen_without_dnr_marks_status_conflict(self):
        r = self.compile([event("e1", "BUYER_REOPEN", "2026-09-14T00:55:00Z", origin="BUYER")])
        self.assertEqual(self.blockers(r)["STATUS-HISTORY-CONFLICT"], "OPEN")

    def test_closed_and_shipped_terminal(self):
        r = self.compile([
            event("e1", "CLOSED", "2026-09-14T00:45:00Z"),
            event("e2", "SHIPPED", "2026-09-14T00:46:00Z"),
        ])
        self.assertEqual(self.blockers(r)["CLOSED"], "OPEN")
        self.assertEqual(self.blockers(r)["ALREADY-SHIPPED"], "OPEN")

    def test_trusted_incomplete_snapshot_adds_blockers(self):
        r = self.compile(custody=False, status=False)
        self.assertEqual(self.item(r)["owner"]["status"], "UNKNOWN")
        self.assertEqual(self.blockers(r)["CUSTODY-INCOMPLETE"], "OPEN")
        self.assertEqual(self.blockers(r)["STATUS-INCOMPLETE"], "OPEN")

    def test_packet_true_cannot_override_trusted_incomplete(self):
        authoritative = packet(custody=False, status=True)
        a = trusted_authority(authoritative)
        candidate = deepcopy(authoritative)
        candidate["snapshot"]["custodyComplete"] = True
        with self.assertRaisesRegex(IntakeError, "custodyComplete disagrees"):
            compile_intake(candidate, trusted_as_of=TRUSTED, trusted_snapshot_authority=a)

    def test_omitted_take_cannot_reuse_complete_authority(self):
        full = packet([event("e1", "TAKE", "2026-09-14T00:50:00Z", actorSeat="OTHER-1")])
        a = trusted_authority(full)
        omitted = deepcopy(full)
        omitted["opportunities"][0]["events"] = []
        with self.assertRaisesRegex(IntakeError, "event projection does not match"):
            compile_intake(omitted, trusted_as_of=TRUSTED, trusted_snapshot_authority=a)

    def test_omitted_dnr_cannot_reuse_complete_authority(self):
        full = packet([event("e1", "DNR", "2026-09-14T00:50:00Z", origin="BUYER")])
        a = trusted_authority(full)
        omitted = deepcopy(full)
        omitted["opportunities"][0]["events"] = []
        with self.assertRaisesRegex(IntakeError, "event projection does not match"):
            compile_intake(omitted, trusted_as_of=TRUSTED, trusted_snapshot_authority=a)

    def test_omitted_opportunity_cannot_reuse_complete_authority(self):
        p = packet()
        second = deepcopy(p["opportunities"][0])
        second["id"] = "opp-2"
        second["title"] = "Second lane"
        second["events"] = [event("e2", "DNR", "2026-09-14T00:50:00Z", origin="BUYER")]
        p["opportunities"].append(second)
        a = trusted_authority(p)
        omitted = deepcopy(p)
        omitted["opportunities"].pop()
        with self.assertRaisesRegex(IntakeError, "event projection does not match|opportunity count"):
            compile_intake(omitted, trusted_as_of=TRUSTED, trusted_snapshot_authority=a)

    def test_snapshot_source_reseal_cannot_reuse_authority(self):
        p = packet()
        a = trusted_authority(p)
        p["snapshot"]["source"]["digestSha256"] = h("forged-snapshot")
        with self.assertRaisesRegex(IntakeError, "source does not match"):
            compile_intake(p, trusted_as_of=TRUSTED, trusted_snapshot_authority=a)

    def test_cross_snapshot_authority_transplant_fails(self):
        first = packet([event("e1", "TAKE", "2026-09-14T00:50:00Z", actorSeat="A-1")])
        second = packet([event("e2", "DNR", "2026-09-14T00:50:00Z", origin="BUYER")])
        a = trusted_authority(first)
        with self.assertRaisesRegex(IntakeError, "event projection does not match"):
            compile_intake(second, trusted_as_of=TRUSTED, trusted_snapshot_authority=a)

    def test_authority_unknown_field_rejected(self):
        p = packet()
        a = trusted_authority(p)
        a["callerOverride"] = True
        with self.assertRaisesRegex(IntakeError, "fields differ"):
            compile_intake(p, trusted_as_of=TRUSTED, trusted_snapshot_authority=a)

    def test_authority_count_type_bool_rejected(self):
        p = packet()
        a = trusted_authority(p)
        a["eventCount"] = False
        with self.assertRaisesRegex(IntakeError, "non-negative integer"):
            compile_intake(p, trusted_as_of=TRUSTED, trusted_snapshot_authority=a)

    def test_event_newer_than_snapshot_rejected(self):
        p = packet([event("e1", "TAKE", "2026-09-14T01:00:30Z", actorSeat="A-1")])
        a = trusted_authority(p)
        with self.assertRaisesRegex(IntakeError, "newer than snapshot"):
            compile_intake(p, trusted_as_of="2026-09-14T01:04:00Z", trusted_snapshot_authority=a)

    def test_snapshot_future_rejected(self):
        p = packet()
        p["snapshot"]["source"]["observedAt"] = "2026-09-14T01:02:00Z"
        with self.assertRaisesRegex(IntakeError, "snapshot.*future"):
            compile_intake(p, trusted_as_of=TRUSTED)

    def test_event_array_permutation_is_irrelevant(self):
        events = [
            event("e2", "RELEASE", "2026-09-14T00:55:00Z", actorSeat="A-1"),
            event("e1", "TAKE", "2026-09-14T00:45:00Z", actorSeat="A-1"),
        ]
        p1 = packet(events)
        p2 = packet(list(reversed(events)))
        r1 = compile_intake(p1, trusted_as_of=TRUSTED, trusted_snapshot_authority=trusted_authority(p1))
        r2 = compile_intake(p2, trusted_as_of=TRUSTED, trusted_snapshot_authority=trusted_authority(p2))
        self.assertEqual(r1["receiptDigestSha256"], r2["receiptDigestSha256"])

    def test_receipt_round_trip_requires_exact_external_authority(self):
        p = packet([event("e1", "TAKE", "2026-09-14T00:50:00Z", actorSeat="ZEP-B4N8")])
        a = trusted_authority(p)
        r = compile_intake(p, trusted_as_of=TRUSTED, trusted_snapshot_authority=a)
        self.assertEqual(verify_receipt(r, trusted_snapshot_authority=a)["receiptDigestSha256"], r["receiptDigestSha256"])
        with self.assertRaisesRegex(IntakeError, "trusted snapshot authority required"):
            verify_receipt(r)
        wrong = deepcopy(a)
        wrong["generation"] = "g2"
        with self.assertRaisesRegex(IntakeError, "digest mismatch"):
            verify_receipt(r, trusted_snapshot_authority=wrong)

    def test_untrusted_receipt_rejects_late_authority_injection(self):
        p = packet()
        r = compile_intake(p, trusted_as_of=TRUSTED)
        with self.assertRaisesRegex(IntakeError, "unexpected"):
            verify_receipt(r, trusted_snapshot_authority=trusted_authority(p))
        self.assertEqual(verify_receipt(r)["receiptDigestSha256"], r["receiptDigestSha256"])

    def test_receipt_tamper_detection(self):
        p = packet()
        a = trusted_authority(p)
        r = compile_intake(p, trusted_as_of=TRUSTED, trusted_snapshot_authority=a)
        tampered = deepcopy(r)
        tampered["authority"]["sendAuthorized"] = True
        with self.assertRaisesRegex(IntakeError, "digest mismatch"):
            verify_receipt(tampered, trusted_snapshot_authority=a)

    def test_authority_ceiling_all_false(self):
        r = self.compile()
        self.assertTrue(r["authority"])
        self.assertFalse(any(r["authority"].values()))

    def test_normalization_deterministic(self):
        p = packet()
        self.assertEqual(normalize_intake(p), normalize_intake(json.loads(json.dumps(p))))

    def test_duplicate_json_key_hook_rejects(self):
        with self.assertRaisesRegex(IntakeError, "duplicate JSON key"):
            _pairs([("a", 1), ("a", 2)])

    def test_secret_shaped_event_reference_rejected(self):
        p = packet([event("e1", "TAKE", "2026-09-14T00:50:00Z", actorSeat="A-1")])
        p["opportunities"][0]["events"][0]["source"]["ref"] = ('xoxb' + '-12345678901234567890-SECRET')
        with self.assertRaisesRegex(IntakeError, "secret-shaped"):
            compile_intake(p, trusted_as_of=TRUSTED)

    def test_downstream_allocator_actually_invoked(self):
        r = self.compile()
        self.assertRegex(r["allocatorReceiptDigestSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(r["portfolioInput"]["schema"], "commons-opportunity-portfolio/v1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
