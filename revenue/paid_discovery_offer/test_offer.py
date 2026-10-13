from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from revenue.paid_discovery_offer import engine


def d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def candidate_at(now: datetime):
    now = now.astimezone(timezone.utc).replace(microsecond=0)
    c = {
        "version": engine.INPUT_VERSION,
        "offer_id": "offer-ACME-001",
        "opportunity": {
            "opportunity_id": "opp-ACME-001",
            "buyer_scope_id": "buyer-scope-ACME",
            "generation": 7,
            "complete": True,
            "captured_at": ts(now - timedelta(hours=1)),
            "valid_until": ts(now + timedelta(days=7)),
            "source_digest": d("opportunity-source"),
        },
        "positive_inbound": {
            "inbound_id": "inbound-001",
            "opportunity_id": "opp-ACME-001",
            "buyer_scope_id": "buyer-scope-ACME",
            "signal": "VERIFIED_HUMAN_POSITIVE",
            "intent_code": "REQUESTED_DISCOVERY",
            "occurred_at": ts(now - timedelta(minutes=30)),
            "captured_at": ts(now - timedelta(minutes=29)),
            "source_digest": d("inbound-source"),
        },
        "custody": {
            "custody_id": "custody-001",
            "opportunity_id": "opp-ACME-001",
            "buyer_scope_id": "buyer-scope-ACME",
            "operation_id": "paid-discovery-ACME-001",
            "owner_seat": "ZIS-F2Q8",
            "generation": 3,
            "state": "ACTIVE_EXCLUSIVE",
            "complete": True,
            "acquired_at": ts(now - timedelta(hours=2)),
            "expires_at": ts(now + timedelta(days=2)),
            "source_digest": d("custody-source"),
        },
        "capabilities": [
            {
                "capability_id": "cap-audit",
                "carrier_ref": "commons-pr-14001",
                "carrier_digest": d("carrier-audit"),
                "state": "LANDED_VERIFIED",
                "verified_at": ts(now - timedelta(hours=3)),
                "evidence_digest": d("evidence-audit"),
            },
            {
                "capability_id": "cap-report",
                "carrier_ref": "commons-pr-14002",
                "carrier_digest": d("carrier-report"),
                "state": "LANDED_VERIFIED",
                "verified_at": ts(now - timedelta(hours=3)),
                "evidence_digest": d("evidence-report"),
            },
        ],
        "commercial_policy": {
            "policy_id": "policy-discovery-v4",
            "generation": 4,
            "currency": "USD",
            "min_price_minor": 250000,
            "min_upfront_bps": 5000,
            "max_duration_days": 10,
            "max_scope_items": 4,
            "custom_work_before_payment_allowed": False,
            "free_discovery_allowed": False,
            "complete": True,
            "effective_at": ts(now - timedelta(days=1)),
            "expires_at": ts(now + timedelta(days=30)),
            "source_digest": d("policy-source"),
        },
        "proposed_offer": {
            "currency": "USD",
            "price_minor": 300000,
            "upfront_minor": 150000,
            "duration_days": 5,
            "prepayment_required": True,
            "scope_items": [
                {
                    "item_id": "scope-1",
                    "deliverable": "Reproduce and bound the observed failure mode against supplied fixtures.",
                    "acceptance_evidence": "Deterministic replay receipt and root-cause table are present.",
                    "capability_ids": ["cap-audit"],
                },
                {
                    "item_id": "scope-2",
                    "deliverable": "Deliver a prioritized remediation packet without production mutation.",
                    "acceptance_evidence": "Owner-readable remediation packet cites every retained evidence digest.",
                    "capability_ids": ["cap-report"],
                },
            ],
            "buyer_inputs": ["Representative fixtures with synthetic identifiers.", "A written success condition for the discovery phase."],
            "exclusions": ["Production deployment or provider mutation.", "External messaging, contracting, payment capture, or implementation work."],
        },
    }
    return c


def roots_for(c, captured_at: datetime):
    return {
        "version": engine.ROOTS_VERSION,
        "authority_generation": "roots-gen-17",
        "captured_at": ts(captured_at),
        "opportunity_root": engine._sha256_value(c["opportunity"]),
        "positive_inbound_root": engine._sha256_value(c["positive_inbound"]),
        "custody_root": engine._sha256_value(c["custody"]),
        "capabilities_root": engine._sha256_value(c["capabilities"]),
        "commercial_policy_root": engine._sha256_value(c["commercial_policy"]),
    }


class OfferTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.c = candidate_at(self.now)
        self.r = roots_for(self.c, self.now - timedelta(minutes=5))

    def compile(self, c=None, r=None):
        return engine._base_packet(
            engine._validate_candidate(c or self.c),
            engine._validate_roots(r or self.r),
            self.now,
            "CURRENT",
        )

    def reroot(self, c):
        return roots_for(c, self.now - timedelta(minutes=5))

    def assertHold(self, reason, c=None, r=None):
        p = self.compile(c, r)
        self.assertEqual(engine.HOLD, p["decision"])
        self.assertIn(reason, p["reasons"])
        return p

    def test_ready_for_owner_review_only(self):
        p = self.compile()
        self.assertEqual(engine.READY, p["decision"])
        self.assertEqual([], p["reasons"])
        self.assertTrue(all(v is False for v in p["authority"].values()))

    def test_audit_never_emits_current_authority(self):
        p = engine.audit_at(self.c, self.r, ts(self.now))
        self.assertEqual(engine.HISTORICAL, p["decision"])
        self.assertEqual(engine.READY, p["historical_assessment"])

    def test_historical_is_deterministic(self):
        a = engine.audit_at(self.c, self.r, ts(self.now))
        b = engine.audit_at(copy.deepcopy(self.c), copy.deepcopy(self.r), ts(self.now))
        self.assertEqual(engine.canonical_json(a), engine.canonical_json(b))

    def test_verify_historical(self):
        p = engine.audit_at(self.c, self.r, ts(self.now))
        self.assertTrue(engine.verify_historical(self.c, self.r, p))

    def test_verify_current(self):
        with mock.patch.object(engine, "datetime") as dt:
            dt.now.return_value = self.now
            dt.side_effect = lambda *a, **k: datetime(*a, **k)
            dt.strptime = datetime.strptime
            p = engine.compile_current(self.c, self.r)
        with mock.patch.object(engine, "datetime") as dt:
            dt.now.return_value = self.now
            dt.side_effect = lambda *a, **k: datetime(*a, **k)
            dt.strptime = datetime.strptime
            self.assertTrue(engine.verify_current(self.c, self.r, p))

    def test_underprice_holds(self):
        c = copy.deepcopy(self.c); c["proposed_offer"]["price_minor"] = 249999
        self.assertHold("PRICE_BELOW_POLICY_FLOOR", c, self.reroot(c))

    def test_under_upfront_holds(self):
        c = copy.deepcopy(self.c); c["proposed_offer"]["upfront_minor"] = 149999
        self.assertHold("UPFRONT_BELOW_POLICY_FLOOR", c, self.reroot(c))

    def test_no_prepayment_holds(self):
        c = copy.deepcopy(self.c); c["proposed_offer"]["prepayment_required"] = False
        self.assertHold("PREPAYMENT_NOT_REQUIRED", c, self.reroot(c))

    def test_duration_holds(self):
        c = copy.deepcopy(self.c); c["proposed_offer"]["duration_days"] = 11
        self.assertHold("DURATION_EXCEEDS_POLICY", c, self.reroot(c))

    def test_scope_count_holds(self):
        c = copy.deepcopy(self.c)
        c["commercial_policy"]["max_scope_items"] = 1
        self.assertHold("SCOPE_EXCEEDS_POLICY", c, self.reroot(c))

    def test_missing_acceptance_evidence_holds(self):
        c = copy.deepcopy(self.c); c["proposed_offer"]["scope_items"][0]["acceptance_evidence"] = ""
        self.assertHold("MISSING_ACCEPTANCE_EVIDENCE", c, self.reroot(c))

    def test_missing_capability_holds(self):
        c = copy.deepcopy(self.c); c["proposed_offer"]["scope_items"][0]["capability_ids"] = ["cap-missing"]
        self.assertHold("CAPABILITY_UNVERIFIED", c, self.reroot(c))

    def test_unverified_capability_holds(self):
        c = copy.deepcopy(self.c); c["capabilities"][0]["state"] = "UNVERIFIED"
        self.assertHold("CAPABILITY_UNVERIFIED", c, self.reroot(c))

    def test_future_capability_verification_holds(self):
        c = copy.deepcopy(self.c); c["capabilities"][0]["verified_at"] = ts(self.now + timedelta(seconds=1))
        self.assertHold("CAPABILITY_VERIFICATION_FROM_FUTURE", c, self.reroot(c))

    def test_unverified_inbound_holds(self):
        c = copy.deepcopy(self.c); c["positive_inbound"]["signal"] = "AMBIGUOUS"
        self.assertHold("POSITIVE_INBOUND_UNVERIFIED", c, self.reroot(c))

    def test_stale_inbound_holds(self):
        c = copy.deepcopy(self.c)
        c["positive_inbound"]["occurred_at"] = ts(self.now - timedelta(days=15))
        c["positive_inbound"]["captured_at"] = ts(self.now - timedelta(days=15) + timedelta(minutes=1))
        self.assertHold("POSITIVE_INBOUND_STALE", c, self.reroot(c))

    def test_inbound_bad_chronology_holds(self):
        c = copy.deepcopy(self.c); c["positive_inbound"]["captured_at"] = ts(self.now - timedelta(hours=1))
        self.assertHold("INBOUND_CHRONOLOGY_INVALID", c, self.reroot(c))

    def test_expired_custody_holds(self):
        c = copy.deepcopy(self.c); c["custody"]["expires_at"] = ts(self.now)
        self.assertHold("CUSTODY_EXPIRED", c, self.reroot(c))

    def test_conflicted_custody_holds(self):
        c = copy.deepcopy(self.c); c["custody"]["state"] = "CONFLICT"
        self.assertHold("CUSTODY_NOT_EXCLUSIVE", c, self.reroot(c))

    def test_incomplete_custody_holds(self):
        c = copy.deepcopy(self.c); c["custody"]["complete"] = False
        self.assertHold("CUSTODY_CENSUS_INCOMPLETE", c, self.reroot(c))

    def test_expired_opportunity_holds(self):
        c = copy.deepcopy(self.c); c["opportunity"]["valid_until"] = ts(self.now)
        self.assertHold("OPPORTUNITY_EXPIRED", c, self.reroot(c))

    def test_incomplete_opportunity_holds(self):
        c = copy.deepcopy(self.c); c["opportunity"]["complete"] = False
        self.assertHold("OPPORTUNITY_INCOMPLETE", c, self.reroot(c))

    def test_opportunity_binding_holds(self):
        c = copy.deepcopy(self.c); c["positive_inbound"]["opportunity_id"] = "opp-OTHER"
        self.assertHold("OPPORTUNITY_BINDING_MISMATCH", c, self.reroot(c))

    def test_buyer_scope_binding_holds(self):
        c = copy.deepcopy(self.c); c["custody"]["buyer_scope_id"] = "buyer-scope-OTHER"
        self.assertHold("BUYER_SCOPE_BINDING_MISMATCH", c, self.reroot(c))

    def test_root_mismatch_holds(self):
        r = copy.deepcopy(self.r); r["custody_root"] = d("wrong")
        self.assertHold("AUTHORITY_ROOT_MISMATCH", self.c, r)

    def test_stale_roots_hold(self):
        r = roots_for(self.c, self.now - timedelta(days=31))
        self.assertHold("AUTHORITY_ROOTS_STALE", self.c, r)

    def test_future_roots_hold(self):
        r = roots_for(self.c, self.now + timedelta(seconds=1))
        self.assertHold("AUTHORITY_ROOTS_FROM_FUTURE", self.c, r)

    def test_free_custom_work_policy_holds(self):
        c = copy.deepcopy(self.c); c["commercial_policy"]["custom_work_before_payment_allowed"] = True
        self.assertHold("FREE_CUSTOM_WORK_POLICY_FORBIDDEN", c, self.reroot(c))

    def test_free_discovery_policy_holds(self):
        c = copy.deepcopy(self.c); c["commercial_policy"]["free_discovery_allowed"] = True
        self.assertHold("FREE_CUSTOM_WORK_POLICY_FORBIDDEN", c, self.reroot(c))

    def test_expired_policy_holds(self):
        c = copy.deepcopy(self.c); c["commercial_policy"]["expires_at"] = ts(self.now)
        self.assertHold("COMMERCIAL_POLICY_EXPIRED", c, self.reroot(c))

    def test_future_policy_holds(self):
        c = copy.deepcopy(self.c); c["commercial_policy"]["effective_at"] = ts(self.now + timedelta(seconds=1))
        self.assertHold("COMMERCIAL_POLICY_NOT_YET_EFFECTIVE", c, self.reroot(c))

    def test_currency_mismatch_holds(self):
        c = copy.deepcopy(self.c); c["proposed_offer"]["currency"] = "EUR"
        self.assertHold("CURRENCY_MISMATCH", c, self.reroot(c))

    def test_duplicate_capability_is_structural_error(self):
        c = copy.deepcopy(self.c); c["capabilities"].append(copy.deepcopy(c["capabilities"][0]))
        with self.assertRaises(engine.OfferError): engine.compile_current(c, self.reroot(c))

    def test_unknown_field_rejected(self):
        c = copy.deepcopy(self.c); c["surprise"] = True
        with self.assertRaises(engine.OfferError): engine.compile_current(c, self.r)

    def test_bool_money_rejected(self):
        c = copy.deepcopy(self.c); c["proposed_offer"]["price_minor"] = True
        with self.assertRaises(engine.OfferError): engine.compile_current(c, self.reroot(c))

    def test_unsafe_integer_rejected(self):
        c = copy.deepcopy(self.c); c["proposed_offer"]["price_minor"] = engine.MAX_SAFE_INTEGER + 1
        with self.assertRaises(engine.OfferError): engine.compile_current(c, self.reroot(c))

    def test_noncanonical_timestamp_rejected(self):
        c = copy.deepcopy(self.c); c["custody"]["expires_at"] = "2026-09-14T12:00:00+00:00"
        with self.assertRaises(engine.OfferError): engine.compile_current(c, self.reroot(c))

    def test_email_in_scope_rejected(self):
        c = copy.deepcopy(self.c); c["proposed_offer"]["buyer_inputs"][0] = "Email alice@example.com the fixture."
        with self.assertRaises(engine.OfferError): engine.compile_current(c, self.reroot(c))

    def test_url_in_scope_rejected(self):
        c = copy.deepcopy(self.c); c["proposed_offer"]["exclusions"][0] = "See https://example.com for details."
        with self.assertRaises(engine.OfferError): engine.compile_current(c, self.reroot(c))

    def test_secret_shaped_scope_rejected(self):
        c = copy.deepcopy(self.c); c["proposed_offer"]["buyer_inputs"][0] = "Provide the API key."
        with self.assertRaises(engine.OfferError): engine.compile_current(c, self.reroot(c))

    def test_bidi_text_rejected(self):
        c = copy.deepcopy(self.c); c["proposed_offer"]["exclusions"][0] = "safe\u202eevil"
        with self.assertRaises(engine.OfferError): engine.compile_current(c, self.reroot(c))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(engine.OfferError): engine.loads_strict('{"a":1,"a":2}')

    def test_json_float_rejected(self):
        with self.assertRaises(engine.OfferError): engine.loads_strict('{"a":1.5}')

    def test_json_nan_rejected(self):
        with self.assertRaises(engine.OfferError): engine.loads_strict('{"a":NaN}')

    def test_packet_tamper_rejected(self):
        p = engine.audit_at(self.c, self.r, ts(self.now)); p["commercial"]["price_minor"] += 1
        with self.assertRaises(engine.OfferError): engine.verify_historical(self.c, self.r, p)

    def test_input_change_invalidates_packet(self):
        p = engine.audit_at(self.c, self.r, ts(self.now))
        c = copy.deepcopy(self.c); c["proposed_offer"]["duration_days"] = 6
        self.assertFalse(engine.verify_historical(c, self.reroot(c), p))

    def test_current_verifier_rejects_historical_packet(self):
        p = engine.audit_at(self.c, self.r, ts(self.now))
        with self.assertRaises(engine.OfferError): engine.verify_current(self.c, self.r, p)

    def test_current_ready_packet_ages_out_after_fifteen_minutes(self):
        p = self.compile()
        later = self.now + timedelta(minutes=16)
        with mock.patch.object(engine, "datetime") as dt:
            dt.now.return_value = later
            dt.side_effect = lambda *a, **k: datetime(*a, **k)
            dt.strptime = datetime.strptime
            self.assertFalse(engine.verify_current(self.c, self.r, p))

    def test_markdown_states_authority_ceiling(self):
        md = engine.markdown(self.compile())
        self.assertIn("does **not** authorize external send", md)
        self.assertIn("READY_FOR_OWNER_PAID_DISCOVERY_REVIEW", md)
        self.assertNotIn("alice@example.com", md)

    def test_create_exclusive_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "bundle"
            result = engine.write_bundle(str(target), self.compile())
            self.assertTrue((target / "packet.json").is_file())
            self.assertTrue((target / "offer.md").is_file())
            self.assertEqual(self.compile()["receipt_sha256"], result["packet_receipt"])
            with self.assertRaises(engine.OfferError): engine.write_bundle(str(target), self.compile())

    @unittest.skipIf(not hasattr(os, "symlink"), "symlink unsupported")
    def test_strict_reader_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            real = Path(td) / "real.json"; real.write_text('{"a":1}', encoding="utf-8")
            link = Path(td) / "link.json"; os.symlink(real, link)
            with self.assertRaises(engine.OfferError): engine.read_strict_json_file(str(link))

    @unittest.skipIf(not hasattr(os, "link"), "hardlink unsupported")
    def test_strict_reader_rejects_hardlink(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a.json"; a.write_text('{"a":1}', encoding="utf-8")
            b = Path(td) / "b.json"; os.link(a, b)
            with self.assertRaises(engine.OfferError): engine.read_strict_json_file(str(a))

    def test_strict_reader_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "input.json"; p.write_text('{"a":1}', encoding="utf-8")
            self.assertEqual({"a": 1}, engine.read_strict_json_file(str(p)))


if __name__ == "__main__":
    unittest.main()
