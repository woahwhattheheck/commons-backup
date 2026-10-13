#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest

import compiler
from authority_test_helpers import T1, clean_pair, compile_current_at, load_authority, load_candidate

class EvidenceAuthorityContractCoreTests(unittest.TestCase):
    def test_trusted_baseline_exact_holds_and_commercial_terms(self) -> None:
        candidate, authority = load_candidate(), load_authority()
        root = compiler.authority_root_sha256(authority)
        report = compile_current_at(candidate, authority, root)
        self.assertEqual(
            report["status_counts"],
            {
                "HOLD_CONFLICT": 1,
                "HOLD_MISSING_EVIDENCE": 1,
                "HOLD_STALE_EVIDENCE": 1,
                "READY": 9,
            },
        )
        self.assertEqual(report["aggregate_state"], "HOLD_FOR_PRIME_EVIDENCE_RECONCILIATION")
        self.assertEqual(report["commercial_terms"]["base_fee_usd"], 24_000)
        self.assertEqual(report["commercial_terms"]["optional_readout_support_usd"], 4_000)
        self.assertFalse(report["trust"]["current_evidence_review_authority"])
        self.assertTrue(all(value is False for value in report["external_authority"].values()))
        for cell in report["assessment_matrix"]:
            if cell["status"] != "READY":
                self.assertIsNone(cell["maturity"])
                self.assertIsNone(cell["confidence_bp"])

    def test_public_untrusted_path_cannot_mint_ready(self) -> None:
        candidate, authority = clean_pair()
        report = compiler.compile_untrusted_inspection(candidate, authority, now=T1)
        self.assertEqual(report["aggregate_state"], "HOLD_TRUSTED_AUTHORITY_REQUIRED")
        self.assertFalse(report["trust"]["current_evidence_review_authority"])
        self.assertEqual(report["status_counts"], {"UNTRUSTED_EVIDENCE_CONSISTENT": 12})
        self.assertTrue(all(row["maturity"] is None for row in report["assessment_matrix"]))

    def test_twelve_fabricated_clean_rows_without_pinned_root_cannot_ready(self) -> None:
        candidate, authority = clean_pair()
        for row in authority["sources"]:
            row["claim"] = "Caller-authored fabricated clean claim for " + row["source_id"]
            row["source_content_sha256"] = compiler._sha256_bytes(row["claim"].encode())
            row["maturity"] = 4
            row["confidence_bp"] = 10_000
        report = compiler.compile_untrusted_inspection(candidate, authority, now=T1)
        self.assertEqual(report["aggregate_state"], "HOLD_TRUSTED_AUTHORITY_REQUIRED")
        self.assertFalse(report["trust"]["authority_root_supplied_out_of_band"])
        self.assertFalse(report["trust"]["current_evidence_review_authority"])

    def test_independently_pinned_clean_authority_can_ready(self) -> None:
        candidate, authority = clean_pair()
        root = compiler.authority_root_sha256(authority)
        report = compile_current_at(candidate, authority, root)
        self.assertEqual(report["status_counts"], {"READY": 12})
        self.assertEqual(report["aggregate_state"], "READY_FOR_PRIME_TEAMING_REVIEW")
        self.assertTrue(report["trust"]["current_evidence_review_authority"])
        self.assertFalse(report["trust"]["module_authenticates_root_provenance"])

    def test_coupled_claim_score_confidence_and_digest_mutation_fails_old_root(self) -> None:
        candidate, authority = clean_pair()
        root = compiler.authority_root_sha256(authority)
        mutated = copy.deepcopy(authority)
        row = mutated["sources"][0]
        row["claim"] += " altered"
        row["source_content_sha256"] = compiler._sha256_bytes(row["claim"].encode())
        row["maturity"] = (row["maturity"] + 1) % 5
        row["confidence_bp"] = 9999
        with self.assertRaisesRegex(compiler.ContractError, "trusted authority root mismatch"):
            compile_current_at(candidate, mutated, root)

    def test_source_transplant_across_group_fails_retained_root(self) -> None:
        candidate, authority = clean_pair()
        root = compiler.authority_root_sha256(authority)
        mutated = copy.deepcopy(authority)
        mutated["sources"][0]["group"] = "RIS"
        with self.assertRaisesRegex(compiler.ContractError, "trusted authority root mismatch"):
            compile_current_at(candidate, mutated, root)

    def test_prime_and_generation_transplant_rejected_semantically(self) -> None:
        candidate, authority = clean_pair()
        mutated = copy.deepcopy(authority)
        mutated["sources"][0]["prime_candidate"] = "Other Prime"
        with self.assertRaisesRegex(compiler.ContractError, "prime_candidate mismatch"):
            compiler.authority_root_sha256(mutated)
        mutated = copy.deepcopy(authority)
        mutated["sources"][0]["authority_generation"] = "other-generation"
        with self.assertRaisesRegex(compiler.ContractError, "authority_generation mismatch"):
            compiler.authority_root_sha256(mutated)

    def test_source_universe_shrink_and_expansion_rejected(self) -> None:
        candidate, authority = clean_pair()
        root = compiler.authority_root_sha256(authority)
        shrunk = copy.deepcopy(candidate)
        shrunk["source_ids"].pop()
        with self.assertRaisesRegex(compiler.ContractError, "source universe mismatch"):
            compile_current_at(shrunk, authority, root)
        expanded = copy.deepcopy(candidate)
        expanded["source_ids"].append("FAKE-EXTRA-01")
        with self.assertRaisesRegex(compiler.ContractError, "source universe mismatch"):
            compile_current_at(expanded, authority, root)

    def test_wrong_and_missing_trusted_root_rejected(self) -> None:
        candidate, authority = clean_pair()
        with self.assertRaisesRegex(compiler.ContractError, "root mismatch"):
            compile_current_at(candidate, authority, "0" * 64)
        with self.assertRaisesRegex(compiler.ContractError, "required out of band"):
            compile_current_at(candidate, authority, None)  # type: ignore[arg-type]

    def test_future_source_rejected(self) -> None:
        candidate, authority = clean_pair()
        authority["sources"][0]["observed_at"] = "2026-09-14T15:00:00Z"
        root = compiler.authority_root_sha256(authority)
        with self.assertRaisesRegex(compiler.ContractError, "future source evidence"):
            compile_current_at(candidate, authority, root)

