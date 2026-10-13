#!/usr/bin/env python3
"""Independent real-compiler interaction checks for QUARTZ's report diff.

ZZ-RELAY / GPT-6 Astra Pro. No parser or verifier mocks. Nine test methods
include 1,312 explicit subcases: 288 cell moves and 1,024 field combinations.
All records are fictional and inherit the parent inspection-only semantics.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import itertools
from typing import Any
import unittest

import review_diff as diff
from synthetic_demo import AFTER_AT, BEFORE_AT, compile_inputs, example_reports, make_inputs
from workshare_contract import MAX_EVIDENCE_AGE_SECONDS


CELLS = tuple(itertools.product(("ESS", "RIS", "IAM"),
                                ("software", "security", "deployment", "ai_readiness")))
# Independent expected classification, not imported from the implementation.
MUTATIONS = (
    ("source_content_sha256", "0" * 64, "CONTENT_REVISION"),
    ("group", "RIS", "CELL_REASSIGNMENT"),
    ("dimension", "security", "CELL_REASSIGNMENT"),
    ("source_ref", "synthetic://relay-revised-reference", "REFERENCE_CHANGE"),
    ("claim", "Fictional revised claim, still not a University finding.", "ASSESSMENT_RECORD_CHANGE"),
    ("maturity", 3, "ASSESSMENT_RECORD_CHANGE"),
    ("confidence_bp", 6000, "ASSESSMENT_RECORD_CHANGE"),
    ("observed_at", AFTER_AT, "EVIDENCE_METADATA_CHANGE"),
    ("evidence_kind", "interview", "EVIDENCE_METADATA_CHANGE"),
)


def rebind(candidate: dict, authority: dict) -> None:
    candidate["authority_generation"] = authority["generation"] = "synthetic-relay-g2"
    for source in authority["sources"]:
        source["authority_generation"] = authority["generation"]


def source_at(authority: dict, cell: tuple[str, str]) -> dict:
    return next(row for row in authority["sources"] if (row["group"], row["dimension"]) == cell)


def cell_map(delta: dict) -> dict[tuple[str, str], dict]:
    return {(row["group"], row["dimension"]): row for row in delta["cell_deltas"]}


def mutable_ids(value: Any) -> set[int]:
    result: set[int] = set()
    if isinstance(value, dict):
        result.add(id(value))
        for item in value.values():
            result.update(mutable_ids(item))
    elif isinstance(value, list):
        result.add(id(value))
        for item in value:
            result.update(mutable_ids(item))
    return result


class InteractionTests(unittest.TestCase):
    def assert_inspection_only(self, delta: dict) -> None:
        self.assertEqual(delta["summary"]["cells_total"], 12)
        self.assertEqual(set(cell_map(delta)), set(CELLS))
        self.assertTrue(all(value is False for value in delta["external_authority"].values()))
        for key in ("evidence_authenticity_verified", "current_evidence_review_authority",
                    "practice_improvement_inferred", "notes_automatically_transferred",
                    "document_rename_inferred"):
            self.assertIs(delta["interpretation"][key], False)

    def exercise_all_cell_moves(self, generation_change: bool) -> None:
        for origin, destination in itertools.product(CELLS, repeat=2):
            with self.subTest(origin=origin, destination=destination,
                              generation_change=generation_change):
                candidate, authority = make_inputs()
                before = compile_inputs(candidate, authority)
                source = source_at(authority, origin)
                sid = source["source_id"]
                source["group"], source["dimension"] = destination
                if generation_change:
                    rebind(candidate, authority)
                after = compile_inputs(candidate, authority, AFTER_AT)
                delta = diff.compare_reports(before, after)
                cells = cell_map(delta)
                expected_changed = {origin, destination} if origin != destination else set()
                self.assertEqual({cell for cell, row in cells.items() if row["changed"]},
                                 expected_changed)
                for cell, row in cells.items():
                    self.assertEqual(row["changed_source_ids"],
                                     [sid] if cell in expected_changed else [])
                if origin != destination:
                    self.assertEqual(cells[origin]["removed_source_ids"], [sid])
                    self.assertEqual(cells[destination]["added_source_ids"], [sid])
                    self.assertEqual(cells[origin]["after_status"], "HOLD_MISSING_EVIDENCE")
                    self.assertEqual(delta["summary"]["source_records_substantively_changed"], 1)
                else:
                    self.assertEqual(delta["summary"]["source_records_substantively_changed"], 0)
                self.assert_inspection_only(delta)
                self.assertTrue(diff.verify_diff(before, after, delta)["integrity_valid"])

    def test_all_144_cell_moves_without_generation_change(self) -> None:
        self.exercise_all_cell_moves(False)

    def test_all_144_cell_moves_with_generation_change(self) -> None:
        self.exercise_all_cell_moves(True)

    def exercise_all_field_combinations(self, generation_change: bool) -> None:
        for mask in range(1 << len(MUTATIONS)):
            with self.subTest(mask=mask, generation_change=generation_change):
                candidate, authority = make_inputs()
                before = compile_inputs(candidate, authority)
                source = source_at(authority, ("ESS", "software"))
                sid = source["source_id"]
                changed_fields, expected_kinds = set(), set()
                for bit, (field, value, kind) in enumerate(MUTATIONS):
                    if mask & (1 << bit):
                        source[field] = value
                        changed_fields.add(field)
                        expected_kinds.add(kind)
                if generation_change:
                    rebind(candidate, authority)
                destination = (source["group"], source["dimension"])
                after = compile_inputs(candidate, authority, AFTER_AT)
                before_bytes, after_bytes = diff.canonical_json_bytes(before), diff.canonical_json_bytes(after)
                delta = diff.compare_reports(before, after)
                changes = {row["source_id"]: row for row in delta["source_changes"]}
                if mask or generation_change:
                    expected_fields = changed_fields | ({"authority_generation"} if generation_change else set())
                    self.assertEqual(changes[sid]["changed_fields"], sorted(expected_fields))
                    self.assertEqual(set(changes[sid]["kinds"]),
                                     expected_kinds if mask else {"GENERATION_REBIND_ONLY"})
                    self.assertEqual(changes[sid]["substantive_change"], bool(mask))
                else:
                    self.assertEqual(changes, {})
                self.assertEqual(delta["summary"]["source_records_substantively_changed"], int(bool(mask)))
                self.assertEqual(delta["summary"]["generation_only_rebindings"],
                                 (11 if mask else 12) if generation_change else 0)
                expected_cells = {("ESS", "software"), destination} if mask else set()
                self.assertEqual({cell for cell, row in cell_map(delta).items() if row["changed"]},
                                 expected_cells)
                self.assertEqual(diff.canonical_json_bytes(before), before_bytes)
                self.assertEqual(diff.canonical_json_bytes(after), after_bytes)
                self.assert_inspection_only(delta)
                self.assertTrue(diff.verify_diff(before, after, delta)["integrity_valid"])

    def test_all_512_field_combinations_without_generation_change(self) -> None:
        self.exercise_all_field_combinations(False)

    def test_all_512_field_combinations_with_generation_change(self) -> None:
        self.exercise_all_field_combinations(True)

    def test_three_persistent_hold_types_survive_rebind_and_reordering(self) -> None:
        candidate, authority = make_inputs()
        authority["sources"].remove(source_at(authority, ("ESS", "software")))
        dissent = copy.deepcopy(source_at(authority, ("RIS", "security")))
        dissent.update(source_id="synthetic-relay-dissent", maturity=3)
        authority["sources"].append(dissent)
        source_at(authority, ("IAM", "deployment"))["observed_at"] = "2026-01-01T00:00:00Z"
        before = compile_inputs(candidate, authority)
        rebind(candidate, authority)
        authority["sources"].reverse()
        after = compile_inputs(candidate, authority, AFTER_AT)
        delta = diff.compare_reports(before, after)
        expected = {("ESS", "software"): "HOLD_MISSING_EVIDENCE",
                    ("RIS", "security"): "HOLD_CONFLICT",
                    ("IAM", "deployment"): "HOLD_STALE_EVIDENCE"}
        self.assertEqual(delta["summary"]["cells_changed"], 0)
        self.assertEqual(delta["summary"]["review_queue_items"], 3)
        self.assertEqual({(row["group"], row["dimension"]) for row in delta["review_queue"]}, set(expected))
        for cell, status in expected.items():
            self.assertEqual(cell_map(delta)[cell]["after_status"], status)
            self.assertTrue(cell_map(delta)[cell]["persistent_hold"])
        self.assertTrue(all(row["trigger"] == "PERSISTENT_HOLD" and row["disposition"] == "UNREVIEWED"
                            for row in delta["review_queue"]))
        self.assert_inspection_only(delta)

    def test_exact_freshness_boundary_then_one_second_aging(self) -> None:
        candidate, authority = make_inputs()
        observed = datetime.strptime(BEFORE_AT, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        cutoff = observed + timedelta(seconds=MAX_EVIDENCE_AGE_SECONDS)
        before = compile_inputs(candidate, authority, cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"))
        after = compile_inputs(candidate, authority, (cutoff + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        delta = diff.compare_reports(before, after)
        self.assertEqual(delta["source_changes"], [])
        self.assertEqual(delta["summary"]["cells_with_evaluation_window_effect"], 12)
        self.assertEqual(delta["summary"]["cells_with_changed_evidence"], 0)
        self.assertTrue(all(row["before_status"] == "UNTRUSTED_EVIDENCE_CONSISTENT"
                            and row["after_status"] == "HOLD_STALE_EVIDENCE"
                            for row in delta["cell_deltas"]))
        self.assert_inspection_only(delta)

    def test_all_returned_containers_are_detached_from_both_inputs(self) -> None:
        before, after = example_reports()
        delta = diff.compare_reports(before, after)
        self.assertTrue(mutable_ids(delta).isdisjoint(mutable_ids(before) | mutable_ids(after)))

    def test_equal_content_does_not_merge_distinct_record_identity(self) -> None:
        candidate, authority = make_inputs()
        first = source_at(authority, ("ESS", "software"))
        second = source_at(authority, ("RIS", "software"))
        second["source_content_sha256"] = first["source_content_sha256"]
        before = compile_inputs(candidate, authority)
        old_id = second["source_id"]
        second["source_id"] = "synthetic-relay-new-id"
        after = compile_inputs(candidate, authority, AFTER_AT)
        delta = diff.compare_reports(before, after)
        changes = {row["source_id"]: row for row in delta["source_changes"]}
        self.assertEqual(set(changes), {old_id, "synthetic-relay-new-id"})
        self.assertEqual(changes[old_id]["kinds"], ["REMOVED_SOURCE"])
        self.assertEqual(changes["synthetic-relay-new-id"]["kinds"], ["ADDED_SOURCE"])
        self.assertFalse(cell_map(delta)["ESS", "software"]["changed"])
        self.assert_inspection_only(delta)

    def test_twelve_way_cyclic_reassignment_conserves_source_changes(self) -> None:
        candidate, authority = make_inputs()
        before = compile_inputs(candidate, authority)
        by_origin = {cell: source_at(authority, cell) for cell in CELLS}
        for index, origin in enumerate(CELLS):
            destination = CELLS[(index + 1) % len(CELLS)]
            by_origin[origin]["group"], by_origin[origin]["dimension"] = destination
        rebind(candidate, authority)
        after = compile_inputs(candidate, authority, AFTER_AT)
        delta = diff.compare_reports(before, after)
        self.assertEqual(delta["summary"]["cells_changed"], 12)
        self.assertEqual(delta["summary"]["cells_with_status_change"], 0)
        self.assertEqual(delta["summary"]["source_records_substantively_changed"], 12)
        self.assertEqual(delta["summary"]["generation_only_rebindings"], 0)
        for index, origin in enumerate(CELLS):
            row = cell_map(delta)[origin]
            outgoing = by_origin[origin]["source_id"]
            incoming = by_origin[CELLS[(index - 1) % len(CELLS)]]["source_id"]
            self.assertEqual(row["removed_source_ids"], [outgoing])
            self.assertEqual(row["added_source_ids"], [incoming])
            self.assertEqual(set(row["changed_source_ids"]), {outgoing, incoming})
        self.assert_inspection_only(delta)
        self.assertTrue(diff.verify_diff(before, after, delta)["integrity_valid"])


if __name__ == "__main__":
    unittest.main()
