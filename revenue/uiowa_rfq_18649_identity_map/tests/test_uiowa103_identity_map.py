"""Core + actual published-register tests. Run with unittest, normal and -O."""
from copy import deepcopy
import importlib.util
import io
import itertools
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "uiowa103_lodestone_test_package"
if PACKAGE not in sys.modules:
    spec = importlib.util.spec_from_file_location(PACKAGE, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = package
    spec.loader.exec_module(package)
from uiowa103_lodestone_test_package.identity_map import (
    IdentityMap, MappingError, SCHEMA, canonical, load_json, reconcile, render_markdown,
)
from uiowa103_lodestone_test_package.register_adapter import import_register, git_blob_sha


def record(namespace="a", kind="source", local_id="EV-1", revision="v1", **extra):
    return {"namespace": namespace, "kind": kind, "id": local_id, "revision": revision,
            "synthetic": True, "source_locators": ["fictional.csv#csv-record=2"],
            "payload": {"statement": "SYNTHETIC; not a University finding"}, **extra}


def ref(row):
    return {k: row[k] for k in ("namespace", "kind", "id", "revision")}


def decision(left, right, did="MAP-1", relation="same_entity"):
    return {"decision_id": did, "relation": relation, "left": ref(left), "right": ref(right),
            "reason": "Explicit synthetic crosswalk; not externally verified",
            "evidence_locators": [f"fictional-crosswalk.json#{did}"]}


class CoreTests(unittest.TestCase):
    def test_different_origins_never_silently_join(self):
        m = IdentityMap([record(), record("b")])
        self.assertEqual(m.resolve({"kind": "source", "id": "EV-1"})["status"], "ambiguous")
        self.assertNotEqual(m.resolve(ref(record()))["resolved_id"], m.resolve(ref(record("b")))["resolved_id"])

    def test_entity_kind_is_part_of_identity(self):
        m = IdentityMap([record(), record(kind="finding")])
        ids = [m.resolve(ref(r))["resolved_id"] for r in [record(), record(kind="finding")]]
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(m.report()["summary"]["collisions"], 0)

    def test_revisions_require_disambiguation(self):
        rows = [record(), record(revision="v2")]
        report = IdentityMap(rows).report()
        self.assertEqual(len({r["entity_id"] for r in report["records"]}), 1)
        self.assertEqual(len({r["occurrence_id"] for r in report["records"]}), 2)
        self.assertEqual(IdentityMap(rows).resolve({"namespace": "a", "kind": "source", "id": "EV-1"})["status"], "ambiguous")

    def test_equivalence_does_not_select_payload_or_revision(self):
        a, b = record(), record("b", payload={"different": "retained"})
        m = IdentityMap([a, b], [decision(a, b)])
        resolution = m.resolve({"kind": "source", "id": "EV-1"})
        self.assertEqual(resolution["status"], "ambiguous")
        self.assertEqual(len(resolution["equivalence_groups"]), 1)
        self.assertIn("does not select", resolution["note"])
        self.assertEqual([r["original"] for r in m.report()["records"]], [a, b])

    def test_positive_transitive_chain_and_cycle(self):
        a, b, c = record(), record("b"), record("c")
        m = IdentityMap([a, b, c], [decision(a, b, "1"), decision(b, c, "2"), decision(c, a, "3")])
        self.assertEqual(len(m.report()["equivalence_groups"]), 1)

    def test_negative_constraint_detects_transitive_conflict_in_every_order(self):
        a, b, c = record(), record("b"), record("c")
        ds = [decision(a, b, "1"), decision(b, c, "2"), decision(a, c, "3", "different_entity")]
        for perm in itertools.permutations(ds):
            with self.subTest(order=[d["decision_id"] for d in perm]):
                with self.assertRaisesRegex(MappingError, "contradictory"):
                    IdentityMap([a, b, c], list(perm))

    def test_negative_constraint_alone_preserves_separation(self):
        a, b = record(), record("b")
        m = IdentityMap([a, b], [decision(a, b, relation="different_entity")])
        self.assertEqual(len(m.report()["equivalence_groups"]), 2)

    def test_equivalence_endpoints_kind_and_synthetic_status(self):
        a = record()
        for b, message in [(record("b", kind="finding"), "mixes entity kinds"),
                           (record("b", synthetic=False), "synthetic and non-synthetic")]:
            with self.subTest(message=message), self.assertRaisesRegex(MappingError, message):
                IdentityMap([a, b], [decision(a, b)])
        with self.assertRaisesRegex(MappingError, "missing endpoint"):
            IdentityMap([a], [decision(a, record("b"))])

    def test_decisions_require_reasons_locators_and_unique_ids(self):
        a, b = record(), record("b")
        d = decision(a, b)
        for field, value in [("reason", ""), ("evidence_locators", []), ("relation", "alias")]:
            bad = {**d, field: value}
            with self.subTest(field=field), self.assertRaises(MappingError):
                IdentityMap([a, b], [bad])
        with self.assertRaisesRegex(MappingError, "duplicate decision_id"):
            IdentityMap([a, b], [d, d])

    def test_identical_duplicate_retains_count_and_payload_types(self):
        row = record(payload={"missing": None, "empty": "", "zero": 0, "false": False, "text": "0", "order": [2, 1]})
        result = IdentityMap([row, deepcopy(row)]).report()
        self.assertEqual(result["summary"]["input_records"], 2)
        self.assertEqual(result["records"][0]["duplicate_count"], 2)
        self.assertEqual(result["records"][0]["original"], row)

    def test_conflicting_duplicates_are_not_last_row_wins(self):
        a, b = record(), record(payload={"new": "content"})
        for rows in ([a, b], [b, a]):
            with self.assertRaisesRegex(MappingError, "conflicting duplicate"):
                IdentityMap(rows)

    def test_unicode_whitespace_case_and_delimiter_ids_are_distinct(self):
        ids = ["é", "e\u0301", "EV-1", "ev-1", " EV-1", "EV-1 ", "a|b", "a:b", "☃"]
        report = IdentityMap([record(local_id=i) for i in ids]).report()
        self.assertEqual(len({r["occurrence_id"] for r in report["records"]}), len(ids))
        self.assertEqual({r["original"]["id"] for r in report["records"]}, set(ids))
        cross = IdentityMap([record("a|b", local_id="c"), record("a", local_id="b|c")]).report()
        self.assertEqual(len({r["entity_id"] for r in cross["records"]}), 2)

    def test_unrelated_addition_preserves_existing_ids_and_qualified_resolution(self):
        before = IdentityMap([record()])
        after = IdentityMap([record(), record("b"), record("a", local_id="OTHER")])
        old = before.report()["records"][0]
        retained = next(r for r in after.report()["records"] if r["original"] == record())
        self.assertEqual(old["occurrence_id"], retained["occurrence_id"])
        self.assertEqual(old["entity_id"], retained["entity_id"])
        self.assertEqual(before.resolve(ref(record()))["resolved_id"], after.resolve(ref(record()))["resolved_id"])
        self.assertEqual(after.resolve({"kind": "source", "id": "EV-1"})["status"], "ambiguous")

    def test_record_link_decision_permutations_are_deterministic(self):
        packet = load_json((ROOT / "examples/collisions.json").read_text())
        baseline = canonical(reconcile(packet))
        rng = random.Random(103)
        for _ in range(30):
            other = deepcopy(packet)
            for key in ("records", "links", "equivalences"):
                rng.shuffle(other[key])
            self.assertEqual(canonical(reconcile(other)), baseline)

    def test_input_and_output_mutations_do_not_change_index(self):
        row = record()
        m = IdentityMap([row])
        baseline = m.report()
        row["payload"]["statement"] = "changed input"
        report = m.report()
        report["records"][0]["original"]["payload"]["statement"] = "changed output"
        self.assertEqual(m.report(), baseline)

    def test_link_missing_and_ambiguous_states_survive(self):
        packet = load_json((ROOT / "examples/collisions.json").read_text())
        report = reconcile(packet)
        self.assertEqual(report["summary"], {"input_records": 10, "occurrences": 10, "collisions": 2, "links": 9, "unresolved_links": 4})
        states = {r["link_id"]: r["to"]["status"] for r in report["links"]}
        self.assertEqual(states["L-08"], "missing")
        self.assertEqual(states["L-06"], "ambiguous")
        self.assertEqual(states["L-09"], "ambiguous")
        self.assertFalse(report["assessment_authority"])

    def test_extensions_and_locator_order_are_retained(self):
        row = record(custom={"retain": [None, "", False]}, source_locators=["z", "a", "z"])
        doc = {"schema": SCHEMA, "records": [row], "unrecognized": {"x": None}}
        result = reconcile(doc)
        self.assertEqual(result["records"][0]["original"], row)
        self.assertEqual(result["extensions"], {"unrecognized": {"x": None}})

    def test_wrong_types_and_malformed_identities_fail(self):
        for field, value in [("namespace", ""), ("kind", "evidence"), ("id", 1), ("id", "a\n"),
                             ("revision", None), ("synthetic", "false"), ("payload", []), ("source_locators", [])]:
            with self.subTest(field=field, value=value), self.assertRaises(MappingError):
                IdentityMap([record(**{field: value})])
        with self.assertRaises(MappingError):
            IdentityMap([{"kind": "source", "id": "x"}])
        for malformed in (None, {}, "x"):
            with self.subTest(malformed=malformed), self.assertRaises(MappingError):
                IdentityMap(malformed)

    def test_strict_json_duplicate_nonfinite_and_nested_library_values(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}', '{'):
            with self.subTest(text=text), self.assertRaises(MappingError):
                load_json(text)
        for payload in ({"x": float("nan")}, {"x": {1: "would coerce"}}, {"x": (1, 2)}, {"x": "\ud800"}):
            with self.subTest(payload=repr(payload)), self.assertRaises(MappingError):
                IdentityMap([record(payload=payload)])
        circular = {}; circular["self"] = circular
        with self.assertRaisesRegex(MappingError, "circular"):
            IdentityMap([record(payload=circular)])

    def test_selector_typos_and_duplicate_link_ids_fail(self):
        m = IdentityMap([record()])
        for selector in ({"kind": "source", "id": "EV-1", "origin": "a"}, {"id": "EV-1"}):
            with self.assertRaises(MappingError):
                m.resolve(selector)
        link = {"link_id": "x", "relation": "related", "from": ref(record()), "to": ref(record())}
        with self.assertRaisesRegex(MappingError, "duplicate link_id"):
            m.report([link, link])

    def test_markdown_escapes_data_and_keeps_diagnostic_table_contiguous(self):
        packet = load_json((ROOT / "examples/collisions.json").read_text())
        text = render_markdown(reconcile(packet))
        table = text.split("|Link|From|To|Status|\n")[1].split("\n\n")[0].splitlines()
        self.assertEqual(len(table), 10)  # separator + all nine links, no paragraph injected
        bad = IdentityMap([record(local_id="<img>|`x`")]).report()
        self.assertNotIn("<img>", render_markdown(bad))
        self.assertIn("&lt;img&gt;&#124;&#96;x&#96;", render_markdown(bad))

    def test_empty_packet_has_no_assessment_authority(self):
        report = reconcile({"schema": SCHEMA, "records": []})
        self.assertEqual(report["summary"]["occurrences"], 0)
        self.assertFalse(report["assessment_authority"])
        with self.assertRaises(MappingError):
            reconcile({"schema": "wrong", "records": []})


class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.raw = (ROOT / "examples/register_023.csv").read_bytes()

    def imported(self, raw=None, **kwargs):
        return import_register(self.raw if raw is None else raw, namespace="methodology-023",
                               source_path="examples/register_023.csv", synthetic=True, **kwargs)

    def test_published_bytes_and_actual_end_to_end_shape(self):
        self.assertEqual(git_blob_sha(self.raw), "fc2ef567e3f9b3f5a5031c74994e62c62b1d9c7e")
        report = reconcile(self.imported(expected_blob="fc2ef567e3f9b3f5a5031c74994e62c62b1d9c7e"))
        self.assertEqual(report["summary"], {"input_records": 19, "occurrences": 19, "collisions": 0, "links": 14, "unresolved_links": 0})
        self.assertNotIn("service", {r["original"]["kind"] for r in report["records"]})

    def test_repeated_findings_preserve_conflicting_memberships(self):
        packet = self.imported()
        finding = next(r for r in packet["records"] if r["kind"] == "finding" and r["id"] == "FND-SYN-IAM-DEP-001")
        self.assertEqual(len(finding["payload"]["memberships"]), 2)
        self.assertEqual({m["row"]["evidence_state"] for m in finding["payload"]["memberships"]}, {"CONFLICTING"})
        self.assertEqual({m["row"]["confidence"] for m in finding["payload"]["memberships"]}, {"UNRESOLVED"})
        self.assertFalse(finding["payload"]["underlying_source_content_read"])

    def test_all_original_csv_cells_and_unknown_columns_survive(self):
        import csv
        rows = list(csv.DictReader(io.StringIO(self.raw.decode())))
        sources = [r for r in self.imported()["records"] if r["kind"] == "source"]
        self.assertEqual(sorted(rows, key=lambda r: r["evidence_id"]),
                         sorted([r["payload"]["memberships"][0]["row"] for r in sources], key=lambda r: r["evidence_id"]))
        raw = b'evidence_id,observation_id,finding_id,group,area,source_ref,extra\nE,O,F,G,A,S,"line1\nline2"\n'
        packet = self.imported(raw)
        self.assertEqual(packet["records"][0]["payload"]["memberships"][0]["row"]["extra"], "line1\nline2")
        self.assertTrue(all(r["source_locators"] == ["examples/register_023.csv#csv-record=2"] for r in packet["records"]))

    def test_register_bad_headers_width_and_duplicate_ids(self):
        inputs = [b'', b'id,id\nx,x\n', b'evidence_id\nx\n',
                  b'evidence_id,observation_id,finding_id,group,area,source_ref\nE,O,F,G,A\n',
                  b'evidence_id,observation_id,finding_id,group,area,source_ref\nE,O,F,G,A,S\nE,O2,F,G,A,S2\n']
        for raw in inputs:
            with self.subTest(raw=raw), self.assertRaises(MappingError):
                self.imported(raw)

    def test_revision_changes_are_not_silently_pinned_to_old_bytes(self):
        with self.assertRaisesRegex(MappingError, "register bytes differ"):
            self.imported(self.raw + b'\n', expected_blob=git_blob_sha(self.raw))
        old = self.imported()
        new = self.imported(self.raw.replace(b'Participant states', b'Fictional participant states'))
        self.assertNotEqual(old["records"][0]["revision"], new["records"][0]["revision"])
        m = IdentityMap(old["records"] + new["records"])
        self.assertEqual(m.resolve({"namespace": "methodology-023", "kind": "finding", "id": "FND-SYN-ESS-SD-001"})["status"], "ambiguous")


class CLITests(unittest.TestCase):
    def run_cli(self, *args):
        # Real interpreter invocation; inherit -O status for the optimized suite.
        command = [sys.executable] + (["-O"] if sys.flags.optimize else []) + [str(ROOT / "identity_map.py"), *map(str, args)]
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=10)

    def test_cli_unresolved_produces_reports_and_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, md = Path(tmp) / "out.json", Path(tmp) / "out.md"
            proc = self.run_cli(ROOT / "examples/collisions.json", "--output", out, "--markdown", md)
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertEqual(json.loads(out.read_text())["summary"]["unresolved_links"], 4)
            self.assertIn("Reference diagnostics", md.read_text())

    def test_cli_valid_zero_invalid_two_and_input_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "in.json"
            source.write_text(json.dumps({"schema": SCHEMA, "records": [record()]}))
            before = source.read_bytes()
            good = self.run_cli(source)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(json.loads(good.stdout)["summary"]["occurrences"], 1)
            bad = self.run_cli(source, "--output", source)
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(source.read_bytes(), before)
            source.write_text('{"x":1,"x":2}')
            malformed = self.run_cli(source)
            self.assertEqual(malformed.returncode, 2)
            self.assertNotIn("Traceback", malformed.stderr)

    def test_actual_register_cli_and_core_cli_compose(self):
        with tempfile.TemporaryDirectory() as tmp:
            packet = Path(tmp) / "packet.json"
            command = [sys.executable] + (["-O"] if sys.flags.optimize else []) + [str(ROOT / "register_adapter.py"),
                str(ROOT / "examples/register_023.csv"), "--namespace", "methodology-023", "--source-path", "examples/register_023.csv",
                "--synthetic", "--expected-blob", "fc2ef567e3f9b3f5a5031c74994e62c62b1d9c7e", "--output", str(packet)]
            proc = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = self.run_cli(packet)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["summary"]["links"], 14)


if __name__ == "__main__":
    unittest.main()
