#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("uiowa140", HERE / "amendment_update.py")
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
assert spec.loader is not None
spec.loader.exec_module(m)

OLD = m.load_json(HERE / "fixtures" / "real_deadline_before.json")
NEW = m.load_json(HERE / "fixtures" / "real_deadline_after.json")
PROPOSAL = m.load_json(HERE / "fixtures" / "proposal_before.json")


class AmendmentUpdateTests(unittest.TestCase):
    def test_real_deadline_propagates_all_declared_fields(self):
        report = m.build_report(
            copy.deepcopy(OLD), copy.deepcopy(NEW), copy.deepcopy(PROPOSAL)
        )
        self.assertEqual(report["summary"]["structured_changes"], 1)
        self.assertEqual(report["summary"]["updated_fields"], 4)
        self.assertEqual(report["summary"]["conflicts"], 0)
        for field_id in (
            "proposal.response_deadline",
            "proposal.timeline.label",
            "proposal.review_window.note",
            "proposal.assumption.rfq_deadline",
        ):
            self.assertEqual(
                report["updated_proposal"]["fields"][field_id]["value"],
                "September 29, 2026, 3:00 PM Central",
            )

    def test_unchanged_price_retains_value(self):
        report = m.build_report(
            copy.deepcopy(OLD), copy.deepcopy(NEW), copy.deepcopy(PROPOSAL)
        )
        fields = report["updated_proposal"]["fields"]
        self.assertEqual(fields["proposal.base_price"]["value"], "USD 24000")
        self.assertEqual(fields["proposal.option_price"]["value"], "USD 4000")
        self.assertEqual(report["summary"]["unchanged"], 2)

    def test_drifted_field_conflicts_instead_of_overwrite(self):
        proposal = copy.deepcopy(PROPOSAL)
        proposal["fields"]["proposal.timeline.label"]["value"] = "Custom timeline text"
        report = m.build_report(copy.deepcopy(OLD), copy.deepcopy(NEW), proposal)
        self.assertEqual(report["summary"]["conflicts"], 1)
        self.assertEqual(
            report["updated_proposal"]["fields"]["proposal.timeline.label"]["value"],
            "Custom timeline text",
        )

    def test_uncertain_wording_requires_review(self):
        old = copy.deepcopy(OLD)
        new = copy.deepcopy(OLD)
        old["requirements"][1]["change_type"] = "text"
        new["requirements"][1]["change_type"] = "text"
        new["requirements"][1]["text"] = (
            "Base amount may exclude an undefined category"
        )
        delta = next(
            item
            for item in m.compare(old, new)
            if item["requirement_id"] == "REQ-BASE-WORKSHARE"
        )
        self.assertEqual(delta["status"], "REVIEW_REQUIRED")
        self.assertFalse(delta["auto_update"])

    def test_added_requirement_requires_review(self):
        newer = copy.deepcopy(NEW)
        newer["requirements"].append({
            "requirement_id": "REQ-SYN-NEW",
            "data_type": "text",
            "change_type": "text",
            "value": "x",
            "text": "Synthetic new requirement",
            "source_ref": "synthetic://fixture",
            "affects": ["proposal.synthetic"],
        })
        delta = next(
            item
            for item in m.compare(copy.deepcopy(NEW), newer)
            if item["requirement_id"] == "REQ-SYN-NEW"
        )
        self.assertEqual(delta["status"], "ADDED")
        self.assertFalse(delta["auto_update"])

    def test_already_current_is_idempotent(self):
        first = m.build_report(
            copy.deepcopy(OLD), copy.deepcopy(NEW), copy.deepcopy(PROPOSAL)
        )
        second = m.build_report(
            copy.deepcopy(OLD),
            copy.deepcopy(NEW),
            copy.deepcopy(first["updated_proposal"]),
        )
        self.assertEqual(
            sum(a["action"] == "ALREADY_CURRENT" for a in second["actions"]), 4
        )
        self.assertEqual(second["summary"]["updated_fields"], 0)


if __name__ == "__main__":
    unittest.main()
