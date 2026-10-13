from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from revenue.capability_service_catalog.catalog import (
    CatalogError,
    READY,
    compile_catalog,
    dumps_canonical,
    load_json_strict,
    mapping_sha256,
    render_csv,
    render_markdown,
    verify_package,
)
from revenue.capability_service_catalog.cli import main as cli_main

AS_OF = "2026-09-13T10:00:00Z"
COMMIT = "a" * 40
SHA = "b" * 64
RECEIPT = "c" * 64


def service_mapping(cap_ids=None, *, commercial=None, mode="VALIDATION"):
    if cap_ids is None:
        cap_ids = ["receipt-verification"]
    if commercial is None:
        commercial = {"mode": "FIXED", "currency": "USD", "minor_units": 250000}
    return {
        "service_id": "crash-resume-proof",
        "title": "Crash Resume Proof",
        "service_mode": mode,
        "delivery_format": "VALIDATION_PACKET",
        "capability_ids": cap_ids,
        "deliverables": [
            {
                "deliverable_id": "proof-packet",
                "description": "Deterministic crash and resume evidence packet",
                "acceptance_criteria": ["Receipt verifies offline", "Restart evidence is replayable"],
            }
        ],
        "exclusions": ["No production deployment", "No buyer acceptance inference"],
        "dependencies": ["Buyer supplies bounded reproduction fixture"],
        "commercial": commercial,
    }


def capability(cap_id="receipt-verification", *, observed="2026-09-12T10:00:00Z", modes=None):
    if modes is None:
        modes = ["VALIDATION", "ASSESSMENT"]
    return {
        "capability_id": cap_id,
        "name": f"Capability {cap_id}",
        "source": {
            "repo": "woahwhattheheck/commons",
            "commit": COMMIT,
            "path": f"revenue/{cap_id}/engine.py",
            "sha256": SHA,
        },
        "evidence": {
            "observed_at": observed,
            "outcome": "Hostile suite passes on exact bytes",
            "verification": "Offline receipt verification reproduced",
            "receipt_sha256": RECEIPT,
        },
        "allowed_service_modes": modes,
    }


def doc(*, capabilities=None, mapping=None, approved="2026-09-12T11:00:00Z", valid="2026-12-31T00:00:00Z"):
    if capabilities is None:
        capabilities = [capability()]
    if mapping is None:
        mapping = service_mapping()
    mapping_digest = mapping_sha256(mapping)
    return {
        "schema": "commons-capability-service-catalog-input/v1",
        "capabilities": capabilities,
        "services": [
            {
                "mapping": mapping,
                "owner_approval": {
                    "ref": "owner-review/2026-09-12/17",
                    "approved_at": approved,
                    "valid_until": valid,
                    "mapping_sha256": mapping_digest,
                },
            }
        ],
    }


class CatalogTests(unittest.TestCase):
    def test_ready_fixed_price(self):
        package = compile_catalog(doc(), as_of=AS_OF)
        self.assertEqual(package["catalog"]["status"], READY)
        self.assertTrue(verify_package(doc(), package, as_of=AS_OF))
        self.assertEqual(package["catalog"]["services"][0]["commercial"]["minor_units"], 250000)
        self.assertFalse(package["catalog"]["authority"]["cash_or_revenue_asserted"])

    def test_unpriced_scope_review_is_allowed_when_approved(self):
        mapping = service_mapping(commercial={"mode": "UNPRICED_SCOPE_REVIEW"})
        package = compile_catalog(doc(mapping=mapping), as_of=AS_OF)
        self.assertEqual(package["catalog"]["status"], READY)

    def test_input_order_is_semantically_deterministic(self):
        caps = [capability("zeta-cap"), capability("alpha-cap")]
        mapping = service_mapping(["zeta-cap", "alpha-cap"])
        first = doc(capabilities=caps, mapping=mapping)
        second = copy.deepcopy(first)
        second["capabilities"].reverse()
        second["services"][0]["mapping"]["capability_ids"].reverse()
        package1 = compile_catalog(first, as_of=AS_OF)
        package2 = compile_catalog(second, as_of=AS_OF)
        self.assertEqual(dumps_canonical(package1), dumps_canonical(package2))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(CatalogError):
            load_json_strict('{"schema":"x","schema":"y"}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(CatalogError):
            load_json_strict('{"x":NaN}')

    def test_unknown_top_key_rejected(self):
        value = doc()
        value["extra"] = True
        with self.assertRaises(CatalogError):
            compile_catalog(value, as_of=AS_OF)

    def test_mutable_source_ref_rejected(self):
        value = doc()
        value["capabilities"][0]["source"]["commit"] = "main"
        with self.assertRaises(CatalogError):
            compile_catalog(value, as_of=AS_OF)

    def test_bad_content_digest_rejected(self):
        value = doc()
        value["capabilities"][0]["source"]["sha256"] = "f00"
        with self.assertRaises(CatalogError):
            compile_catalog(value, as_of=AS_OF)

    def test_path_traversal_rejected(self):
        value = doc()
        value["capabilities"][0]["source"]["path"] = "revenue/../secret"
        with self.assertRaises(CatalogError):
            compile_catalog(value, as_of=AS_OF)

    def test_duplicate_capability_id_rejected(self):
        value = doc(capabilities=[capability(), capability()])
        with self.assertRaises(CatalogError):
            compile_catalog(value, as_of=AS_OF)

    def test_duplicate_service_id_rejected(self):
        value = doc()
        value["services"].append(copy.deepcopy(value["services"][0]))
        with self.assertRaises(CatalogError):
            compile_catalog(value, as_of=AS_OF)

    def test_unknown_capability_holds(self):
        mapping = service_mapping(["not-present"])
        package = compile_catalog(doc(mapping=mapping), as_of=AS_OF)
        self.assertEqual(package["catalog"]["status"], "HOLD")
        self.assertIn("SERVICE_REFERENCES_UNKNOWN_CAPABILITY", package["catalog"]["reason_codes"])
        self.assertIn("DEMONSTRATED_CAPABILITY_UNCOVERED", package["catalog"]["reason_codes"])

    def test_uncovered_capability_holds(self):
        caps = [capability(), capability("second-cap")]
        package = compile_catalog(doc(capabilities=caps), as_of=AS_OF)
        self.assertIn("DEMONSTRATED_CAPABILITY_UNCOVERED", package["catalog"]["reason_codes"])
        self.assertEqual(package["catalog"]["uncovered_capability_ids"], ["second-cap"])

    def test_stale_evidence_holds(self):
        value = doc(capabilities=[capability(observed="2025-01-01T00:00:00Z")], approved="2025-01-01T01:00:00Z")
        package = compile_catalog(value, as_of=AS_OF, max_evidence_age_days=90)
        self.assertIn("CAPABILITY_EVIDENCE_STALE", package["catalog"]["reason_codes"])

    def test_future_evidence_holds(self):
        value = doc(capabilities=[capability(observed="2026-09-14T00:00:00Z")], approved="2026-09-14T01:00:00Z")
        package = compile_catalog(value, as_of=AS_OF)
        self.assertIn("CAPABILITY_EVIDENCE_FROM_FUTURE", package["catalog"]["reason_codes"])
        self.assertIn("OWNER_APPROVAL_FROM_FUTURE", package["catalog"]["reason_codes"])

    def test_approval_mapping_digest_drift_holds(self):
        value = doc()
        value["services"][0]["mapping"]["title"] = "Changed after approval"
        package = compile_catalog(value, as_of=AS_OF)
        self.assertIn("OWNER_APPROVAL_MAPPING_DIGEST_MISMATCH", package["catalog"]["reason_codes"])

    def test_expired_approval_holds(self):
        value = doc(valid="2026-09-13T09:59:59Z")
        package = compile_catalog(value, as_of=AS_OF)
        self.assertIn("OWNER_APPROVAL_EXPIRED", package["catalog"]["reason_codes"])

    def test_approval_predating_evidence_holds(self):
        value = doc(approved="2026-09-12T09:00:00Z")
        package = compile_catalog(value, as_of=AS_OF)
        self.assertIn("OWNER_APPROVAL_PREDATES_CAPABILITY_EVIDENCE", package["catalog"]["reason_codes"])

    def test_invalid_approval_window_rejected(self):
        with self.assertRaises(CatalogError):
            compile_catalog(doc(approved="2026-09-12T11:00:00Z", valid="2026-09-12T10:59:59Z"), as_of=AS_OF)

    def test_mode_mismatch_holds(self):
        value = doc(capabilities=[capability(modes=["ASSESSMENT"])])
        package = compile_catalog(value, as_of=AS_OF)
        self.assertIn("CAPABILITY_MODE_NOT_AUTHORIZED", package["catalog"]["reason_codes"])

    def test_duplicate_capability_ref_rejected(self):
        mapping = service_mapping(["receipt-verification", "receipt-verification"])
        with self.assertRaises(CatalogError):
            compile_catalog(doc(mapping=mapping), as_of=AS_OF)

    def test_deliverable_requires_acceptance(self):
        mapping = service_mapping()
        mapping["deliverables"][0]["acceptance_criteria"] = []
        with self.assertRaises(CatalogError):
            compile_catalog(doc(mapping=mapping), as_of=AS_OF)

    def test_duplicate_deliverable_id_rejected(self):
        mapping = service_mapping()
        mapping["deliverables"].append(copy.deepcopy(mapping["deliverables"][0]))
        with self.assertRaises(CatalogError):
            compile_catalog(doc(mapping=mapping), as_of=AS_OF)

    def test_fixed_price_bool_rejected(self):
        mapping = service_mapping(commercial={"mode": "FIXED", "currency": "USD", "minor_units": True})
        with self.assertRaises(CatalogError):
            compile_catalog(doc(mapping=mapping), as_of=AS_OF)

    def test_fixed_price_zero_rejected(self):
        mapping = service_mapping(commercial={"mode": "FIXED", "currency": "USD", "minor_units": 0})
        with self.assertRaises(CatalogError):
            compile_catalog(doc(mapping=mapping), as_of=AS_OF)

    def test_fixed_price_missing_currency_rejected(self):
        mapping = service_mapping(commercial={"mode": "FIXED", "minor_units": 100})
        with self.assertRaises(CatalogError):
            compile_catalog(doc(mapping=mapping), as_of=AS_OF)

    def test_unpriced_cannot_smuggle_price(self):
        mapping = service_mapping(commercial={"mode": "UNPRICED_SCOPE_REVIEW", "currency": "USD", "minor_units": 1})
        with self.assertRaises(CatalogError):
            compile_catalog(doc(mapping=mapping), as_of=AS_OF)

    def test_secret_shaped_text_rejected(self):
        mapping = service_mapping()
        mapping["dependencies"] = ["Use Bearer abcdefghijklmnopqrstuvwxyz"]
        with self.assertRaises(CatalogError):
            compile_catalog(doc(mapping=mapping), as_of=AS_OF)

    def test_email_shaped_pii_rejected(self):
        mapping = service_mapping()
        mapping["dependencies"] = ["Ask person@example.com for data"]
        with self.assertRaises(CatalogError):
            compile_catalog(doc(mapping=mapping), as_of=AS_OF)

    def test_ssn_shaped_pii_rejected(self):
        mapping = service_mapping()
        mapping["dependencies"] = ["Fixture 123-45-6789"]
        with self.assertRaises(CatalogError):
            compile_catalog(doc(mapping=mapping), as_of=AS_OF)

    def test_receipt_tamper_rejected(self):
        value = doc()
        package = compile_catalog(value, as_of=AS_OF)
        package["receipt"]["status"] = "HOLD"
        self.assertFalse(verify_package(value, package, as_of=AS_OF))

    def test_catalog_tamper_rejected(self):
        value = doc()
        package = compile_catalog(value, as_of=AS_OF)
        package["catalog"]["services"][0]["title"] = "tampered"
        self.assertFalse(verify_package(value, package, as_of=AS_OF))

    def test_verifier_rejects_wrong_clock(self):
        value = doc()
        package = compile_catalog(value, as_of=AS_OF)
        self.assertFalse(verify_package(value, package, as_of="2026-09-13T10:00:01Z"))

    def test_csv_and_markdown_are_deterministic(self):
        package = compile_catalog(doc(), as_of=AS_OF)
        self.assertEqual(render_csv(package), render_csv(package))
        self.assertEqual(render_markdown(package), render_markdown(package))
        self.assertIn("crash-resume-proof", render_csv(package))
        self.assertIn("Authority boundary", render_markdown(package))

    def test_cli_create_exclusive_outputs_and_refuses_clobber(self):
        value = doc()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "input.json"
            out = root / "out"
            source.write_text(json.dumps(value), encoding="utf-8")
            rc = cli_main([str(source), "--as-of", AS_OF, "--out-dir", str(out)])
            self.assertEqual(rc, 0)
            self.assertTrue((out / "catalog.json").exists())
            self.assertTrue((out / "catalog.csv").exists())
            self.assertTrue((out / "catalog.md").exists())
            self.assertTrue((out / "receipt.json").exists())
            with self.assertRaises(FileExistsError):
                cli_main([str(source), "--as-of", AS_OF, "--out-dir", str(out)])

    def test_large_catalog_acceptance_is_complete_and_deterministic(self):
        caps = [capability(f"cap-{i:03d}") for i in range(120)]
        mapping = service_mapping([c["capability_id"] for c in caps])
        value = doc(capabilities=caps, mapping=mapping)
        first = compile_catalog(value, as_of=AS_OF)
        reversed_value = copy.deepcopy(value)
        reversed_value["capabilities"].reverse()
        reversed_value["services"][0]["mapping"]["capability_ids"].reverse()
        second = compile_catalog(reversed_value, as_of=AS_OF)
        self.assertEqual(first["catalog"]["status"], READY)
        self.assertEqual(first["catalog"]["uncovered_capability_ids"], [])
        self.assertEqual(first["catalog"]["capability_count"], 120)
        self.assertEqual(dumps_canonical(first), dumps_canonical(second))
        self.assertTrue(verify_package(value, first, as_of=AS_OF))

    def test_boolean_age_limit_rejected(self):
        with self.assertRaises(CatalogError):
            compile_catalog(doc(), as_of=AS_OF, max_evidence_age_days=True)

    def test_fractional_age_limit_rejected(self):
        with self.assertRaises(CatalogError):
            compile_catalog(doc(), as_of=AS_OF, max_evidence_age_days=30.5)

    def test_schema_requires_exact_known_keys(self):
        mapping = service_mapping()
        mapping["surprise"] = "ignored?"
        with self.assertRaises(CatalogError):
            compile_catalog(doc(mapping=mapping), as_of=AS_OF)

    def test_authority_flags_all_false(self):
        package = compile_catalog(doc(), as_of=AS_OF)
        self.assertTrue(all(value is False for value in package["catalog"]["authority"].values()))
        self.assertIs(package["receipt"]["side_effects_authorized"], False)


if __name__ == "__main__":
    unittest.main()
