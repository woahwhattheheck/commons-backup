from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import unittest

from revenue.outbound_connector_lease.authority import (
    IDENTITY_STATE,
    STATE,
    SeamAuthorityError,
    admit_compiled_seam,
    admit_json,
    main,
)
from revenue.outbound_connector_lease.key import LeaseKeyError, compile_key
from revenue.outbound_mutex.lease import lead_key as legacy_lead_key


def cold(scope: str = "example.com"):
    return compile_key(scope, {"kind": "cold"})


def external(scope: str = "prime.example", authority: str = "issuer.example", ident: str = "rfp-04254"):
    return compile_key(
        scope,
        {"kind": "external", "authority": authority, "id": ident},
    )


def legacy(opportunity: str = "Acme / $199 diagnostic"):
    return {
        "version": 1,
        "key": legacy_lead_key(
            opportunity=opportunity,
            channel="email",
            destination="buyer@example.com",
        ),
        "opportunity": opportunity,
        "channel": "email",
        "destination_sha256": "0" * 64,
        "holder": "Z-Test",
        "state": "active",
        "acquired_at": "2026-09-14T03:00:00Z",
        "expires_at": "2026-09-14T03:30:00Z",
        "provider_snapshot": "1" * 64,
        "generation": 1,
        "released_at": None,
        "release_reason": None,
        "sent_at": None,
        "send_receipt_sha256": None,
    }


class CanonicalSeamAuthorityTests(unittest.TestCase):
    def assert_incomplete_production_receipt(self, receipt):
        self.assertEqual(receipt["state"], STATE)
        self.assertEqual(receipt["identity_state"], IDENTITY_STATE)
        self.assertTrue(receipt["canonical_seam_identity_valid"])
        self.assertTrue(receipt["atomic_branch_create_required"])
        self.assertTrue(receipt["ref_rollback_protection_required"])
        self.assertFalse(receipt["ref_rollback_protection_verified"])
        self.assertTrue(receipt["pre_protection_history_ambiguous"])
        self.assertFalse(receipt["branch_create_authority"])
        self.assertTrue(receipt["organization_scope_authority_required"])
        self.assertTrue(receipt["organization_wide_mutex_required"])
        self.assertFalse(receipt["production_mutex_complete"])
        self.assertTrue(receipt["provider_reread_required"])
        self.assertFalse(receipt["legacy_mutex_accepted"])
        self.assertFalse(receipt["external_send_authorized"])

    def test_canonical_cold_seam_is_admitted_but_incomplete_for_production(self):
        self.assert_incomplete_production_receipt(admit_compiled_seam(cold()))

    def test_canonical_external_seam_round_trips(self):
        candidate = external()
        receipt = admit_json(json.dumps(candidate, sort_keys=True))
        self.assertEqual(receipt["branch"], candidate["branch"])
        self.assertEqual(receipt["seam_sha256"], candidate["seam_sha256"])
        self.assert_incomplete_production_receipt(receipt)

    def test_same_org_cold_spelling_normalizes_but_identity_fields_cannot_expand(self):
        first = cold("Example.COM.")
        second = cold("example.com")
        self.assertEqual(first, second)
        for field in ("recipient", "price", "route", "draft", "subject", "campaign"):
            with self.subTest(field=field), self.assertRaises(LeaseKeyError):
                compile_key("example.com", {"kind": "cold", field: "alias"})

    def test_external_contact_price_route_aliases_have_no_schema_slot(self):
        baseline = external()
        for field in ("recipient", "price", "route", "draft", "subject"):
            mutated = {
                "kind": "external",
                "authority": "issuer.example",
                "id": "rfp-04254",
                field: "variant",
            }
            with self.subTest(field=field), self.assertRaises(LeaseKeyError):
                compile_key("prime.example", mutated)
        self.assertEqual(baseline, external("PRIME.EXAMPLE.", "ISSUER.EXAMPLE.", "RFP-04254"))

    def test_distinct_org_opportunities_remain_distinct_and_require_org_mutex(self):
        candidates = (
            cold("example.com"),
            external("example.com", "issuer.example", "rfp-a"),
            external("example.com", "issuer.example", "rfp-b"),
        )
        self.assertEqual(len({candidate["branch"] for candidate in candidates}), 3)
        for candidate in candidates:
            with self.subTest(opportunity=candidate["opportunity"]):
                self.assert_incomplete_production_receipt(admit_compiled_seam(candidate))

    def test_buyer_scope_subdomain_alias_is_not_claimed_canonical(self):
        primary = cold("example.com")
        subdomain = cold("www.example.com")
        self.assertNotEqual(primary["branch"], subdomain["branch"])
        for candidate in (primary, subdomain):
            receipt = admit_compiled_seam(candidate)
            self.assertTrue(receipt["organization_scope_authority_required"])
            self.assertFalse(receipt["production_mutex_complete"])

    def test_external_authority_domain_alias_is_not_claimed_canonical(self):
        issuer = external("buyer.example", "issuer.example", "rfp-42")
        portal = external("buyer.example", "portal.issuer.example", "rfp-42")
        self.assertNotEqual(issuer["branch"], portal["branch"])
        for candidate in (issuer, portal):
            self.assert_incomplete_production_receipt(admit_compiled_seam(candidate))

    def test_legacy_free_form_aliases_reproduce_parallel_key_bug(self):
        a = legacy_lead_key(
            opportunity="SigNoz / $2,500 survival proof",
            channel="email",
            destination="dev@signoz.io",
        )
        b = legacy_lead_key(
            opportunity="signoz agent reliability pilot",
            channel="email",
            destination="dev@signoz.io",
        )
        self.assertNotEqual(a, b)

    def test_legacy_active_document_is_rejected(self):
        with self.assertRaisesRegex(SeamAuthorityError, "legacy revenue/outbound_mutex"):
            admit_compiled_seam(legacy())

    def test_legacy_sent_document_is_still_rejected_as_canonical_seam(self):
        candidate = legacy()
        candidate.update(
            state="sent",
            sent_at="2026-09-14T03:10:00Z",
            send_receipt_sha256="2" * 64,
        )
        with self.assertRaisesRegex(SeamAuthorityError, "non-authoritative"):
            admit_compiled_seam(candidate)

    def test_tampered_branch_is_rejected(self):
        candidate = cold()
        candidate["branch"] += "-alias"
        with self.assertRaisesRegex(SeamAuthorityError, "canonical recomputation"):
            admit_compiled_seam(candidate)

    def test_tampered_digest_is_rejected(self):
        candidate = cold()
        candidate["seam_sha256"] = "0" * 64
        with self.assertRaisesRegex(SeamAuthorityError, "canonical recomputation"):
            admit_compiled_seam(candidate)

    def test_extra_compiled_field_is_rejected(self):
        candidate = {**cold(), "recipient": "buyer@example.com"}
        with self.assertRaisesRegex(SeamAuthorityError, "exact schema"):
            admit_compiled_seam(candidate)

    def test_schema_downgrade_is_rejected(self):
        candidate = cold()
        candidate["schema"] = "outbound-mutex/v1"
        with self.assertRaisesRegex(SeamAuthorityError, "schema must"):
            admit_compiled_seam(candidate)

    def test_duplicate_json_key_is_rejected(self):
        good = cold()
        raw = (
            '{"schema":"outbound-connector-lease/v1",'
            '"schema":"outbound-mutex/v1",'
            f'"buyer_scope":{json.dumps(good["buyer_scope"])},'
            f'"opportunity":{json.dumps(good["opportunity"])},'
            f'"seam_sha256":{json.dumps(good["seam_sha256"])},'
            f'"branch":{json.dumps(good["branch"])}' + "}"
        )
        with self.assertRaises(SeamAuthorityError):
            admit_json(raw)

    def test_plain_dict_only(self):
        class Sneaky(dict):
            pass

        with self.assertRaisesRegex(SeamAuthorityError, "plain JSON object"):
            admit_compiled_seam(Sneaky(cold()))

    def test_cli_holds_after_identity_validation_until_ref_protection_is_verified(self):
        candidate = json.dumps(cold(), sort_keys=True)
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = main(["--json", candidate])
        self.assertEqual(result, 2)
        receipt = json.loads(stdout.getvalue())
        self.assert_incomplete_production_receipt(receipt)
        self.assertIn("HOLD: ref rollback protection", stderr.getvalue())

    def test_package_readme_preserves_production_composition_order(self):
        text = Path(__file__).with_name("README.md").read_text(encoding="utf-8")
        self.assertIn("not, by itself, an organization-wide production mutex", text)
        self.assertIn("production_mutex_complete=false", text)
        self.assertIn("external_send_authorized=false", text)
        org_scope = text.index("1. **Authoritative organization scope.**")
        org_mutex = text.index("2. **Organization-wide atomic control.**")
        seam = text.index("3. **Canonical opportunity/reply seam.**")
        provider = text.index("4. **Provider readback and ordinary gates.**")
        self.assertLess(org_scope, org_mutex)
        self.assertLess(org_mutex, seam)
        self.assertLess(seam, provider)

    def test_all_operator_docs_hold_on_unverified_ref_rollback_protection(self):
        package = Path(__file__).resolve().parent
        root = package.parents[1]
        documents = {
            "README": (package / "README.md").read_text(encoding="utf-8"),
            "AUTHORITY": (package / "AUTHORITY.md").read_text(encoding="utf-8"),
            "SKILL": (root / ".agents" / "skills" / "outbound-send" / "SKILL.md").read_text(encoding="utf-8"),
        }
        for label, text in documents.items():
            with self.subTest(document=label):
                self.assertIn("ref_rollback_protection_required=true", text)
                self.assertIn("ref_rollback_protection_verified=false", text)
                self.assertIn("branch_create_authority=false", text)
                self.assertIn("HOLD_REF_ROLLBACK_PROTECTION_UNVERIFIED", text)


if __name__ == "__main__":
    unittest.main()
