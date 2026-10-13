from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from . import engine as engine_module
    from .engine import compile_current, markdown
    from .schema import DeltaError
    from .test_helpers import decision_for, doc, generation, h, req
except ImportError:
    import engine as engine_module
    from engine import compile_current, markdown
    from schema import DeltaError
    from test_helpers import decision_for, doc, generation, h, req


class DeltaCoreTests(unittest.TestCase):
    NOW = "2026-09-13T18:00:00Z"

    def report(self, old, new, decisions=None):
        with patch.object(engine_module, "_process_now", return_value=self.NOW):
            return compile_current(old, new, decisions or [])

    def test_identical_semantics_with_review_is_clear(self):
        old = generation()
        new = generation("g2", "2026-09-13T13:00:00Z")
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "NO_MATERIAL_CHANGE")
        self.assertEqual(out["review_required"], [])

    def test_identical_semantics_without_review_requires_review(self):
        out = self.report(generation(), generation("g2", "2026-09-13T13:00:00Z"))
        self.assertEqual(out["state"], "REVIEW_REQUIRED")
        self.assertEqual(out["review_required"], ["R-001"])

    def test_new_addendum_requirement_requires_review(self):
        old = generation()
        new = generation(
            "g2", "2026-09-13T13:00:00Z",
            documents=[doc(), doc("add-1", role="ADDENDUM")],
            requirements=[req(), req("R-002", doc_id="add-1", category="security")],
        )
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "REVIEW_REQUIRED")
        self.assertEqual(out["document_delta"]["added"], ["add-1"])
        self.assertEqual(out["review_required"], ["R-002"])

    def test_information_only_addition_does_not_require_review_but_is_material(self):
        old = generation()
        new = generation(
            "g2", "2026-09-13T13:00:00Z",
            requirements=[req(), req("I-1", cls="INFORMATIONAL", response=None)],
        )
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "REVIEW_REQUIRED")
        self.assertEqual(out["review_required"], [])

    def test_changed_requirement_with_exact_supersession(self):
        old = generation()
        old_statement = old["requirements"][0]["statement_sha256"]
        new_req = req(statement=h("changed"), supersedes=old_statement)
        new = generation("g2", "2026-09-13T13:00:00Z", requirements=[new_req])
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "REVIEW_REQUIRED")
        self.assertFalse(out["conflicts"])
        self.assertIn("statement_sha256", out["requirement_delta"]["changed"][0]["fields"])

    def test_changed_requirement_without_supersession_conflicts(self):
        old = generation()
        new = generation("g2", "2026-09-13T13:00:00Z", requirements=[req(statement=h("changed"))])
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "CONFLICT")
        self.assertIn("requirement_changed_without_exact_supersession:R-001", out["conflicts"])

    def test_deadline_acceleration_is_material(self):
        old = generation(requirements=[req(deadline="2026-10-01T12:00:00Z")])
        base_statement = old["requirements"][0]["statement_sha256"]
        new = generation(
            "g2", "2026-09-13T13:00:00Z",
            requirements=[req(deadline="2026-09-29T12:00:00Z", supersedes=base_statement)],
        )
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "REVIEW_REQUIRED")
        self.assertIn("deadline_utc", out["requirement_delta"]["changed"][0]["fields"])

    def test_mandatory_to_optional_is_material(self):
        old = generation()
        s = old["requirements"][0]["statement_sha256"]
        new = generation("g2", "2026-09-13T13:00:00Z", requirements=[req(cls="SCOREABLE", supersedes=s)])
        out = self.report(old, new, [decision_for(old)])
        self.assertIn("class", out["requirement_delta"]["changed"][0]["fields"])

    def test_route_change_is_material(self):
        old = generation()
        s = old["requirements"][0]["statement_sha256"]
        new = generation("g2", "2026-09-13T13:00:00Z", requirements=[req(route="PRIME", supersedes=s)])
        out = self.report(old, new, [decision_for(old)])
        self.assertIn("route", out["requirement_delta"]["changed"][0]["fields"])

    def test_curable_change_is_material(self):
        old = generation()
        s = old["requirements"][0]["statement_sha256"]
        new = generation("g2", "2026-09-13T13:00:00Z", requirements=[req(curable=True, supersedes=s)])
        out = self.report(old, new, [decision_for(old)])
        self.assertIn("curable", out["requirement_delta"]["changed"][0]["fields"])

    def test_changed_document_with_exact_supersession(self):
        old = generation()
        oldsha = old["documents"][0]["sha256"]
        newdoc = doc(digest=h("rfp-v2"), supersedes=oldsha)
        new = generation("g2", "2026-09-13T13:00:00Z", documents=[newdoc])
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "REVIEW_REQUIRED")
        self.assertFalse(out["conflicts"])

    def test_changed_document_without_supersession_conflicts(self):
        old = generation()
        new = generation("g2", "2026-09-13T13:00:00Z", documents=[doc(digest=h("rfp-v2"))])
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "CONFLICT")
        self.assertIn("document_changed_without_exact_supersession:rfp", out["conflicts"])

    def test_replacement_document_may_change_id_with_exact_lineage(self):
        old = generation()
        oldsha = old["documents"][0]["sha256"]
        replacement = doc("rfp-revised", digest=h("rfp-v2"), supersedes=oldsha)
        new = generation(
            "g2", "2026-09-13T13:00:00Z",
            documents=[replacement],
            requirements=[req(doc_id="rfp-revised")],
        )
        new["requirements"][0]["supersedes_sha256"] = old["requirements"][0]["statement_sha256"]
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "REVIEW_REQUIRED")
        self.assertFalse(out["conflicts"])
        self.assertEqual(out["document_delta"]["removed"], [])
        self.assertEqual(out["document_delta"]["added"], [])
        self.assertEqual(out["document_delta"]["changed"][0]["old_document_id"], "rfp")
        self.assertEqual(out["document_delta"]["changed"][0]["new_document_id"], "rfp-revised")

    def test_markdown_renders_cross_id_document_replacement(self):
        old = generation()
        oldsha = old["documents"][0]["sha256"]
        new = generation(
            "g2", "2026-09-13T13:00:00Z",
            documents=[doc("rfp-revised", digest=h("rfp-v2"), supersedes=oldsha)],
            requirements=[req(doc_id="rfp-revised", supersedes=old["requirements"][0]["statement_sha256"])],
        )
        out = self.report(old, new, [decision_for(old)])
        self.assertIn("rfp->rfp-revised", markdown(out))

    def test_duplicate_old_document_bytes_make_cross_id_replacement_ambiguous(self):
        shared = h("same-bytes")
        old = generation(
            documents=[doc("rfp", digest=shared), doc("copy", role="ADDENDUM", digest=shared)]
        )
        new = generation(
            "g2", "2026-09-13T13:00:00Z",
            documents=[doc("rfp-revised", digest=h("new"), supersedes=shared)],
            requirements=[req(doc_id="rfp-revised", supersedes=old["requirements"][0]["statement_sha256"])],
        )
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "CONFLICT")
        self.assertIn("controlling_document_ambiguous_predecessor:rfp", out["conflicts"])
        self.assertIn("controlling_document_ambiguous_predecessor:copy", out["conflicts"])

    def test_multiple_replacement_documents_for_one_old_generation_conflict(self):
        old = generation()
        oldsha = old["documents"][0]["sha256"]
        new = generation(
            "g2", "2026-09-13T13:00:00Z",
            documents=[
                doc("rfp-a", digest=h("a"), supersedes=oldsha),
                doc("rfp-b", role="ADDENDUM", digest=h("b"), supersedes=oldsha),
            ],
            requirements=[req(doc_id="rfp-a")],
        )
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "CONFLICT")
        self.assertIn("controlling_document_multiple_successors:rfp", out["conflicts"])

    def test_removed_controlling_document_conflicts(self):
        old = generation(documents=[doc(), doc("add-1", role="ADDENDUM")])
        new = generation("g2", "2026-09-13T13:00:00Z")
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "CONFLICT")
        self.assertIn("controlling_document_removed:add-1", out["conflicts"])

    def test_removed_requirement_is_historical_only_but_material(self):
        old = generation(requirements=[req(), req("R-002")])
        new = generation("g2", "2026-09-13T13:00:00Z", requirements=[req()])
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "REVIEW_REQUIRED")
        self.assertIn("R-002", out["requirement_delta"]["removed"])
        self.assertNotIn("R-002", out["review_required"])

    def test_incomplete_new_source_requires_refresh(self):
        old = generation()
        new = generation("g2", "2026-09-13T13:00:00Z", complete=False)
        out = self.report(old, new, [decision_for(old)])
        self.assertEqual(out["state"], "SOURCE_REFRESH_REQUIRED")

    def test_stale_new_source_requires_refresh(self):
        old = generation(captured="2026-09-01T12:00:00Z")
        new = generation("g2", "2026-09-02T12:00:00Z")
        dec = decision_for(old)
        dec["decided_at"] = "2026-09-01T13:00:00Z"
        out = self.report(old, new, [dec])
        self.assertEqual(out["state"], "SOURCE_REFRESH_REQUIRED")

    def test_future_source_rejected(self):
        with self.assertRaises(DeltaError):
            self.report(generation(), generation("g2", "2026-09-14T19:00:00Z"))

    def test_new_generation_may_not_predate_old(self):
        with self.assertRaises(DeltaError):
            self.report(generation(), generation("g2", "2026-09-12T13:00:00Z"))

    def test_same_generation_changed_content_rejected(self):
        old = generation()
        new = generation(requirements=[req(statement=h("different"), supersedes=h("R-001"))])
        with self.assertRaises(DeltaError):
            self.report(old, new)

    def test_cross_opportunity_decision_rejected(self):
        old = generation()
        d = decision_for(old)
        d["opportunity_id"] = "other"
        with self.assertRaises(DeltaError):
            self.report(old, generation("g2", "2026-09-13T13:00:00Z"), [d])

    def test_stale_decision_requirement_digest_rejected(self):
        old = generation()
        d = decision_for(old)
        d["requirement_sha256"] = h("forged")
        with self.assertRaises(DeltaError):
            self.report(old, generation("g2", "2026-09-13T13:00:00Z"), [d])

    def test_duplicate_decisions_for_one_requirement_rejected(self):
        old = generation()
        d1 = decision_for(old)
        d2 = dict(d1)
        d2["decision_id"] = "d-two"
        with self.assertRaises(DeltaError):
            self.report(old, generation("g2", "2026-09-13T13:00:00Z"), [d1, d2])

    def test_future_decision_rejected(self):
        old = generation()
        d = decision_for(old)
        d["decided_at"] = "2026-09-14T12:00:00Z"
        with self.assertRaisesRegex(DeltaError, "from the future"):
            self.report(old, generation("g2", "2026-09-13T13:00:00Z"), [d])

    def test_decision_before_generation_rejected(self):
        old = generation()
        d = decision_for(old)
        d["decided_at"] = "2026-09-13T11:59:59Z"
        with self.assertRaises(DeltaError):
            self.report(old, generation("g2", "2026-09-13T13:00:00Z"), [d])


if __name__ == "__main__":
    unittest.main()
