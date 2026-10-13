"""UIOWA-124: preserve rejection diagnostics when a native ID already exists.

These are adapter-level tests of the actual prepare_cycle/stage_comments code.
They are not a compiler, provider-CI, or full-parent execution receipt.
Fictional records only. No native engine files are modified.
"""
from copy import deepcopy
import csv
import io
import unittest

import native_bridge as bridge


SOURCE_ID = "K4J9-SYNTHETIC-REVIEW"
RECEIPT = "a" * 64


def row(**changes):
    item = {"comment_id": "COMMENT-SYN-1", "reviewer_role": "Practitioner",
            "comment_text": "Retain this original sentence.\nAnd this line.",
            "finding_id": "FND-SYN-1", "report_version": "DRAFT-1",
            "comment_kind": "wording", "owner_role": "Review chair",
            "proposed_edit": "Do not automatically apply this proposal.",
            "decision": "ACCEPT", "extension": "Original extension Δ"}
    item.update(changes)
    return item


def encode(*rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(row()), lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def document():
    return {"schema": bridge.DOC_SCHEMA, "version": "DRAFT-1", "synthetic": True,
            "report_receipt_sha256": RECEIPT, "applied_cycles": [], "unresolved": [],
            "findings": [{"id": "FND-SYN-1"}]}


def prepare(raw=None, doc=None, **kwargs):
    return bridge.prepare_cycle(raw if raw is not None else encode(row()), SOURCE_ID,
                                "synthetic-review.csv", doc if doc is not None else document(),
                                {"receipt_sha256": RECEIPT}, "IMPORT-K4J9-2", "DRAFT-2", **kwargs)


def pending_document():
    comment = prepare()["cycle"]["comments"][0]
    doc = document()
    # The native unresolved row really has these seven fields, not kind/target_type.
    doc["unresolved"] = [{"cycle_id": "IMPORT-K4J9-1", "comment_id": comment["id"],
                          "target_id": comment["target_id"], "comment": comment["comment"],
                          "decision": "OPEN", "rationale": "Previous synthetic import.",
                          "owner_role": comment["owner_role"]}]
    return doc


def reject_owner(value, field):
    """Exercise the adapter's documented validator-callback contract, not native CI."""
    if field == "owner_role":
        raise ValueError("test callback: owner needs review")


class TestNativeDuplicateDiagnostics(unittest.TestCase):
    def assert_unresolved(self, result, codes):
        self.assertEqual(result["already_present"], [])
        self.assertEqual(result["cycle"]["comments"], [])
        self.assertEqual(result["summary"]["native_unresolved"], 1)
        self.assertEqual(len(result["native_unresolved"]), 1)
        self.assertEqual([d["code"] for d in result["native_unresolved"][0]["diagnostics"]], codes)

    def test_unknown_kind_duplicate_stays_unresolved(self):
        self.assert_unresolved(prepare(encode(row(comment_kind="unsupported")), pending_document()),
                               ["NATIVE_KIND_REQUIRED"])

    def test_empty_kind_duplicate_stays_unresolved(self):
        self.assert_unresolved(prepare(encode(row(comment_kind="")), pending_document()),
                               ["NATIVE_KIND_REQUIRED"])

    def test_whitespace_kind_duplicate_stays_unresolved(self):
        self.assert_unresolved(prepare(encode(row(comment_kind=" wording ")), pending_document()),
                               ["NATIVE_KIND_REQUIRED"])

    def test_callback_rejection_is_not_suppressed_by_duplicate(self):
        self.assert_unresolved(prepare(doc=pending_document(), validate_text=reject_owner),
                               ["NATIVE_TEXT_REJECTED"])

    def test_multiple_rejections_survive_duplicate(self):
        self.assert_unresolved(prepare(encode(row(comment_kind="unknown")), pending_document(),
                                       validate_text=reject_owner),
                               ["NATIVE_KIND_REQUIRED", "NATIVE_TEXT_REJECTED"])

    def test_native_conflict_does_not_erase_kind_rejection(self):
        doc = pending_document(); doc["unresolved"][0]["comment"] = "A different retained comment."
        self.assert_unresolved(prepare(encode(row(comment_kind="unknown")), doc),
                               ["NATIVE_KIND_REQUIRED", "NATIVE_ID_CONFLICT"])

    def test_native_conflict_does_not_erase_callback_rejection(self):
        doc = pending_document(); doc["unresolved"][0]["target_id"] = "FND-SYN-2"
        self.assert_unresolved(prepare(doc=doc, validate_text=reject_owner),
                               ["NATIVE_TEXT_REJECTED", "NATIVE_ID_CONFLICT"])

    def test_all_rejections_are_retained_with_conflict(self):
        doc = pending_document(); doc["unresolved"][0]["comment"] = "Other retained text."
        self.assert_unresolved(prepare(encode(row(comment_kind="unknown")), doc,
                                       validate_text=reject_owner),
                               ["NATIVE_KIND_REQUIRED", "NATIVE_TEXT_REJECTED", "NATIVE_ID_CONFLICT"])

    def test_rejected_record_preserves_all_source_content_and_locators(self):
        original = row(comment_kind="unknown", extension="line one\r\nline two Δ")
        result = prepare(encode(original), pending_document())
        self.assertEqual(result["summary"]["native_unresolved"], 1)
        record = result["native_unresolved"][0]["record"]
        self.assertEqual(record["values"], original)
        self.assertEqual(record["occurrences"][0]["record_number"], 1)
        self.assertGreater(record["occurrences"][0]["line_end"], record["occurrences"][0]["line_start"])
        self.assertEqual(record["occurrences"][0]["source_id"], SOURCE_ID)

    def test_valid_duplicate_remains_idempotent(self):
        doc = pending_document(); snapshot = deepcopy(doc)
        result = prepare(doc=doc)
        self.assertEqual(result["summary"]["already_present"], 1)
        self.assertEqual(result["summary"]["native_unresolved"], 0)
        self.assertEqual(result["cycle"]["comments"], [])
        self.assertEqual(doc, snapshot)
        self.assertEqual(result, prepare(doc=doc))

    def test_valid_new_comment_stays_open_and_does_not_apply_source_decision(self):
        result = prepare(encode(row(comment_id="COMMENT-SYN-NEW")), pending_document())
        self.assertEqual(result["summary"]["native_open_comments"], 1)
        comment = result["cycle"]["comments"][0]
        self.assertEqual(comment["decision"], "OPEN")
        self.assertEqual(comment["proposed_changes"], [])
        self.assertEqual(comment["source_ids"], [])

    def test_mixed_batch_has_one_new_comment_and_one_explicit_rejection(self):
        result = prepare(encode(row(comment_kind="unknown"), row(comment_id="COMMENT-SYN-NEW")),
                         pending_document())
        self.assertEqual(result["summary"]["native_open_comments"], 1)
        self.assertEqual(result["summary"]["native_unresolved"], 1)
        self.assertEqual(result["summary"]["already_present"], 0)
        self.assertEqual(result["cycle"]["comments"][0]["decision"], "OPEN")

    def test_input_document_and_prior_state_are_not_mutated(self):
        doc = pending_document(); old = prepare(encode(row(comment_kind="unknown")))["staged"]["state"]
        before = deepcopy((doc, old))
        result = prepare(encode(row(comment_kind="unknown")), doc, prior=old)
        self.assertEqual((doc, old), before)
        self.assertEqual(result["summary"]["native_unresolved"], 1)
        self.assertEqual(result, prepare(encode(row(comment_kind="unknown")), doc, prior=old))

    def test_plain_native_conflict_is_unchanged(self):
        doc = pending_document(); doc["unresolved"][0]["comment"] = "A distinct retained original."
        self.assert_unresolved(prepare(doc=doc), ["NATIVE_ID_CONFLICT"])


if __name__ == "__main__":
    unittest.main()
