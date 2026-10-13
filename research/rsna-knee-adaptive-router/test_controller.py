import random
import unittest

from controller import (
    LABELS, Calibration, Policy, Series, aggregate, assert_inference_record_has_no_report,
    assert_runtime_budget, assert_vram_budget, fit_calibration, local_efficiency_surrogate,
    project_runtime, receipt, run_dataset, run_study, select_initial, select_upgrade,
    submission_csv_bytes, uncertain_labels, verify_receipt, verify_receipt_authoritative,
)


def probs(x): return {label: x for label in LABELS}
def s(study, sid, plane, fluid=1, fat=0, n=40): return Series(study, sid, plane, fluid, fat, n)


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.series = [s("S", "sag", "Sagittal"), s("S", "cor", "Coronal", 1, 1), s("S", "axi", "Axial", 1, 1), s("S", "extra", "Sagittal", 0, 0, 90)]

    def test_initial_deterministic_under_shuffle(self):
        expected = select_initial(self.series, Policy())
        for seed in range(8):
            rows = self.series[:]; random.Random(seed).shuffle(rows)
            self.assertEqual(select_initial(rows, Policy()), expected)

    def test_cross_study_rejected(self):
        with self.assertRaises(ValueError): select_initial([self.series[0], s("X", "x", "Axial")], Policy())

    def test_uncertainty_boundary_inclusive(self):
        row = probs(.9); row["ACL"] = .66
        self.assertIn("ACL", uncertain_labels(row, .16))

    def test_no_uncertainty_no_upgrade(self):
        self.assertEqual(select_upgrade(self.series, ("sag",), (), Policy()), ())

    def test_upgrade_excludes_initial(self):
        out = select_upgrade(self.series, ("sag",), ("Effusion", "PF OA"), Policy(max_extra_series=2))
        self.assertNotIn("sag", out); self.assertLessEqual(len(out), 2)

    def test_duplicate_series_rejected(self):
        with self.assertRaises(ValueError): select_initial([self.series[0], self.series[0]], Policy())


class AggregationTests(unittest.TestCase):
    def setUp(self): self.series = [s("S", "sag", "Sagittal"), s("S", "axi", "Axial", 1, 1)]

    def test_unknown_series_rejected(self):
        with self.assertRaises(ValueError): aggregate(self.series, {"ghost": probs(.8)})

    def test_bad_probability_rejected(self):
        row = probs(.8); row["ACL"] = 1.2
        with self.assertRaises(ValueError): aggregate(self.series, {"sag": row})

    def test_calibration_requires_oof(self):
        row = {"study_id": "S", "fold": 0, "truth": {x: 1 for x in LABELS}, "prediction": probs(.8), "is_oof": False}
        with self.assertRaises(ValueError): fit_calibration([row], 2)

    def test_small_calibration_stays_identity(self):
        rows = [{"study_id": f"S{i}", "fold": i, "truth": {x: i % 2 for x in LABELS}, "prediction": probs(.7), "is_oof": True} for i in range(4)]
        self.assertFalse(fit_calibration(rows, 3)["ACL"].fitted)

    def test_fit_separated_oof(self):
        rows = []
        for i in range(20):
            y = i % 2; rows.append({"study_id": f"S{i}", "fold": i % 5, "truth": {x: y for x in LABELS}, "prediction": probs(.58 if y else .42), "is_oof": True})
        self.assertTrue(fit_calibration(rows, 8)["ACL"].fitted)

    def test_calibrated_aggregate_finite(self):
        cals = {label: Calibration(1.1, .05, True) for label in LABELS}
        out = aggregate(self.series, {"sag": probs(.7), "axi": probs(.8)}, cals)
        self.assertTrue(all(0 < x < 1 for x in out.values()))


class BudgetTests(unittest.TestCase):
    def test_local_efficiency_surrogate_direction_across_reference_band(self):
        for reference_max in (.93, .95, .99):
            fast = local_efficiency_surrogate(.90, 1200, .50, reference_max)
            slow = local_efficiency_surrogate(.90, 7200, .50, reference_max)
            better_auc = local_efficiency_surrogate(.92, 1200, .50, reference_max)
            self.assertLess(fast, slow)
            self.assertLess(better_auc, fast)

    def test_local_efficiency_surrogate_rejects_sign_inverting_reference(self):
        with self.assertRaises(ValueError): local_efficiency_surrogate(.90, 1200, .95, .50)
        with self.assertRaises(ValueError): local_efficiency_surrogate(.90, 1200, .95, .95)

    def test_local_efficiency_surrogate_reference_ceiling(self):
        for reference_max in (.93, .95, .99):
            at_ceiling = local_efficiency_surrogate(reference_max, 1200, .50, reference_max)
            self.assertAlmostEqual(at_ceiling, 1200 / 32400.0)
            with self.assertRaises(ValueError):
                local_efficiency_surrogate(min(1.0, reference_max + .001), 1200, .50, reference_max)

    def test_runtime_pass(self):
        p = Policy(); assert_runtime_budget(project_runtime(1300, p, 60, .05, .3), p)

    def test_runtime_reject(self):
        with self.assertRaises(ValueError): assert_runtime_budget(30000, Policy(target_fraction=.7))

    def test_vram_pass_zero_or_pair(self):
        assert_vram_budget(0, 0); assert_vram_budget(6000, 16000)

    def test_vram_partial_reject(self):
        with self.assertRaises(ValueError): assert_vram_budget(6000, 0)

    def test_vram_overbudget_reject(self):
        with self.assertRaises(ValueError): assert_vram_budget(15000, 16000)

    def test_receipt_tamper(self):
        r = receipt("x", {"a": 1}); verify_receipt(r); r["payload"]["a"] = 2
        with self.assertRaises(ValueError): verify_receipt(r)

    def test_receipt_detaches_caller_payload(self):
        payload = {"nested": {"values": [1]}}
        r = receipt("x", payload)
        payload["nested"]["values"].append(2)
        self.assertEqual(r["payload"], {"nested": {"values": [1]}})
        verify_receipt(r)

    def test_receipt_rejects_nonfinite_json_numbers(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                receipt("x", {"metric": value})
            forged = receipt("x", {"metric": 0.0})
            forged["payload"]["metric"] = value
            with self.assertRaises(ValueError):
                verify_receipt(forged)

    def test_authoritative_receipt_rejects_validly_resealed_payload(self):
        trusted = receipt("x", {"a": 1})
        verify_receipt_authoritative(trusted, expected_sha256=trusted["sha256"], expected_kind="x")
        resealed = receipt("x", {"a": 2})
        verify_receipt(resealed)
        with self.assertRaises(ValueError):
            verify_receipt_authoritative(resealed, expected_sha256=trusted["sha256"], expected_kind="x")

    def test_authoritative_receipt_rejects_context_transplant(self):
        trusted = receipt("x", {"a": 1})
        transplant = receipt("y", {"a": 1})
        with self.assertRaises(ValueError):
            verify_receipt_authoritative(transplant, expected_sha256=trusted["sha256"], expected_kind="x")

    def test_bool_not_numeric(self):
        with self.assertRaises(ValueError): Policy(initial_series=True).validate()


class AdapterTests(unittest.TestCase):
    def setUp(self): self.series = [s("S", "sag", "Sagittal"), s("S", "cor", "Coronal", 1, 1), s("S", "axi", "Axial", 1, 1), s("S", "extra", "Sagittal", 0, 0, 90)]

    def test_no_report(self):
        assert_inference_record_has_no_report({"StudyInstanceUID": "S"})
        with self.assertRaises(ValueError): assert_inference_record_has_no_report({"StudyInstanceUID": "S", "Report": "x"})

    def test_confident_skips_upgrade(self):
        calls = []
        def pred(study, ids, stage): calls.append(stage); return {sid: probs(.9) for sid in ids}, .1
        run = run_study(self.series, pred, Policy())
        self.assertFalse(run["upgrade_series"]); self.assertEqual(calls, ["stage1"])

    def test_uncertain_triggers_upgrade(self):
        calls = []
        def pred(study, ids, stage): calls.append(stage); return {sid: probs(.5 if stage == "stage1" else .8) for sid in ids}, .1
        run = run_study(self.series, pred, Policy(initial_series=2, max_extra_series=1))
        self.assertTrue(run["upgrade_series"]); self.assertEqual(calls, ["stage1", "upgrade"])

    def test_extra_predictor_series_rejected(self):
        def pred(study, ids, stage):
            rows = {sid: probs(.9) for sid in ids}; rows["ghost"] = probs(.9); return rows, .1
        with self.assertRaises(ValueError): run_study(self.series, pred, Policy())

    def test_dataset_receipt_binds_resource_budget(self):
        def pred(study, ids, stage): return {sid: probs(.8) for sid in ids}, .2
        runs, r = run_dataset([self.series], pred, Policy(), fixed_seconds=30, seconds_per_slice=.01, expected_upgrade_rate=.1, estimated_peak_vram_mb=6000, available_vram_mb=16000)
        verify_receipt(r); self.assertEqual(r["payload"]["estimated_peak_vram_mb"], 6000)
        self.assertTrue(submission_csv_bytes(runs, ["S"]).startswith(b"StudyInstanceUID,ACL,MCL"))

    def test_submission_order_rejected(self):
        def pred(study, ids, stage): return {sid: probs(.8) for sid in ids}, .2
        run = run_study(self.series, pred, Policy())
        with self.assertRaises(ValueError): submission_csv_bytes([run], ["OTHER"])


if __name__ == "__main__": unittest.main()
