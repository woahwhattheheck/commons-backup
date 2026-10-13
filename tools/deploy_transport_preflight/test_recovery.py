"""Ordinary API/CLI integration regressions retained by VECTOR-91."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import preflight as p
from .demo import run_demo

HERE = Path(__file__).resolve().parent


def inputs(repo="https://example.test/team/sample"):
    return (
        {"schema": p.REQUEST_SCHEMA, "provider": "synthetic-host",
         "source": {"repo": repo, "commit_sha": "1" * 40},
         "target": {"project_id": None}},
        {"schema": p.MANIFEST_SCHEMA, "provider": "synthetic-host", "actions": [
            {"name": "deploy-repo", "kind": "DEPLOY_REPO", "source_binding": "repo_commit"}]},
    )


class RecoveryTests(unittest.TestCase):
    def test_malformed_repository_components_use_domain_error(self):
        for url in ("https://example.test:invalid/team/sample", "https://[broken/team/sample",
                    "https://example.test:99999/team/sample"):
            with self.subTest(url=url), self.assertRaises(p.DomainError):
                p.compile_values(*inputs(url))

    def test_malformed_binding_repository_uses_same_boundary(self):
        req, man = inputs()
        req["target"]["project_id"] = "synthetic-project"
        bind = {"schema": p.BINDING_SCHEMA, "provider": "synthetic-host",
                "project_id": "synthetic-project", "source": {
                    "repo": "https://example.test:invalid/team/sample", "commit_sha": "1" * 40}}
        with self.assertRaises(p.DomainError):
            p.compile_values(req, man, bind)

    def test_floats_have_same_direct_and_text_contract(self):
        for value in (0.0, 1.25, float("inf"), float("nan")):
            with self.subTest(value=value), self.assertRaises(p.DomainError):
                p.canonical_bytes({"value": value})
        with self.assertRaises(p.DomainError):
            p.strict_loads(b'{"value":1.25}')

    def test_cli_malformed_urls_return_two_in_all_optimization_modes(self):
        for opt in ([], ["-O"], ["-OO"]):
            for url in ("https://example.test:invalid/team/sample", "https://[broken/team/sample"):
                with self.subTest(opt=opt, url=url), tempfile.TemporaryDirectory() as td:
                    root = Path(td)
                    req, man = inputs(url)
                    (root / "request.json").write_bytes(p.canonical_bytes(req))
                    (root / "manifest.json").write_bytes(p.canonical_bytes(man))
                    run = subprocess.run([sys.executable, *opt, str(HERE / "preflight.py"),
                        "compile", "--request", str(root / "request.json"),
                        "--manifest", str(root / "manifest.json"), "--out", str(root / "report.json")],
                        capture_output=True, text=True, timeout=15, check=False)
                    self.assertEqual(run.returncode, 2, run.stderr)
                    self.assertNotIn("Traceback", run.stderr)
                    self.assertEqual(run.stdout, "")
                    self.assertFalse((root / "report.json").exists())

    def test_file_read_is_bounded_before_allocation(self):
        class BoundedReader(io.BytesIO):
            def read(self, size=-1):
                if size != p.MAX_INPUT_BYTES + 1:
                    raise AssertionError("file reader requested unbounded allocation")
                return super().read(size)
        with patch.object(Path, "open", return_value=BoundedReader(b"x" * (p.MAX_INPUT_BYTES + 1))):
            with self.assertRaises(p.DomainError):
                p._read("synthetic-input.json")

    def test_small_file_read_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "small.json"
            source.write_bytes(b'{"example":1}\n')
            self.assertEqual(p._read(str(source)), b'{"example":1}\n')

    def test_missing_or_invalid_paths_are_domain_errors(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(p.DomainError):
                p._read(str(Path(td) / "missing.json"))
        with self.assertRaises(p.DomainError):
            p._read("invalid\x00path")
        with self.assertRaises(p.DomainError):
            p._write_exclusive("invalid\x00path", b"test")

    def test_write_sync_failure_is_reported_and_partial_output_removed(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "report.json"
            with patch.object(p.os, "fsync", side_effect=OSError("synthetic sync failure")):
                with self.assertRaises(p.DomainError):
                    p._write_exclusive(str(target), b"test")
            self.assertFalse(target.exists())

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "keep.json"
            target.write_bytes(b"KEEP ORIGINAL")
            with self.assertRaises(p.DomainError):
                p._write_exclusive(str(target), b"replacement")
            self.assertEqual(target.read_bytes(), b"KEEP ORIGINAL")

    def test_demo_preserves_source_change_semantics(self):
        results = run_demo()
        self.assertEqual(results["evidence_class"], "SYNTHETIC_OFFLINE_REHEARSAL")
        self.assertEqual([r["report"]["status"] for r in results["cases"]],
            [p.HOLD_UNBOUND, p.READY, p.HOLD_UNBOUND, p.READY, p.HOLD_AMBIGUOUS])
        old, stale, new = [results["cases"][i]["report"] for i in (1, 2, 3)]
        self.assertNotEqual(old["request_sha256"], stale["request_sha256"])
        self.assertEqual(old["binding_sha256"], stale["binding_sha256"])
        self.assertNotEqual(stale["binding_sha256"], new["binding_sha256"])
        for row in results["cases"]:
            self.assertTrue(all(v is False for v in row["report"]["external_authority"].values()))

    def test_demo_script_and_package_outputs_identical_under_optimization(self):
        outputs = []
        for opt in ([], ["-O"], ["-OO"]):
            for entry in ([str(HERE / "demo.py")], ["-m", "tools.deploy_transport_preflight.demo"]):
                run = subprocess.run([sys.executable, *opt, *entry], cwd=HERE.parents[1],
                    capture_output=True, timeout=15, check=False)
                self.assertEqual(run.returncode, 0, run.stderr.decode())
                self.assertEqual(run.stderr, b"")
                outputs.append(run.stdout)
        self.assertTrue(all(out == outputs[0] for out in outputs))
        self.assertEqual(len(json.loads(outputs[0])["cases"]), 5)


if __name__ == "__main__":
    unittest.main()
