from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.repo_portability import (
    INVENTORY_SCHEMA,
    ValidationError,
    VerificationError,
    canonical_json,
    compile_migration_plan,
    create_snapshot,
    loads_strict,
    verify_snapshot,
    write_migration_plan,
)


def git(cwd: Path, *args: str) -> str:
    p = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env={**os.environ, "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1"},
        check=False,
    )
    if p.returncode:
        raise AssertionError(f"git {args} failed: {p.stderr}")
    return p.stdout


def build_repo(root: Path) -> Path:
    repo = root / "source"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Portability Test")
    git(repo, "config", "user.email", "portability@example.invalid")
    (repo / "alpha.txt").write_text("alpha\n", encoding="utf-8")
    git(repo, "add", "alpha.txt")
    git(repo, "commit", "-m", "alpha")
    git(repo, "tag", "v1")
    git(repo, "checkout", "-b", "feature")
    (repo / "beta.txt").write_text("beta\n", encoding="utf-8")
    git(repo, "add", "beta.txt")
    git(repo, "commit", "-m", "beta")
    git(repo, "checkout", "main")
    return repo


class SnapshotTests(unittest.TestCase):
    def test_snapshot_roundtrip_exact_refs_and_head(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = build_repo(root)
            out = root / "cold"
            manifest = create_snapshot(repo, out, repository_label="demo")
            self.assertEqual(manifest["repository_label"], "demo")
            self.assertEqual(manifest["head"]["mode"], "symbolic")
            self.assertEqual(manifest["head"]["target"], "refs/heads/main")
            refs = {x["name"] for x in manifest["refs"]}
            self.assertIn("refs/heads/main", refs)
            self.assertIn("refs/heads/feature", refs)
            self.assertIn("refs/tags/v1", refs)
            self.assertTrue((out / "repository.bundle").is_file())
            verified = verify_snapshot(out / "repository.bundle", out / "manifest.json")
            self.assertEqual(verified, manifest)
            self.assertEqual((out / "manifest.json").read_bytes(), canonical_json(manifest))
            self.assertEqual(
                manifest["authority"],
                {
                    "delete_source_repo": False,
                    "publish_source_repo": False,
                    "change_visibility": False,
                    "billing_change": False,
                    "push_destination": False,
                },
            )

    def test_bundle_tamper_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = build_repo(root)
            out = root / "cold"
            create_snapshot(repo, out)
            bundle = out / "repository.bundle"
            data = bytearray(bundle.read_bytes())
            data[len(data) // 2] ^= 1
            bundle.write_bytes(bytes(data))
            with self.assertRaises(VerificationError):
                verify_snapshot(bundle, out / "manifest.json")

    def test_manifest_ref_tamper_rejected_even_if_recanonicalized(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = build_repo(root)
            out = root / "cold"
            create_snapshot(repo, out)
            mp = out / "manifest.json"
            manifest = loads_strict(mp.read_bytes())
            manifest["refs"][0]["object_id"] = "0" * len(manifest["refs"][0]["object_id"])
            mp.write_bytes(canonical_json(manifest))
            with self.assertRaises(VerificationError):
                verify_snapshot(out / "repository.bundle", mp)

    def test_noncanonical_manifest_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = build_repo(root)
            out = root / "cold"
            create_snapshot(repo, out)
            mp = out / "manifest.json"
            value = loads_strict(mp.read_bytes())
            mp.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
            with self.assertRaises(VerificationError):
                verify_snapshot(out / "repository.bundle", mp)

    def test_existing_output_refused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = build_repo(root)
            out = root / "cold"
            out.mkdir()
            with self.assertRaises(ValidationError):
                create_snapshot(repo, out)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_symlink_repository_and_bundle_refused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = build_repo(root)
            link = root / "repo-link"
            link.symlink_to(repo, target_is_directory=True)
            with self.assertRaises(ValidationError):
                create_snapshot(link, root / "bad-out")

            out = root / "cold"
            create_snapshot(repo, out)
            bundle_link = root / "bundle-link"
            bundle_link.symlink_to(out / "repository.bundle")
            with self.assertRaises(ValidationError):
                verify_snapshot(bundle_link, out / "manifest.json")

    def test_parent_traversal_output_refused(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = build_repo(root)
            with self.assertRaises(ValidationError):
                create_snapshot(repo, root / "x" / ".." / "cold")


class StrictJsonTests(unittest.TestCase):
    def test_duplicate_keys_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            loads_strict(b'{"a":1,"a":2}')

    def test_float_and_nonfinite_rejected(self) -> None:
        for raw in [b'{"x":1.0}', b'{"x":NaN}', b'{"x":Infinity}']:
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                loads_strict(raw)

    def test_oversized_integer_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            loads_strict(b'{"x":1234567890123456789}')


class PlanTests(unittest.TestCase):
    def inventory(self) -> dict:
        return {
            "schema": INVENTORY_SCHEMA,
            "repositories": [
                {
                    "name": "app",
                    "action": "MIGRATE_PRIVATE",
                    "bundle_path": "/retained/app/repository.bundle",
                    "destination_url": "https://git.example.invalid/team/app.git",
                },
                {"name": "old", "action": "COLD_ARCHIVE", "bundle_path": "/retained/old/repository.bundle"},
                {"name": "secret", "action": "KEEP_PRIVATE"},
                {"name": "candidate", "action": "PUBLIC_REVIEW"},
            ],
        }

    def compile(self, value: dict) -> dict:
        raw = canonical_json(value)
        return loads_strict(compile_migration_plan(raw))

    def test_plan_is_deterministic_non_authorizing_and_argv_only(self) -> None:
        inv = self.inventory()
        raw = canonical_json(inv)
        a = compile_migration_plan(raw)
        b = compile_migration_plan(raw)
        self.assertEqual(a, b)
        plan = loads_strict(a)
        self.assertFalse(any(plan["authority"].values()))
        migrate = plan["repositories"][0]
        self.assertEqual(migrate["state"], "PLAN_REQUIRES_SEPARATE_EXECUTOR_APPROVAL")
        self.assertFalse(migrate["destination_push_authorized"])
        self.assertTrue(all(isinstance(cmd, list) for cmd in migrate["commands"]))
        self.assertEqual(migrate["commands"][-1][-2:], ["--mirror", "destination"])
        public = plan["repositories"][3]
        self.assertEqual(public["state"], "HOLD_PUBLICATION_REVIEW_REQUIRED")
        self.assertFalse(public["publication_authorized"])
        self.assertEqual(public["commands"], [])

    def test_credential_bearing_urls_rejected(self) -> None:
        for bad in [
            "https://user:pass@git.example.invalid/team/app.git",
            "https://token@git.example.invalid/team/app.git",
            "ssh://git@git.example.invalid/team/app.git",
            "https://git.example.invalid/team/app.git?token=secret",
            "https://git.example.invalid/team/app.git#secret",
        ]:
            with self.subTest(bad=bad):
                inv = self.inventory()
                inv["repositories"][0]["destination_url"] = bad
                with self.assertRaises(ValidationError):
                    compile_migration_plan(canonical_json(inv))

    def test_shell_controls_and_parent_traversal_rejected(self) -> None:
        inv = self.inventory()
        inv["repositories"][0]["name"] = "app\nrm"
        with self.assertRaises(ValidationError):
            compile_migration_plan(canonical_json(inv))
        inv = self.inventory()
        inv["repositories"][0]["bundle_path"] = "../secret/repository.bundle"
        with self.assertRaises(ValidationError):
            compile_migration_plan(canonical_json(inv))

    def test_unknown_fields_and_action_shape_rejected(self) -> None:
        inv = self.inventory()
        inv["repositories"][0]["surprise"] = "x"
        with self.assertRaises(ValidationError):
            compile_migration_plan(canonical_json(inv))
        inv = self.inventory()
        inv["repositories"][1]["destination_url"] = "https://git.example.invalid/team/old.git"
        with self.assertRaises(ValidationError):
            compile_migration_plan(canonical_json(inv))
        inv = self.inventory()
        inv["repositories"][2]["action"] = "DELETE"
        with self.assertRaises(ValidationError):
            compile_migration_plan(canonical_json(inv))

    def test_duplicate_repo_names_rejected(self) -> None:
        inv = self.inventory()
        inv["repositories"][1]["name"] = "app"
        with self.assertRaises(ValidationError):
            compile_migration_plan(canonical_json(inv))

    def test_plan_writer_is_create_exclusive_and_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            inv = root / "inventory.json"
            inv.write_bytes(canonical_json(self.inventory()))
            out = root / "plan.json"
            plan = write_migration_plan(inv, out)
            self.assertEqual(out.read_bytes(), canonical_json(plan))
            with self.assertRaises(ValidationError):
                write_migration_plan(inv, out)


class CliTests(unittest.TestCase):
    def test_cli_snapshot_verify_plan(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            repo = build_repo(root)
            snap = root / "snap"
            proc = subprocess.run(
                ["python", "-m", "tools.repo_portability.cli", "snapshot", "--repo", str(repo), "--out", str(snap), "--label", "demo"],
                cwd=str(Path(__file__).resolve().parents[2]),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("SNAPSHOT_VERIFIED", proc.stdout)

            proc = subprocess.run(
                ["python", "-m", "tools.repo_portability.cli", "verify", "--bundle", str(snap / "repository.bundle"), "--manifest", str(snap / "manifest.json")],
                cwd=str(Path(__file__).resolve().parents[2]),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)

            inv = root / "inventory.json"
            inv.write_bytes(canonical_json({"schema": INVENTORY_SCHEMA, "repositories": [{"name": "demo", "action": "KEEP_PRIVATE"}]}))
            plan = root / "plan.json"
            proc = subprocess.run(
                ["python", "-m", "tools.repo_portability.cli", "plan", "--inventory", str(inv), "--out", str(plan)],
                cwd=str(Path(__file__).resolve().parents[2]),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("PLAN_COMPILED_NO_ACTION_EXECUTED", proc.stdout)


if __name__ == "__main__":
    unittest.main()
