from .test_support import *  # noqa: F401,F403


class PolicyTests(unittest.TestCase):
    def test_strict_json_duplicate_key(self):
        with self.assertRaisesRegex(RoadV2Error, "duplicate JSON key"):
            loads_strict('{"x":1,"x":2}')

    def test_strict_json_float(self):
        with self.assertRaisesRegex(RoadV2Error, "floats forbidden"):
            loads_strict('{"x":1.5}')

    def test_strict_json_nonfinite(self):
        with self.assertRaisesRegex(RoadV2Error, "non-finite"):
            loads_strict('{"x":NaN}')

    def test_manifest_happy(self):
        self.assertEqual(validate_manifest(manifest())["models"][0]["model_id"], "alpha")

    def test_manifest_rejects_license_claim(self):
        m = manifest(); m["models"][0]["commercial_use_compatible"] = False
        with self.assertRaisesRegex(RoadV2Error, "LICENSE_NOT_COMMERCIAL"):
            validate_manifest(m)

    def test_manifest_rejects_nonopen_model(self):
        m = manifest(); m["models"][0]["openly_available"] = False
        with self.assertRaisesRegex(RoadV2Error, "NOT_OPENLY_AVAILABLE"):
            validate_manifest(m)

    def test_manifest_rejects_external_training(self):
        m = manifest(); m["models"][0]["external_training_data"] = True
        with self.assertRaisesRegex(RoadV2Error, "EXTERNAL_TRAINING"):
            validate_manifest(m)

    def test_manifest_rejects_external_adaptation(self):
        m = manifest(); m["models"][0]["adaptation_data"] = "internet"
        with self.assertRaisesRegex(RoadV2Error, "EXTERNAL_ADAPTATION"):
            validate_manifest(m)

    def test_manifest_rejects_hosted_api(self):
        m = manifest(); m["models"][0]["hosted_api"] = True
        with self.assertRaisesRegex(RoadV2Error, "HOSTED_API"):
            validate_manifest(m)

    def test_manifest_rejects_automl(self):
        m = manifest(); m["models"][0]["automl"] = True
        with self.assertRaisesRegex(RoadV2Error, "AUTOML"):
            validate_manifest(m)

    def test_manifest_rejects_authority(self):
        m = manifest(); m["authority"]["submit_to_zindi"] = True
        with self.assertRaisesRegex(RoadV2Error, "AUTHORITY_ESCALATION"):
            validate_manifest(m)

    def test_normalize_transcript_nfc_whitespace(self):
        self.assertEqual(normalize_transcript("  Cafe\u0301\n  Barbados  "), "Café Barbados")

    def test_edit_distance(self):
        self.assertEqual(edit_distance("kitten", "sitting"), 3)

    def test_metric_exact(self):
        metric = aggregate_metric({"x": "cat dog"}, {"x": "cat dig"})
        self.assertEqual(metric["word_edits"], 1)
        self.assertEqual(metric["reference_words"], 2)
        self.assertEqual(metric["char_edits"], 1)
        self.assertEqual(metric["reference_chars"], 7)
        self.assertEqual(metric["combined"], {"numerator": 9, "denominator": 28})

    def test_metric_id_mismatch(self):
        with self.assertRaisesRegex(RoadV2Error, "ID sets differ"):
            aggregate_metric({"x": "a"}, {"y": "a"})

    def test_profile_reliability_sums_exactly(self):
        p = build_profile(manifest(), labels(), oof())
        self.assertEqual(sum(p["reliability_ppm"].values()), 1_000_000)
        self.assertEqual(set(p["reliability_ppm"]), {"alpha", "beta", "gamma"})

    def test_profile_oof_model_mismatch(self):
        bad = oof(); bad.pop("gamma")
        with self.assertRaisesRegex(RoadV2Error, "OOF model set"):
            build_profile(manifest(), labels(), bad)

    def test_profile_manifest_transplant(self):
        m = manifest(); p = build_profile(m, labels(), oof()); m2 = deepcopy(m); m2["models"][0]["base_revision"] = "changed"
        with self.assertRaisesRegex(RoadV2Error, "PROFILE_MANIFEST_TRANSPLANT"):
            ensemble(m2, p, labels(), preds())

    def test_profile_label_transplant(self):
        m = manifest(); p = build_profile(m, labels(), oof()); l2 = labels(); l2["tr1"] = "Different Label"
        with self.assertRaisesRegex(RoadV2Error, "PROFILE_LABEL_TRANSPLANT"):
            ensemble(m, p, l2, preds())

    def test_profile_receipt_tamper(self):
        m = manifest(); p = build_profile(m, labels(), oof()); p["reliability_ppm"]["alpha"] += 1; p["reliability_ppm"]["beta"] -= 1
        with self.assertRaisesRegex(RoadV2Error, "PROFILE_RECEIPT_MISMATCH"):
            ensemble(m, p, labels(), preds())
