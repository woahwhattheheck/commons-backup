#!/usr/bin/env python3
"""Independent, synthetic UIOWA-042 source/CLI review; no network or live data.

Run from any directory:
  python review_limen7c94.py --source path/to/trace.py --out NEW_receipt.json
  python -O review_limen7c94.py --source path/to/trace.py --out NEW_optimized.json

This imports and executes the specified local source. It never fetches code.
Outputs are create-only. Production source and original author tests are not
modified. A failing case is retained as a finding, not relabelled as success.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest

SOURCE: Path
ENGINE = None
EXPECTED_SOURCE = "d625dbbe73729638e1dfbe887a3c2c7a607b0524"
COUNTERS: dict[str, int] = {}
OBSERVATIONS: list[dict] = []


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def packet(n: int = 1) -> dict:
    """All records are invented. No person, institution or delivery is attested."""
    p = {"example_id": "SYN-LIMEN-042", "delivery_style": "project",
         "requests": [{"request_id": "R0", "text": "Fictional request"}],
         "criteria": [], "implementations": [], "tests": [], "acceptances": []}
    for i in range(n):
        cid = f"C{i}"
        p["criteria"].append({"criterion_id": cid, "request_id": "R0",
                              "revision": 2, "text": f"Fictional criterion {i}"})
        p["implementations"].append({"impl_id": f"I{i}", "criterion_id": cid,
                                     "ref": f"synthetic:implementation/{i}"})
        p["tests"].append({"test_id": f"T{i}", "criterion_id": cid,
                           "ref": f"synthetic:test/{i}", "result": "PASS"})
        p["acceptances"].append({"acceptance_id": f"A{i}", "criterion_id": cid,
                                 "criterion_revision": 2,
                                 "evidence_ref": f"synthetic:acceptance/{i}",
                                 "accepted_by_role": "Fictional service role",
                                 "accepted_at": "2026-09-01"})
    return p


def cli(args: list[str]) -> subprocess.CompletedProcess:
    flags = ["-O"] if sys.flags.optimize else []
    return subprocess.run([sys.executable, *flags, str(SOURCE), *args],
                          capture_output=True, text=True, timeout=15)


def state_map(payload: dict) -> dict[str, str]:
    return {r["criterion_id"]: r["state"] for r in ENGINE.Example(payload).results}


def graph_expected(edges: tuple, requests: tuple) -> dict[str, str]:
    """Independent bounded oracle via adjacency-matrix transitive closure.

    A node with no successor is current and has the complete synthetic chain.
    A predecessor is broken if its reachable closure includes a cycle, missing
    target, or a request partition different from its own. No assumption about
    increasing revision numbers between *distinct criterion IDs* is introduced.
    """
    n = len(edges)
    reach = [[False] * n for _ in range(n)]
    missing = [False] * n
    for i, target in enumerate(edges):
        if target == "X":
            missing[i] = True
        elif target is not None:
            reach[i][target] = True
    for k in range(n):
        for i in range(n):
            for j in range(n):
                reach[i][j] = reach[i][j] or (reach[i][k] and reach[k][j])
    result = {}
    for i, target in enumerate(edges):
        reachable = [j for j in range(n) if reach[i][j]]
        broken = missing[i] or any(missing[j] or reach[j][j] or
                                  requests[j] != requests[i] for j in reachable)
        result[f"C{i}"] = ("TRACED" if target is None else
                           "BROKEN_LINK" if broken else "SUPERSEDED")
    return result


class Review(unittest.TestCase):
    def test_source_identity(self):
        self.assertEqual(blob(SOURCE.read_bytes()), EXPECTED_SOURCE)

    def test_positive_complete_chain(self):
        ex = ENGINE.Example(packet())
        self.assertEqual(ex.verdict(), "EVIDENCED")
        self.assertEqual(state_map(packet()), {"C0": "TRACED"})
        self.assertEqual(len(ex.open_criteria()), 0)

    def test_all_three_node_successor_graphs_and_request_partitions(self):
        count = 0
        for edges in itertools.product((None, 0, 1, 2, "X"), repeat=3):
            for reqs in itertools.product(("R0", "R1"), repeat=3):
                p = packet(3)
                p["requests"].append({"request_id": "R1", "text": "Fictional other request"})
                for i, target in enumerate(edges):
                    p["criteria"][i]["request_id"] = reqs[i]
                    if target is not None:
                        p["criteria"][i]["superseded_by"] = "X" if target == "X" else f"C{target}"
                expected = graph_expected(edges, reqs)
                ex = ENGINE.Example(p)
                self.assertEqual(state_map(p), expected, (edges, reqs))
                want = "NOT_ESTABLISHED" if "BROKEN_LINK" in expected.values() else "EVIDENCED"
                self.assertEqual(ex.verdict(), want, (edges, reqs))
                self.assertEqual(len(ex.open_criteria()), sum(v == "BROKEN_LINK" for v in expected.values()))
                for order in itertools.permutations(p["criteria"]):
                    q = copy.deepcopy(p)
                    q["criteria"] = list(order)
                    self.assertEqual(state_map(q), expected, (edges, reqs))
                count += 1
        COUNTERS["distinct_graph_partition_cases"] = count
        COUNTERS["graph_order_replays"] = count * 6

    def test_revision_cartesian_panel(self):
        count = 0
        invalid = [None, True, False, 0, -1, "2", 2.0, [], {}]
        for rev in range(1, 5):
            for accepted in [*invalid, 1, 2, 3, 4, 5]:
                p = packet()
                p["criteria"][0]["revision"] = rev
                p["acceptances"][0]["criterion_revision"] = accepted
                want = ("INCOMPLETE_ACCEPTANCE" if type(accepted) is not int or accepted <= 0 else
                        "BROKEN_LINK" if accepted > rev else
                        "ACCEPTED_AGAINST_SUPERSEDED_REVISION" if accepted < rev else "TRACED")
                self.assertEqual(state_map(p)["C0"], want, (rev, accepted))
                count += 1
        for value in invalid:
            p = packet()
            p["criteria"][0]["revision"] = value
            self.assertEqual(state_map(p)["C0"], "BROKEN_LINK")
            self.assertEqual(ENGINE.Example(p).verdict(), "NOT_ESTABLISHED")
            count += 1
        COUNTERS["revision_cases"] = count

    def test_old_current_future_acceptance_orderings(self):
        count = 0
        for revisions in itertools.product((1, 2, 3, None), repeat=3):
            p = packet()
            first = p["acceptances"][0]
            p["acceptances"] = [dict(first, acceptance_id=f"A{i}", criterion_revision=r)
                                  for i, r in enumerate(revisions)]
            expected = ("INCOMPLETE_ACCEPTANCE" if None in revisions else
                        "BROKEN_LINK" if 3 in revisions else
                        "TRACED" if 2 in revisions else "ACCEPTED_AGAINST_SUPERSEDED_REVISION")
            for order in itertools.permutations(p["acceptances"]):
                q = copy.deepcopy(p)
                q["acceptances"] = list(order)
                self.assertEqual(state_map(q)["C0"], expected, revisions)
                count += 1
        COUNTERS["acceptance_order_replays"] = count

    def test_orphans_block_packet_but_not_unrelated_criterion(self):
        count = 0
        for section, ident in (("implementations", "impl_id"), ("tests", "test_id"),
                               ("acceptances", "acceptance_id")):
            for ref in (None, "", "UNKNOWN", "MISSING"):
                p = packet()
                p[section].append(dict(p[section][0], **{ident: "ORPHAN", "criterion_id": ref}))
                ex = ENGINE.Example(p)
                self.assertEqual(state_map(p)["C0"], "TRACED")
                self.assertEqual(ex.verdict(), "NOT_ESTABLISHED")
                self.assertEqual(len(ex.dangling_links()), 1)
                self.assertEqual(len(ex.open_criteria()), 0)
                count += 1
        COUNTERS["orphan_cases"] = count

    def test_missing_locators_never_close_chain(self):
        for section, key in (("implementations", "ref"), ("tests", "ref"), ("acceptances", "evidence_ref")):
            for value in (None, "", " ", "UNKNOWN", " unknown "):
                p = packet()
                p[section][0][key] = value
                self.assertEqual(ENGINE.Example(p).verdict(), "NOT_ESTABLISHED")

    def test_declared_coverage_is_style_specific(self):
        for style, expected in (("project", "UNTESTED"), ("maintenance_change", "TRACED")):
            p = packet()
            p["delivery_style"] = style
            p["tests"] = []
            p["criteria"][0]["covered_by_regression_ref"] = "synthetic:declared-coverage"
            self.assertEqual(state_map(p)["C0"], expected)

    def test_failing_test_cannot_hide_behind_passing_test(self):
        for result in ("FAIL", "NOT_RUN", None, "UNKNOWN"):
            p = packet()
            p["tests"].append(dict(p["tests"][0], test_id="OTHER", result=result))
            for order in itertools.permutations(p["tests"]):
                q = copy.deepcopy(p)
                q["tests"] = list(order)
                self.assertEqual(state_map(q)["C0"], "TEST_NOT_PASSING")

    def test_duplicate_records_are_typed_input_errors(self):
        for section in ("requests", "criteria", "implementations", "tests", "acceptances"):
            p = packet()
            p[section].append(copy.deepcopy(p[section][0]))
            with self.assertRaises(ENGINE.TraceError):
                ENGINE.Example(p)

    def test_payload_is_not_mutated_and_input_snapshot_is_detached(self):
        p = packet()
        before = copy.deepcopy(p)
        ex = ENGINE.Example(p)
        self.assertEqual(p, before)
        result = copy.deepcopy(ex.as_dict())
        p["acceptances"].clear()
        self.assertEqual(ex.as_dict(), result)

    def test_cli_exit_json_and_markdown_agree_for_clean_and_orphan(self):
        for orphan in (False, True):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                p = packet()
                if orphan:
                    p["tests"].append(dict(p["tests"][0], test_id="ORPHAN", criterion_id="MISSING"))
                source = root / "input.json"
                source.write_text(json.dumps(p), encoding="utf-8")
                original = source.read_bytes()
                out = root / "out"
                run = cli(["--input", str(source), "--outdir", str(out)])
                expected = "NOT_ESTABLISHED" if orphan else "EVIDENCED"
                self.assertEqual(run.returncode, int(orphan), run.stderr)
                report = json.loads((out / "traceability.json").read_text())
                self.assertEqual(report[0]["verdict"], expected)
                self.assertIn(f"**Verdict: `{expected}`**", (out / "traceability_report.md").read_text())
                self.assertEqual(source.read_bytes(), original)
                OBSERVATIONS.append({"case": "orphan" if orphan else "complete", "exit": run.returncode,
                                     "verdict": report[0]["verdict"], "open_criteria": report[0]["open_criteria"],
                                     "dangling_links": report[0]["dangling_links"]})

    def test_cli_strict_json_and_utf8_errors_leave_no_output(self):
        bad_inputs = [b"[]", b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff', b'{']
        for raw in bad_inputs:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "bad.json"
                source.write_bytes(raw)
                out = root / "out"
                run = cli(["--input", str(source), "--outdir", str(out)])
                self.assertEqual(run.returncode, 2, run.stderr)
                self.assertNotIn("Traceback", run.stderr)
                self.assertFalse(out.exists())
                self.assertEqual(source.read_bytes(), raw)

    def test_csv_retains_packet_level_orphan_blocker(self):
        """The spreadsheet must not lose a blocker visible only at packet scope."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = packet()
            p["acceptances"].append(dict(p["acceptances"][0], acceptance_id="ORPHAN", criterion_id="MISSING"))
            source = root / "input.json"
            source.write_text(json.dumps(p), encoding="utf-8")
            out = root / "out"
            run = cli(["--input", str(source), "--outdir", str(out)])
            sheet = (out / "traceability_sheet.csv").read_text(encoding="utf-8")
            with (out / "traceability_sheet.csv").open(newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            OBSERVATIONS.append({"case": "csv_orphan_projection", "exit": run.returncode,
                                 "csv_headers": list(rows[0]), "csv_states": [r["state"] for r in rows],
                                 "csv_closed": [r["closed"] for r in rows], "csv_text": sheet})
            self.assertEqual(run.returncode, 1, run.stderr)
            self.assertIn("NOT_ESTABLISHED", sheet, "CSV omits packet verdict; every exported criterion is closed")
            self.assertIn("ORPHAN", sheet, "CSV loses the orphan record identity")
            self.assertIn("MISSING", sheet, "CSV loses the unresolved target")

    def test_cli_refuses_output_that_aliases_any_input(self):
        """Real direct-path, symlink and hardlink aliases in disposable directories."""
        for filename in ("traceability.json", "traceability_sheet.csv", "traceability_report.md"):
            for alias in ("direct", "symlink", "hardlink"):
                with self.subTest(filename=filename, alias=alias), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    out = root / "out"
                    out.mkdir()
                    target = out / filename
                    source = target if alias == "direct" else root / "input.json"
                    source.write_text(json.dumps(packet()), encoding="utf-8")
                    original = source.read_bytes()
                    if alias == "symlink":
                        target.symlink_to(source)
                    elif alias == "hardlink":
                        os.link(source, target)
                    run = cli(["--input", str(source), "--outdir", str(out)])
                    OBSERVATIONS.append({"case": "input_output_alias", "filename": filename,
                                         "alias": alias, "exit": run.returncode,
                                         "input_preserved": source.read_bytes() == original})
                    self.assertEqual(source.read_bytes(), original, "CLI overwrote the supplied evidence input")
                    self.assertEqual(run.returncode, 2, run.stderr)


def main() -> int:
    global SOURCE, ENGINE, EXPECTED_SOURCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--expect-blob", default=EXPECTED_SOURCE)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    SOURCE = args.source.resolve(strict=True)
    EXPECTED_SOURCE = args.expect_blob
    if blob(SOURCE.read_bytes()) != EXPECTED_SOURCE:
        parser.error("source blob mismatch; no source code was executed")
    if args.out.exists() or args.out.is_symlink():
        parser.error("receipt path already exists; choose a new path")
    spec = importlib.util.spec_from_file_location("limen_reviewed_trace042", SOURCE)
    if spec is None or spec.loader is None:
        parser.error("cannot load the provided source")
    ENGINE = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ENGINE)
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Review))
    data = {"schema": "uiowa042-independent-review/v1", "synthetic": True,
            "seat": "ZZ-LIMEN-7C94", "family": "gpt", "model": "GPT-6 Astra Pro",
            "operation": "uiowa042-review-limen7c94-20260919",
            "source_git_blob": blob(SOURCE.read_bytes()), "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            "review_git_blob": blob(Path(__file__).read_bytes()),
            "python": platform.python_version(), "optimization": sys.flags.optimize,
            "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
            "skips": len(result.skipped), "passed": result.wasSuccessful(),
            "case_counts": COUNTERS, "observations": OBSERVATIONS,
            "failures_and_errors": [{"test": test.id(), "traceback": text} for test, text in result.failures + result.errors],
            "log": log.getvalue(),
            "limits": ["Sparse exact-source review, not full-repository execution.",
                       "Does not replay the author's 67-test suite.",
                       "No hosted-CI, source-authenticity, University finding or runtime-merge claim.",
                       "Graph coverage is exhaustive only over the documented three-node finite domain."]}
    with args.out.open("x", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(log.getvalue(), end="")
    print(json.dumps({key: data[key] for key in ("tests_run", "failures", "errors", "skips", "passed", "case_counts")}, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
