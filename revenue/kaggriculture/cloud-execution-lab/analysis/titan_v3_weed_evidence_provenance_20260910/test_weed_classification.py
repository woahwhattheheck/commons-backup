# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import weed_evidence_certifier as gate
from weed_test_fixtures import *  # noqa: F403

class ClassificationTests(unittest.TestCase):
    def certify(
        self,
        spatial=FIXED_SPATIAL,
        runtime=FIXED_RUNTIME,
        cfg=config(False),
        entrypoint=FIXED_ENTRYPOINT,
    ):
        return gate.certify_bytes(
            spatial,
            runtime,
            cfg,
            entrypoint_source=entrypoint,
            source_revision="fixture",
        )

    def test_current_legacy_shape_is_not_w0(self):
        receipt = self.certify(LEGACY_SPATIAL, LEGACY_RUNTIME, LEGACY_CONFIG)
        self.assertEqual(receipt["classification"], gate.Semantics.LEGACY_PRE_GATE_W1.value)
        self.assertFalse(receipt["promotion_eligible_as_w0"])
        self.assertIn("P0_T0_DOES_NOT_IMPLY_W0", receipt["reason_codes"])

    def test_explicit_w0_end_to_end(self):
        receipt = self.certify(cfg=config(False))
        self.assertEqual(receipt["classification"], gate.Semantics.EXPLICIT_W0.value)
        self.assertEqual(receipt["claimable_semantics"], ["W0"])
        self.assertTrue(receipt["promotion_eligible_as_w0"])

    def test_explicit_w1_end_to_end(self):
        receipt = self.certify(cfg=config(True))
        self.assertEqual(receipt["classification"], gate.Semantics.EXPLICIT_W1.value)
        self.assertEqual(receipt["claimable_semantics"], ["W1"])

    def test_early_return_independent_guard_is_accepted(self):
        receipt = self.certify(spatial=EARLY_RETURN_FIXED_SPATIAL)
        self.assertEqual(receipt["classification"], gate.Semantics.EXPLICIT_W0.value)

    def test_constructor_must_symbolically_store_the_independent_bit(self):
        receipt = self.certify(spatial=CONSTANT_STORE_SPATIAL)
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("SPATIAL_CONSTRUCTOR_W_BIT_INCOMPLETE", receipt["reason_codes"])

    def test_path_tempo_pseudo_fix_is_coupled_not_w0(self):
        receipt = self.certify(COUPLED_SPATIAL, LEGACY_RUNTIME, LEGACY_CONFIG)
        self.assertEqual(receipt["classification"], gate.Semantics.COUPLED_WEED.value)
        self.assertFalse(receipt["promotion_eligible_as_w0"])

    def test_flag_without_effective_guard_is_ambiguous(self):
        receipt = self.certify(spatial=UNGUARDED_WITH_BIT_SPATIAL)
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("WEED_CALL_NOT_INDEPENDENTLY_GUARDED", receipt["reason_codes"])

    def test_or_guard_fails_closed(self):
        receipt = self.certify(spatial=OR_GUARD_SPATIAL)
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)

    def test_config_key_missing_after_source_fix_is_ambiguous(self):
        receipt = self.certify(cfg=b'{"spatial_pathing": false}\n')
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("CONFIG_W_BIT_MISSING_OR_DUPLICATE", receipt["reason_codes"])

    def test_config_non_boolean_is_ambiguous(self):
        receipt = self.certify(cfg=b'{"weed_continuation": "false"}\n')
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("CONFIG_W_BIT_NOT_BOOLEAN", receipt["reason_codes"])

    def test_duplicate_config_key_is_parse_failure(self):
        receipt = self.certify(cfg=b'{"weed_continuation": false, "weed_continuation": true}\n')
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("CONFIG_PARSE_FAILED", receipt["reason_codes"])

    def test_non_finite_json_is_parse_failure(self):
        receipt = self.certify(cfg=b'{"weed_continuation": false, "x": NaN}\n')
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("CONFIG_PARSE_FAILED", receipt["reason_codes"])

    def test_malformed_source_is_ambiguous(self):
        receipt = self.certify(spatial=b'class SpatialTempo(:\n')
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("SPATIAL_PARSE_FAILED", receipt["reason_codes"])

    def test_runtime_constant_keyword_does_not_prove_wiring(self):
        runtime = FIXED_RUNTIME.replace(
            b"weed_continuation=f.weed_continuation", b"weed_continuation=False"
        )
        receipt = self.certify(runtime=runtime)
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("RUNTIME_W_BIT_NOT_SYMBOLICALLY_WIRED", receipt["reason_codes"])

    def test_entrypoint_must_expand_bound_feature_data(self):
        receipt = self.certify(entrypoint=NO_EXPANSION_ENTRYPOINT)
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("ENTRYPOINT_CONFIG_NOT_SYMBOLICALLY_WIRED", receipt["reason_codes"])

    def test_entrypoint_must_load_the_bound_config(self):
        receipt = self.certify(entrypoint=NO_LOAD_ENTRYPOINT)
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("ENTRYPOINT_CONFIG_NOT_SYMBOLICALLY_WIRED", receipt["reason_codes"])

    def test_entrypoint_must_forward_feature_data(self):
        receipt = self.certify(entrypoint=NO_FORWARD_ENTRYPOINT)
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("ENTRYPOINT_CONFIG_NOT_SYMBOLICALLY_WIRED", receipt["reason_codes"])

    def test_malformed_entrypoint_is_ambiguous(self):
        receipt = self.certify(entrypoint=b"def agent(:\n")
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("ENTRYPOINT_PARSE_FAILED", receipt["reason_codes"])

    def test_removed_capability_is_safe_w0(self):
        receipt = self.certify(spatial=NO_WEED_SPATIAL, runtime=LEGACY_RUNTIME, cfg=LEGACY_CONFIG)
        self.assertEqual(receipt["classification"], gate.Semantics.EXPLICIT_W0.value)
        self.assertIn("WEED_CAPABILITY_ABSENT", receipt["reason_codes"])

    def test_hashes_and_receipt_id_are_content_stable(self):
        one = self.certify()
        two = gate.certify_bytes(
            FIXED_SPATIAL,
            FIXED_RUNTIME,
            config(False),
            entrypoint_source=FIXED_ENTRYPOINT,
            source_revision="fixture",
            generated_utc="2099-01-01T00:00:00Z",
        )
        self.assertEqual(one["receipt_id"], two["receipt_id"])
        changed = self.certify(cfg=config(True))
        self.assertNotEqual(one["receipt_id"], changed["receipt_id"])
        self.assertNotEqual(
            one["artifacts"]["runtime_config"]["sha256"],
            changed["artifacts"]["runtime_config"]["sha256"],
        )
    def test_entrypoint_reassignment_breaks_exact_config_flow(self):
        receipt = self.certify(entrypoint=REASSIGNED_ENTRYPOINT)
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("ENTRYPOINT_CONFIG_NOT_SYMBOLICALLY_WIRED", receipt["reason_codes"])

    def test_entrypoint_in_place_mutation_breaks_exact_config_flow(self):
        receipt = self.certify(entrypoint=MUTATED_ENTRYPOINT)
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("ENTRYPOINT_CONFIG_NOT_SYMBOLICALLY_WIRED", receipt["reason_codes"])

    def test_new_instance_mutation_breaks_exact_config_flow(self):
        receipt = self.certify(entrypoint=MUTATED_NEW_INSTANCE_ENTRYPOINT)
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("ENTRYPOINT_CONFIG_NOT_SYMBOLICALLY_WIRED", receipt["reason_codes"])

    def test_loader_must_be_json_loads_not_name_only(self):
        receipt = self.certify(entrypoint=FAKE_LOADS_ENTRYPOINT)
        self.assertEqual(receipt["classification"], gate.Semantics.AMBIGUOUS.value)
        self.assertIn("ENTRYPOINT_CONFIG_NOT_SYMBOLICALLY_WIRED", receipt["reason_codes"])

