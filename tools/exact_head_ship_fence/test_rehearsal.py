"""Consumer checks for the actual CLI and its fictional operator rehearsal."""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from . import cli, fence, rehearsal
from .demo import snapshot


class CaseCatalog(unittest.TestCase):
    def test_all_twenty_cases_use_the_existing_engine(self):
        cases = rehearsal.catalog()
        self.assertEqual(len(cases), 20)
        verdicts = set()
        rejected = 0
        for case in cases:
            with self.subTest(case=case.name):
                before = deepcopy(case.packet)
                if case.verdict is None:
                    with self.assertRaises(fence.EvidenceError):
                        fence.compile_current(case.packet)
                    rejected += 1
                else:
                    report = fence.compile_current(case.packet)
                    self.assertEqual((report["verdict"], report["next_action"]), (case.verdict, case.action))
                    self.assertTrue(fence.verify_current(report, case.packet))
                    self.assertTrue(all(value is False for value in report["authority"].values()))
                    verdicts.add(report["verdict"])
                self.assertEqual(case.packet, before)
        self.assertEqual(rejected, 3)
        self.assertEqual(len(verdicts), 8)

    def test_case_packets_do_not_share_mutable_children(self):
        cases = rehearsal.catalog()
        before = [deepcopy(case.packet) for case in cases[1:]]
        cases[0].packet["checks"][0]["conclusion"] = "FAILURE"
        self.assertEqual([case.packet for case in cases[1:]], before)

    def test_case_ids_are_unique_sorted_and_fixed_repositories_are_fictional(self):
        cases = rehearsal.catalog()
        names = [case.name for case in cases]
        self.assertEqual(names, sorted(set(names)))
        for case in cases:
            self.assertRegex(case.name, r"^[0-9]{2}-[a-z-]+$")
            self.assertEqual(case.packet["repository"], "example/repo")

    def test_empty_policy_is_explained_without_minting_a_check(self):
        case = next(c for c in rehearsal.catalog() if c.name == "16-empty-policy")
        report = fence.compile_current(case.packet)
        self.assertEqual(report["summary"]["required_check_count"], 0)
        self.assertEqual(report["summary"]["current_review_pass_count"], 0)
        self.assertIn("not proof", case.explanation)

    def test_optional_failure_is_retained_in_the_teaching_input(self):
        case = next(c for c in rehearsal.catalog() if c.name == "17-optional-failure")
        self.assertEqual(case.packet["checks"][0]["conclusion"], "FAILURE")
        self.assertFalse(case.packet["check_policy"][0]["required"])
        self.assertEqual(fence.compile_current(case.packet)["verdict"], "READY_TO_MERGE_EVIDENCE")


class NativeConsumer(unittest.TestCase):
    def test_normal_and_optimized_native_reports_have_semantic_parity(self):
        for case in rehearsal.catalog()[:2]:
            with self.subTest(case=case.name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "snapshot.json"
                source.write_bytes(rehearsal.json_bytes(case.packet))
                reports = []
                for flags, name in (([], "normal"), (["-O"], "optimized")):
                    bundle = root / name
                    command = [sys.executable, *flags, "-m", "tools.exact_head_ship_fence"]
                    compiled = subprocess.run(command + ["compile", str(source), str(bundle)], cwd=rehearsal.ROOT, capture_output=True, text=True, timeout=30)
                    self.assertEqual(compiled.returncode, 0, compiled.stderr)
                    verified = subprocess.run(command + ["verify", str(source), str(bundle)], cwd=rehearsal.ROOT, capture_output=True, text=True, timeout=30)
                    self.assertEqual((verified.returncode, verified.stdout.strip()), (0, "VERIFIED"), verified.stderr)
                    report = json.loads((bundle / "report.json").read_bytes())
                    report.pop("evaluated_at")
                    report.pop("receipt_sha256")
                    reports.append(report)
                self.assertEqual(reports[0], reports[1])

    def test_native_command_propagates_real_optimization_level(self):
        result = subprocess.CompletedProcess([], 0, "x", "")
        with patch.object(rehearsal.subprocess, "run", return_value=result) as run:
            rehearsal.native_command("compile", Path("a"), Path("b"))
        argv = run.call_args.args[0]
        expected = ["-" + "O" * sys.flags.optimize] if sys.flags.optimize else []
        self.assertEqual(argv[1:1 + len(expected)], expected)
        self.assertIn("tools.exact_head_ship_fence", argv)
        self.assertEqual(run.call_args.kwargs["cwd"], rehearsal.ROOT)
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_subset_run_binds_actual_files_and_preserves_hold(self):
        cases = rehearsal.catalog()
        selected = [cases[1], cases[17]]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "rehearsal"
            with patch.object(rehearsal, "catalog", return_value=selected):
                complete = rehearsal.run(output)
            self.assertEqual(complete["case_count"], 2)
            self.assertTrue(complete["synthetic"])
            for name, expected in complete["files"].items():
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), expected)
            capture = json.loads((output / "RUN.json").read_bytes())
            self.assertEqual(capture["cases"][0]["report"]["verdict"], "HOLD_CI_UNKNOWN")
            self.assertEqual(capture["cases"][0]["verify"]["returncode"], 0)
            self.assertIsNone(capture["cases"][1]["report"])
            self.assertFalse((output / selected[1].name / "bundle").exists())
            text = (output / "REHEARSAL.md").read_text()
            self.assertIn("INPUT_REJECTED", text)
            self.assertIn("Neither means permission to merge", text)
            self.assertIn("Every repository, commit, job and review", text)
            self.assertEqual(set(complete["source_file_inventory"]), set(rehearsal.SOURCE_FILES))

    def test_existing_output_is_untouched(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            marker = output / "keep.txt"; marker.write_bytes(b"KEEP")
            with self.assertRaises(FileExistsError):
                rehearsal.run(output)
            self.assertEqual(marker.read_bytes(), b"KEEP")
            self.assertEqual(list(output.iterdir()), [marker])

    def test_interrupted_native_run_retains_partial_without_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "partial"
            with patch.object(rehearsal, "native_command", side_effect=RuntimeError("controlled interruption")):
                with self.assertRaisesRegex(RuntimeError, "controlled interruption"):
                    rehearsal.run(output)
            self.assertTrue((output / "01-ready" / "snapshot.json").is_file())
            self.assertFalse((output / "COMPLETE.json").exists())

    def test_unexpected_engine_result_does_not_create_complete(self):
        case = replace(rehearsal.catalog()[0], verdict="HOLD_CI_RED", action="REPAIR_CI")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "wrong-expectation"
            with patch.object(rehearsal, "catalog", return_value=[case]):
                with self.assertRaisesRegex(RuntimeError, "differs from the teaching case"):
                    rehearsal.run(output)
            self.assertFalse((output / "COMPLETE.json").exists())
            self.assertTrue((output / case.name / "bundle" / "report.json").exists())

    def test_changed_source_inventory_does_not_create_complete(self):
        before = rehearsal.source_inventory()
        after = deepcopy(before); after["fence.py"]["sha256"] = "0" * 64
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "source-changed"
            with patch.object(rehearsal, "catalog", return_value=[rehearsal.catalog()[17]]):
                with patch.object(rehearsal, "source_inventory", side_effect=[before, after]):
                    with self.assertRaisesRegex(RuntimeError, "source files changed"):
                        rehearsal.run(output)
            self.assertFalse((output / "COMPLETE.json").exists())

    def test_cli_reports_existing_output_as_domain_error(self):
        with tempfile.TemporaryDirectory() as temporary, redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            result = rehearsal.main([temporary])
        self.assertEqual(result, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertNotIn("Traceback", err.getvalue())


class BundleReadContinuity(unittest.TestCase):
    def prepare(self, root):
        source = root / "snapshot.json"
        data = rehearsal.json_bytes(snapshot())
        source.write_bytes(data)
        bundle = root / "bundle"
        report = cli.compile_current(json.loads(data))
        cli._write_bundle(bundle, report)
        return source, bundle, data

    def verify_after_first_read(self, source, bundle, change):
        read = cli._read_bundle
        calls = 0
        def observed(path):
            nonlocal calls
            result = read(path)
            calls += 1
            if calls == 1:
                change(path)
            return result
        with patch.object(cli, "_read_bundle", side_effect=observed), redirect_stdout(io.StringIO()) as out:
            with self.assertRaises(cli.EvidenceError):
                cli._verify(argparse.Namespace(snapshot=str(source), output_dir=str(bundle)))
        self.assertEqual(out.getvalue(), "")

    def test_same_bytes_in_a_new_report_file_are_not_the_same_generation(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, bundle, data = self.prepare(Path(temporary))
            original = (bundle / "report.json").read_bytes()
            def replace_member(path):
                replacement = path / "replacement.json"
                replacement.write_bytes(original)
                os.replace(replacement, path / "report.json")
            self.verify_after_first_read(source, bundle, replace_member)
            self.assertEqual((bundle / "report.json").read_bytes(), original)
            self.assertEqual(source.read_bytes(), data)

    def test_markdown_change_between_reads_is_rejected_without_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, bundle, data = self.prepare(Path(temporary))
            self.verify_after_first_read(source, bundle, lambda path: (path / "report.md").write_text("NEW REVISION"))
            self.assertEqual((bundle / "report.md").read_text(), "NEW REVISION")
            self.assertEqual(source.read_bytes(), data)

    def test_replacement_directory_is_not_reported_verified(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, bundle, data = self.prepare(root)
            def replace_directory(path):
                os.rename(path, root / "previous-bundle")
                path.mkdir()
                for name in ("report.json", "report.md"):
                    (path / name).write_bytes((root / "previous-bundle" / name).read_bytes())
            self.verify_after_first_read(source, bundle, replace_directory)
            self.assertTrue((root / "previous-bundle" / "report.json").is_file())
            self.assertTrue((bundle / "report.json").is_file())
            self.assertEqual(source.read_bytes(), data)


if __name__ == "__main__":
    unittest.main()
