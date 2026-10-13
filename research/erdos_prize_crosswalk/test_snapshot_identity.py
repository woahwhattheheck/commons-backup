"""Independent regression coverage for the immutable 2026-09-18 snapshot.

The retained JSON and original tests are unchanged. Cases change local copies;
no source download, theorem work, claim, or provider operation is performed.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import verify_crosswalk as vc

ROOT = Path(__file__).resolve().parent
EXPECTED = "7d7302297e166f50409f39d216462940312dc0dd013be5490f721e4b15669a93"


def nodes(value, path=()):
    """Visit each retained JSON value, including containers, deterministically."""
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from nodes(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from nodes(child, path + (index,))


def replace(document, path, value):
    if not path:
        return value
    parent = document
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    return document


class SnapshotIdentityTests(unittest.TestCase):
    def setUp(self):
        self.doc = vc.load_strict(ROOT / "crosswalk.json")

    def reject(self, changed):
        with self.assertRaises(vc.CrosswalkError):
            vc.verify(changed)

    def test_exact_retained_digest(self):
        self.assertEqual(vc.verify(self.doc), EXPECTED)

    def test_formal_source_commit_is_bound(self):
        self.doc["source_snapshot"]["formal_conjectures_commit"] = "0" * 40
        self.reject(self.doc)

    def test_each_present_blob_is_bound(self):
        for index, row in enumerate(self.doc["problems"]):
            if row["formal_target"]["status"] == "PRESENT":
                with self.subTest(erdos=row["erdos_number"]):
                    changed = copy.deepcopy(self.doc)
                    changed["problems"][index]["formal_target"]["blob_sha"] = "0" * 40
                    self.reject(changed)

    def test_each_present_theorem_is_bound(self):
        for index, row in enumerate(self.doc["problems"]):
            if row["formal_target"]["status"] == "PRESENT":
                with self.subTest(erdos=row["erdos_number"]):
                    changed = copy.deepcopy(self.doc)
                    changed["problems"][index]["formal_target"]["theorem"] = "Different.theorem"
                    self.reject(changed)

    def test_each_ppl_mapping_and_consistent_url_are_bound(self):
        for index, row in enumerate(self.doc["problems"]):
            if row["ppl_id"] is not None:
                with self.subTest(erdos=row["erdos_number"]):
                    changed = copy.deepcopy(self.doc)
                    changed["problems"][index]["ppl_id"] = 9999
                    changed["problems"][index]["ppl_source"] = "https://prizeproblems.org/problems/9999/"
                    self.reject(changed)

    def test_mapped_ppl_cannot_be_erased_as_unknown(self):
        for index, row in enumerate(self.doc["problems"]):
            if row["ppl_id"] is not None:
                with self.subTest(erdos=row["erdos_number"]):
                    changed = copy.deepcopy(self.doc)
                    changed["problems"][index].update(ppl_id=None, ppl_source=None, ppl_status="NOT_MAPPED_IN_V1")
                    self.reject(changed)

    def test_unknown_ppl_cannot_be_guessed_as_known(self):
        row = next(r for r in self.doc["problems"] if r["erdos_number"] == 64)
        row.update(ppl_id=9999, ppl_source="https://prizeproblems.org/problems/9999/", ppl_status="VERIFIED_OPEN")
        self.reject(self.doc)

    def test_source_repository_is_bound(self):
        self.doc["source_snapshot"]["formal_conjectures_repository"] = "example/another-repository"
        self.reject(self.doc)

    def test_unclaimed_carrier_cannot_be_added(self):
        self.doc["problems"][0]["commons_ownership"]["carrier"] = "another-carrier"
        self.reject(self.doc)

    def test_ordinary_reward_scope_is_bound(self):
        self.doc["problems"][0]["reward_scope"] = "disproof_maximum"
        self.reject(self.doc)

    def test_all_leaf_values_are_bound(self):
        for path, value in nodes(self.doc):
            if isinstance(value, (dict, list)):
                continue
            replacement = (not value) if type(value) is bool else value + 1 if type(value) is int else "changed-retained-value"
            with self.subTest(path=path):
                self.reject(replace(copy.deepcopy(self.doc), path, replacement))

    def test_every_object_field_is_required(self):
        for path, value in nodes(self.doc):
            if not isinstance(value, dict):
                continue
            for key in value:
                with self.subTest(path=path, key=key):
                    changed = copy.deepcopy(self.doc)
                    parent = changed
                    for part in path:
                        parent = parent[part]
                    del parent[key]
                    self.reject(changed)

    def test_additional_object_fields_are_not_new_authority(self):
        for path, value in nodes(self.doc):
            if not isinstance(value, dict):
                continue
            with self.subTest(path=path):
                changed = copy.deepcopy(self.doc)
                parent = changed
                for part in path:
                    parent = parent[part]
                parent["extra_snapshot_claim"] = True
                self.reject(changed)

    def test_integer_float_and_boolean_aliases_are_rejected(self):
        for path, value in nodes(self.doc):
            if type(value) is int:
                with self.subTest(path=path, alias="float"):
                    self.reject(replace(copy.deepcopy(self.doc), path, float(value)))
                with self.subTest(path=path, alias="boolean"):
                    self.reject(replace(copy.deepcopy(self.doc), path, bool(value)))

    def test_array_order_is_part_of_this_snapshot(self):
        self.doc["problems"].reverse()
        self.reject(self.doc)

    def test_every_list_element_is_required(self):
        for path, value in nodes(self.doc):
            if not isinstance(value, list):
                continue
            for index in range(len(value)):
                with self.subTest(path=path, index=index):
                    changed = copy.deepcopy(self.doc)
                    parent = changed
                    for part in path:
                        parent = parent[part]
                    del parent[index]
                    self.reject(changed)

    def test_unknown_root_and_row_annotations_are_not_ignored(self):
        self.doc["problems"][0]["acceptance"] = "awarded"
        self.doc["current"] = True
        self.reject(self.doc)

    def test_input_digest_cannot_supply_the_expected_pin(self):
        self.doc["source_snapshot"]["formal_conjectures_commit"] = "0" * 40
        encoded = json.dumps(self.doc, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        self.doc["expected_sha256"] = hashlib.sha256(encoded).hexdigest()
        self.reject(self.doc)

    def test_json_object_order_and_spacing_are_irrelevant(self):
        def reverse_keys(value):
            if isinstance(value, dict):
                return {key: reverse_keys(value[key]) for key in reversed(list(value))}
            if isinstance(value, list):
                return [reverse_keys(v) for v in value]
            return value
        changed_order = reverse_keys(self.doc)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "spaced.json"
            path.write_text(json.dumps(changed_order, ensure_ascii=True, indent=4) + "\n\n", encoding="utf-8")
            self.assertEqual(vc.verify(vc.load_strict(path)), EXPECTED)

    def test_verification_does_not_modify_input(self):
        before = copy.deepcopy(self.doc)
        vc.verify(self.doc)
        self.assertEqual(self.doc, before)

    def test_direct_nonfinite_extension_is_a_typed_rejection(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                changed = copy.deepcopy(self.doc)
                changed["extra"] = value
                self.reject(changed)

    def test_direct_lone_surrogate_is_a_typed_rejection(self):
        self.doc["problems"][0]["title_short"] = "\ud800"
        self.reject(self.doc)

    def test_direct_non_json_extension_is_a_typed_rejection(self):
        self.doc["extra"] = object()
        self.reject(self.doc)

    def test_recursive_direct_extension_is_a_typed_rejection(self):
        self.doc["extra"] = self.doc
        self.reject(self.doc)

    def test_deep_json_is_a_typed_rejection(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "deep.json"
            path.write_text("[" * 1200 + "0" + "]" * 1200, encoding="utf-8")
            try:
                loaded = vc.load_strict(path)
            except vc.CrosswalkError:
                return
            self.reject(loaded)

    def test_parser_recursion_error_is_normalized(self):
        with mock.patch.object(vc.json, "loads", side_effect=RecursionError("parser depth")):
            with self.assertRaises(vc.CrosswalkError):
                vc.load_strict(ROOT / "crosswalk.json")

    def test_oversized_integer_is_a_typed_rejection(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "integer.json"
            path.write_text('{"x":' + "9" * 5000 + "}", encoding="utf-8")
            try:
                loaded = vc.load_strict(path)
            except vc.CrosswalkError:
                return
            self.reject(loaded)

    def test_cli_retains_old_success_line(self):
        run = subprocess.run([sys.executable, *(["-O"] if sys.flags.optimize else []), "-B", str(ROOT / "verify_crosswalk.py")], text=True, capture_output=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, f"CROSSWALK_OK rows=9 total_usd=22000 sha256={EXPECTED}\n")

    def test_cli_refuses_changed_snapshot_without_success_line(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "changed.json"
            self.doc["source_snapshot"]["formal_conjectures_commit"] = "0" * 40
            path.write_text(json.dumps(self.doc), encoding="utf-8")
            original = path.read_bytes()
            run = subprocess.run([sys.executable, *(["-O"] if sys.flags.optimize else []), "-B", str(ROOT / "verify_crosswalk.py"), str(path)], text=True, capture_output=True, timeout=10)
            self.assertEqual(run.returncode, 2)
            self.assertEqual(run.stdout, "")
            self.assertIn("CROSSWALK_ERROR", run.stderr)
            self.assertNotIn("Traceback", run.stderr)
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
