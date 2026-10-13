from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("audit_import_provenance.py")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_candidate(root: Path, *, callable_name: str = "agent") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    runtime = root / "titan_runtime.py"
    runtime.write_text(
        "class Features:\n"
        "    def __init__(self, **values): self.values = values\n"
        "class TitanAgent:\n"
        "    def __init__(self, features, funded_module=None):\n"
        "        self.features = features\n"
        "        self.funded_module = funded_module\n"
        "def load(name, path): return None\n",
        encoding="utf-8",
    )
    main = root / "main.py"
    main.write_text(
        "def _new_instance(root, feature_data):\n"
        "    from titan_runtime import Features, TitanAgent\n"
        "    return TitanAgent(Features(**feature_data))\n"
        + ("def agent(observation, configuration): return None\n" if callable_name == "agent" else ""),
        encoding="utf-8",
    )
    config = root / "TITAN-CONFIG.json"
    config.write_text("{}\n", encoding="utf-8")
    manifest = root / "FILES.json"
    manifest.write_text(
        json.dumps(
            {
                "TITAN-CONFIG.json": sha256(config),
                "main.py": sha256(main),
                "titan_runtime.py": sha256(runtime),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return manifest


class ImportProvenanceCustodyTests(unittest.TestCase):
    def run_audit(
        self,
        root: Path,
        manifest: Path,
        *extra: str,
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--candidate-root",
                str(root),
                "--manifest",
                str(manifest),
                *extra,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertTrue(completed.stdout, completed.stderr)
        return completed, json.loads(completed.stdout)

    def test_clean_candidate_passes_and_records_runtime_origin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "candidate"
            manifest = write_candidate(root)
            completed, receipt = self.run_audit(root, manifest)

            self.assertEqual(completed.returncode, 0, receipt)
            self.assertEqual(receipt["verdict"], "PASS")
            runtime = next(item for item in receipt["loaded_modules"] if item["name"] == "titan_runtime")
            self.assertEqual(runtime["manifest_path"], "titan_runtime.py")
            self.assertEqual(runtime["observed_sha256"], sha256(root / "titan_runtime.py"))
            self.assertEqual(receipt["python"]["flags"]["isolated"], 1)
            self.assertEqual(receipt["python"]["flags"]["dont_write_bytecode"], 1)

    def test_identical_preloaded_foreign_tree_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "candidate"
            manifest = write_candidate(root)
            foreign = base / "foreign"
            write_candidate(foreign)

            completed, receipt = self.run_audit(
                root,
                manifest,
                "--preload-root",
                f"titan_runtime={foreign}",
            )

            self.assertEqual(completed.returncode, 1)
            self.assertEqual(receipt["verdict"], "FAIL")
            outside = [
                item
                for item in receipt["violations"]
                if item["code"] == "MODULE_OUTSIDE_ROOT" and item.get("module") == "titan_runtime"
            ]
            self.assertTrue(outside, receipt)
            runtime = next(item for item in receipt["loaded_modules"] if item["name"] == "titan_runtime")
            self.assertEqual(runtime["observed_sha256"], sha256(root / "titan_runtime.py"))
            self.assertEqual(runtime["file"]["lexical_inside_root"], False)

    def test_manifest_mutation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "candidate"
            manifest = write_candidate(root)
            with (root / "titan_runtime.py").open("a", encoding="utf-8") as handle:
                handle.write("MUTATED = True\n")

            completed, receipt = self.run_audit(root, manifest)
            self.assertEqual(completed.returncode, 1)
            self.assertTrue(
                any(item["code"] == "MODULE_HASH_MISMATCH" for item in receipt["violations"]),
                receipt,
            )

    def test_missing_callable_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "candidate"
            manifest = write_candidate(root, callable_name="missing")

            completed, receipt = self.run_audit(root, manifest)
            self.assertEqual(completed.returncode, 1)
            self.assertTrue(
                any(item["code"] == "EXECUTION_ERROR" for item in receipt["violations"]),
                receipt,
            )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_module_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "candidate"
            manifest = write_candidate(root)
            outside = base / "outside_runtime.py"
            outside.write_bytes((root / "titan_runtime.py").read_bytes())
            (root / "titan_runtime.py").unlink()
            try:
                (root / "titan_runtime.py").symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlink creation denied: {exc}")

            completed, receipt = self.run_audit(root, manifest)
            self.assertEqual(completed.returncode, 1)
            codes = {item["code"] for item in receipt["violations"]}
            self.assertTrue({"SYMLINKED_MODULE", "MODULE_PATH_ESCAPE"} & codes, receipt)

    def test_hung_entrypoint_is_killed_by_parent_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "candidate"
            manifest = write_candidate(root)
            main = root / "main.py"
            main.write_text("while True: pass\n", encoding="utf-8")
            values = json.loads(manifest.read_text(encoding="utf-8"))
            values["main.py"] = sha256(main)
            manifest.write_text(json.dumps(values, sort_keys=True), encoding="utf-8")

            completed, receipt = self.run_audit(
                root, manifest, "--timeout-seconds", "0.2"
            )
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(receipt["verdict"], "FAIL")
            self.assertEqual(
                receipt["violations"][0]["code"], "AUDITOR_CHILD_TIMEOUT"
            )

    def test_receipt_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "candidate"
            manifest = write_candidate(root)

            first_completed, first = self.run_audit(root, manifest)
            second_completed, second = self.run_audit(root, manifest)
            self.assertEqual(first_completed.returncode, 0)
            self.assertEqual(second_completed.returncode, 0)
            self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
