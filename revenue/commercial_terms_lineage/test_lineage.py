from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest

from lineage import (
    AUTHORITY_SCHEMA,
    REVIEW_SCHEMA,
    TermsLineageError,
    canonical_bytes,
    canonical_sha256,
    authority_sha256,
    compile_review,
    loads_strict,
    read_json_file,
    render_markdown,
    verify_review,
    write_exclusive,
)

NOW = datetime(2026, 9, 13, 13, 45, 0, tzinfo=timezone.utc)
H = lambda ch: ch * 64


def source(source_id: str, role: str, digest: str, *, reviewed=True, controlling=True, captured="2026-09-13T12:00:00Z"):
    return {
        "source_id": source_id,
        "role": role,
        "captured_at": captured,
        "url": f"https://buyer.example/{source_id}.pdf",
        "sha256": digest,
        "reviewed": reviewed,
        "controlling": controlling,
    }


def term(term_id: str, category: str, source_id: str, digest: str, *, mandatory=True, label=None, lineage="NEW", prior=None):
    return {
        "term_id": term_id,
        "category": category,
        "source_id": source_id,
        "clause_sha256": digest,
        "mandatory": mandatory,
        "label": label or term_id.replace("-", " ").title(),
        "lineage": lineage,
        "prior_clause_sha256": prior,
    }


def authority_one():
    return {
        "schema": AUTHORITY_SCHEMA,
        "authority_id": "auth-op-1-g1",
        "opportunity_id": "op-1",
        "source_generation": 1,
        "previous_authority_sha256": None,
        "issued_at": "2026-09-13T12:05:00Z",
        "source_set_complete": True,
        "max_source_age_days": 30,
        "max_decision_age_days": 30,
        "sources": [
            source("base", "BASE_TERMS", H("a")),
            source("form", "REQUIRED_FORM", H("b")),
        ],
        "terms": [
            term("mfn", "PRICING_MFN", "base", H("1")),
            term("public-records", "CONFIDENTIALITY_PUBLIC_RECORDS", "base", H("2")),
            term("audit", "AUDIT", "base", H("3")),
            term("insurance", "INSURANCE", "form", H("4")),
            term("data", "DATA_SECURITY", "form", H("5")),
        ],
        "retired_terms": [],
    }


def decision(term_id: str, digest: str, choice="ACCEPT_AS_WRITTEN", *, generation=1, opportunity="op-1", decision_id=None, decided_at="2026-09-13T12:10:00Z", evidence=None):
    return {
        "decision_id": decision_id or f"decision-{term_id}-g{generation}",
        "opportunity_id": opportunity,
        "source_generation": generation,
        "term_id": term_id,
        "term_digest": digest,
        "decision": choice,
        "decided_at": decided_at,
        "evidence_sha256": evidence or H("e"),
    }


def review_for(auth=None, posture="NO_EXCEPTIONS_CERTIFICATION_REQUIRED"):
    auth = auth or authority_one()
    return {
        "schema": REVIEW_SCHEMA,
        "opportunity_id": auth["opportunity_id"],
        "source_generation": auth["source_generation"],
        "certification_posture": posture,
        "decisions": [decision(t["term_id"], t["clause_sha256"], generation=auth["source_generation"], opportunity=auth["opportunity_id"]) for t in auth["terms"]],
    }


def authority_two(previous=None):
    previous = previous or authority_one()
    return {
        "schema": AUTHORITY_SCHEMA,
        "authority_id": "auth-op-1-g2",
        "opportunity_id": "op-1",
        "source_generation": 2,
        "previous_authority_sha256": authority_sha256(previous),
        "issued_at": "2026-09-13T13:00:00Z",
        "source_set_complete": True,
        "max_source_age_days": 30,
        "max_decision_age_days": 30,
        "sources": [
            source("base", "BASE_TERMS", H("a")),
            source("form", "REQUIRED_FORM", H("b")),
            source("addendum-1", "ADDENDUM", H("c"), captured="2026-09-13T12:55:00Z"),
        ],
        "terms": [
            term("mfn", "PRICING_MFN", "addendum-1", H("6"), lineage="REVISED", prior=H("1")),
            term("public-records", "CONFIDENTIALITY_PUBLIC_RECORDS", "base", H("2"), lineage="CARRY_FORWARD", prior=H("2")),
            term("audit", "AUDIT", "base", H("3"), lineage="CARRY_FORWARD", prior=H("3")),
            term("insurance", "INSURANCE", "form", H("4"), lineage="CARRY_FORWARD", prior=H("4")),
            term("data", "DATA_SECURITY", "form", H("5"), lineage="CARRY_FORWARD", prior=H("5")),
            term("ip", "INTELLECTUAL_PROPERTY", "addendum-1", H("7"), lineage="NEW", prior=None),
        ],
        "retired_terms": [],
    }


class LineageTests(unittest.TestCase):
    def test_clean_no_exceptions_is_owner_review_ready(self):
        auth = authority_one()
        receipt = compile_review(auth, review_for(auth), as_of=NOW)
        self.assertEqual(receipt["state"], "TERMS_CLEAR_FOR_OWNER_SUBMISSION_REVIEW")
        self.assertEqual(receipt["exception_manifest"], [])
        self.assertTrue(all(value is False for value in receipt["authority_ceiling"].values()))
        verify_review(auth, review_for(auth), receipt, trusted_now=NOW)

    def test_disclosed_exception_requires_manifest(self):
        auth = authority_one()
        review = review_for(auth, posture="EXCEPTIONS_MAY_BE_DISCLOSED")
        review["decisions"][0]["decision"] = "EXCEPTION_REQUESTED"
        receipt = compile_review(auth, review, as_of=NOW)
        self.assertEqual(receipt["state"], "EXCEPTION_DISCLOSURE_REQUIRED")
        self.assertEqual(len(receipt["exception_manifest"]), 1)
        self.assertEqual(receipt["exception_manifest"][0]["term_id"], "mfn")

    def test_exception_conflicts_with_no_exceptions_certification(self):
        auth = authority_one()
        review = review_for(auth)
        review["decisions"][0]["decision"] = "EXCEPTION_REQUESTED"
        receipt = compile_review(auth, review, as_of=NOW)
        self.assertEqual(receipt["state"], "CONFLICT")
        self.assertIn("NO_EXCEPTIONS_CERTIFICATION_CONFLICT", receipt["reasons"])

    def test_missing_decision_is_owner_required(self):
        auth = authority_one()
        review = review_for(auth)
        review["decisions"] = review["decisions"][1:]
        receipt = compile_review(auth, review, as_of=NOW)
        self.assertEqual(receipt["state"], "OWNER_DECISION_REQUIRED")

    def test_unknown_certification_posture_cannot_green(self):
        auth = authority_one()
        review = review_for(auth, posture="TERMS_POSTURE_NOT_YET_KNOWN")
        receipt = compile_review(auth, review, as_of=NOW)
        self.assertEqual(receipt["state"], "OWNER_DECISION_REQUIRED")

    def test_addendum_revised_term_invalidates_stale_prior_decision(self):
        prev = authority_one()
        auth = authority_two(prev)
        review = {
            "schema": REVIEW_SCHEMA,
            "opportunity_id": "op-1",
            "source_generation": 2,
            "certification_posture": "NO_EXCEPTIONS_CERTIFICATION_REQUIRED",
            "decisions": [],
        }
        for current in auth["terms"]:
            if current["term_id"] == "mfn":
                review["decisions"].append(decision("mfn", H("1"), generation=1))
            elif current["term_id"] == "ip":
                review["decisions"].append(decision("ip", H("7"), generation=2, decided_at="2026-09-13T13:05:00Z"))
            else:
                review["decisions"].append(decision(current["term_id"], current["clause_sha256"], generation=1))
        receipt = compile_review(auth, review, as_of=NOW, previous_authority=prev)
        self.assertEqual(receipt["state"], "OWNER_DECISION_REQUIRED")
        mfn = next(row for row in receipt["active_terms"] if row["term_id"] == "mfn")
        self.assertEqual(mfn["coverage_reason"], "STALE_TERM_DIGEST")

    def test_exact_carry_forward_retains_previous_generation_decision(self):
        prev = authority_one()
        auth = authority_two(prev)
        auth["terms"] = [t for t in auth["terms"] if t["term_id"] not in {"mfn", "ip"}]
        auth["retired_terms"] = [{"term_id": "mfn", "prior_clause_sha256": H("1"), "reason": "BUYER_REMOVED", "replaced_by_term_id": None}]
        review = {
            "schema": REVIEW_SCHEMA,
            "opportunity_id": "op-1",
            "source_generation": 2,
            "certification_posture": "NO_EXCEPTIONS_CERTIFICATION_REQUIRED",
            "decisions": [decision(t["term_id"], t["clause_sha256"], generation=1) for t in auth["terms"]],
        }
        receipt = compile_review(auth, review, as_of=NOW, previous_authority=prev)
        self.assertEqual(receipt["state"], "TERMS_CLEAR_FOR_OWNER_SUBMISSION_REVIEW")

    def test_new_addendum_term_without_decision_blocks(self):
        prev = authority_one()
        auth = authority_two(prev)
        review = {
            "schema": REVIEW_SCHEMA,
            "opportunity_id": "op-1",
            "source_generation": 2,
            "certification_posture": "NO_EXCEPTIONS_CERTIFICATION_REQUIRED",
            "decisions": [],
        }
        for current in auth["terms"]:
            if current["term_id"] == "ip":
                continue
            generation = 2 if current["term_id"] == "mfn" else 1
            review["decisions"].append(decision(current["term_id"], current["clause_sha256"], generation=generation, decided_at="2026-09-13T13:05:00Z" if generation == 2 else "2026-09-13T12:10:00Z"))
        receipt = compile_review(auth, review, as_of=NOW, previous_authority=prev)
        self.assertEqual(receipt["state"], "OWNER_DECISION_REQUIRED")
        self.assertIn("TERM_DECISION_REQUIRED:ip", receipt["reasons"])

    def test_generation_change_requires_previous_authority(self):
        auth = authority_two()
        with self.assertRaisesRegex(TermsLineageError, "previous authority required"):
            compile_review(auth, review_for(auth), as_of=NOW)

    def test_previous_authority_digest_is_exact(self):
        prev = authority_one()
        auth = authority_two(prev)
        auth["previous_authority_sha256"] = H("9")
        with self.assertRaisesRegex(TermsLineageError, "previous authority digest mismatch"):
            compile_review(auth, review_for(auth), as_of=NOW, previous_authority=prev)

    def test_disappearing_term_requires_explicit_retirement(self):
        prev = authority_one()
        auth = authority_two(prev)
        auth["terms"] = [t for t in auth["terms"] if t["term_id"] != "audit"]
        with self.assertRaisesRegex(TermsLineageError, "disappeared without explicit retirement"):
            compile_review(auth, review_for(auth), as_of=NOW, previous_authority=prev)

    def test_source_set_incomplete_and_unreviewed_addendum_refresh(self):
        auth = authority_one()
        auth["source_set_complete"] = False
        receipt = compile_review(auth, review_for(auth), as_of=NOW)
        self.assertEqual(receipt["state"], "SOURCE_REFRESH_REQUIRED")
        auth = authority_one()
        auth["sources"][0]["reviewed"] = False
        receipt = compile_review(auth, review_for(auth), as_of=NOW)
        self.assertEqual(receipt["state"], "SOURCE_REFRESH_REQUIRED")

    def test_stale_and_future_source_refresh(self):
        auth = authority_one()
        auth["sources"][0]["captured_at"] = "2026-07-01T00:00:00Z"
        receipt = compile_review(auth, review_for(auth), as_of=NOW)
        self.assertEqual(receipt["state"], "SOURCE_REFRESH_REQUIRED")
        auth = authority_one()
        auth["sources"][0]["captured_at"] = "2026-09-14T00:00:00Z"
        receipt = compile_review(auth, review_for(auth), as_of=NOW)
        self.assertEqual(receipt["state"], "SOURCE_REFRESH_REQUIRED")

    def test_cross_opportunity_decision_is_rejected(self):
        auth = authority_one()
        review = review_for(auth)
        review["decisions"][0]["opportunity_id"] = "op-2"
        with self.assertRaisesRegex(TermsLineageError, "cross-opportunity transplant"):
            compile_review(auth, review, as_of=NOW)

    def test_future_decision_holds(self):
        auth = authority_one()
        review = review_for(auth)
        review["decisions"][0]["decided_at"] = "2026-09-14T00:00:00Z"
        receipt = compile_review(auth, review, as_of=NOW)
        self.assertEqual(receipt["state"], "HOLD")

    def test_stale_decision_reopens_owner_review(self):
        auth = authority_one()
        auth["max_decision_age_days"] = 1
        review = review_for(auth)
        review["decisions"][0]["decided_at"] = "2026-09-01T00:00:00Z"
        receipt = compile_review(auth, review, as_of=NOW)
        self.assertEqual(receipt["state"], "OWNER_DECISION_REQUIRED")

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(TermsLineageError, "duplicate JSON key"):
            loads_strict('{"schema":"x","schema":"y"}')

    def test_bool_is_not_integer(self):
        auth = authority_one()
        auth["source_generation"] = True
        with self.assertRaisesRegex(TermsLineageError, "invalid integer"):
            compile_review(auth, review_for(authority_one()), as_of=NOW)

    def test_unknown_keys_rejected(self):
        auth = authority_one()
        auth["surprise"] = "nope"
        with self.assertRaisesRegex(TermsLineageError, "key mismatch"):
            compile_review(auth, review_for(authority_one()), as_of=NOW)

    def test_bad_url_and_hash_rejected(self):
        auth = authority_one()
        auth["sources"][0]["url"] = "http://buyer.example/base.pdf"
        with self.assertRaisesRegex(TermsLineageError, "HTTPS URL"):
            compile_review(auth, review_for(authority_one()), as_of=NOW)
        auth = authority_one()
        auth["sources"][0]["sha256"] = "xyz"
        with self.assertRaisesRegex(TermsLineageError, "SHA-256"):
            compile_review(auth, review_for(authority_one()), as_of=NOW)

    def test_input_order_invariant(self):
        auth = authority_one()
        review = review_for(auth)
        first = compile_review(auth, review, as_of=NOW)
        auth["sources"].reverse()
        auth["terms"].reverse()
        review["decisions"].reverse()
        second = compile_review(auth, review, as_of=NOW)
        self.assertEqual(canonical_bytes(first), canonical_bytes(second))

    def test_receipt_tamper_is_rejected(self):
        auth = authority_one()
        review = review_for(auth)
        receipt = compile_review(auth, review, as_of=NOW)
        tampered = deepcopy(receipt)
        tampered["state"] = "TERMS_CLEAR_FOR_OWNER_SUBMISSION_REVIEW"
        tampered["reasons"] = ["forged"]
        with self.assertRaisesRegex(TermsLineageError, "byte-identically"):
            verify_review(auth, review, tampered, trusted_now=NOW)

    def test_markdown_is_deterministic_and_contains_authority_ceiling(self):
        receipt = compile_review(authority_one(), review_for(), as_of=NOW)
        one = render_markdown(receipt)
        two = render_markdown(receipt)
        self.assertEqual(one, two)
        self.assertIn("does not authorize legal advice", one)
        self.assertIn("PRICING_MFN", one)

    def test_file_io_refuses_overwrite_and_symlink_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_path = root / "input.json"
            input_path.write_bytes(canonical_bytes(authority_one()))
            self.assertEqual(read_json_file(input_path)["schema"], AUTHORITY_SCHEMA)
            link = root / "link.json"
            try:
                link.symlink_to(input_path)
            except (OSError, NotImplementedError):
                link = None
            if link is not None:
                with self.assertRaisesRegex(TermsLineageError, "non-symlink"):
                    read_json_file(link)
            out = root / "out.json"
            write_exclusive(out, "first")
            with self.assertRaisesRegex(TermsLineageError, "overwrite"):
                write_exclusive(out, "second")

    def test_synthetic_multi_pursuit_fixture_exercises_material_categories(self):
        fixture_path = Path(__file__).with_name("synthetic_acceptance.json")
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        self.assertEqual(fixture["schema"], "commercial-terms-synthetic/v1")
        categories = set()
        states = []
        for case in fixture["cases"]:
            auth = case["authority"]
            review = case["review"]
            categories.update(term["category"] for term in auth["terms"])
            receipt = compile_review(auth, review, as_of=NOW)
            states.append(receipt["state"])
            self.assertEqual(receipt["state"], case["expected_state"])
        self.assertTrue({"PRICING_MFN", "CONFIDENTIALITY_PUBLIC_RECORDS", "AUDIT", "INSURANCE", "DATA_SECURITY"} <= categories)
        self.assertIn("TERMS_CLEAR_FOR_OWNER_SUBMISSION_REVIEW", states)
        self.assertIn("EXCEPTION_DISCLOSURE_REQUIRED", states)
        self.assertIn("OWNER_DECISION_REQUIRED", states)

    def test_same_digest_cannot_silently_change_category_or_mandatory_semantics(self):
        prev = authority_one()
        auth = authority_two(prev)
        target = next(t for t in auth["terms"] if t["term_id"] == "audit")
        target["category"] = "PRICING_MFN"
        with self.assertRaisesRegex(TermsLineageError, "semantic classification changed"):
            compile_review(auth, review_for(auth), as_of=NOW, previous_authority=prev)

    def test_changed_decision_bytes_under_same_id_invalidate_old_receipt(self):
        auth = authority_one()
        review = review_for(auth, posture="EXCEPTIONS_MAY_BE_DISCLOSED")
        receipt = compile_review(auth, review, as_of=NOW)
        changed = deepcopy(review)
        changed["decisions"][0]["decision"] = "EXCEPTION_REQUESTED"
        with self.assertRaisesRegex(TermsLineageError, "byte-identically"):
            verify_review(auth, changed, receipt, trusted_now=NOW)

    def test_source_set_shrink_cannot_verify_old_receipt(self):
        auth = authority_one()
        review = review_for(auth)
        receipt = compile_review(auth, review, as_of=NOW)
        shrunk = authority_one()
        shrunk["sources"] = [s for s in shrunk["sources"] if s["source_id"] != "form"]
        shrunk["terms"] = [t for t in shrunk["terms"] if t["source_id"] != "form"]
        shrunk_review = review_for(shrunk)
        with self.assertRaisesRegex(TermsLineageError, "byte-identically"):
            verify_review(shrunk, shrunk_review, receipt, trusted_now=NOW)

    def test_credentialed_https_url_is_rejected(self):
        auth = authority_one()
        auth["sources"][0]["url"] = "https://user:secret@buyer.example/base.pdf"
        with self.assertRaisesRegex(TermsLineageError, "HTTPS URL"):
            compile_review(auth, review_for(authority_one()), as_of=NOW)


if __name__ == "__main__":
    unittest.main()
