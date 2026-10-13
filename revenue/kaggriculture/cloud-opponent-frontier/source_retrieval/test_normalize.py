"""Deterministic source extraction checks; no provider access or game execution."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import normalize as subject


def code(text):
    return {"cell_type": "code", "source": text, "outputs": [], "metadata": {}}


def notebook(*cells):
    return {"nbformat": 4, "nbformat_minor": 5, "cells": list(cells), "metadata": {}}


class NormalizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.meta = self.root / "metadata.json"
        self.meta.write_bytes(b'{"metadata":{"currentVersionNumber":7,"license":"Apache-2.0"}}\n')
        self.output = self.root / "package"

    def run_source(self, data, name="source.ipynb", **kwargs):
        src = self.root / name
        src.write_bytes(data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode())
        return subject.normalize(src, self.meta, self.output, **kwargs)

    def assert_no_output(self):
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".source-normalize-*")), [])

    def test_python_exact_bytes_and_no_execution(self):
        marker = self.root / "must-not-exist"
        source = (f"from pathlib import Path\r\nPath({str(marker)!r}).write_text('executed')\r\n"
                  "name='caf\u00e9'\r\n").encode()
        report = self.run_source(source, "source.py")
        self.assertEqual((self.output / "main.py").read_bytes(), source)
        self.assertFalse(marker.exists())
        self.assertFalse(report["execution_performed"])
        self.assertEqual(report["runtime_dependency_completeness"], "UNMEASURED")
        self.assertEqual(report["files"]["main.py"]["sha256"], subject.digest(source))

    def test_writefile_preserves_adjacent_files_and_ignores_other_cells(self):
        nb = notebook(code("!pip install do-not-run\n"),
                      code(["%%writefile main.py\n", "from helper import VALUE\n"]),
                      code("%%writefile helper.py\nVALUE = 4\n"),
                      code("%%writefile assets/data.json\n{\"x\": 1}\n"),
                      {"cell_type": "markdown", "source": "%%writefile wrong.py\n"})
        r = self.run_source(nb)
        self.assertEqual(set(r["files"]), {"main.py", "helper.py", "assets/data.json"})
        self.assertEqual((self.output / "main.py").read_text(), "from helper import VALUE\n")
        self.assertEqual(r["unexecuted_code_cells"], [0])
        self.assertEqual([w["cell"] for w in r["writes"]], [1, 2, 3])

    def test_append_overwrite_follows_notebook_order(self):
        r = self.run_source(notebook(code("%%writefile -a main.py\nfirst = 1\n"),
                                    code("%%writefile --append main.py\nsecond = 2\n"),
                                    code("%%writefile main.py\nreplacement = 3\n"),
                                    code("%%writefile -a main.py\nfinal = 4\n")))
        self.assertEqual((self.output / "main.py").read_bytes(), b"replacement = 3\nfinal = 4\n")
        self.assertEqual([w["operation"] for w in r["writes"]], ["append", "append", "overwrite", "append"])

    def test_explicit_notebook_root(self):
        self.run_source(notebook(code("%%writefile /kaggle/working/main.py\nx=1\n")),
                        notebook_root="/kaggle/working")
        self.assertEqual((self.output / "main.py").read_bytes(), b"x=1\n")

    def test_literal_path_errors(self):
        for path in ("../main.py", "/kaggle/main.py", "provenance/main.py", "${OUT}/main.py",
                     "x\\main.py", ".", "", "x/../main.py"):
            with self.subTest(path=path), self.assertRaises(subject.SourceError):
                subject.local_name(path)
        with self.assertRaises(subject.SourceError):
            subject.local_name("/elsewhere/main.py", "/kaggle/working")

    def test_provider_wrapper_requires_explicit_source_pointer(self):
        obj = {"blob": {"source": json.dumps(notebook(code("%%writefile main.py\nx=7\n")))}}
        with self.assertRaises(subject.SourceError):
            self.run_source(obj)
        self.assert_no_output()
        r = self.run_source(obj, source_pointer="/blob/source")
        self.assertEqual(r["input_kind"], "notebook")
        self.assertEqual((self.output / "main.py").read_bytes(), b"x=7\n")

    def test_wrapped_python_and_escaped_json_pointer(self):
        r = self.run_source({"a/b": {"~": ["x=9\n"]}}, source_pointer="/a~1b/~0/0")
        self.assertEqual(r["input_kind"], "python")
        self.assertEqual((self.output / "main.py").read_bytes(), b"x=9\n")
        self.assertEqual(subject.pointer({"a": 1}, ""), {"a": 1})

    def test_json_pointer_errors(self):
        for value, ptr in (({}, "a"), ({}, "/missing"), ({"x": 1}, "/x/no"),
                           ([1], "/01"), ([1], "/-1"), ([1], "/1"), ({}, "/~2")):
            with self.subTest(ptr=ptr), self.assertRaises(subject.SourceError):
                subject.pointer(value, ptr)

    def test_version_comparison_is_not_url_inference(self):
        r = self.run_source(b"x=1\n", "source.py", source_url="https://example.test/?scriptVersionId=341074820",
                            expected_version="341074820")
        self.assertEqual(r["version"]["comparison"], "MISSING")
        self.assertIsNone(r["version"]["observed"])

    def test_version_match_mismatch_uncompared(self):
        src = self.root / "source.py"; src.write_bytes(b"x=1\n")
        for expected, status in (("7", "MATCH"), ("8", "MISMATCH"), (None, "UNCOMPARED")):
            with self.subTest(expected=expected):
                r = subject.normalize(src, self.meta, self.root / status,
                                      version_pointer="/metadata/currentVersionNumber", expected_version=expected)
                self.assertEqual(r["version"]["comparison"], status)
                self.assertEqual(r["version"]["observed"], 7)

    def test_missing_explicit_pointer_does_not_guess(self):
        with self.assertRaises(subject.SourceError):
            self.run_source(b"x=1\n", "source.py", version_pointer="/version")
        self.assert_no_output()

    def test_license_evidence_is_preserved_exactly(self):
        license = self.root / "LICENSE.txt"; license.write_bytes(b"A test license.\r\n\xff")
        r = self.run_source(b"x=1\n", "source.py", licenses=[license], license_pointer="/metadata/license")
        self.assertEqual(r["license"]["observed"], "Apache-2.0")
        self.assertEqual((self.output / r["license"]["files"][0]["path"]).read_bytes(), license.read_bytes())
        self.assertEqual((self.output / "provenance/METADATA.json").read_bytes(), self.meta.read_bytes())

    def test_no_implicit_notebook_execution(self):
        with self.assertRaises(subject.SourceError):
            self.run_source(notebook(code("from pathlib import Path\nPath('main.py').write_text('x=1')\n")))
        self.assert_no_output()

    def test_explicit_plain_python_cells(self):
        nb = notebook(code("!bad\n"), code("x=1\n"), code("y=x+2\n"))
        r = self.run_source(nb, code_cells=[1, 2])
        self.assertEqual((self.output / "main.py").read_text(), "x=1\n\n\ny=x+2\n")
        self.assertEqual(r["unexecuted_code_cells"], [0])

    def test_invalid_explicit_cell_selections(self):
        nb = notebook(code("!bad"), {"cell_type": "markdown", "source": "x=1"})
        for selection in ([], [0, 0], [False], [-1], [2], [1], [0]):
            with self.subTest(selection=selection), self.assertRaises(subject.SourceError):
                self.run_source(nb, code_cells=selection)
            self.assert_no_output()

    def test_source_structure_errors(self):
        for nb in (notebook(None), {"nbformat": 3, "cells": []}, notebook(code([1])),
                   notebook(code("%%writefiles main.py\nx=1")), notebook(code("%%writefile -x main.py\nx=1"))):
            with self.subTest(nb=nb), self.assertRaises(subject.SourceError):
                self.run_source(nb)
            self.assert_no_output()

    def test_missing_entrypoint_does_not_guess(self):
        with self.assertRaises(subject.SourceError):
            self.run_source(notebook(code("%%writefile agent.py\nx=1")))
        self.assert_no_output()
        self.run_source(notebook(code("%%writefile agent.py\nx=1")), entrypoint="agent.py")
        self.assertTrue((self.output / "agent.py").is_file())

    def test_parse_and_prefix_collision_leave_no_partial_package(self):
        bad = (notebook(code("%%writefile main.py\nnot python 123")),
               notebook(code("%%writefile main.py\nx=1"), code("%%writefile main.py/child\ntext")))
        for nb in bad:
            with self.subTest(nb=nb), self.assertRaises(subject.SourceError):
                self.run_source(nb)
            self.assert_no_output()

    def test_bad_metadata_nonfinite_and_duplicate_keys(self):
        for raw in (b"[]", b"\xff", b"{broken", b'{"x":NaN}', b'{"x":1,"x":2}'):
            self.meta.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(subject.SourceError):
                self.run_source(b"x=1", "source.py")
            self.assert_no_output()

    def test_existing_directory_is_never_modified(self):
        self.output.mkdir(); old = self.output / "keep"; old.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            self.run_source(b"x=1", "source.py")
        self.assertEqual(list(self.output.iterdir()), [old])
        self.assertEqual(old.read_bytes(), b"keep")

    def test_broken_output_symlink_is_never_replaced(self):
        self.output.symlink_to(self.root / "not-present", target_is_directory=True)
        with self.assertRaises(FileExistsError):
            self.run_source(b"x=1", "source.py")
        self.assertTrue(self.output.is_symlink())

    def test_transfer_failure_removes_only_own_partial_output(self):
        with patch.object(subject.os, "rename", side_effect=OSError("synthetic disk failure")):
            with self.assertRaises(OSError):
                self.run_source(b"x=1", "source.py")
        self.assert_no_output()
        self.assertTrue(self.meta.exists())

    def test_manifest_is_reproducible_at_different_destinations(self):
        src = self.root / "source.py"; src.write_bytes(b"x=1\n")
        first = subject.normalize(src, self.meta, self.root / "one")
        second = subject.normalize(src, self.meta, self.root / "two")
        self.assertEqual(first, second)
        self.assertEqual((self.root / "one/provenance/MANIFEST.json").read_bytes(),
                         (self.root / "two/provenance/MANIFEST.json").read_bytes())

    def test_cli_success_and_error(self):
        src = self.root / "source.py"; src.write_bytes(b"x=1\n")
        cmd = [sys.executable, str(Path(subject.__file__)), "--input", str(src),
               "--metadata", str(self.meta), "--output", str(self.output)]
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse(json.loads(run.stdout)["execution_performed"])
        again = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        self.assertEqual(again.returncode, 2)
        self.assertIn("NORMALIZE_ERROR", again.stderr)
        self.assertNotIn("Traceback", again.stderr)


if __name__ == "__main__":
    unittest.main()
