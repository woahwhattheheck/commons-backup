"""Native schema adapter tests; actual parent execution is native_rehearsal.py."""
from copy import deepcopy
import csv
import io
import unittest

import native_bridge as b


def document():
    return {"schema": b.DOC_SCHEMA, "version": "DRAFT-1", "synthetic": True,
            "report_receipt_sha256": "a" * 64, "applied_cycles": [], "unresolved": [],
            "findings": [{"id": "FND-SYN-01"}]}


def csv_data(**extra):
    row = dict(comment_id="Source ID with Unicode Δ", reviewer_role="Practitioner",
               comment_text="Original comment\nSecond line", finding_id="FND-SYN-01", report_version="DRAFT-1",
               comment_kind="wording", proposed_edit="Requested title", decision="ACCEPT")
    row.update(extra)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(row), lineterminator="\r\n")
    writer.writeheader(); writer.writerow(row)
    return stream.getvalue().encode()


def prep(raw=None, doc=None, **kwargs):
    return b.prepare_cycle(raw or csv_data(), "collection-1", "source.csv", doc or document(),
                           {"receipt_sha256": "a" * 64}, "IMPORT-1", "DRAFT-2", **kwargs)


class TestNativeBridge(unittest.TestCase):
    def test_native_cycle_fields_and_digest_contract(self):
        p = prep()
        self.assertEqual(set(p["cycle"]), {"schema", "id", "base_document_sha256", "base_report_receipt_sha256",
                                          "target_report_receipt_sha256", "new_version", "comments"})
        import hashlib
        import json
        expected = hashlib.sha256((json.dumps(document(), sort_keys=True, ensure_ascii=False,
                                               separators=(",", ":")) + "\n").encode()).hexdigest()
        self.assertEqual(p["cycle"]["base_document_sha256"], expected)

    def test_open_does_not_take_supplied_acceptance_or_edit(self):
        c = prep()["cycle"]["comments"][0]
        self.assertEqual(c["decision"], "OPEN")
        self.assertEqual(c["proposed_changes"], [])
        self.assertEqual(c["source_ids"], [])
        self.assertEqual(c["owner_role"], "UNASSIGNED")

    def test_source_id_and_role_and_proposed_edit_survive(self):
        p = prep()
        mapped = p["mapped"][0]
        self.assertEqual(mapped["record"]["values"]["comment_id"], "Source ID with Unicode Δ")
        self.assertEqual(mapped["reviewer_role"], "Practitioner")
        self.assertEqual(mapped["record"]["values"]["proposed_edit"], "Requested title")
        self.assertRegex(mapped["native_comment_id"], r"^IMP-[0-9a-f]{64}$")
        self.assertEqual(p["cycle"]["comments"][0]["comment"], "Original comment\nSecond line")

    def test_reviewer_does_not_become_owner(self):
        self.assertEqual(prep()["cycle"]["comments"][0]["owner_role"], "UNASSIGNED")
        self.assertEqual(prep(csv_data(owner_role="Review chair"))["cycle"]["comments"][0]["owner_role"], "Review chair")

    def test_unknown_kind_retained_not_guessed(self):
        p = prep(csv_data(comment_kind="comment"))
        self.assertEqual(p["cycle"]["comments"], [])
        self.assertEqual(p["native_unresolved"][0]["diagnostics"][0]["code"], "NATIVE_KIND_REQUIRED")

    def test_native_rejection_retains_original_without_normalizing(self):
        def native_text(value, where):
            if "\r" in value:
                raise ValueError("comment: control character")
        p = prep(csv_data(comment_text="one\r\ntwo"), validate_text=native_text)
        self.assertEqual(p["cycle"]["comments"], [])
        self.assertEqual(p["native_unresolved"][0]["record"]["values"]["comment_text"], "one\r\ntwo")
        self.assertEqual(p["native_unresolved"][0]["diagnostics"][0]["code"], "NATIVE_TEXT_REJECTED")

    def test_reference_failures_do_not_enter_native_list(self):
        for extra in ({"finding_id": "missing"}, {"report_version": "DRAFT-0"}, {"finding_namespace": "other"}):
            with self.subTest(extra=extra):
                p = prep(csv_data(**extra))
                self.assertEqual(p["cycle"]["comments"], [])
                self.assertEqual(p["summary"]["unresolved"], 1)

    def test_same_pending_comment_is_not_added_twice(self):
        first = prep()
        c = first["cycle"]["comments"][0]
        doc = document()
        doc["unresolved"] = [{"comment_id": c["id"], "target_id": c["target_id"], "comment": c["comment"]}]
        second = prep(doc=doc)
        self.assertEqual(second["cycle"]["comments"], [])
        self.assertEqual(second["summary"]["already_present"], 1)

    def test_same_pending_id_different_text_is_explicit(self):
        first = prep()
        c = first["cycle"]["comments"][0]
        doc = document()
        doc["unresolved"] = [{"comment_id": c["id"], "target_id": c["target_id"], "comment": "other"}]
        second = prep(doc=doc)
        self.assertEqual(second["cycle"]["comments"], [])
        self.assertEqual(second["native_unresolved"][0]["diagnostics"][0]["code"], "NATIVE_ID_CONFLICT")

    def test_document_report_drift_is_rejected(self):
        doc = document(); doc["report_receipt_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "receipt mismatch"):
            prep(doc=doc)

    def test_cycle_reapplication_rejected(self):
        doc = document(); doc["applied_cycles"] = ["IMPORT-1"]
        with self.assertRaisesRegex(ValueError, "already applied"):
            prep(doc=doc)

    def test_duplicate_document_ids_are_not_resolved(self):
        doc = document(); doc["findings"].append(dict(doc["findings"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            prep(doc=doc)

    def test_no_mutation_and_repeat_preparation_identical(self):
        doc = document(); snapshot = deepcopy(doc)
        a = prep(doc=doc); z = prep(doc=doc)
        self.assertEqual(a, z)
        self.assertEqual(doc, snapshot)

    def test_changed_reimport_variants_stay_out_of_native(self):
        first = prep()
        second = prep(csv_data(comment_text="changed"), prior=first["staged"]["state"])
        self.assertEqual(second["cycle"]["comments"], [])
        self.assertEqual(second["summary"]["unresolved"], 1)


if __name__ == "__main__":
    unittest.main()
