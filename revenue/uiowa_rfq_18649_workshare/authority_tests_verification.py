#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest

import compiler
from authority_test_helpers import T1, clean_pair, compile_current_at, load_authority, load_candidate, verify_current_at

class EvidenceAuthorityVerificationTests(unittest.TestCase):
    def test_fresh_ready_becomes_current_hold_after_freshness_window(self) -> None:
        candidate, authority = clean_pair()
        root = compiler.authority_root_sha256(authority)
        report = compile_current_at(candidate, authority, root)
        self.assertTrue(report["trust"]["current_evidence_review_authority"])
        verification = verify_current_at(report, root, "2027-01-15T15:00:01Z")
        self.assertFalse(verification["current_evidence_review_authority"])
        self.assertEqual(verification["current_aggregate_state"], "HOLD_FOR_PRIME_EVIDENCE_RECONCILIATION")
        self.assertEqual(verification["current_status_counts"], {"HOLD_STALE_EVIDENCE": 12})

    def test_verifier_clock_cannot_precede_report(self) -> None:
        candidate, authority = clean_pair()
        root = compiler.authority_root_sha256(authority)
        report = compile_current_at(candidate, authority, root)
        with self.assertRaisesRegex(compiler.ContractError, "VERIFIER_TIME_BEFORE_REPORT"):
            verify_current_at(report, root, "2026-09-13T14:59:59Z")

    def test_historical_replay_is_deterministic_and_non_current(self) -> None:
        candidate, authority = clean_pair()
        root = compiler.authority_root_sha256(authority)
        one = compiler.compile_historical(candidate, authority, root, evaluated_at=T1)
        two = compiler.compile_historical(
            {**candidate, "source_ids": list(reversed(candidate["source_ids"]))},
            {**authority, "sources": list(reversed(authority["sources"]))},
            root,
            evaluated_at=T1,
        )
        self.assertEqual(compiler.canonical_json_bytes(one), compiler.canonical_json_bytes(two))
        self.assertEqual(one["aggregate_state"], "HISTORICAL_READY_NON_CURRENT")
        self.assertFalse(one["trust"]["current_evidence_review_authority"])
        self.assertEqual(one["status_counts"], {"HISTORICAL_READY_NON_CURRENT": 12})

    def test_report_receipt_detects_tamper(self) -> None:
        candidate, authority = clean_pair()
        root = compiler.authority_root_sha256(authority)
        report = compile_current_at(candidate, authority, root)
        tampered = copy.deepcopy(report)
        tampered["commercial_terms"]["base_fee_usd"] += 1
        with self.assertRaisesRegex(compiler.ContractError, "receipt mismatch"):
            compiler.verify_report_integrity(tampered, trusted_authority_sha256=root)

    def test_arbitrary_report_with_recomputed_checksum_fails_semantic_recompile(self) -> None:
        candidate, authority = clean_pair()
        root = compiler.authority_root_sha256(authority)
        report = compile_current_at(candidate, authority, root)
        tampered = copy.deepcopy(report)
        tampered["aggregate_state"] = "READY_FOR_UNIVERSITY_SUBMISSION"
        unsigned = dict(tampered)
        unsigned.pop("receipt_sha256")
        tampered["receipt_sha256"] = compiler._sha256_value(unsigned)
        with self.assertRaisesRegex(compiler.ContractError, "semantic recompile mismatch"):
            compiler.verify_report_integrity(tampered, trusted_authority_sha256=root)

    def test_integrity_only_never_claims_trusted_root(self) -> None:
        candidate, authority = clean_pair()
        root = compiler.authority_root_sha256(authority)
        report = compile_current_at(candidate, authority, root)
        result = compiler.verify_report_integrity(report)
        self.assertTrue(result["integrity_valid"])
        self.assertFalse(result["trusted_authority_root_verified"])
        self.assertFalse(result["current_authority_verified"])

    def test_duplicate_key_nonfinite_bool_and_unknown_fields_rejected(self) -> None:
        with self.assertRaisesRegex(compiler.ContractError, "duplicate JSON key"):
            compiler.loads_strict('{"schema":2,"schema":2}')
        with self.assertRaisesRegex(compiler.ContractError, "non-finite"):
            compiler.loads_strict('{"x":NaN}')
        candidate, authority = load_candidate(), load_authority()
        authority["sources"][0]["maturity"] = True
        with self.assertRaisesRegex(compiler.ContractError, "must be integer"):
            compiler.authority_root_sha256(authority)
        candidate = load_candidate()
        candidate["evaluation_date"] = "2020-01-01"
        with self.assertRaisesRegex(compiler.ContractError, "keys mismatch"):
            compiler.normalize_candidate(candidate)

    def test_commercial_drift_rejected(self) -> None:
        candidate = load_candidate()
        candidate["engagement"]["base_fee_usd"] = 23_999
        with self.assertRaisesRegex(compiler.ContractError, "base fee drift"):
            compiler.normalize_candidate(candidate)

    def test_returned_report_mutation_cannot_poison_later_compiles(self) -> None:
        candidate, authority = clean_pair()
        root = compiler.authority_root_sha256(authority)
        first = compile_current_at(candidate, authority, root)
        first["external_authority"]["contact_buyer"] = True
        first["commercial_terms"]["payment_schedule"][0]["amount_usd"] = 0
        first["deliverables"][0]["name"] = "POISON"
        first["prime_retains"].append("POISON")
        second = compile_current_at(candidate, authority, root)
        self.assertTrue(all(value is False for value in second["external_authority"].values()))
        self.assertEqual(second["commercial_terms"]["payment_schedule"][0]["amount_usd"], 9_600)
        self.assertNotEqual(second["deliverables"][0]["name"], "POISON")
        self.assertNotIn("POISON", second["prime_retains"])

    def test_source_order_and_candidate_order_are_canonical(self) -> None:
        candidate, authority = load_candidate(), load_authority()
        root = compiler.authority_root_sha256(authority)
        one = compile_current_at(candidate, authority, root)
        candidate["source_ids"].reverse()
        authority["sources"].reverse()
        two = compile_current_at(candidate, authority, root)
        self.assertEqual(compiler.canonical_json_bytes(one), compiler.canonical_json_bytes(two))


