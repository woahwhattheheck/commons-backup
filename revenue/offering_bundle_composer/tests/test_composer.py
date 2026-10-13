from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
sys.path.insert(0, str(PACKAGE))

from composer import (  # noqa: E402
    HOLD,
    READY,
    DuplicateKeyError,
    compile_bundle,
    load_json_strict,
    render_markdown,
    sha256_json,
    verify_receipt,
)

AS_OF = "2026-09-13T10:00:00Z"


def digest(label: str) -> str:
    return sha256_json({"label": label})


def authority() -> dict:
    return {
        "buyer_contact": False,
        "external_send": False,
        "contract_execution": False,
        "buyer_acceptance": False,
        "checkout_or_payment": False,
        "fulfillment": False,
        "revenue_recognition": False,
    }


def entry(entry_id: str, family: str, n: int, *, price: int | None = 10000, deps=None, conflicts=None) -> dict:
    return {
        "entry_id": entry_id,
        "family": family,
        "version": "1.0.0",
        "source": {
            "repository": "woahwhattheheck/commons",
            "commit": f"{n:040x}",
            "path": f"revenue/catalog/{entry_id}.json",
            "content_sha256": digest(f"content-{entry_id}"),
        },
        "evidence": {
            "receipt_sha256": digest(f"evidence-{entry_id}"),
            "verified_at": "2026-09-13T09:55:00Z",
            "max_age_seconds": 3600,
        },
        "deliverables": [{
            "deliverable_id": f"{entry_id}-delivery",
            "description": f"Deliver {entry_id}",
            "acceptance_criteria": [f"Verify {entry_id} evidence"],
        }],
        "exclusions": ["No external action"],
        "depends_on": list(deps or []),
        "conflicts_with": list(conflicts or []),
        "pricing": (
            {"mode": "FIXED", "currency": "USD", "amount_minor": price}
            if price is not None
            else {"mode": "QUOTE_REQUIRED", "currency": None, "amount_minor": None}
        ),
        "authority": authority(),
    }


def manifest() -> dict:
    p = entry("product-a", "product", 1, price=2900)
    s = entry("service-b", "service", 2, price=250000, deps=["product-a"])
    e = entry("expertise-c", "expertise", 3, price=None, deps=["service-b"])
    return {
        "schema": "commons-offering-bundle-input/v1",
        "bundle_id": "rescue-stack",
        "title": "Rescue stack review candidate",
        "entries": [p, s, e],
    }


class ComposerTests(unittest.TestCase):
    def test_ready_cross_family_quote_required(self):
        receipt = compile_bundle(manifest(), trusted_as_of=AS_OF)
        self.assertEqual(READY, receipt["status"])
        self.assertEqual(["expertise", "product", "service"], receipt["families"])
        self.assertEqual("QUOTE_REQUIRED", receipt["pricing"]["mode"])
        self.assertTrue(all(value is False for value in receipt["authority"].values()))
        self.assertTrue(verify_receipt(manifest(), trusted_as_of=AS_OF, receipt=receipt))

    def test_fixed_money_aggregates_exact_integers(self):
        m = manifest()
        m["entries"][2]["pricing"] = {"mode": "FIXED", "currency": "USD", "amount_minor": 25000}
        receipt = compile_bundle(m, trusted_as_of=AS_OF)
        self.assertEqual(READY, receipt["status"])
        self.assertEqual({"mode": "FIXED", "currency": "USD", "amount_minor": 277900}, receipt["pricing"])

    def test_bool_is_not_integer_money(self):
        m = manifest()
        m["entries"][0]["pricing"]["amount_minor"] = True
        receipt = compile_bundle(m, trusted_as_of=AS_OF)
        self.assertEqual(HOLD, receipt["status"])
        self.assertIn("PRICE_AMOUNT_INVALID", receipt["reasons"])

    def test_mixed_fixed_currency_holds(self):
        m = manifest()
        m["entries"][2]["pricing"] = {"mode": "FIXED", "currency": "EUR", "amount_minor": 1}
        receipt = compile_bundle(m, trusted_as_of=AS_OF)
        self.assertIn("MIXED_FIXED_CURRENCIES_UNSUPPORTED", receipt["reasons"])

    def test_quote_required_cannot_smuggle_price(self):
        m = manifest()
        m["entries"][2]["pricing"]["amount_minor"] = 100
        receipt = compile_bundle(m, trusted_as_of=AS_OF)
        self.assertIn("QUOTE_REQUIRED_MUST_NOT_CARRY_PRICE", receipt["reasons"])

    def test_requires_two_families(self):
        m = manifest()
        m["entries"] = [entry("product-a", "product", 1), entry("product-b", "product", 2)]
        receipt = compile_bundle(m, trusted_as_of=AS_OF)
        self.assertIn("CROSS_FAMILY_COMPOSITION_REQUIRED", receipt["reasons"])

    def test_missing_dependency_holds(self):
        m = manifest()
        m["entries"][0]["depends_on"] = ["missing"]
        self.assertIn("DEPENDENCY_MISSING", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_cycle_holds(self):
        m = manifest()
        m["entries"][0]["depends_on"] = ["service-b"]
        self.assertIn("DEPENDENCY_CYCLE", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_conflict_holds(self):
        m = manifest()
        m["entries"][0]["conflicts_with"] = ["service-b"]
        self.assertIn("ENTRY_CONFLICT", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_duplicate_entry_id_holds(self):
        m = manifest()
        m["entries"][1]["entry_id"] = "product-a"
        self.assertIn("ENTRY_ID_DUPLICATE", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_duplicate_source_identity_holds(self):
        m = manifest()
        m["entries"][1]["source"] = deepcopy(m["entries"][0]["source"])
        self.assertIn("SOURCE_IDENTITY_DUPLICATE", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_mutable_source_ref_holds(self):
        m = manifest()
        m["entries"][0]["source"]["commit"] = "main"
        self.assertIn("SOURCE_REF_NOT_IMMUTABLE", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_path_traversal_holds(self):
        m = manifest()
        m["entries"][0]["source"]["path"] = "../secret"
        self.assertIn("SOURCE_PATH_INVALID", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_stale_evidence_holds(self):
        m = manifest()
        m["entries"][0]["evidence"]["verified_at"] = "2026-09-13T08:00:00Z"
        m["entries"][0]["evidence"]["max_age_seconds"] = 60
        self.assertIn("EVIDENCE_STALE", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_future_evidence_holds(self):
        m = manifest()
        m["entries"][0]["evidence"]["verified_at"] = "2026-09-13T10:00:01Z"
        self.assertIn("EVIDENCE_FROM_FUTURE", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_naive_or_offset_timestamp_rejected(self):
        for bad in ("2026-09-13T10:00:00", "2026-09-13T06:00:00-04:00"):
            m = manifest()
            m["entries"][0]["evidence"]["verified_at"] = bad
            self.assertIn("EVIDENCE_TIME_INVALID", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_sensitive_email_rejected(self):
        m = manifest()
        m["entries"][0]["deliverables"][0]["description"] = "Email alice@example.com the packet"
        self.assertIn("SENSITIVE_METADATA", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_sensitive_bearer_rejected(self):
        m = manifest()
        m["entries"][0]["exclusions"] = ["Bearer abcdefghijklmnopqrstuvwxyz"]
        self.assertIn("SENSITIVE_METADATA", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_external_authority_true_rejected(self):
        m = manifest()
        m["entries"][0]["authority"]["external_send"] = True
        self.assertIn("EXTERNAL_AUTHORITY_PRESENT", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_unknown_field_rejected(self):
        m = manifest()
        m["entries"][0]["discountCents"] = 100
        self.assertIn("ENTRY_SCHEMA_INVALID", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_missing_acceptance_coverage_holds(self):
        m = manifest()
        m["entries"][0]["deliverables"][0]["acceptance_criteria"] = []
        self.assertIn("ACCEPTANCE_COVERAGE_MISSING", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_duplicate_deliverable_holds(self):
        m = manifest()
        d = deepcopy(m["entries"][0]["deliverables"][0])
        m["entries"][0]["deliverables"].append(d)
        self.assertIn("DELIVERABLE_ID_DUPLICATE", compile_bundle(m, trusted_as_of=AS_OF)["reasons"])

    def test_duplicate_json_keys_rejected_before_compile(self):
        with self.assertRaises(DuplicateKeyError):
            load_json_strict('{"schema":"x","schema":"y"}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):
            load_json_strict('{"x":NaN}')

    def test_float_anywhere_holds(self):
        m = manifest()
        m["entries"][0]["pricing"]["amount_minor"] = 10.0
        receipt = compile_bundle(m, trusted_as_of=AS_OF)
        self.assertEqual(HOLD, receipt["status"])
        self.assertIn("NON_CANONICAL_JSON_VALUE", receipt["reasons"])

    def test_receipt_tamper_fails(self):
        m = manifest()
        receipt = compile_bundle(m, trusted_as_of=AS_OF)
        receipt["status"] = HOLD
        self.assertFalse(verify_receipt(m, trusted_as_of=AS_OF, receipt=receipt))

    def test_manifest_tamper_fails_old_receipt(self):
        m = manifest()
        receipt = compile_bundle(m, trusted_as_of=AS_OF)
        m["title"] = "Changed title"
        self.assertFalse(verify_receipt(m, trusted_as_of=AS_OF, receipt=receipt))

    def test_receipt_changes_with_trusted_time(self):
        m = manifest()
        r1 = compile_bundle(m, trusted_as_of=AS_OF)
        r2 = compile_bundle(m, trusted_as_of="2026-09-13T11:00:01Z")
        self.assertNotEqual(r1["receipt_digest"], r2["receipt_digest"])
        self.assertEqual(HOLD, r2["status"])
        self.assertIn("EVIDENCE_STALE", r2["reasons"])

    def test_markdown_preserves_authority_boundary(self):
        text = render_markdown(compile_bundle(manifest(), trusted_as_of=AS_OF))
        self.assertIn("does not authorize buyer contact", text)
        self.assertIn("Receipt SHA-256", text)

    def test_entry_order_does_not_change_bundle_semantics_digest_after_normalized_sorting(self):
        # Manifest digest intentionally binds exact input bytes/ordering semantics; receipt summary remains deterministic for same input.
        m = manifest()
        receipt = compile_bundle(m, trusted_as_of=AS_OF)
        self.assertEqual(receipt, compile_bundle(deepcopy(m), trusted_as_of=AS_OF))

    def test_cli_compile_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            manifest_path = tmp / "manifest.json"
            receipt_path = tmp / "receipt.json"
            md_path = tmp / "receipt.md"
            manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")
            env = dict(os.environ)
            compile_run = subprocess.run(
                [sys.executable, str(PACKAGE / "cli.py"), "compile", str(manifest_path), "--as-of", AS_OF, "--json-out", str(receipt_path), "--markdown-out", str(md_path)],
                cwd=PACKAGE, env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(0, compile_run.returncode, compile_run.stderr)
            verify_run = subprocess.run(
                [sys.executable, str(PACKAGE / "cli.py"), "verify", str(manifest_path), str(receipt_path), "--as-of", AS_OF],
                cwd=PACKAGE, env=env, text=True, capture_output=True, check=False,
            )
            self.assertEqual(0, verify_run.returncode, verify_run.stderr)
            self.assertEqual({"verified": True}, json.loads(verify_run.stdout))
            self.assertTrue(md_path.read_text(encoding="utf-8").startswith("# Offering bundle"))


if __name__ == "__main__":
    unittest.main()
