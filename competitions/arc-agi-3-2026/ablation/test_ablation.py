from __future__ import annotations

import copy
import json
import unittest

from .benchmark import ADAPTER_DIGEST, arms, build
from .harness import AblationKind, ArmConfig, TrialRow, canonical_bytes, compile_experiment, sha256, verify_experiment
from .synthetic import make_scenario, paired_rows, run_animation, run_coordinate, run_info_gain, run_transfer


class HarnessTests(unittest.TestCase):
    def receipt(self, kind=AblationKind.ANIMATION, n=8):
        c, t = arms(kind)
        rows, d = paired_rows(kind, range(n), c, t)
        return compile_experiment(kind=kind, control=c, treatment=t, rows=rows,
                                  scenario_manifest_digest=d, adapter_digest=ADAPTER_DIGEST, max_real_actions=24)

    def test_all_four_build_and_verify(self):
        for kind in AblationKind:
            doc = build(kind, 16, 24)
            self.assertEqual(verify_experiment(doc).document, doc)

    def test_animation_treatment_retains_more_evidence(self):
        doc = self.receipt(AblationKind.ANIMATION, 32).document
        self.assertGreater(doc["aggregate"]["evidence_delta_sum"], 0)
        self.assertLess(doc["aggregate"]["action_delta_sum"], 0)

    def test_info_gain_uses_no_more_real_actions(self):
        doc = self.receipt(AblationKind.INFO_GAIN, 32).document
        self.assertLessEqual(doc["aggregate"]["action_delta_sum"], 0)
        self.assertGreater(doc["aggregate"]["treatment_simulated_expansions"], 0)

    def test_coordinate_reduction_is_offline_not_real_action(self):
        doc = self.receipt(AblationKind.COORDINATE, 32).document
        self.assertGreater(doc["aggregate"]["treatment_simulated_expansions"], 0)
        self.assertLess(doc["aggregate"]["action_delta_sum"], 0)

    def test_transfer_reuses_evidence(self):
        doc = self.receipt(AblationKind.TRANSFER, 32).document
        self.assertGreater(doc["aggregate"]["transfer_reuse_delta_sum"], 0)

    def test_missing_pair_rejected(self):
        c, t = arms(AblationKind.ANIMATION)
        rows, d = paired_rows(AblationKind.ANIMATION, range(2), c, t)
        with self.assertRaisesRegex(ValueError, "missing paired"):
            compile_experiment(kind=AblationKind.ANIMATION, control=c, treatment=t, rows=rows[:-1],
                               scenario_manifest_digest=d, adapter_digest=ADAPTER_DIGEST, max_real_actions=24)

    def test_duplicate_pair_rejected(self):
        c, t = arms(AblationKind.ANIMATION)
        rows, d = paired_rows(AblationKind.ANIMATION, range(2), c, t)
        with self.assertRaisesRegex(ValueError, "duplicate trial"):
            compile_experiment(kind=AblationKind.ANIMATION, control=c, treatment=t, rows=rows + [rows[0]],
                               scenario_manifest_digest=d, adapter_digest=ADAPTER_DIGEST, max_real_actions=24)

    def test_changed_identity_rejected(self):
        c, t = arms(AblationKind.ANIMATION)
        rows, d = paired_rows(AblationKind.ANIMATION, range(2), c, t)
        changed = TrialRow(**{**rows[0].as_dict(), "real_actions": rows[0].real_actions + 1})
        with self.assertRaisesRegex(ValueError, "changed trial"):
            compile_experiment(kind=AblationKind.ANIMATION, control=c, treatment=t, rows=rows + [changed],
                               scenario_manifest_digest=d, adapter_digest=ADAPTER_DIGEST, max_real_actions=24)

    def test_budget_excess_rejected(self):
        c, t = arms(AblationKind.ANIMATION)
        rows, d = paired_rows(AblationKind.ANIMATION, range(2), c, t)
        bad = TrialRow(**{**rows[0].as_dict(), "real_actions": 25})
        with self.assertRaisesRegex(ValueError, "budget"):
            compile_experiment(kind=AblationKind.ANIMATION, control=c, treatment=t,
                               rows=[bad if r == rows[0] else r for r in rows], scenario_manifest_digest=d,
                               adapter_digest=ADAPTER_DIGEST, max_real_actions=24)

    def test_bool_is_not_integer_metric(self):
        r = self.receipt().document
        tampered = copy.deepcopy(r)
        tampered["rows"][0]["real_actions"] = True
        tampered.pop("receipt_digest")
        tampered["receipt_digest"] = sha256(canonical_bytes(tampered))
        with self.assertRaises(ValueError): verify_experiment(tampered)

    def test_authority_escalation_rejected_even_resealed(self):
        r = self.receipt().document
        tampered = copy.deepcopy(r)
        tampered["authority"]["kaggle_submission"] = True
        tampered.pop("receipt_digest")
        tampered["receipt_digest"] = sha256(canonical_bytes(tampered))
        with self.assertRaisesRegex(ValueError, "authority"): verify_experiment(tampered)

    def test_row_tamper_rejected(self):
        r = self.receipt().document
        tampered = copy.deepcopy(r)
        tampered["rows"][0]["evidence_bits"] += 1
        with self.assertRaisesRegex(ValueError, "tamper"): verify_experiment(tampered)

    def test_semantic_tamper_resealed_rejected(self):
        r = self.receipt().document
        tampered = copy.deepcopy(r)
        tampered["aggregate"]["action_delta_sum"] += 1
        tampered.pop("receipt_digest")
        tampered["receipt_digest"] = sha256(canonical_bytes(tampered))
        with self.assertRaisesRegex(ValueError, "semantic"): verify_experiment(tampered)

    def test_rows_digest_tamper_resealed_rejected(self):
        r = self.receipt().document
        tampered = copy.deepcopy(r)
        tampered["rows_digest"] = "0" * 64
        tampered.pop("receipt_digest")
        tampered["receipt_digest"] = sha256(canonical_bytes(tampered))
        with self.assertRaisesRegex(ValueError, "semantic"): verify_experiment(tampered)

    def test_arm_role_rejected(self):
        c = ArmConfig("c", True)
        t = ArmConfig("t", True)
        rows = []
        with self.assertRaisesRegex(ValueError, "arm role"):
            compile_experiment(kind=AblationKind.ANIMATION, control=c, treatment=t, rows=rows,
                               scenario_manifest_digest="1"*64, adapter_digest="2"*64, max_real_actions=24)

    def test_deterministic_receipt_across_row_order(self):
        c, t = arms(AblationKind.TRANSFER)
        rows, d = paired_rows(AblationKind.TRANSFER, range(20), c, t)
        a = compile_experiment(kind=AblationKind.TRANSFER, control=c, treatment=t, rows=rows,
                               scenario_manifest_digest=d, adapter_digest=ADAPTER_DIGEST, max_real_actions=24)
        b = compile_experiment(kind=AblationKind.TRANSFER, control=c, treatment=t, rows=list(reversed(rows)),
                               scenario_manifest_digest=d, adapter_digest=ADAPTER_DIGEST, max_real_actions=24)
        self.assertEqual(a.canonical_bytes(), b.canonical_bytes())

    def test_scenario_is_seed_deterministic(self):
        self.assertEqual(make_scenario(5, "animation"), make_scenario(5, "animation"))
        self.assertNotEqual(make_scenario(5, "animation").digest, make_scenario(6, "animation").digest)

    def test_trace_is_arm_bound(self):
        s = make_scenario(9, "animation")
        c, t = arms(AblationKind.ANIMATION)
        self.assertNotEqual(run_animation(s, c).trace_digest, run_animation(s, t).trace_digest)

    def test_settled_never_sees_intermediate_cue(self):
        s = make_scenario(13, "animation")
        c, t = arms(AblationKind.ANIMATION)
        self.assertLess(run_animation(s, t).real_actions, run_animation(s, c).real_actions + 1)
        self.assertGreater(run_animation(s, t).evidence_bits, run_animation(s, c).evidence_bits)

    def test_random_and_info_policies_differ(self):
        s = make_scenario(22, "info")
        c, t = arms(AblationKind.INFO_GAIN)
        self.assertNotEqual(run_info_gain(s, c).trace_digest, run_info_gain(s, t).trace_digest)

    def test_coordinate_candidate_reduction(self):
        s = make_scenario(18, "coordinate")
        c, t = arms(AblationKind.COORDINATE)
        control = run_coordinate(s, c); treatment = run_coordinate(s, t)
        self.assertGreater(treatment.simulated_expansions, control.simulated_expansions)
        self.assertLessEqual(treatment.real_actions, 12)

    def test_transfer_does_not_reuse_literal_ids(self):
        s = make_scenario(19, "transfer")
        c, t = arms(AblationKind.TRANSFER)
        treatment = run_transfer(s, t)
        self.assertGreater(treatment.transfer_reuse, 0)
        self.assertGreater(treatment.simulated_expansions, 0)

    def test_digest_shape_strict(self):
        c, t = arms(AblationKind.ANIMATION)
        rows, d = paired_rows(AblationKind.ANIMATION, range(2), c, t)
        with self.assertRaisesRegex(ValueError, "source digest"):
            compile_experiment(kind=AblationKind.ANIMATION, control=c, treatment=t, rows=rows,
                               scenario_manifest_digest=d.upper(), adapter_digest=ADAPTER_DIGEST, max_real_actions=24)

    def test_receipt_json_roundtrip(self):
        r = self.receipt(AblationKind.COORDINATE, 10)
        decoded = json.loads(r.canonical_bytes())
        self.assertEqual(verify_experiment(decoded).document, r.document)


if __name__ == "__main__":
    unittest.main()
