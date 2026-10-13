# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import weed_evidence_certifier as gate
from weed_test_fixtures import *  # noqa: F403

class ExactReceiptVerificationTests(unittest.TestCase):
    def setUp(self):
        self.revision = "0123456789abcdef"
        self.receipt = gate.certify_bytes(
            FIXED_SPATIAL,
            FIXED_RUNTIME,
            config(False),
            entrypoint_source=FIXED_ENTRYPOINT,
            source_revision=self.revision,
        )

    def verify(self, receipt=None, *, cfg=None, entrypoint=None, revision=None):
        return gate.verify_receipt_against_bytes(
            self.receipt if receipt is None else receipt,
            FIXED_SPATIAL,
            FIXED_RUNTIME,
            config(False) if cfg is None else cfg,
            entrypoint_source=(
                FIXED_ENTRYPOINT if entrypoint is None else entrypoint
            ),
            source_revision=self.revision if revision is None else revision,
        )

    def test_exact_checkout_reanalysis_matches(self):
        self.assertEqual(self.verify(), [])

    def test_recomputed_forgery_is_rejected_by_reanalysis(self):
        forged = copy.deepcopy(self.receipt)
        forged["classification"] = gate.Semantics.EXPLICIT_W1.value
        forged["claimable_semantics"] = ["W1"]
        forged["promotion_eligible_as_w0"] = False
        forged["reason_codes"] = ["CONFIG_W1"]
        forged["receipt_id"] = gate.receipt_id(forged)
        errors = self.verify(forged)
        self.assertIn("RECEIPT_EXACT_REANALYSIS_MISMATCH", errors)

    def test_config_drift_is_rejected(self):
        errors = self.verify(cfg=config(True))
        self.assertIn("RECEIPT_EXACT_REANALYSIS_MISMATCH", errors)

    def test_entrypoint_drift_is_rejected(self):
        errors = self.verify(entrypoint=NO_FORWARD_ENTRYPOINT)
        self.assertIn("RECEIPT_EXACT_REANALYSIS_MISMATCH", errors)

    def test_revision_drift_is_rejected(self):
        errors = self.verify(revision="different-head")
        self.assertIn("RECEIPT_SOURCE_REVISION_MISMATCH", errors)

    def test_invalid_digest_format_is_rejected(self):
        malformed = copy.deepcopy(self.receipt)
        malformed["artifacts"]["runtime_config"]["sha256"] = "not-a-digest"
        malformed["receipt_id"] = gate.receipt_id(malformed)
        errors = self.verify(malformed)
        self.assertIn("RECEIPT_ARTIFACT_RUNTIME_CONFIG_SHA256_INVALID", errors)

    def test_certify_paths_uses_checkout_root_independent_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "arbitrary-worker-root"
            root.mkdir()
            spatial = root / "spatial_tempo.py"
            runtime = root / "titan_runtime.py"
            entrypoint = root / "main.py"
            cfg = root / "TITAN-CONFIG.json"
            spatial.write_bytes(FIXED_SPATIAL)
            runtime.write_bytes(FIXED_RUNTIME)
            entrypoint.write_bytes(FIXED_ENTRYPOINT)
            cfg.write_bytes(config(False))
            receipt = gate.certify_paths(
                spatial,
                runtime,
                cfg,
                entrypoint_path=entrypoint,
                source_revision=self.revision,
            )
            self.assertEqual(
                {row["path"] for row in receipt["artifacts"].values()},
                {"spatial_tempo.py", "titan_runtime.py", "main.py", "TITAN-CONFIG.json"},
            )


class ClaimGateTests(unittest.TestCase):
    def setUp(self):
        self.w0 = gate.certify_bytes(
            FIXED_SPATIAL,
            FIXED_RUNTIME,
            config(False),
            entrypoint_source=FIXED_ENTRYPOINT,
        )
        self.w1 = gate.certify_bytes(
            FIXED_SPATIAL,
            FIXED_RUNTIME,
            config(True),
            entrypoint_source=FIXED_ENTRYPOINT,
        )
        self.legacy = gate.certify_bytes(
            LEGACY_SPATIAL,
            LEGACY_RUNTIME,
            LEGACY_CONFIG,
            entrypoint_source=FIXED_ENTRYPOINT,
        )

    def claim(self, receipt, declared="W0", labels=()):
        return gate.build_claim(receipt, "panel-001", declared, labels)

    def test_matching_w0_claim_accepted(self):
        result = gate.gate_claim(self.w0, self.claim(self.w0, "W0", ["R0P0O0"]))
        self.assertEqual(result["decision"], gate.Decision.ACCEPT.value)

    def test_legacy_evidence_claimed_as_w0_is_quarantined(self):
        result = gate.gate_claim(self.legacy, self.claim(self.legacy, "W0", ["R0P0O0"]))
        self.assertEqual(result["decision"], gate.Decision.QUARANTINE.value)
        self.assertIn("FAIL_CLOSED_EVIDENCE_QUARANTINE", result["reason_codes"])

    def test_legacy_evidence_may_only_use_explicit_legacy_label(self):
        accepted = gate.gate_claim(
            self.legacy,
            self.claim(self.legacy, "LEGACY_PRE_GATE_W1", ["legacy-pre-gate"]),
        )
        self.assertEqual(accepted["decision"], gate.Decision.ACCEPT.value)
        rejected = gate.gate_claim(self.legacy, self.claim(self.legacy, "W1", ["W1"]))
        self.assertEqual(rejected["decision"], gate.Decision.QUARANTINE.value)

    def test_w1_cannot_be_labeled_w0(self):
        result = gate.gate_claim(self.w1, self.claim(self.w1, "W0", ["W0"]))
        self.assertEqual(result["decision"], gate.Decision.QUARANTINE.value)

    def test_tampered_receipt_is_invalid(self):
        tampered = copy.deepcopy(self.w0)
        tampered["classification"] = gate.Semantics.EXPLICIT_W1.value
        result = gate.gate_claim(tampered, self.claim(self.w0, "W0"))
        self.assertEqual(result["decision"], gate.Decision.INVALID.value)
        self.assertIn("RECEIPT_ID_MISMATCH", result["reason_codes"])

    def test_artifact_hash_mismatch_is_invalid(self):
        claim = self.claim(self.w0, "W0")
        claim["artifact_sha256"]["runtime_config"] = "0" * 64
        result = gate.gate_claim(self.w0, claim)
        self.assertEqual(result["decision"], gate.Decision.INVALID.value)
        self.assertIn("CLAIM_ARTIFACT_HASH_MISMATCH", result["reason_codes"])

    def test_r0p0o0_alias_requires_w0_declaration(self):
        claim = self.claim(self.w0, "W1", ["R0P0O0"])
        result = gate.gate_claim(self.w0, claim)
        self.assertEqual(result["decision"], gate.Decision.INVALID.value)
        self.assertIn("R0P0O0_REQUIRES_EXPLICIT_W0_DECLARATION", result["reason_codes"])
