from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from kaggle.hermetic import (
    ExecutionPolicy,
    HermeticError,
    _read_regular_no_symlink,
    run_hermetic,
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
        rows.append({"path": rel, "sha256": sha256(data).hexdigest(), "bytes": len(data), "findings": []})
    manifest = {
        "schema": "arc3-sage-offline-source-manifest/v1",
        "files": rows,
        "network_or_secret_findings": [],
    }
    manifest["manifest_sha256"] = _canonical_sha(manifest)
    (bundle / "source_manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return bundle


def _policy() -> ExecutionPolicy:
    return ExecutionPolicy(
        timeout_seconds=2.0,
        competition_runtime_seconds=32400.0,
        runtime_margin_fraction=0.80,
        max_output_bytes=64 * 1024,
        poll_interval_seconds=0.005,
        terminate_grace_seconds=0.10,
    )


class SourceCustodyTests(unittest.TestCase):
    @unittest.skipUnless(
        hasattr(os, "symlink")
        and os.open in getattr(os, "supports_dir_fd", set())
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW"),
        "descriptor-safe symlink traversal unavailable",
    )
    def test_parent_symlink_swap_cannot_redirect_verified_read(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = _bundle(root, {"pkg/main.py": "print('trusted')\n"})
            src = bundle / "src"
            pkg = src / "pkg"
            moved = src / "pkg-original"
            external = root / "external"
            external.mkdir()
            (external / "main.py").write_text("print('evil')\n", encoding="utf-8")
            real_open = os.open
            swapped = False

            def adversarial_open(path, flags, *args, **kwargs):
                nonlocal swapped
                if path == "pkg" and kwargs.get("dir_fd") is not None and not swapped:
                    pkg.rename(moved)
                    pkg.symlink_to(external, target_is_directory=True)
                    swapped = True
                return real_open(path, flags, *args, **kwargs)

            with patch("kaggle.hermetic.os.open", side_effect=adversarial_open) as mocked_open:
                with patch("kaggle.hermetic.os.supports_dir_fd", {mocked_open}):
                    with self.assertRaisesRegex(HermeticError, "manifest parent"):
                        _read_regular_no_symlink(src, PurePosixPath("pkg/main.py"))
            self.assertTrue(swapped)

    def test_live_bundle_mutation_after_verification_cannot_change_executed_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bundle = _bundle(Path(td), {"main.py": "print('VERIFIED')\n"})
            live = bundle / "src" / "main.py"
            real_popen = subprocess.Popen
            mutated = False

            def mutate_then_spawn(*args, **kwargs):
                nonlocal mutated
                if not mutated:
                    live.write_text("print('MUTATED')\n", encoding="utf-8")
                    mutated = True
                return real_popen(*args, **kwargs)

            with patch("kaggle.hermetic.subprocess.Popen", side_effect=mutate_then_spawn):
                receipt = run_hermetic(bundle, entrypoint="main.py", policy=_policy())
            self.assertTrue(mutated)
            self.assertEqual(receipt.returncode, 0)
            self.assertEqual(receipt.stdout_sha256, sha256(b"VERIFIED\n").hexdigest())
            self.assertFalse(receipt.source_unchanged_after_execution)
            self.assertIn("SOURCE_MUTATED_DURING_EXECUTION", receipt.blockers)
            self.assertEqual(receipt.state, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
