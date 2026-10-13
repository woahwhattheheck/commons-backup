"""Synthetic unit-only checks of draft triage, not parent-compiler integration.

Run with HANDOFF_REVIEW_SOURCE set to the exact module being reviewed.
The parent verifier is explicitly stubbed; no report here is evidence of a
successful real parent verification or an assessment of a University system.
"""
from __future__ import annotations

import copy
import importlib.util
import os
from pathlib import Path
import random
import unittest
from unittest.mock import patch

SOURCE = Path(os.environ.get("HANDOFF_REVIEW_SOURCE", str(Path(__file__).with_name("handoff_review.py")))).resolve()
spec = importlib.util.spec_from_file_location("reviewed_handoff_module", SOURCE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot load specified review module: {SOURCE}")
hr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hr)


def stub_report() -> dict:
    return {
        "schema": "UNIT_TEST_STUB_NOT_COMPILER_OUTPUT",
        "mode": hr.MODE,
        "receipt_sha256": "a" * 64,
        "aggregate_state": "HOLD_TRUSTED_AUTHORITY_REQUIRED",
        "trust": {
            "authority_root_supplied_out_of_band": False,
            "current_evidence_review_authority": False,
        },
        "assessment_matrix": [
            {
                "group": group,
                "dimension": dimension,
                "status": "UNTRUSTED_EVIDENCE_CONSISTENT",
                "source_ids": [f"SYNTHETIC-{group}-{dimension}"],
                "source_record_sha256s": ["b" * 64],
                "reason_codes": ["TRUSTED_AUTHORITY_ROOT_REQUIRED"],
            }
            for group, dimension in hr.CELLS
        ],
    }


def stub_integrity(report: dict) -> dict:
    return {
        "integrity_valid": True,
        "semantic_recompile_valid": True,
        "trusted_authority_root_verified": False,
        "current_authority_verified": False,
        "receipt_sha256": report["receipt_sha256"],
    }


def projection(result: dict) -> dict:
    """Exclude provenance multiplicity, which SHOULD preserve all submitted labels."""
    return {
        "review_queue": result["review_queue"],
        "reason_counts": result["reason_counts"],
        "cell_reasons": [c["review_reason_codes"] for c in result["assessment_cells"]],
    }


class CloneInvariantTriageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = stub_report()
        self.handoff = hr._blank_handoff(self.report)
        verifier = patch.object(hr, "_parent_integrity", side_effect=stub_integrity)
        verifier.start()
        self.addCleanup(verifier.stop)

    def active(self, mask: int = 4095) -> dict:
        handoff = copy.deepcopy(self.handoff)
        for i, row in enumerate(handoff["cell_notes"]):
            if mask & (1 << i):
                row["disposition"] = "TECHNICAL_DRAFT_NOTE"
                row["analyst_note"] = f"SYNTHETIC unit observation {i}; not real evidence."
        return handoff

    def run_handoffs(self, *handoffs: dict) -> dict:
        return hr.reconcile(self.report, [(f"input-{i}", h) for i, h in enumerate(handoffs)])

    def test_all_active_copy_cannot_clear_twelve_review_items(self) -> None:
        active = self.active()
        original = self.run_handoffs(active)
        copied = self.run_handoffs(active, copy.deepcopy(active))
        self.assertEqual(len(original["review_queue"]), 12)
        self.assertEqual(len(copied["review_queue"]), 12)
        self.assertEqual(projection(copied), projection(original))

    def test_one_active_cell_cannot_disappear_after_copy(self) -> None:
        active = self.active(1)
        self.assertEqual(projection(self.run_handoffs(active)),
                         projection(self.run_handoffs(active, copy.deepcopy(active))))

    def test_all_twenty_aliases_preserve_single_content_triage(self) -> None:
        active = self.active()
        result = self.run_handoffs(*[copy.deepcopy(active) for _ in range(20)])
        self.assertEqual(result["input_count"], 20)
        self.assertEqual(result["distinct_handoff_content_count"], 1)
        self.assertEqual(len(result["identical_content_groups"][0]), 20)
        self.assertEqual(len(result["review_queue"]), 12)
        self.assertEqual(len(result["assessment_cells"][0]["entries"]), 20)

    def test_cell_reorder_and_json_key_reorder_are_still_a_copy(self) -> None:
        active = self.active(7)
        copied = dict(reversed(list(copy.deepcopy(active).items())))
        copied["cell_notes"].reverse()
        result = self.run_handoffs(active, copied)
        self.assertEqual(result["distinct_handoff_content_count"], 1)
        self.assertEqual(projection(result), projection(self.run_handoffs(active)))

    def test_exhaustive_active_unreviewed_masks_are_clone_invariant(self) -> None:
        # All 2^12 combinations, not just a single convenient screenshot.
        failures = []
        for mask in range(4096):
            active = self.active(mask)
            one = self.run_handoffs(active)
            two = self.run_handoffs(active, copy.deepcopy(active))
            if projection(one) != projection(two):
                failures.append(mask)
        self.assertEqual(len(failures), 0,
                         f"{len(failures)}/4096 masks changed triage after cloning; first={failures[:3]}")

    def test_all_unreviewed_stays_missing_review(self) -> None:
        one = self.run_handoffs(self.handoff)
        many = self.run_handoffs(self.handoff, copy.deepcopy(self.handoff))
        self.assertEqual(projection(one), projection(many))
        self.assertEqual(many["reason_counts"], {"ALL_UNREVIEWED": 12})

    def test_distinct_packets_can_have_matching_cell(self) -> None:
        first = self.active(1)
        second = copy.deepcopy(first)
        second["cell_notes"][1]["analyst_note"] = "SYNTHETIC distinct packet context."
        result = self.run_handoffs(first, second)
        self.assertEqual(result["distinct_handoff_content_count"], 2)
        self.assertEqual(result["assessment_cells"][0]["review_reason_codes"],
                         ["MATCHING_DRAFT_ENTRIES"])
        self.assertEqual(len(result["review_queue"]), 11)
        self.assertIs(result["reviewer_identity_verified"], False)

    def test_genuine_disagreement_survives_many_copies(self) -> None:
        first = self.active(1)
        second = copy.deepcopy(first)
        second["cell_notes"][0]["disposition"] = "NEEDS_EVIDENCE"
        two = self.run_handoffs(first, second)
        many = self.run_handoffs(first, second, *[copy.deepcopy(first) for _ in range(18)])
        self.assertEqual(projection(two), projection(many))
        self.assertIn("DISPOSITION_DISAGREEMENT",
                      many["assessment_cells"][0]["review_reason_codes"])

    def test_seeded_distinct_sets_unchanged_by_cloning(self) -> None:
        rng = random.Random(16174)
        choices = sorted(hr.DISPOSITIONS)
        for case in range(128):
            packets = []
            for _ in range(3):
                packet = copy.deepcopy(self.handoff)
                for row in packet["cell_notes"]:
                    row["disposition"] = rng.choice(choices)
                    row["analyst_note"] = f"SYNTHETIC note {rng.randrange(3)}"
                packets.append(packet)
            a = self.run_handoffs(*packets)
            b = self.run_handoffs(*packets, copy.deepcopy(packets[case % 3]))
            self.assertEqual(projection(a), projection(b), f"seeded case {case}")

    def test_provenance_and_inputs_preserved(self) -> None:
        active = self.active()
        saved = copy.deepcopy((self.report, active))
        result = self.run_handoffs(active, copy.deepcopy(active))
        self.assertEqual((self.report, active), saved)
        for cell, source in zip(result["assessment_cells"], self.report["assessment_matrix"]):
            self.assertEqual(cell["source_ids"], source["source_ids"])
            self.assertEqual(cell["source_record_sha256s"], source["source_record_sha256s"])
            self.assertEqual(len(cell["entries"]), 2)

    def test_no_authority_or_identity_promotion_and_digest_valid(self) -> None:
        active = self.active()
        result = self.run_handoffs(active, copy.deepcopy(active))
        self.assertTrue(all(flag is False for flag in result["authority"].values()))
        self.assertIs(result["source_authenticity_verified"], False)
        self.assertIs(result["reviewer_identity_verified"], False)
        receipt = result.pop("reconciliation_sha256")
        self.assertEqual(receipt, hr.digest(result))

    def test_unicode_notes_and_alias_order_preserved(self) -> None:
        active = self.active(1)
        active["cell_notes"][0]["analyst_note"] = "SYNTHETIC café / 研究 / 🙂\nline two"
        original = self.run_handoffs(active, copy.deepcopy(active))
        reverse = hr.reconcile(self.report, [("input-1", active), ("input-0", copy.deepcopy(active))])
        self.assertEqual(original, reverse)
        self.assertEqual(original["assessment_cells"][0]["entries"][0]["analyst_note"],
                         active["cell_notes"][0]["analyst_note"])
        self.assertIn("SINGLE_DRAFT_ENTRY", original["assessment_cells"][0]["review_reason_codes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
