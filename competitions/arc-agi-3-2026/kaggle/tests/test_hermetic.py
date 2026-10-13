from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kaggle.hermetic import (
    ExecutionPolicy,
    HermeticError,
    dependency_closure,
    receipt_json,
    require_closed_dependencies,
    run_hermetic,
    verify_receipt,
)


def _canonical_sha(obj: object) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return sha256(raw).hexdigest()


def _bundle(root: Path, files: dict[str, str]) -> Path:
    bundle = root / "bundle"
    src = bundle / "src"
    src.mkdir(parents=True)
    rows = []
    for rel, text in sorted(files.items()):
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        data = text.encode()
        path.write_bytes(data)
        rows.append({
            "path": rel,
            "sha256": sha256(data).hexdigest(),
            "bytes": len(data),
            "findings": [],
        })
    manifest = {
        "schema": "arc3-sage-offline-source-manifest/v1",
        "files": rows,
        "network_or_secret_findings": [],
    }
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    (bundle / "source_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return bundle


def _policy(**kwargs: object) -> ExecutionPolicy:
    values: dict[str, object] = {
        "timeout_seconds": 2.0,
        "competition_runtime_seconds": 32400.0,
        "runtime_margin_fraction": 0.80,
        "max_output_bytes": 64 * 1024,
        "poll_interval_seconds": 0.005,
        "terminate_grace_seconds": 0.10,
    }
    values.update(kwargs)
    return ExecutionPolicy(**values)  # type: ignore[arg-type]


class DependencyClosureTests(unittest.TestCase):
    def test_accepts_local_and_stdlib_imports(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {
                "main.py": "import json\nfrom pkg import helper\nprint(json.dumps(helper.VALUE))\n",
                "pkg/__init__.py": "from .helper import VALUE\n",
                "pkg/helper.py": "VALUE = 7\n",
            })
            closure = dependency_closure(bundle)
            self.assertEqual(closure["undeclared_imports"], [])
            self.assertEqual(closure["dynamic_import_sites"], [])
            self.assertIn("json", closure["stdlib_imports"])
            self.assertIn("pkg", closure["local_imports"])
            require_closed_dependencies(closure)

    def test_rejects_undeclared_third_party_import(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {"main.py": "import imaginary_arc3_vendor_sdk\n"})
            closure = dependency_closure(bundle)
            self.assertEqual(closure["undeclared_imports"], ["imaginary_arc3_vendor_sdk"])
            with self.assertRaisesRegex(HermeticError, "undeclared third-party"):
                require_closed_dependencies(closure)

    def test_rejects_dynamic_import(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {"main.py": "name='json'\nmod=__import__(name)\n"})
            closure = dependency_closure(bundle)
            self.assertTrue(closure["dynamic_import_sites"])
            with self.assertRaisesRegex(HermeticError, "dynamic imports"):
                require_closed_dependencies(closure)

    def test_rejects_aliased_builtin_import_capability(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {
                "main.py": "from builtins import __import__ as load\nnative=load('ctypes')\n",
            })
            closure = dependency_closure(bundle)
            self.assertTrue(closure["dynamic_import_sites"])
            with self.assertRaisesRegex(HermeticError, "dynamic imports"):
                require_closed_dependencies(closure)

    def test_rejects_builtins_module_importer_alias(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {
                "main.py": "import builtins as b\nnative=b.__import__('ctypes')\n",
            })
            closure = dependency_closure(bundle)
            self.assertTrue(closure["dynamic_import_sites"])
            with self.assertRaisesRegex(HermeticError, "dynamic imports"):
                require_closed_dependencies(closure)

    def test_rejects_dunder_builtins_importer_access(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {
                "main.py": "native=__builtins__['__import__']('ctypes')\n",
            })
            closure = dependency_closure(bundle)
            self.assertTrue(closure["dynamic_import_sites"])
            with self.assertRaisesRegex(HermeticError, "dynamic imports"):
                require_closed_dependencies(closure)

    def test_rejects_reflective_builtins_importer_access(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {
                "main.py": "import builtins as b\nload=getattr(b, '__import__')\nload('ctypes')\n",
            })
            closure = dependency_closure(bundle)
            self.assertTrue(closure["dynamic_import_sites"])
            with self.assertRaisesRegex(HermeticError, "dynamic imports"):
                require_closed_dependencies(closure)

    def test_safe_selective_builtins_import_remains_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {
                "main.py": "from builtins import len as builtin_len\nprint(builtin_len([1,2]))\n",
            })
            closure = dependency_closure(bundle)
            self.assertEqual(closure["dynamic_import_sites"], [])
            self.assertEqual(closure["runtime_escape_imports"], [])
            require_closed_dependencies(closure)

    def test_rejects_source_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {"main.py": "print('ok')\n"})
            (bundle / "src" / "main.py").write_text("print('changed')\n", encoding="utf-8")
            with self.assertRaisesRegex(HermeticError, "source byte mismatch"):
                dependency_closure(bundle)

    def test_rejects_unmanifested_source_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {"main.py": "print('ok')\n"})
            (bundle / "src" / "shadow.py").write_text("VALUE=1\n", encoding="utf-8")
            with self.assertRaisesRegex(HermeticError, "inventory mismatch"):
                dependency_closure(bundle)

    def test_rejects_importlib_alias_capability(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {"main.py": "import importlib as il\nil.import_module('json')\n"})
            closure = dependency_closure(bundle)
            self.assertTrue(closure["dynamic_import_sites"])
            with self.assertRaisesRegex(HermeticError, "dynamic imports"):
                require_closed_dependencies(closure)

    def test_rejects_ctypes_runtime_escape_capability(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {"main.py": "import ctypes\nprint(ctypes.sizeof(ctypes.c_int))\n"})
            closure = dependency_closure(bundle)
            self.assertTrue(closure["runtime_escape_imports"])
            with self.assertRaisesRegex(HermeticError, "runtime escape imports"):
                require_closed_dependencies(closure)

    def test_rejects_low_level_ctypes_runtime_escape_capability(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {"main.py": "import _ctypes\nprint(_ctypes.__name__)\n"})
            closure = dependency_closure(bundle)
            self.assertTrue(closure["runtime_escape_imports"])
            with self.assertRaisesRegex(HermeticError, "runtime escape imports"):
                require_closed_dependencies(closure)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_rejects_symlinked_manifest_source(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = _bundle(root, {"main.py": "print('ok')\n"})
            target = root / "outside.py"
            target.write_text("print('ok')\n", encoding="utf-8")
            path = bundle / "src" / "main.py"
            path.unlink()
            path.symlink_to(target)
            with self.assertRaisesRegex(HermeticError, "safely open"):
                dependency_closure(bundle)


class HermeticExecutionTests(unittest.TestCase):
    def test_success_receipt_and_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {"main.py": "import json\nprint(json.dumps({'ok': True}, sort_keys=True))\n"})
            receipt = run_hermetic(bundle, entrypoint="main.py", policy=_policy())
            self.assertEqual(receipt.state, "HERMETIC_RUNTIME_CONFORMANT")
            self.assertEqual(receipt.returncode, 0)
            self.assertFalse(receipt.timed_out)
            self.assertFalse(receipt.output_limit_exceeded)
            self.assertTrue(receipt.source_unchanged_after_execution)
            self.assertFalse(receipt.authority["kaggle_submit"])
            as_map = asdict(receipt)
            verify_receipt(as_map)
            self.assertIn('"execution_identity_sha256"', receipt_json(receipt))

    def test_audit_hook_denies_socket(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {
                "main.py": "import socket\nsocket.socket()\nprint('unreachable')\n",
            })
            receipt = run_hermetic(bundle, entrypoint="main.py", policy=_policy())
            self.assertEqual(receipt.state, "BLOCKED")
            self.assertNotEqual(receipt.returncode, 0)
            self.assertIn("NONZERO_EXIT", receipt.blockers)

    def test_audit_hook_denies_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {
                "main.py": "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'print(1)'])\n",
            })
            receipt = run_hermetic(bundle, entrypoint="main.py", policy=_policy())
            self.assertEqual(receipt.state, "BLOCKED")
            self.assertNotEqual(receipt.returncode, 0)

    def test_audit_hook_denies_ctypes_dlopen_defense_in_depth(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {
                "main.py": "import ctypes\nctypes.CDLL(None)\nprint('unreachable')\n",
            })
            with patch("kaggle.hermetic.require_closed_dependencies", lambda closure: None):
                receipt = run_hermetic(bundle, entrypoint="main.py", policy=_policy())
            self.assertEqual(receipt.state, "BLOCKED")
            self.assertNotEqual(receipt.returncode, 0)
            self.assertIn("NONZERO_EXIT", receipt.blockers)

    def test_parent_environment_is_not_inherited(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {
                "main.py": "import os\nprint(os.environ.get('ARC3_SECRET_MARKER'))\n",
            })
            prior = os.environ.get("ARC3_SECRET_MARKER")
            os.environ["ARC3_SECRET_MARKER"] = "do-not-inherit"
            try:
                receipt = run_hermetic(bundle, entrypoint="main.py", policy=_policy())
            finally:
                if prior is None:
                    os.environ.pop("ARC3_SECRET_MARKER", None)
                else:
                    os.environ["ARC3_SECRET_MARKER"] = prior
            self.assertEqual(receipt.returncode, 0)
            self.assertEqual(receipt.stdout_sha256, sha256(b"None\n").hexdigest())

    def test_timeout_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {"main.py": "import time\ntime.sleep(5)\n"})
            receipt = run_hermetic(bundle, entrypoint="main.py", policy=_policy(timeout_seconds=0.05))
            self.assertTrue(receipt.timed_out)
            self.assertIn("LOCAL_TIMEOUT", receipt.blockers)
            self.assertEqual(receipt.state, "BLOCKED")

    def test_output_limit_fails_closed_without_unbounded_capture(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {"main.py": "print('x' * 200000)\n"})
            receipt = run_hermetic(bundle, entrypoint="main.py", policy=_policy(max_output_bytes=1024))
            self.assertTrue(receipt.output_limit_exceeded)
            self.assertGreater(receipt.stdout_bytes, 1024)
            self.assertIn("OUTPUT_LIMIT_EXCEEDED", receipt.blockers)
            self.assertEqual(receipt.state, "BLOCKED")

    def test_source_mutation_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {
                "main.py": "from pathlib import Path\np=Path(__file__)\np.write_text(p.read_text()+'#mutated\\n')\n",
            })
            receipt = run_hermetic(bundle, entrypoint="main.py", policy=_policy())
            self.assertFalse(receipt.source_unchanged_after_execution)
            self.assertIn("SOURCE_MUTATED_DURING_EXECUTION", receipt.blockers)
            self.assertEqual(receipt.state, "BLOCKED")

    @unittest.skipUnless(Path("/proc").is_dir(), "Linux /proc required")
    def test_rss_measurement_is_per_run_not_cumulative_children_max(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            heavy = _bundle(root / "heavy", {
                "main.py": (
                    "import time\n"
                    "buf=bytearray(64*1024*1024)\n"
                    "for i in range(0, len(buf), 4096): buf[i]=1\n"
                    "time.sleep(0.15)\n"
                ),
            })
            light = _bundle(root / "light", {"main.py": "import time\ntime.sleep(0.15)\n"})
            first = run_hermetic(heavy, entrypoint="main.py", policy=_policy())
            second = run_hermetic(light, entrypoint="main.py", policy=_policy())
            self.assertEqual(first.rss_measurement, "LINUX_PROC_PROCESS_TREE")
            self.assertEqual(second.rss_measurement, "LINUX_PROC_PROCESS_TREE")
            self.assertIsNotNone(first.peak_process_tree_rss_mib)
            self.assertIsNotNone(second.peak_process_tree_rss_mib)
            assert first.peak_process_tree_rss_mib is not None
            assert second.peak_process_tree_rss_mib is not None
            self.assertGreater(first.peak_process_tree_rss_mib, second.peak_process_tree_rss_mib + 30.0)

    def test_declared_memory_limit_is_enforced_but_never_invented(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {"main.py": "import time\ntime.sleep(0.05)\n"})
            receipt = run_hermetic(
                bundle,
                entrypoint="main.py",
                policy=_policy(memory_limit_mib=1.0, runtime_margin_fraction=0.8),
            )
            if receipt.peak_process_tree_rss_mib is None:
                self.assertIn("MEMORY_MEASUREMENT_UNAVAILABLE", receipt.blockers)
            else:
                self.assertIn("MEMORY_MARGIN_INSUFFICIENT", receipt.blockers)
            self.assertTrue(receipt.authority["declared_memory_limit"])

    def test_receipt_identity_detects_tamper(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {"main.py": "print('ok')\n"})
            receipt = run_hermetic(bundle, entrypoint="main.py", policy=_policy())
            as_map = asdict(receipt)
            as_map["returncode"] = 99
            with self.assertRaisesRegex(HermeticError, "identity hash mismatch"):
                verify_receipt(as_map)
            state_map = asdict(receipt)
            state_map["state"] = "BLOCKED"
            with self.assertRaises(HermeticError):
                verify_receipt(state_map)


class PolicyTests(unittest.TestCase):
    def test_policy_rejects_nonsense(self) -> None:
        for kwargs in (
            {"timeout_seconds": 0.0},
            {"timeout_seconds": float("nan")},
            {"timeout_seconds": 1.0, "runtime_margin_fraction": 1.0},
            {"timeout_seconds": 1.0, "memory_limit_mib": float("inf")},
            {"timeout_seconds": 1.0, "max_output_bytes": 0},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(HermeticError):
                    ExecutionPolicy(**kwargs)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
