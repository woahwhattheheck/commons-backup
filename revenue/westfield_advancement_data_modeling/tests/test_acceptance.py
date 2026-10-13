import copy
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acceptance import (
    ContractError,
    ENTITY_KEY_POLICY,
    PRICING_POSTURE,
    SOURCE_PROVENANCE_MODE,
    TIME_ANCHOR_POLICY,
    compile_acceptance,
    load_strict_json,
    make_receipt,
    verify_receipt,
)

MANIFEST_PATH = ROOT / "westfield_manifest.json"
MANIFEST = load_strict_json(MANIFEST_PATH.read_text(encoding="utf-8"))


class AcceptanceTests(unittest.TestCase):
    def test_good_manifest_compiles_and_receipt_verifies(self):
        plan = compile_acceptance(copy.deepcopy(MANIFEST))
        self.assertEqual(plan["commercial"]["state"], "PROPOSED_NOT_ACCEPTED")
        self.assertEqual(plan["commercial"]["pricing_posture"], PRICING_POSTURE)
        self.assertEqual(
            plan["source_provenance"]["mode"],
            SOURCE_PROVENANCE_MODE,
        )
        self.assertFalse(plan["source_provenance"]["live_provider_authenticated"])
        self.assertEqual(
            plan["acceptance_plan"]["entity_key_policy"],
            ENTITY_KEY_POLICY,
        )
        self.assertEqual(
            plan["acceptance_plan"]["time_anchor_policy"],
            TIME_ANCHOR_POLICY,
        )
        self.assertTrue(verify_receipt(MANIFEST, make_receipt(MANIFEST)))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(ContractError):
            load_strict_json('{"schema":"a","schema":"b"}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ContractError):
            load_strict_json('{"x":NaN}')

    def test_authority_claim_cannot_be_promoted(self):
        for key in MANIFEST["authority"]:
            bad = copy.deepcopy(MANIFEST)
            bad["authority"][key] = True
            with self.subTest(key=key), self.assertRaises(ContractError):
                compile_acceptance(bad)

    def test_stronger_commercial_states_are_not_mintable(self):
        for state in ("ACCEPTED_UNFUNDED", "FUNDED_NOT_DELIVERED", "PAID"):
            bad = copy.deepcopy(MANIFEST)
            bad["commercial"]["state"] = state
            with self.subTest(state=state), self.assertRaises(ContractError):
                compile_acceptance(bad)

    def test_pricing_posture_is_closed_not_prose_screened(self):
        attempts = (
            "$12,000 fixed",
            "USD 12000 fixed",
            "€12000 fixed",
            "twelve thousand dollars fixed",
            "scope-and-deliverables to be agreed later",
        )
        for attempt in attempts:
            bad = copy.deepcopy(MANIFEST)
            bad["commercial"]["pricing_posture"] = attempt
            with self.subTest(attempt=attempt), self.assertRaises(ContractError):
                compile_acceptance(bad)

    def test_opportunity_identity_is_code_owned(self):
        mutations = {
            "buyer": "Other University",
            "solicitation": "RFP #9999",
            "deadline": "2026-10-25",
            "submission_route": "Email",
        }
        for key, value in mutations.items():
            bad = copy.deepcopy(MANIFEST)
            bad["opportunity"][key] = value
            with self.subTest(key=key), self.assertRaises(ContractError):
                compile_acceptance(bad)

    def test_source_role_and_url_are_code_owned(self):
        bad = copy.deepcopy(MANIFEST)
        bad["sources"][0]["url"] = "https://example.com/open-bids"
        with self.assertRaises(ContractError):
            compile_acceptance(bad)

        bad = copy.deepcopy(MANIFEST)
        bad["sources"][0]["kind"] = "partner_public"
        with self.assertRaises(ContractError):
            compile_acceptance(bad)

        bad = copy.deepcopy(MANIFEST)
        bad["sources"].append(
            {
                "kind": "buyer_official",
                "url": "https://www.westfield.ma.edu/offices/open-general-bids",
                "note": "Pinned public source identity only; compiler does not authenticate live availability.",
            }
        )
        with self.assertRaises(ContractError):
            compile_acceptance(bad)

    def test_source_order_is_not_authority(self):
        bad = copy.deepcopy(MANIFEST)
        bad["sources"].reverse()
        plan = compile_acceptance(bad)
        self.assertEqual(
            [row["kind"] for row in plan["sources"]],
            ["buyer_official", "partner_public"],
        )

    def test_closed_policy_ids_reject_contradictory_prose(self):
        bad = copy.deepcopy(MANIFEST)
        bad["model_acceptance"]["entity_key_policy"] = (
            "random row split; household grouping optional"
        )
        with self.assertRaises(ContractError):
            compile_acceptance(bad)

        bad = copy.deepcopy(MANIFEST)
        bad["model_acceptance"]["time_anchor_policy"] = (
            "future gifts may be used as features"
        )
        with self.assertRaises(ContractError):
            compile_acceptance(bad)

    def test_temporal_holdout_required(self):
        bad = copy.deepcopy(MANIFEST)
        bad["model_acceptance"]["metrics"]["evaluation_split"] = "random_split"
        with self.assertRaises(ContractError):
            compile_acceptance(bad)

    def test_required_checks_are_exact_closed_set(self):
        bad = copy.deepcopy(MANIFEST)
        bad["model_acceptance"]["required_checks"].remove("household_leakage")
        with self.assertRaises(ContractError):
            compile_acceptance(bad)

        bad = copy.deepcopy(MANIFEST)
        bad["model_acceptance"]["required_checks"].append("caller_claimed_certified")
        with self.assertRaises(ContractError):
            compile_acceptance(bad)

    def test_source_note_is_code_owned_not_authority_prose(self):
        attempts = (
            "LIVE VERIFIED FOREVER",
            "Westfield awarded and paid Token Junkie Labs",
            "KHow accepted Token Junkie Labs as its subcontractor",
        )
        for attempt in attempts:
            bad = copy.deepcopy(MANIFEST)
            bad["sources"][0]["note"] = attempt
            with self.subTest(attempt=attempt), self.assertRaises(ContractError):
                compile_acceptance(bad)

    def test_transplanted_manifest_cannot_be_rehashed_into_valid_receipt(self):
        bad = copy.deepcopy(MANIFEST)
        bad["opportunity"]["buyer"] = "Other University"
        self.assertFalse(verify_receipt(bad, make_receipt(MANIFEST)))

    def test_tampered_receipt_rejected(self):
        receipt = make_receipt(MANIFEST)
        receipt["plan_sha256"] = "0" * 64
        self.assertFalse(verify_receipt(MANIFEST, receipt))

    def test_truth_receipt_remains_pre_award_and_non_authoritative(self):
        receipt = make_receipt(MANIFEST)
        truth = receipt["truth"]
        self.assertEqual(truth["commercial_state"], "PROPOSED_NOT_ACCEPTED")
        self.assertFalse(truth["live_provider_authenticated"])
        self.assertFalse(truth["submission_authorized"])
        self.assertFalse(truth["award_received"])
        self.assertFalse(truth["payment_received"])
        self.assertFalse(truth["revenue_recognized"])

    def test_signed_scope_vocab_is_code_owned(self):
        attempts = (
            ("deliverables", "Westfield awarded and paid Token Junkie Labs"),
            ("exclusions", "buyer portal submission included and authorized"),
        )
        for field, replacement in attempts:
            bad = copy.deepcopy(MANIFEST)
            bad["workshare"][field][0] = replacement
            with self.subTest(field=field), self.assertRaises(ContractError):
                compile_acceptance(bad)

        bad = copy.deepcopy(MANIFEST)
        bad["model_acceptance"]["handoff_artifacts"][0] = (
            "buyer-approved production-data export"
        )
        with self.assertRaises(ContractError):
            compile_acceptance(bad)

        for field in ("deliverables", "exclusions"):
            bad = copy.deepcopy(MANIFEST)
            bad["workshare"][field].reverse()
            with self.subTest(field=field, mutation="reorder"), self.assertRaises(ContractError):
                compile_acceptance(bad)

        bad = copy.deepcopy(MANIFEST)
        bad["model_acceptance"]["handoff_artifacts"].reverse()
        with self.assertRaises(ContractError):
            compile_acceptance(bad)

    def test_metric_choices_are_code_owned(self):
        attempts = {
            "calibration": "log_loss_and_reliability",
            "ranking": "precision_recall_at_k",
            "evaluation_split": "random_split",
        }
        for field, replacement in attempts.items():
            bad = copy.deepcopy(MANIFEST)
            bad["model_acceptance"]["metrics"][field] = replacement
            with self.subTest(field=field), self.assertRaises(ContractError):
                compile_acceptance(bad)

    def test_false_signed_scope_cannot_be_resealed(self):
        mutations = []

        bad = copy.deepcopy(MANIFEST)
        bad["workshare"]["deliverables"][0] = (
            "Westfield awarded and paid Token Junkie Labs"
        )
        mutations.append(bad)

        bad = copy.deepcopy(MANIFEST)
        bad["workshare"]["exclusions"][0] = (
            "buyer portal submission included and authorized"
        )
        mutations.append(bad)

        bad = copy.deepcopy(MANIFEST)
        bad["model_acceptance"]["handoff_artifacts"][0] = (
            "buyer-approved production-data export"
        )
        mutations.append(bad)

        bad = copy.deepcopy(MANIFEST)
        bad["sources"][1]["note"] = "KHow confirmed this workshare"
        mutations.append(bad)

        for index, mutated in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(ContractError):
                make_receipt(mutated)
            self.assertFalse(verify_receipt(mutated, make_receipt(MANIFEST)))


if __name__ == "__main__":
    unittest.main()
