from __future__ import annotations

import hashlib
import json
import unittest

from revenue.outbound_connector_lease.key import (
    BRANCH_PREFIX,
    SUPPORTED_REPLY_PROVIDERS,
    LeaseKeyError,
    _parse_json,
    compile_document,
    compile_key,
)


def cold():
    return {"kind": "cold"}


def external(authority="uiowa.edu", ident="1255311"):
    return {"kind": "external", "authority": authority, "id": ident}


def reply(provider="gmail", event_id="1a09b2e381d7fa0e"):
    return {"kind": "reply", "provider": provider, "event_id": event_id}


class LeaseKeyTests(unittest.TestCase):
    def test_deterministic_known_workday_external_seam(self):
        result = compile_key("workday.com", external())
        canonical = json.dumps(
            {
                "schema": "outbound-connector-lease/v1",
                "buyer_scope": "workday.com",
                "opportunity": {"kind": "external", "authority": "uiowa.edu", "id": "1255311"},
            }, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
        expected = hashlib.sha256(canonical).hexdigest()
        self.assertEqual(result["seam_sha256"], expected)
        self.assertEqual(result["branch"], BRANCH_PREFIX + expected)

    def test_domain_and_external_authority_normalization(self):
        a = compile_key("ExAmPle.COM.", external("Issuer.EXAMPLE.", "RFP-04254"))
        b = compile_key("example.com", external("issuer.example", "rfp-04254"))
        self.assertEqual(a, b)
        self.assertEqual(compile_key("BÜCHER.example", cold())["buyer_scope"], "xn--bcher-kva.example")

    def test_price_contact_route_cannot_enter_external_schema(self):
        base = external("lacsd.org", "04254")
        for field in ("price", "recipient", "route", "draft", "subject"):
            mutated = {**base, field: "variant"}
            with self.subTest(field=field), self.assertRaises(LeaseKeyError):
                compile_key("ghd.com", mutated)

    def test_external_id_is_stable_across_case(self):
        self.assertEqual(
            compile_key("ghd.com", external("lacsd.org", "RFP-04254")),
            compile_key("GHD.COM.", external("LACSD.ORG", "rfp-04254")),
        )

    def test_cold_scope_is_exact_and_org_level(self):
        self.assertEqual(compile_key("example.com", cold()), compile_key("EXAMPLE.COM.", {"kind": "COLD"}))
        with self.assertRaises(LeaseKeyError):
            compile_key("example.com", {"kind": "cold", "campaign": "x"})

    def test_reply_binds_provider_event_only(self):
        a = compile_key("example.com", reply("GMAIL", "ABC123"))
        b = compile_key("EXAMPLE.COM", reply("gmail", "abc123"))
        self.assertEqual(a, b)
        with self.assertRaises(LeaseKeyError):
            compile_key("example.com", {**reply(), "recipient": "other@example.com"})

    def test_known_gmail_reply_hash_remains_backward_compatible(self):
        result = compile_key("example.com", reply("gmail", "abc123"))
        canonical = json.dumps(
            {
                "schema": "outbound-connector-lease/v1",
                "buyer_scope": "example.com",
                "opportunity": {"kind": "reply", "provider": "gmail", "event_id": "abc123"},
            }, sort_keys=True, separators=(",", ":")
        ).encode("ascii")
        expected = hashlib.sha256(canonical).hexdigest()
        self.assertEqual(expected, result["seam_sha256"])
        self.assertEqual(BRANCH_PREFIX + expected, result["branch"])

    def test_canonical_reply_provider_registry_is_closed(self):
        for provider in sorted(SUPPORTED_REPLY_PROVIDERS):
            with self.subTest(provider=provider):
                result = compile_key("example.com", reply(provider, "event-1"))
                self.assertEqual(provider, result["opportunity"]["provider"])
        for alias in (
            "email",
            "gmail-api",
            "googlemail",
            "google-mail",
            "github-api",
            "github.com",
            "slack-api",
            "webform",
            "unknown",
        ):
            with self.subTest(alias=alias), self.assertRaisesRegex(
                LeaseKeyError, "canonical providers"
            ):
                compile_key("example.com", reply(alias, "event-1"))

    def test_url_and_email_are_rejected_as_domains(self):
        for value in ("https://example.com", "person@example.com", "example.com/path", "localhost"):
            with self.subTest(value=value), self.assertRaises(LeaseKeyError):
                compile_key(value, cold())
        for value in ("https://issuer.example", "x@issuer.example", "issuer.example/path"):
            with self.subTest(value=value), self.assertRaises(LeaseKeyError):
                compile_key("example.com", external(value, "123"))

    def test_invalid_domain_labels_rejected(self):
        for value in ("-a.example", "a-.example", "a..example", "a_example.com"):
            with self.subTest(value=value), self.assertRaises(LeaseKeyError):
                compile_key(value, cold())

    def test_machine_ids_reject_free_text_and_price_punctuation(self):
        for value in ("", "price $5000", "human contact", "a" * 192):
            with self.subTest(value=value), self.assertRaises(LeaseKeyError):
                compile_key("example.com", external("issuer.example", value))

    def test_opportunity_kind_exact_fields(self):
        with self.assertRaises(LeaseKeyError): compile_key("example.com", {"kind": "external", "authority": "x.example"})
        with self.assertRaises(LeaseKeyError): compile_key("example.com", {"kind": "reply", "provider": "gmail"})
        with self.assertRaises(LeaseKeyError): compile_key("example.com", {"kind": "unknown"})

    def test_document_schema_and_exact_fields(self):
        doc = {"schema": "outbound-connector-lease/v1", "buyer_scope": "example.com", "opportunity": cold()}
        self.assertEqual(compile_document(doc), compile_key("example.com", cold()))
        for mutation in ({**doc, "extra": 1}, {**doc, "schema": "v2"}, {"buyer_scope": "example.com", "opportunity": cold()}):
            with self.assertRaises(LeaseKeyError): compile_document(mutation)

    def test_strict_json_duplicate_and_nonfinite_rejected(self):
        with self.assertRaises(LeaseKeyError):
            _parse_json('{"schema":"outbound-connector-lease/v1","buyer_scope":"example.com","buyer_scope":"evil.com","opportunity":{"kind":"cold"}}')
        with self.assertRaises(LeaseKeyError):
            _parse_json('{"schema":"outbound-connector-lease/v1","buyer_scope":"example.com","opportunity":{"kind":"cold"},"x":NaN}')

    def test_bool_and_nonstring_rejected(self):
        for buyer, opportunity in ((True, cold()), (1, cold()), ("example.com", True), ("example.com", {"kind": True})):
            with self.assertRaises(LeaseKeyError): compile_key(buyer, opportunity)


if __name__ == "__main__":
    unittest.main()
