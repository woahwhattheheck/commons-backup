#!/usr/bin/env python3
"""UIOWA-095 tests.

The central claim of this lane is "the optimized workflow is faster AND returns
exactly the same answer." The speed half is measured by benchmark.py. The
sameness half is this file's job, and it is the half that matters, because a
faster wrong answer is not an improvement.

Run:  python3 -m unittest discover -v
"""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import generate_collection as gen
import workflow as wf


def _write_csv(path: Path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def minimal_collection(root: Path, *, statements, report_text,
                       documents=None, evidence=None, findings=None,
                       recommendations=None):
    """Hand-built collection, for the cases the generator deliberately cannot
    produce (ambiguous ids, everything missing, and so on)."""
    root = Path(root)
    (root / "documents").mkdir(parents=True, exist_ok=True)
    evidence = evidence if evidence is not None else [
        {"evidence_id": "E-001", "service": "ESS", "assessment_area": "security",
         "source_type": "requirement", "source_name": "Fictional", "locator": "s1",
         "observation": "SYNTHETIC", "evidence_state": "strength", "synthetic": "true"},
    ]
    findings = findings if findings is not None else [
        {"finding_id": "F-001", "service": "ESS", "assessment_area": "security",
         "statement": "SYNTHETIC", "evidence_ids": "E-001", "confidence": "supported",
         "synthetic": "true"},
    ]
    _write_csv(root / "evidence.csv",
               ["evidence_id", "service", "assessment_area", "source_type",
                "source_name", "locator", "observation", "evidence_state", "synthetic"],
               evidence)
    _write_csv(root / "findings.csv",
               ["finding_id", "service", "assessment_area", "statement",
                "evidence_ids", "confidence", "synthetic"],
               findings)
    recommendations = recommendations if recommendations is not None else [
        {"recommendation_id": "R-001", "linked_findings": "F-001",
         "horizon": "0-90", "effort_estimate": "UNKNOWN", "synthetic": "true"},
    ]
    _write_csv(root / "recommendations.csv",
               ["recommendation_id", "linked_findings", "horizon", "effort_estimate", "synthetic"],
               recommendations)
    _write_csv(root / "trace-map.csv",
               ["statement_id", "report_location", "statement_summary",
                "recommendation_ids", "finding_ids", "evidence_ids", "synthetic"],
               [{"statement_id": s, "report_location": "final-report.md#f",
                 "statement_summary": "SYNTHETIC", "recommendation_ids": "R-001",
                 "finding_ids": "F-001", "evidence_ids": "E-001", "synthetic": "true"}
                for s in statements])
    (root / "final-report.md").write_text(report_text, encoding="utf-8")
    documents = documents or []
    for doc in documents:
        body = doc.pop("_body", None)
        if body is not None:
            (root / doc["path"]).write_text(body, encoding="utf-8")
    (root / "manifest.json").write_text(json.dumps({
        "schema": "uiowa-095-collection-v1", "synthetic": True,
        "services": ["ESS"], "assessment_areas": ["security", "ai_readiness"],
        "report_files": ["final-report.md"], "documents": documents,
    }, indent=2, sort_keys=True), encoding="utf-8")
    return root


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="uiowa095-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)


class TestGeneratorIsDeterministic(TempCase):
    def test_same_seed_produces_identical_bytes(self):
        """A benchmark a second operator cannot reproduce is not a benchmark."""
        a = gen.generate(self.tmp / "a", gen.PROFILES["small"], seed=7)
        b = gen.generate(self.tmp / "b", gen.PROFILES["small"], seed=7)
        self.assertEqual(a, b)
        for name in ("evidence.csv", "findings.csv", "recommendations.csv",
                     "trace-map.csv", "manifest.json", "final-report.md",
                     "executive-summary.md"):
            self.assertEqual((self.tmp / "a" / name).read_bytes(),
                             (self.tmp / "b" / name).read_bytes(),
                             f"{name} differs between two same-seed generations")

    def test_different_seed_changes_content_but_not_shape(self):
        a = gen.generate(self.tmp / "a", gen.PROFILES["small"], seed=7)
        b = gen.generate(self.tmp / "b", gen.PROFILES["small"], seed=8)
        self.assertEqual(a["evidence_rows"], b["evidence_rows"])
        self.assertNotEqual((self.tmp / "a" / "evidence.csv").read_bytes(),
                            (self.tmp / "b" / "evidence.csv").read_bytes())

    def test_every_generated_document_is_labelled_synthetic(self):
        gen.generate(self.tmp / "a", gen.PROFILES["small"], seed=7)
        docs = sorted((self.tmp / "a" / "documents").iterdir())
        self.assertTrue(docs)
        for p in docs:
            head = p.read_text(encoding="utf-8")[:wf.LABEL_WINDOW_CHARS]
            self.assertIn("SYNTHETIC", head.upper(), f"{p.name} is not labelled fiction")


class TestSeededDefectsAreFound(TempCase):
    """The fixture demonstrates a strength (most links resolve, most statements
    land in the report) and a real gap (a few deliberately do not). Both halves
    must show up, or the fixture is not exercising anything."""

    def setUp(self):
        super().setUp()
        self.root = self.tmp / "c"
        gen.generate(self.root, gen.PROFILES["small"], seed=20260919)
        self.manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        self.result = wf.run_workflow(self.root, mode="optimized")

    def test_broken_evidence_citations_surface(self):
        expected = self.manifest["seeded_defects"]["findings_with_unresolvable_evidence"]
        self.assertEqual(len(self.result.link_errors), len(expected))
        for fid in expected:
            self.assertTrue(any(e.startswith(fid + ":") for e in self.result.link_errors),
                            f"{fid} broken citation was not reported")

    def test_statements_missing_from_the_report_surface(self):
        expected = self.manifest["seeded_defects"]["statements_absent_from_report"]
        self.assertEqual(len(self.result.statement_errors), len(expected))
        for sid in expected:
            self.assertTrue(any(e.startswith(sid + ":") for e in self.result.statement_errors))

    def test_document_listed_but_not_on_disk_is_an_error_not_a_pass(self):
        expected = self.manifest["seeded_defects"]["documents_listed_but_absent"]
        self.assertEqual(len(self.result.document_errors), len(expected))
        self.assertIn("missing on disk", self.result.document_errors[0])

    def test_the_majority_of_links_do_resolve(self):
        """The strength half: the fixture is mostly sound, so the errors above
        are signal and not just a broken corpus."""
        with (self.root / "findings.csv").open(encoding="utf-8", newline="") as fh:
            total_findings = sum(1 for _ in csv.DictReader(fh))
        self.assertGreater(total_findings, 10)
        self.assertLess(len(self.result.link_errors), total_findings * 0.1)


class TestUnknownStaysUnknown(TempCase):
    def test_uncovered_cell_is_UNKNOWN_never_zero(self):
        """An unexamined cell and an examined-and-empty cell are different
        claims. Absent evidence must never be rendered as a 0 or a pass."""
        root = self.tmp / "c"
        gen.generate(root, gen.PROFILES["small"], seed=20260919)
        result = wf.run_workflow(root, mode="optimized")
        unknown = [r for r in result.coverage if r["cell_state"] == "UNKNOWN"]
        self.assertEqual(len(unknown), 1)
        cell = unknown[0]
        for field in ("evidence_count", "strength_count", "gap_count", "unknown_count"):
            self.assertEqual(cell[field], "UNKNOWN",
                             f"{field} on an uncovered cell must be UNKNOWN, got {cell[field]!r}")
        self.assertNotIn(0, cell.values())

    def test_export_carries_unknown_through_to_csv_and_json(self):
        root = self.tmp / "c"
        gen.generate(root, gen.PROFILES["small"], seed=20260919)
        result = wf.run_workflow(root, mode="optimized")
        out = self.tmp / "out"
        wf.export_bundle(result, out)
        self.assertIn("UNKNOWN", (out / "coverage-matrix.csv").read_text(encoding="utf-8"))
        payload = json.loads((out / "workflow-result.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["unknown_coverage_cells"], 1)
        self.assertTrue(any(r["cell_state"] == "UNKNOWN" for r in payload["coverage"]))


class TestModesAgree(TempCase):
    def test_small_and_medium_produce_identical_results(self):
        """The whole before/after claim rests on this."""
        for size in ("small", "medium"):
            with self.subTest(size=size):
                root = self.tmp / size
                gen.generate(root, gen.PROFILES[size], seed=20260919)
                base = wf.run_workflow(root, mode="baseline").canonical()
                opt = wf.run_workflow(root, mode="optimized").canonical()
                self.assertEqual(base, opt)

    def test_exported_bytes_are_identical_across_modes(self):
        root = self.tmp / "c"
        gen.generate(root, gen.PROFILES["small"], seed=20260919)
        outs = {}
        for mode in wf.MODES:
            out = self.tmp / f"out-{mode}"
            wf.export_bundle(wf.run_workflow(root, mode=mode), out)
            outs[mode] = {p.name: p.read_bytes() for p in sorted(out.iterdir())}
        self.assertEqual(outs["baseline"], outs["optimized"])

    def test_export_is_deterministic_across_repeat_runs(self):
        root = self.tmp / "c"
        gen.generate(root, gen.PROFILES["small"], seed=20260919)
        result = wf.run_workflow(root, mode="optimized")
        a, b = self.tmp / "a", self.tmp / "b"
        wf.export_bundle(result, a)
        wf.export_bundle(result, b)
        for name in ("coverage-matrix.csv", "workflow-result.json", "workflow-report.md"):
            self.assertEqual((a / name).read_bytes(), (b / name).read_bytes())


class TestHostileStatementIds(TempCase):
    """The nastiest correctness case in this lane.

    The delivered check is a substring test, so `S-001` counts as present when
    the report only ever mentions `S-0012`. That is arguably a bug -- but it is
    the *current answer*, and an optimization is not the place to silently
    change an answer. The optimized path must reproduce it exactly, including
    when reproducing it means agreeing with the weaker behaviour."""

    def test_id_embedded_in_a_longer_token_matches_baseline_exactly(self):
        report = "# SYNTHETIC\n\n[S-0012] a fictional statement that mentions only the longer id.\n"
        ids = {"S-001", "S-0012", "S-999"}
        base = wf.statements_absent_baseline(ids, report)
        opt = wf.statements_absent_optimized(ids, report)
        self.assertEqual(base, opt)
        # Pin the actual behaviour so a future change is a deliberate decision.
        self.assertEqual(base, ["S-999"])
        self.assertNotIn("S-001", base, "baseline substring semantics changed unnoticed")

    def test_ids_adjacent_to_punctuation_and_brackets(self):
        report = "SYNTHETIC (S-002), [S-003]. S-004; S-005/S-006 -- end\n"
        ids = {f"S-{i:03d}" for i in range(1, 8)}
        self.assertEqual(wf.statements_absent_baseline(ids, report),
                         wf.statements_absent_optimized(ids, report))

    def test_unicode_and_multiline_report_text(self):
        report = ("# SYNTHETIC — résumé 中文\n\n"
                  "[S-001] fictional statement ✓ with an em—dash\nand a newline.\n"
                  " [S-002] non-breaking space around the id.\n")
        ids = {"S-001", "S-002", "S-003"}
        self.assertEqual(wf.statements_absent_baseline(ids, report),
                         wf.statements_absent_optimized(ids, report))
        self.assertEqual(wf.statements_absent_optimized(ids, report), ["S-003"])

    def test_worst_case_every_statement_absent(self):
        """Degenerate input: nothing matches, so the optimized path falls all
        the way back to the baseline scan. It must still be correct -- the
        honest cost of that case is stated in the report, not hidden."""
        report = "# SYNTHETIC\n\nA fictional report that cites nothing at all.\n" * 50
        ids = {f"S-{i:04d}" for i in range(1, 201)}
        base = wf.statements_absent_baseline(ids, report)
        opt = wf.statements_absent_optimized(ids, report)
        self.assertEqual(base, opt)
        self.assertEqual(len(opt), 200)

    def test_empty_report_text(self):
        ids = {"S-001"}
        self.assertEqual(wf.statements_absent_baseline(ids, ""),
                         wf.statements_absent_optimized(ids, ""))

    def test_no_statements_at_all(self):
        self.assertEqual(wf.statements_absent_baseline(set(), "SYNTHETIC"), [])
        self.assertEqual(wf.statements_absent_optimized(set(), "SYNTHETIC"), [])


class TestLabelWindowEquivalence(TempCase):
    def test_bounded_read_returns_the_same_window_as_a_full_read(self):
        cases = {
            "tiny.md": "SYNTHETIC\n",
            "short.md": "x" * (wf.LABEL_WINDOW_CHARS - 1),
            "exact.md": "y" * wf.LABEL_WINDOW_CHARS,
            "long.md": "SYNTHETIC header\n" + ("z" * 200_000),
            "unlabelled.md": "no marker here\n" + ("q" * 50_000),
            # Multibyte characters: read_text()[:500] slices CHARACTERS, and so
            # does TextIOWrapper.read(500). If either ever became byte-based the
            # two windows would drift apart and this catches it.
            "unicode.md": ("中文SYNTHETICé—" * 400),
            "empty.md": "",
        }
        for name, body in cases.items():
            p = self.tmp / name
            p.write_text(body, encoding="utf-8")
            with self.subTest(file=name):
                self.assertEqual(wf.read_label_window_baseline(p),
                                 wf.read_label_window_optimized(p))
                self.assertEqual(wf._label_ok(wf.read_label_window_baseline(p)),
                                 wf._label_ok(wf.read_label_window_optimized(p)))

    def test_label_beyond_the_window_is_not_accepted_in_either_mode(self):
        """A label 600 characters down is not "near the top". Both modes must
        agree that this document fails."""
        p = self.tmp / "late.md"
        p.write_text(("a" * 600) + "SYNTHETIC\n", encoding="utf-8")
        self.assertFalse(wf._label_ok(wf.read_label_window_baseline(p)))
        self.assertFalse(wf._label_ok(wf.read_label_window_optimized(p)))


class TestHostileAndMissingInput(TempCase):
    """Missing evidence must fail loudly. It must never become a zero, a pass,
    or a silently shorter result set."""

    def test_missing_manifest_raises_rather_than_passing(self):
        root = self.tmp / "empty"
        root.mkdir()
        with self.assertRaises(wf.WorkflowError) as ctx:
            wf.run_workflow(root)
        self.assertIn("manifest.json", str(ctx.exception))

    def test_missing_required_table_raises(self):
        root = self.tmp / "c"
        gen.generate(root, gen.PROFILES["small"], seed=1)
        (root / "findings.csv").unlink()
        with self.assertRaises(wf.WorkflowError) as ctx:
            wf.run_workflow(root)
        self.assertIn("findings.csv", str(ctx.exception))

    def test_report_surface_listed_but_missing_raises(self):
        root = self.tmp / "c"
        gen.generate(root, gen.PROFILES["small"], seed=1)
        (root / "final-report.md").unlink()
        with self.assertRaises(wf.WorkflowError) as ctx:
            wf.run_workflow(root)
        self.assertIn("final-report.md", str(ctx.exception))

    def test_totally_empty_tables_do_not_crash_and_report_nothing_false(self):
        """Zero rows is a legitimate (if useless) collection. It must not be
        reported as a clean pass with coverage -- every cell is UNKNOWN."""
        root = minimal_collection(self.tmp / "c", statements=[], report_text="SYNTHETIC\n",
                                  evidence=[], findings=[], recommendations=[])
        for mode in wf.MODES:
            with self.subTest(mode=mode):
                r = wf.run_workflow(root, mode=mode)
                self.assertEqual(r.link_errors, [])
                self.assertEqual(r.statement_errors, [])
                self.assertEqual(r.unknown_cells(), len(r.coverage))
                self.assertTrue(all(c["cell_state"] == "UNKNOWN" for c in r.coverage))

    def test_malformed_id_cells_are_not_silently_dropped(self):
        """Whitespace, stray separators and a genuinely bad id in one cell.
        The real id still resolves; the bad one is reported."""
        root = minimal_collection(
            self.tmp / "c", statements=["S-001"], report_text="SYNTHETIC [S-001]\n",
            findings=[{"finding_id": "F-001", "service": "ESS", "assessment_area": "security",
                       "statement": "SYNTHETIC", "evidence_ids": " E-001 ;; ,E-BOGUS;",
                       "confidence": "supported", "synthetic": "true"}])
        for mode in wf.MODES:
            with self.subTest(mode=mode):
                r = wf.run_workflow(root, mode=mode)
                self.assertEqual(len(r.link_errors), 1)
                self.assertIn("E-BOGUS", r.link_errors[0])

    def test_document_with_unreadable_encoding_does_not_pass_silently(self):
        """A document that is not valid UTF-8 must not be scored as labelled."""
        root = minimal_collection(
            self.tmp / "c", statements=["S-001"], report_text="SYNTHETIC [S-001]\n",
            documents=[{"source_id": "D-001", "path": "documents/D-001.md", "synthetic": True}])
        (root / "documents" / "D-001.md").write_bytes(b"\xff\xfe\x00SYNTHETIC")
        for mode in wf.MODES:
            with self.subTest(mode=mode):
                with self.assertRaises(UnicodeDecodeError):
                    wf.run_workflow(root, mode=mode)

    def test_unknown_mode_is_rejected(self):
        root = self.tmp / "c"
        gen.generate(root, gen.PROFILES["small"], seed=1)
        with self.assertRaises(ValueError):
            wf.run_workflow(root, mode="turbo")


class TestBenchmarkHarness(TempCase):
    def test_environment_records_what_the_numbers_mean(self):
        import benchmark
        env = benchmark.environment()
        for key in ("python_version", "platform", "cpu_count_logical", "timer",
                    "memory_probe", "measured_at_utc"):
            self.assertIn(key, env)
            self.assertNotIn(env[key], ("", None))
        self.assertEqual(env["timer"], "time.perf_counter")

    def test_a_real_small_sweep_produces_real_numbers(self):
        """Runs the harness for one size and checks the outputs are measurements
        -- positive elapsed times, a recorded environment, and matching modes."""
        import benchmark
        res = benchmark.bench_size("small", self.tmp, seed=20260919)
        self.assertTrue(res["outputs_identical_across_modes"])
        for mode in wf.MODES:
            total = res["timings_seconds"][mode]["total"]
            self.assertGreater(total["min"], 0.0)
            self.assertGreaterEqual(total["max"], total["min"])
            self.assertEqual(total["samples"], res["repeats"])
            self.assertGreater(res["memory_peak_bytes"][mode], 0)
        self.assertGreater(res["workflow_findings"]["analyst_followups"], 0)

    def test_harness_refuses_to_publish_when_modes_disagree(self):
        """The correctness gate must actually gate. Monkeypatch the optimized
        statement check into a wrong-but-fast answer and confirm the harness
        aborts rather than reporting a speedup."""
        import benchmark
        original = wf.statements_absent_optimized
        wf.statements_absent_optimized = lambda ids, text: []
        try:
            with self.assertRaises(SystemExit) as ctx:
                benchmark.bench_size("small", self.tmp, seed=20260919)
            self.assertIn("disagree", str(ctx.exception))
        finally:
            wf.statements_absent_optimized = original


class TestPublishedNumbersAreNotStale(unittest.TestCase):
    """The README quotes figures from results/benchmark_results.json.

    Re-running benchmark.py regenerates the results but not the README, so the
    two can drift apart silently -- which is exactly how a benchmark ends up
    publishing a number nobody measured. This test re-derives every headline
    figure from the committed results file and fails if the prose disagrees.
    It caught a real drift during this lane's build.
    """

    HERE = Path(__file__).resolve().parent

    def setUp(self):
        results = self.HERE / "results" / "benchmark_results.json"
        if not results.exists():
            self.skipTest("no committed results yet -- run benchmark.py first")
        self.data = json.loads(results.read_text(encoding="utf-8"))
        self.readme = (self.HERE / "README.md").read_text(encoding="utf-8")

    def assertQuoted(self, text, label):
        self.assertIn(text, self.readme,
                      f"README no longer matches the committed results for {label}. "
                      f"Expected to find: {text!r}. Re-sync the README or re-run benchmark.py.")

    def test_large_stage_figures_match_results(self):
        large = self.data["sizes"]["large"]["timings_seconds"]
        for stage, label in (("statement_presence", "statement-presence stage"),
                             ("document_labels", "document-label stage")):
            b = large["baseline"][stage]["min"]
            o = large["optimized"][stage]["min"]
            with self.subTest(stage=stage):
                self.assertQuoted(f"{b:.6f} s", f"{label} baseline")
                self.assertQuoted(f"{o:.6f} s", f"{label} optimized")
                self.assertQuoted(f"**{b / o:.2f}x**", f"{label} speedup")

    def test_end_to_end_figure_matches_results(self):
        t = self.data["sizes"]["large"]["timings_seconds"]
        b = t["baseline"]["total"]["min"]
        o = t["optimized"]["total"]["min"]
        self.assertQuoted(f"**{b:.4f} s \u2192 {o:.4f} s** ({b / o:.2f}x)", "end-to-end")

    def test_crossover_figure_matches_results(self):
        self.assertQuoted(f"Below **{self.data['crossover']['crossover_statements']} trace statements**",
                          "crossover")

    def test_variant_table_matches_results(self):
        for v in self.data["statement_variants"]["variants"]:
            with self.subTest(variant=v["variant"]):
                self.assertQuoted(f"{v['seconds_min']:.5f} s", v["variant"] + " time")
                self.assertQuoted(f"{v['peak_bytes']:,} bytes peak", v["variant"] + " peak")

    def test_memory_figures_match_results(self):
        mem = self.data["sizes"]["large"]["memory_peak_bytes"]
        self.assertQuoted(f"({mem['baseline']:,} \u2192 {mem['optimized']:,} bytes at large)",
                          "large peak memory")

    def test_workload_sizes_match_results(self):
        w = self.data["sizes"]["large"]["workload"]
        self.assertQuoted(f"{w['trace_rows']:,} statements, {w['report_chars']:,} report characters",
                          "large workload shape")


if __name__ == "__main__":
    unittest.main(verbosity=2)
