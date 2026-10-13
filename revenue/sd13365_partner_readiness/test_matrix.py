from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import matrix


HERE = Path(__file__).resolve().parent
BASELINE = matrix.load_matrix(HERE / "requirements.json")


class MatrixTests(unittest.TestCase):
    def fresh(self) -> dict:
        return copy.deepcopy(BASELINE)

    def requirement(self, value: dict, requirement_id: str) -> dict:
        return next(item for item in value["requirements"] if item["id"] == requirement_id)

    def test_baseline_is_complete_and_conservative(self) -> None:
        receipt = matrix.build_receipt(self.fresh())
        self.assertEqual(receipt["counts"], {"PASS": 0, "RED": 0, "UNKNOWN": 13})
        self.assertEqual(receipt["strongest_state"], "PUBLIC_EVIDENCE_GAPS_DOCUMENTED")
        self.assertEqual(set(receipt["unknown_ids"]), set(matrix.EXPECTED_REQUIREMENTS))
        self.assertTrue(all(value is False for value in receipt["authority"].values()))

    def test_receipt_is_deterministic_across_key_and_requirement_order(self) -> None:
        first = self.fresh()
        second = dict(reversed(list(self.fresh().items())))
        second["requirements"] = list(reversed(second["requirements"]))
        first_receipt = matrix.build_receipt(first)
        second_receipt = matrix.build_receipt(second)
        self.assertEqual(first_receipt["matrix_sha256"], second_receipt["matrix_sha256"])
        self.assertEqual(first_receipt, second_receipt)

    def test_changed_evidence_is_rejected_by_reviewed_source_binding(self) -> None:
        value = self.fresh()
        self.requirement(value, "fips-140-3")["rationale"] += " Additional evidence pending."
        with self.assertRaisesRegex(matrix.MatrixError, "matrix differs from reviewed source generation"):
            matrix.build_receipt(value)

    def test_changed_due_date_is_rejected_by_reviewed_source_binding(self) -> None:
        value = self.fresh()
        value["opportunity"]["due_at"] = "2026-10-17T15:00:00-07:00"
        with self.assertRaisesRegex(matrix.MatrixError, "matrix differs from reviewed source generation"):
            matrix.build_receipt(value)

    def test_duplicate_json_key_is_rejected(self) -> None:
        with self.assertRaisesRegex(matrix.MatrixError, "duplicate JSON key"):
            matrix.loads_strict('{"schema":1,"schema":1}')

    def test_nonfinite_json_number_is_rejected(self) -> None:
        with self.assertRaisesRegex(matrix.MatrixError, "non-finite"):
            matrix.loads_strict('{"schema":NaN}')

    def test_bool_schema_is_rejected(self) -> None:
        value = self.fresh()
        value["schema"] = True
        with self.assertRaisesRegex(matrix.MatrixError, "not bool"):
            matrix.build_receipt(value)

    def test_missing_requirement_is_rejected(self) -> None:
        value = self.fresh()
        value["requirements"].pop()
        with self.assertRaisesRegex(matrix.MatrixError, "requirement set mismatch"):
            matrix.build_receipt(value)

    def test_duplicate_requirement_is_rejected(self) -> None:
        value = self.fresh()
        value["requirements"][-1] = copy.deepcopy(value["requirements"][0])
        with self.assertRaisesRegex(matrix.MatrixError, "duplicate requirement id"):
            matrix.build_receipt(value)

    def test_unknown_cannot_hide_direct_support(self) -> None:
        value = self.fresh()
        target = self.requirement(value, "sso-saml-oauth")
        target["public_evidence"][0]["relationship"] = "direct_support"
        with self.assertRaisesRegex(matrix.MatrixError, "UNKNOWN may contain only adjacent"):
            matrix.build_receipt(value)

    def test_unknown_cannot_hide_direct_contradiction(self) -> None:
        value = self.fresh()
        target = self.requirement(value, "fips-140-3")
        target["public_evidence"][0]["relationship"] = "direct_contradiction"
        with self.assertRaisesRegex(matrix.MatrixError, "UNKNOWN may contain only adjacent"):
            matrix.build_receipt(value)

    def test_pass_requires_direct_support(self) -> None:
        value = self.fresh()
        self.requirement(value, "sso-saml-oauth")["status"] = "PASS"
        with self.assertRaisesRegex(matrix.MatrixError, "PASS requires direct_support"):
            matrix.build_receipt(value)

    def test_red_requires_direct_contradiction(self) -> None:
        value = self.fresh()
        self.requirement(value, "fips-140-3")["status"] = "RED"
        with self.assertRaisesRegex(matrix.MatrixError, "RED requires direct_contradiction"):
            matrix.build_receipt(value)

    def test_pass_and_contradiction_conflict_is_rejected(self) -> None:
        value = self.fresh()
        target = self.requirement(value, "fips-140-3")
        target["status"] = "PASS"
        target["public_evidence"].append(copy.deepcopy(target["public_evidence"][0]))
        target["public_evidence"][0]["relationship"] = "direct_support"
        target["public_evidence"][1]["relationship"] = "direct_contradiction"
        with self.assertRaisesRegex(matrix.MatrixError, "PASS cannot coexist"):
            matrix.build_receipt(value)

    def test_red_and_support_conflict_is_rejected(self) -> None:
        value = self.fresh()
        target = self.requirement(value, "fips-140-3")
        target["status"] = "RED"
        target["public_evidence"].append(copy.deepcopy(target["public_evidence"][0]))
        target["public_evidence"][0]["relationship"] = "direct_contradiction"
        target["public_evidence"][1]["relationship"] = "direct_support"
        with self.assertRaisesRegex(matrix.MatrixError, "RED cannot coexist"):
            matrix.build_receipt(value)

    def test_http_evidence_url_is_rejected(self) -> None:
        value = self.fresh()
        self.requirement(value, "fips-140-3")["public_evidence"][0]["url"] = "http://cognisen.com/security-compliance"
        with self.assertRaisesRegex(matrix.MatrixError, "must use https"):
            matrix.build_receipt(value)

    def test_unallowlisted_host_is_rejected(self) -> None:
        value = self.fresh()
        self.requirement(value, "fips-140-3")["public_evidence"][0]["url"] = "https://example.com/evidence"
        with self.assertRaisesRegex(matrix.MatrixError, "not allowlisted"):
            matrix.build_receipt(value)

    def test_url_credentials_are_rejected(self) -> None:
        value = self.fresh()
        self.requirement(value, "fips-140-3")["public_evidence"][0]["url"] = "https://user:secret@cognisen.com/evidence"
        with self.assertRaisesRegex(matrix.MatrixError, "credentials"):
            matrix.build_receipt(value)

    def test_url_fragment_is_rejected(self) -> None:
        value = self.fresh()
        self.requirement(value, "fips-140-3")["public_evidence"][0]["url"] = "https://cognisen.com/security-compliance#claim"
        with self.assertRaisesRegex(matrix.MatrixError, "fragment"):
            matrix.build_receipt(value)

    def test_requirement_needs_official_county_source(self) -> None:
        value = self.fresh()
        target = self.requirement(value, "fips-140-3")
        target["county_sources"] = [target["county_sources"][1]]
        with self.assertRaisesRegex(matrix.MatrixError, "lacks an official"):
            matrix.build_receipt(value)

    def test_opportunity_identity_is_bound(self) -> None:
        value = self.fresh()
        value["opportunity"]["portal_id"] = "BPM013366"
        with self.assertRaisesRegex(matrix.MatrixError, "portal id mismatch"):
            matrix.build_receipt(value)

    def test_due_date_requires_timezone(self) -> None:
        value = self.fresh()
        value["opportunity"]["due_at"] = "2026-10-16T15:00:00"
        with self.assertRaisesRegex(matrix.MatrixError, "include an offset"):
            matrix.build_receipt(value)

    def test_authority_escalation_is_rejected(self) -> None:
        for field in sorted(matrix.FALSE_AUTHORITY_FIELDS):
            with self.subTest(field=field):
                value = self.fresh()
                value["authority"][field] = True
                with self.assertRaisesRegex(matrix.MatrixError, "must be false"):
                    matrix.build_receipt(value)

    def test_missing_forbidden_action_is_rejected(self) -> None:
        value = self.fresh()
        value["subcontract_wedge"]["forbidden_actions"].pop()
        with self.assertRaisesRegex(matrix.MatrixError, "exactly preserve"):
            matrix.build_receipt(value)

    def test_extra_forbidden_action_is_rejected(self) -> None:
        value = self.fresh()
        value["subcontract_wedge"]["forbidden_actions"].append("send_email")
        with self.assertRaisesRegex(matrix.MatrixError, "exactly preserve"):
            matrix.build_receipt(value)

    def test_duplicate_wedge_component_is_rejected(self) -> None:
        value = self.fresh()
        value["subcontract_wedge"]["components"][1]["id"] = value["subcontract_wedge"]["components"][0]["id"]
        with self.assertRaisesRegex(matrix.MatrixError, "duplicate or noncanonical"):
            matrix.build_receipt(value)

    def test_atomic_receipt_write_and_readback(self) -> None:
        receipt = matrix.build_receipt(self.fresh())
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "nested" / "receipt.json"
            matrix.write_receipt(output, receipt)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), receipt)
            self.assertTrue(output.read_bytes().endswith(b"\n"))

    def test_symlink_output_is_rejected(self) -> None:
        receipt = matrix.build_receipt(self.fresh())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            link = root / "receipt.json"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(matrix.MatrixError, "symlink output"):
                matrix.write_receipt(link, receipt)


if __name__ == "__main__":
    unittest.main()
