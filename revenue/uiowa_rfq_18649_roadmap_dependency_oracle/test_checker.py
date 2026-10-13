"""Behavioral and independent graph-oracle tests; unittest, including python -O."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

if __package__:
    from . import checker as c
else:
    import checker as c


def item(ident, requires=(), phase="now", kind="recommendation", title=None):
    return {"id": ident, "title": title or ident, "phase": phase,
            "kind": kind, "requires": list(requires)}


def packet(*items):
    return {"schema": c.INPUT_SCHEMA,
            "phases": [{"id": "now", "label": "Now"}, {"id": "next", "label": "Next"},
                       {"id": "later", "label": "Later"}], "items": list(items)}


def upstream(*rows):
    recommendations = []
    for row in rows:
        recommendations.append({"id": row["id"], "title": row["title"], "group": "ESS",
                               "phase": {"now": "0-90", "next": "90-180", "later": "180+"}[row["phase"]],
                               "owner_role": "Synthetic service owner", "depends_on": row["requires"],
                               "duration_days": [1, 3], "finding_refs": ["SYN-F1"],
                               "evidence_refs": ["SYN-E1"], "practice_change": "Synthetic change",
                               "observable_outcome": "Synthetic outcome", "assumptions": ["Synthetic case"]})
    return {"schema_version": 1, "title": "Synthetic 085 integration", "synthetic": True,
            "assumptions": ["Fixture only"], "recommendations": recommendations}


def brute_frontiers(ids, edges):
    """Repeated-set reference algorithm, intentionally unlike production SCC code."""
    done, waves = set(), []
    while True:
        wave = sorted(node for node in ids - done
                      if all(a in done for a, b in edges if b == node))
        if not wave:
            return waves, ids - done
        waves.append(wave)
        done.update(wave)


class GraphTests(unittest.TestCase):
    def test_package_scope_ignores_a_foreign_top_level_checker(self):
        import importlib.util
        import types
        package_name = "_quartz_isolation_probe"
        foreign = types.ModuleType("checker")
        foreign.origin = "unrelated-lane"
        old = sys.modules.get("checker")
        sys.modules["checker"] = foreign
        try:
            root = Path(__file__).resolve().parent
            spec = importlib.util.spec_from_file_location(package_name, root / "__init__.py",
                                                          submodule_search_locations=[str(root)])
            module = importlib.util.module_from_spec(spec)
            sys.modules[package_name] = module
            spec.loader.exec_module(module)
            self.assertEqual(module.analyze(packet(item("A")))["dependency_frontiers"], [["A"]])
            helper = importlib.import_module(package_name + ".verify_examples")
            self.assertIs(helper.checker, sys.modules[package_name + ".checker"])
            self.assertIsNot(helper.checker, foreign)
            self.assertIs(sys.modules["checker"], foreign)
        finally:
            if old is None:
                sys.modules.pop("checker", None)
            else:
                sys.modules["checker"] = old
            for name in list(sys.modules):
                if name == package_name or name.startswith(package_name + "."):
                    sys.modules.pop(name, None)

    def test_package_api_does_not_change_search_path(self):
        import importlib.util
        package_name = "_quartz_path_probe"
        before = sys.path.copy()
        root = Path(__file__).resolve().parent
        spec = importlib.util.spec_from_file_location(package_name, root / "__init__.py",
                                                      submodule_search_locations=[str(root)])
        module = importlib.util.module_from_spec(spec)
        sys.modules[package_name] = module
        try:
            spec.loader.exec_module(module)
            self.assertEqual(sys.path, before)
            self.assertEqual(module.__all__, ["InputError", "analyze", "analyze_roadmap085", "dot", "loads", "markdown"])
            self.assertEqual(module.analyze(packet(item("A")))["counts"]["items"], 1)
        finally:
            for name in list(sys.modules):
                if name == package_name or name.startswith(package_name + "."):
                    sys.modules.pop(name, None)

    def test_nonblank_human_labels(self):
        data = packet(item("A", title=" \t\n"))
        with self.assertRaises(c.InputError):
            c.analyze(data)
        data = upstream(item("A"))
        data["recommendations"][0]["practice_change"] = " "
        with self.assertRaises(c.InputError):
            c.analyze_roadmap085(data)

    def test_adapter_does_not_widen_upstream_identifier_grammar(self):
        data = upstream(item("A+B"))
        with self.assertRaises(c.InputError):
            c.analyze_roadmap085(data)
        # Native phase IDs need '+' for the published 180+ phase, but the
        # upstream recommendation ID contract deliberately excludes it.
        self.assertEqual(c.analyze(packet(item("A+B")))["counts"]["items"], 1)

    def test_parallel_shared_dependencies(self):
        report = c.analyze(packet(item("D", kind="shared_dependency"),
                                  item("A", ["D"], "next"), item("B", ["D"], "next"),
                                  item("C", ["A", "B"], "later")))
        self.assertEqual(report["dependency_check_status"], "CONSISTENT")
        self.assertEqual(report["dependency_frontiers"], [["D"], ["A", "B"], ["C"]])

    def test_missing_reference_exact_location_and_downstream(self):
        report = c.analyze(packet(item("A", ["Z", "Absent"]), item("B", ["A"]), item("Z")))
        finding = report["diagnostics"][0]
        self.assertEqual(finding["code"], "MISSING_PREREQUISITE")
        self.assertEqual(finding["path"], "$.items[0].requires[1]")
        self.assertEqual(finding["edge"], {"from": "Absent", "to": "A"})
        self.assertEqual(report["dependency_frontiers"], [["Z"]])
        self.assertEqual(report["blocked_items"][1]["blocked_by"], "A")

    def test_cycles_are_not_conflated_with_downstream_items(self):
        report = c.analyze(packet(item("A", ["B"]), item("B", ["A"]),
                                  item("C", ["B"]), item("Independent")))
        self.assertEqual(report["cycles"][0]["members"], ["A", "B"])
        self.assertEqual({r["id"] for r in report["blocked_items"]}, {"A", "B", "C"})
        self.assertEqual(report["dependency_frontiers"], [["Independent"]])

    def test_cycle_witness_edges_are_actual_directed_edges(self):
        report = c.analyze(packet(item("A", ["C"]), item("B", ["A", "C"]), item("C", ["B"])))
        edges = {(e["from"], e["to"]) for e in report["edges"]}
        for cycle in report["cycles"]:
            witness = cycle["witness_path"]
            self.assertEqual(witness[0], witness[-1])
            self.assertTrue(all(edge in edges for edge in zip(witness, witness[1:])))
            self.assertEqual(len(witness) - 1, len(set(witness[:-1])))

    def test_self_dependency(self):
        report = c.analyze(packet(item("A", ["A"])))
        self.assertEqual(report["cycles"][0]["witness_path"], ["A", "A"])
        self.assertEqual(report["dependency_frontiers"], [])

    def test_disjoint_cycles(self):
        report = c.analyze(packet(item("A", ["B"]), item("B", ["A"]),
                                  item("C", ["D"]), item("D", ["C"])))
        self.assertEqual([x["members"] for x in report["cycles"]], [["A", "B"], ["C", "D"]])

    def test_direct_phase_inversion(self):
        report = c.analyze(packet(item("A", phase="later"), item("B", ["A"]), item("C", ["B"])))
        self.assertEqual(report["diagnostics"][0]["code"], "PHASE_INVERSION")
        self.assertEqual(report["dependency_frontiers"], [["A"]])
        self.assertEqual({x["id"] for x in report["blocked_items"]}, {"B", "C"})

    def test_transitive_phase_inversion_through_unassigned_item(self):
        report = c.analyze(packet(item("A", phase="later"), item("B", ["A"], phase=None),
                                  item("C", ["B"], phase="now"), item("D", ["C"], phase="later")))
        conflict = next(x for x in report["diagnostics"] if x["code"] == "TRANSITIVE_PHASE_INVERSION")
        self.assertEqual(conflict["witness_path"], ["A", "B", "C"])
        self.assertEqual(report["dependency_frontiers"], [["A"], ["B"]])
        self.assertEqual({x["id"] for x in report["blocked_items"]}, {"C", "D"})

    def test_same_phase_dependency_is_valid(self):
        report = c.analyze(packet(item("A"), item("B", ["A"])))
        self.assertEqual(report["dependency_check_status"], "CONSISTENT")
        self.assertEqual(report["dependency_frontiers"], [["A"], ["B"]])

    def test_unassigned_phase_is_incomplete_not_zero_or_invalid_graph(self):
        report = c.analyze(packet(item("A", phase=None), item("B", ["A"])))
        self.assertEqual(report["dependency_check_status"], "INCOMPLETE")
        self.assertEqual(report["dependency_frontiers"], [["A"], ["B"]])
        self.assertEqual(report["counts"]["errors"], 0)

    def test_empty_packet_is_not_a_completed_roadmap(self):
        report = c.analyze(packet())
        self.assertEqual(report["dependency_check_status"], "INCOMPLETE")
        self.assertEqual(report["diagnostics"][0]["code"], "EMPTY_ROADMAP")

    def test_input_is_not_mutated_and_report_is_detached(self):
        original = packet(item("A"))
        snapshot = copy.deepcopy(original)
        report = c.analyze(original)
        report["nodes"][0]["requires"].append("B")
        report["phases"][0]["label"] = "Changed"
        self.assertEqual(original, snapshot)

    def test_source_digest_is_canonical_input_not_graph_authentication(self):
        source = packet(item("A"), item("B"))
        report = c.analyze(source)
        self.assertEqual(report["input_sha256"], hashlib.sha256(c._canonical(source)).hexdigest())
        self.assertIn("not source authentication", report["digest_basis"])
        reordered = copy.deepcopy(source)
        reordered["items"].reverse()
        second = c.analyze(reordered)
        self.assertEqual(second["dependency_frontiers"], report["dependency_frontiers"])
        self.assertNotEqual(second["input_sha256"], report["input_sha256"])

    def test_no_schedule_release_or_assessment_authority(self):
        report = c.analyze(packet(item("A")))
        self.assertTrue(all(type(v) is bool and v is False for v in report["authority"].values()))
        self.assertIn("not a promise", report["frontier_meaning"])

    def test_exhaustive_all_512_three_node_directed_graphs(self):
        ids = {"A", "B", "C"}
        possible = [(a, b) for a in sorted(ids) for b in sorted(ids)]
        for mask in range(1 << len(possible)):
            edges = {e for i, e in enumerate(possible) if mask & (1 << i)}
            source = packet(*(item(n, sorted(a for a, b in edges if b == n)) for n in sorted(ids)))
            report = c.analyze(source)
            waves, blocked = brute_frontiers(ids, edges)
            self.assertEqual(report["dependency_frontiers"], waves, f"mask={mask}")
            self.assertEqual({x["id"] for x in report["blocked_items"]}, blocked, f"mask={mask}")
            # Independent positive-length reachability oracle distinguishes SCC members from their tails.
            reach = set(edges)
            for middle in ids:
                reach |= {(a, b) for a in ids for b in ids if (a, middle) in reach and (middle, b) in reach}
            actual_cycle_members = {x for component in report["cycles"] for x in component["members"]}
            self.assertEqual(actual_cycle_members, {n for n in ids if (n, n) in reach}, f"mask={mask}")

    def test_random_dag_parallel_frontiers_match_reference(self):
        rng = random.Random(731)
        for _ in range(60):
            names = [f"R{i:02}" for i in range(25)]
            edges = {(names[a], names[b]) for a in range(25) for b in range(a + 1, 25) if rng.random() < 0.14}
            report = c.analyze(packet(*(item(n, sorted(a for a, b in edges if b == n)) for n in names)))
            expected, blocked = brute_frontiers(set(names), edges)
            self.assertFalse(blocked)
            self.assertEqual(report["dependency_frontiers"], expected)

    def test_maximum_length_chain_uses_no_recursion(self):
        source = packet(*(item(f"R{i:04}", [f"R{i-1:04}"] if i else []) for i in range(c.MAX_ITEMS)))
        report = c.analyze(source)
        self.assertEqual(len(report["dependency_frontiers"]), c.MAX_ITEMS)
        self.assertEqual(report["dependency_frontiers"][-1], [f"R{c.MAX_ITEMS-1:04}"])

    def test_transitive_phase_root_does_not_duplicate_descendant_errors(self):
        source = packet(item("A", phase="later"), item("B", ["A"], phase=None),
                        item("C", ["B"], phase="now"), item("D", ["C"], phase="now"),
                        item("E", ["D"], phase="now"))
        report = c.analyze(source)
        self.assertEqual(sum(d["code"] == "TRANSITIVE_PHASE_INVERSION" for d in report["diagnostics"]), 1)
        self.assertEqual({r["id"] for r in report["blocked_items"]}, {"C", "D", "E"})

    def test_overlapping_cycles_require_review_not_one_automatic_cut(self):
        source = packet(item("A", ["B", "C"]), item("B", ["A", "C"]), item("C", ["A", "B"]))
        report = c.analyze(source)
        self.assertEqual(len(report["cycles"][0]["internal_edges"]), 6)
        source["items"][0]["requires"].remove("B")
        self.assertTrue(c.analyze(source)["cycles"])

    def test_all_four_node_ordered_dags_and_phase_assignments(self):
        # 64 DAGs x 256 phase assignments = 16,384 independent phase cases.
        import itertools
        names = ["A", "B", "C", "D"]
        possible = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
        phase_values = ["now", "next", "later", None]
        for mask in range(1 << len(possible)):
            edges = {e for i, e in enumerate(possible) if mask & (1 << i)}
            ancestors = {name: set() for name in names}
            for name in names:
                for a, b in edges:
                    if b == name:
                        ancestors[name] |= {a} | ancestors[a]
            for assignments in itertools.product(range(4), repeat=4):
                phases = dict(zip(names, assignments))
                bad = {name for name in names if phases[name] < 3 and
                       any(phases[a] < 3 and phases[a] > phases[name] for a in ancestors[name])}
                expected = bad | {name for name in names if ancestors[name] & bad}
                source = packet(*(item(name, sorted(a for a, b in edges if b == name),
                                       phase=phase_values[phases[name]]) for name in names))
                actual = {r["id"] for r in c.analyze(source)["blocked_items"]}
                self.assertEqual(actual, expected, (mask, assignments))


class InputAndRenderingTests(unittest.TestCase):
    def test_duplicate_json_keys(self):
        with self.assertRaisesRegex(c.InputError, "duplicate object key"):
            c.loads('{"schema":"one","schema":"two"}')

    def test_float_nonfinite_and_integer_native_tokens_rejected(self):
        for value in ("NaN", "Infinity", "-Infinity", "1.0", "10", "1e9999"):
            with self.subTest(value=value), self.assertRaises(c.InputError):
                c.loads('{"schema":' + value + '}')

    def test_bad_utf8_surrogate_and_parser_depth(self):
        for value in (b'\xff', '"\\ud800"', '[' * 1500 + ']' * 1500):
            with self.subTest(value=repr(value)[:50]), self.assertRaises(c.InputError):
                c.loads(value)
        source = packet(item("A", title="\ud800"))
        with self.assertRaises(c.InputError):
            c.analyze(source)

    def test_duplicate_ids_edges_and_phases(self):
        cases = [packet(item("A"), item("A")), packet(item("A", ["B", "B"]), item("B"))]
        duplicate_phase = packet(item("A"))
        duplicate_phase["phases"].append(duplicate_phase["phases"][0].copy())
        cases.append(duplicate_phase)
        for source in cases:
            with self.assertRaises(c.InputError):
                c.analyze(source)

    def test_unknown_phase_and_unknown_fields(self):
        for source in (packet(item("A", phase="typo")), {**packet(item("A")), "ignored": True}):
            with self.assertRaises(c.InputError):
                c.analyze(source)

    def test_exact_plain_json_types(self):
        class CustomDict(dict):
            pass
        for source in (CustomDict(packet(item("A"))), packet(item("A", phase=True))):
            with self.assertRaises(c.InputError):
                c.analyze(source)

    def test_bounded_bytes_items_and_edges(self):
        with self.assertRaises(c.InputError):
            c.loads(b' ' * (c.MAX_BYTES + 1))
        with self.assertRaises(c.InputError):
            c.analyze(packet(*(item(f"R{i}") for i in range(c.MAX_ITEMS + 1))))
        with self.assertRaises(c.InputError):
            c.analyze(packet(item("A", [f"Missing{i}" for i in range(c.MAX_EDGES + 1)])))

    def test_identifier_grammar_matches_adapter_phase_and_recommendation_ids(self):
        report = c.analyze(packet(item("0.alpha-1")))
        self.assertEqual(report["nodes"][0]["id"], "0.alpha-1")
        for ident in ('A" -> B', "__missing__A", "A/B", "A B", "A\nB"):
            with self.assertRaises(c.InputError):
                c.analyze(packet(item(ident)))

    def test_markdown_and_dot_escape_human_titles(self):
        report = c.analyze(packet(item("A", title='<script>x</script> | [click](url) "line"\nnew')))
        md, graph = c.markdown(report), c.dot(report)
        self.assertNotIn("<script>", md)
        self.assertIn("&lt;script&gt;", md)
        self.assertIn("\\|", md)
        self.assertIn("<br>", md)
        self.assertIn('\\"line\\"\\nnew', graph)

    def test_dot_includes_missing_and_inversion_edges(self):
        report = c.analyze(packet(item("A", phase="later"), item("B", ["A", "Gone"])))
        graph = c.dot(report)
        self.assertIn('"__missing__Gone" -> "B"', graph)
        self.assertIn('"A" -> "B" [label="phase inversion"', graph)

    def test_deterministic_repeated_report_and_renderings(self):
        source = packet(item("A", ["B"]), item("B", ["A"]), item("X"))
        first, second = c.analyze(source), c.analyze(source)
        self.assertEqual(first, second)
        self.assertEqual(c.markdown(first), c.markdown(second))
        self.assertEqual(c.dot(first), c.dot(second))


class AdapterTests(unittest.TestCase):
    def test_consumes_real_085_schema_and_preserves_parallelism(self):
        document = upstream(item("R1"), item("R2", ["R1"], "next"), item("R3", ["R1"], "next"))
        report = c.analyze_roadmap085(document)
        self.assertEqual(report["dependency_frontiers"], [["R1"], ["R2", "R3"]])
        self.assertEqual(report["source_projection"]["full_input_sha256"], hashlib.sha256(c._canonical(document)).hexdigest())
        self.assertEqual(report["source_projection"]["contract_reference"]["inspected_blob"], "4870639c2cb077657feeba3a4e9dae739df5acfe")

    def test_085_phase_inversion(self):
        report = c.analyze_roadmap085(upstream(item("R1", phase="later"), item("R2", ["R1"])))
        self.assertEqual(report["dependency_check_status"], "NEEDS_REPAIR")
        self.assertEqual(report["diagnostics"][0]["prerequisite_phase"], "180+")

    def test_085_missing_duration_is_not_invented_as_zero(self):
        document = upstream(item("R1"))
        document["recommendations"][0]["duration_days"] = None
        report = c.analyze_roadmap085(document)
        self.assertIn("Duration feasibility", report["source_projection"]["not_evaluated"])
        self.assertNotIn("start_min", report["nodes"][0])
        self.assertNotIn("duration_days", report["nodes"][0])

    def test_085_evidence_changes_affect_full_source_digest_not_graph_digest(self):
        first = upstream(item("R1"))
        second = copy.deepcopy(first)
        second["recommendations"][0]["evidence_refs"] = ["SYN-E2"]
        a, b = c.analyze_roadmap085(first), c.analyze_roadmap085(second)
        self.assertEqual(a["input_sha256"], b["input_sha256"])
        self.assertNotEqual(a["source_projection"]["full_input_sha256"], b["source_projection"]["full_input_sha256"])

    def test_085_refuses_derived_report_as_input(self):
        document = upstream(item("R1"))
        document["recommendations"][0]["start_min"] = 0
        with self.assertRaises(c.InputError):
            c.analyze_roadmap085(document)

    def test_085_invalid_shapes_types_and_duration(self):
        for field, value in (("group", "UNKNOWN"), ("phase", "unknown"), ("duration_days", [True, 3]),
                             ("duration_days", [4, 3]), ("duration_days", [1, 2.0]),
                             ("duration_days", [0, 10**17]), ("owner_role", {})):
            document = upstream(item("R1"))
            document["recommendations"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(c.InputError):
                c.analyze_roadmap085(document)
        document = upstream(item("R1"))
        document["synthetic"] = "true"
        with self.assertRaises(c.InputError):
            c.analyze_roadmap085(document)

    def test_085_plain_source_is_not_mutated(self):
        document = upstream(item("R1"))
        before = copy.deepcopy(document)
        report = c.analyze_roadmap085(document)
        report["nodes"][0]["requires"].append("R2")
        self.assertEqual(document, before)


class CliTests(unittest.TestCase):
    def run_cli(self, path, *args):
        return subprocess.run([sys.executable, str(Path(c.__file__)), str(path), *map(str, args)],
                              capture_output=True, text=True, timeout=10)

    def test_cli_valid_invalid_graph_and_invalid_input_exit_codes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.json"
            for source, status in ((packet(item("A")), 0), (packet(item("A", ["Missing"])), 1)):
                path.write_text(json.dumps(source), encoding="utf-8")
                result = self.run_cli(path)
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertEqual(json.loads(result.stdout)["schema"], c.REPORT_SCHEMA)
            path.write_text('{"broken":', encoding="utf-8")
            result = self.run_cli(path)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(result.stdout, "")

    def test_cli_output_formats_and_input_preservation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "input.json"
            original = json.dumps(packet(item("A")))
            path.write_text(original, encoding="utf-8")
            for format in ("markdown", "dot"):
                output = Path(temp) / ("report." + format)
                result = self.run_cli(path, "--format", format, "--output", output)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(output.stat().st_size)
            result = self.run_cli(path, "--output", path)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_cli_rejects_hardlink_input_output_alias(self):
        with tempfile.TemporaryDirectory() as temp:
            path, alias = Path(temp) / "input.json", Path(temp) / "alias.json"
            path.write_text(json.dumps(packet(item("A"))), encoding="utf-8")
            os.link(path, alias)
            result = self.run_cli(path, "--output", alias)
            self.assertEqual(result.returncode, 2)
            self.assertIn("input-file alias", result.stderr)

    def test_cli_085_and_oversized_integer(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "085.json"
            path.write_text(json.dumps(upstream(item("R1"))), encoding="utf-8")
            result = self.run_cli(path, "--input-format", "roadmap085")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("source_projection", json.loads(result.stdout))
            path.write_text('{"schema_version":' + '1' * 5000 + '}', encoding="utf-8")
            result = self.run_cli(path, "--input-format", "roadmap085")
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)

    def test_invalid_input_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path, output = Path(temp) / "bad.json", Path(temp) / "retained.txt"
            path.write_text('{"bad":', encoding="utf-8")
            output.write_text("Retain this", encoding="utf-8")
            result = self.run_cli(path, "--output", output)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "Retain this")


if __name__ == "__main__":
    unittest.main(verbosity=2)
