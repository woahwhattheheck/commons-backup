"""Consumer boundary tests use explicit report doubles; actual demo is separate."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("cirrus_import_impact_tested", ROOT / "import_impact.py")
I = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = I
SPEC.loader.exec_module(I)


def seal(report):
    report["snapshot_sha256"] = I.source_digest(report)
    return report


def record(oid, namespace="a", ident="S1"):
    return {"occurrence_id": oid, "entity_id": "entity-" + oid,
            "equivalence_group": "eq-" + oid, "duplicate_count": 1,
            "original": {"namespace": namespace, "kind": "source", "id": ident,
                         "revision": "r1", "synthetic": True, "payload": {"note": "fiction"},
                         "source_locators": ["test-double:" + oid]}}


def endpoint(ids, selector=None):
    ids = list(ids)
    return {"selector": selector or {"kind": "source", "id": "S1"},
            "status": "missing" if not ids else "resolved" if len(ids) == 1 else "ambiguous",
            "resolved_id": ids[0] if len(ids) == 1 else None, "candidate_ids": ids,
            "equivalence_groups": [], "note": "explicit report double"}


def link(lid, target_ids):
    left, right = endpoint(["o1"], {"namespace": "a", "kind": "source", "id": "S1", "revision": "r1"}), endpoint(target_ids)
    return {"link_id": lid, "original": {"link_id": lid, "relation": "test", "from": left["selector"], "to": right["selector"]},
            "from": left, "to": right, "status": "resolved" if right["status"] == "resolved" else "unresolved"}


def snapshot():
    return seal({"schema": I.SOURCE_SCHEMA, "assessment_authority": False,
                 "records": [record("o1")], "links": [link("L1", ["o1"]), link("L2", [])],
                 "equivalences": [], "equivalence_groups": [], "collisions": [],
                 "extensions": {"provenance": "test double, not canonical execution"}})


def import_pair():
    before = snapshot()
    after = deepcopy(before)
    after["records"].append(record("o2", namespace="b"))
    after["links"][0] = link("L1", ["o1", "o2"])
    after["links"][1] = link("L2", ["o2"])
    return before, seal(after)


class ImpactTests(unittest.TestCase):
    def test_equal_totals_hide_two_real_transitions(self):
        before, after = import_pair()
        result = I.compare(before, after)
        self.assertEqual(result["summary"]["unresolved_before"], 1)
        self.assertEqual(result["summary"]["unresolved_after"], 1)
        self.assertEqual(result["summary"]["newly_unresolved_links"], 1)
        self.assertEqual(result["summary"]["newly_resolved_links"], 1)

    def test_unchanged_occurrence_is_not_rekeyed(self):
        result = I.compare(*import_pair())
        self.assertEqual(result["summary"]["occurrences_unchanged"], 1)
        self.assertEqual(result["summary"]["same_key_rekeys"], 0)
        self.assertEqual(result["records"]["added"][0]["occurrence_id"], "o2")

    def test_preserves_complete_snapshots_and_unknown_fields(self):
        before, after = import_pair()
        result = I.compare(before, after)
        self.assertEqual(result["snapshots"], {"before": before, "after": after})
        result["snapshots"]["before"]["extensions"]["provenance"] = "changed copy"
        self.assertEqual(before["extensions"]["provenance"], "test double, not canonical execution")

    def test_does_not_mutate_inputs(self):
        before, after = import_pair()
        originals = deepcopy((before, after))
        I.compare(before, after)
        self.assertEqual((before, after), originals)

    def test_repeatable_result_bytes(self):
        self.assertEqual(I.canonical(I.compare(*import_pair())), I.canonical(I.compare(*import_pair())))

    def test_tampered_seal_rejected(self):
        bad = snapshot()
        bad["records"][0]["original"]["payload"]["note"] = "modified"
        with self.assertRaisesRegex(ValueError, "seal mismatch"):
            I.compare(snapshot(), bad)

    def test_authority_claim_rejected(self):
        bad = snapshot()
        bad["assessment_authority"] = True
        with self.assertRaisesRegex(ValueError, "disclaim"):
            I.compare(snapshot(), seal(bad))

    def test_duplicate_occurrence_id_rejected(self):
        bad = snapshot()
        bad["records"].append(deepcopy(bad["records"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate record"):
            I.compare(snapshot(), seal(bad))

    def test_duplicate_original_key_rejected(self):
        bad = snapshot()
        bad["records"].append(record("other-oid"))
        with self.assertRaisesRegex(ValueError, "duplicate original"):
            I.compare(snapshot(), seal(bad))

    def test_dangling_candidate_rejected(self):
        bad = snapshot()
        bad["links"][0] = link("L1", ["absent"])
        with self.assertRaisesRegex(ValueError, "absent"):
            I.compare(snapshot(), seal(bad))

    def test_ambiguous_selected_target_rejected(self):
        before, bad = import_pair()
        bad["links"][0]["to"]["resolved_id"] = "o1"
        with self.assertRaisesRegex(ValueError, "selected ID"):
            I.compare(before, seal(bad))

    def test_duplicate_link_id_rejected(self):
        bad = snapshot()
        bad["links"].append(deepcopy(bad["links"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate link"):
            I.compare(snapshot(), seal(bad))

    def test_selected_target_rekey_is_exposed(self):
        before = snapshot()
        after = deepcopy(before)
        after["records"][0]["occurrence_id"] = "changed-oid"
        for row in after["links"]:
            for side in ("from", "to"):
                ep = row[side]
                ep["candidate_ids"] = ["changed-oid" if x == "o1" else x for x in ep["candidate_ids"]]
                if ep["resolved_id"] == "o1":
                    ep["resolved_id"] = "changed-oid"
        result = I.compare(before, seal(after))
        self.assertEqual(result["summary"]["same_key_rekeys"], 1)
        self.assertGreater(result["summary"]["retargeted_endpoints_without_selector_change"], 0)

    def test_same_revision_payload_change_is_exposed(self):
        before = snapshot()
        after = deepcopy(before)
        after["records"][0]["original"]["payload"]["note"] = "different note, reused revision"
        result = I.compare(before, seal(after))
        self.assertEqual(result["summary"]["same_revision_original_changes"], 1)
        self.assertEqual(result["summary"]["same_key_rekeys"], 0)

    def test_duplicate_multiplicity_is_not_original_change(self):
        before = snapshot()
        after = deepcopy(before)
        after["records"][0]["duplicate_count"] = 2
        row = I.compare(before, seal(after))["records"]["changed"][0]
        self.assertTrue(row["duplicate_count_changed"])
        self.assertFalse(row["original_changed_without_new_revision"])

    def test_group_snapshot_change_is_not_occurrence_rekey(self):
        before = snapshot()
        after = deepcopy(before)
        after["records"][0]["equivalence_group"] = "different-membership"
        row = I.compare(before, seal(after))["records"]["changed"][0]
        self.assertTrue(row["equivalence_snapshot_changed"])
        self.assertFalse(row["occurrence_rekeyed"])

    def test_removed_link_is_not_falsely_resolved(self):
        before = snapshot()
        after = deepcopy(before)
        after["links"] = after["links"][:1]
        result = I.compare(before, seal(after))
        self.assertEqual(result["summary"]["links_removed"], 1)
        self.assertEqual(result["summary"]["newly_resolved_links"], 0)
        self.assertEqual(result["links"]["removed"][0]["link_id"], "L2")

    def test_persistent_unresolved_reference_is_retained(self):
        result = I.compare(snapshot(), snapshot())
        self.assertEqual(len(result["links"]["unresolved_after"]), 1)
        self.assertEqual(result["links"]["unresolved_after"][0]["link_id"], "L2")

    def test_changed_selector_is_not_silent_retarget(self):
        before = snapshot()
        after = deepcopy(before)
        after["links"][0]["to"]["selector"]["namespace"] = "a"
        after["links"][0]["original"]["to"]["namespace"] = "a"
        row = I.compare(before, seal(after))["links"]["changed"][0]
        self.assertTrue(row["declaration_changed"])
        self.assertFalse(row["endpoints"]["to"]["retargeted_without_selector_change"])

    def test_html_escapes_source_markup(self):
        before = snapshot()
        before["links"][0]["link_id"] = "<em>example & text</em>"
        before["links"][0]["original"]["link_id"] = before["links"][0]["link_id"]
        page = I.render_html(I.compare(seal(before), seal(before)))
        self.assertNotIn("<em>example", page)
        self.assertIn("&lt;em&gt;example &amp; text&lt;/em&gt;", page)
        self.assertNotIn("<script", page)

    def test_html_is_labelled_and_narrow_table_is_scrollable(self):
        page = I.render_html(I.compare(*import_pair()))
        for expected in ('SYNTHETIC DEMONSTRATION', 'not University findings', 'name="viewport"', 'tabindex="0"', 'role="region"', '<caption', 'No reference is automatically selected'):
            self.assertIn(expected, page)

    def test_empty_reports_are_inspectable(self):
        report = seal({"schema": I.SOURCE_SCHEMA, "assessment_authority": False, "records": [], "links": []})
        self.assertEqual(I.compare(report, report)["summary"]["occurrences_after"], 0)

    def test_duplicate_json_key_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "input.json"
            p.write_text('{"records":[],"records":[]}')
            with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
                I.load_report(p)

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "input.json"
            p.write_text('{"x":NaN}')
            with self.assertRaisesRegex(ValueError, 'non-finite'):
                I.load_report(p)

    def test_cli_missing_input_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            p = str(Path(directory) / "missing.json")
            self.assertEqual(I.main([p, p]), 2)

    def test_boolean_duplicate_count_rejected(self):
        bad = snapshot()
        bad["records"][0]["duplicate_count"] = True
        with self.assertRaisesRegex(ValueError, 'duplicate_count'):
            I.compare(snapshot(), seal(bad))

    def test_explicit_validation_survives_optimized_python(self):
        with self.assertRaises(ValueError):
            I._require(False, 'must remain active')


if __name__ == '__main__':
    unittest.main()
