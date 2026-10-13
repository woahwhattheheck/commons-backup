import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("fresh", HERE / "check_native_freshness.py")
fresh = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fresh)

CORE = {
    "main.py": b"def agent(obs, cfg):\n    return {}\n",
    "titan_runtime.py": b"RUNTIME = 1\n",
    "scheduler.py": b"SCHEDULER = 1\n",
    "frozen_selected.py": b"FROZEN = 1\n",
    "TITAN-CONFIG.json": b'{"consumer":"frozen"}\n',
}
PACKAGE = {
    **CORE,
    "spatial_tempo.py": b"SPATIAL = 1\n",
    "seed_retry.py": b"SEED_RETRY = 1\n",
}
SOURCES = {
    **{name: name for name in PACKAGE if name != "seed_retry.py"},
    "seed_retry.py": "../cloud-committed-seed-retry/seed_retry.py",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


class FreshnessTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        run("git", "init", "-q", cwd=self.root)
        run("git", "config", "user.email", "test@example.invalid", cwd=self.root)
        run("git", "config", "user.name", "test", cwd=self.root)
        self.live = self.root / "revenue/kaggriculture/cloud-execution-lab"
        self.live.mkdir(parents=True)
        for name, data in PACKAGE.items():
            if name == "seed_retry.py":
                path = self.root / "revenue/kaggriculture/cloud-committed-seed-retry/seed_retry.py"
            else:
                path = self.live / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.write_publisher(SOURCES)
        run("git", "add", ".", cwd=self.root)
        run("git", "commit", "-qm", "base", cwd=self.root)
        self.commit = run("git", "rev-parse", "HEAD", cwd=self.root)

    def tearDown(self):
        self.td.cleanup()

    def write_publisher(self, mapping, *, target=None):
        literal = repr(dict(mapping))
        target = self.live if target is None else Path(target)
        target.mkdir(parents=True, exist_ok=True)
        (target / "build_integrated.py").write_text(
            "from pathlib import Path\n"
            "ROOT=Path(__file__).resolve().parent\n"
            "RUNTIME=[]\n"
            "def source_files():\n"
            f"    return {literal}\n",
            encoding="utf-8",
        )

    def archive(
        self,
        members=None,
        *,
        duplicate=None,
        symlink=None,
        source_paths=None,
        declared_members=None,
        extra_unmapped=None,
    ):
        members = dict(PACKAGE if members is None else members)
        source_paths = dict(SOURCES if source_paths is None else source_paths)
        declared = dict(members if declared_members is None else declared_members)
        runtime = {
            name: {
                "source_path": source_paths[name],
                "sha256": sha256(data),
                "bytes": len(data),
            }
            for name, data in declared.items()
        }
        source = (json.dumps({"runtime": runtime}, sort_keys=True) + "\n").encode()
        path = self.root / "candidate.tar.gz"
        with tarfile.open(path, "w:gz") as tf:
            for name, data in members.items():
                if name == symlink:
                    continue
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
            for name, data in (extra_unmapped or {}).items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
            if duplicate:
                data = members[duplicate]
                info = tarfile.TarInfo(duplicate)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
            if symlink:
                info = tarfile.TarInfo(symlink)
                info.type = tarfile.SYMTYPE
                info.linkname = "main.py"
                tf.addfile(info)
            info = tarfile.TarInfo("SOURCE.json")
            info.size = len(source)
            tf.addfile(info, io.BytesIO(source))
        return path, sha256(path.read_bytes())

    def verify(self, archive, digest, commit=None, live_dir=None):
        return fresh.verify_freshness(
            repo_root=self.root,
            live_dir=fresh.CANONICAL_LIVE_DIR if live_dir is None else live_dir,
            archive=archive,
            expected_archive_sha256=digest,
            expected_commit=commit or self.commit,
        )

    def test_current_exact_publisher_map(self):
        archive, digest = self.archive()
        report = self.verify(archive, digest)
        self.assertEqual("CURRENT", report["verdict"])
        self.assertEqual([], report["stale_paths"])
        self.assertEqual(len(PACKAGE), report["publisher_members"])
        self.assertTrue(all(row["same"] for row in report["files"]))
        seed = next(row for row in report["files"] if row["path"] == "seed_retry.py")
        self.assertEqual("../cloud-committed-seed-retry/seed_retry.py", seed["source_path"])

    def test_stale_runtime_only(self):
        old = dict(PACKAGE)
        old["titan_runtime.py"] = b"RUNTIME = 0\n"
        archive, digest = self.archive(old)
        report = self.verify(archive, digest)
        self.assertEqual("STALE", report["verdict"])
        self.assertEqual(["titan_runtime.py"], report["stale_paths"])
        row = next(r for r in report["files"] if r["path"] == "titan_runtime.py")
        self.assertNotEqual(row["live"]["git_blob"], row["package"]["git_blob"])

    def test_stale_source_mapped_helper_cannot_false_current(self):
        old = dict(PACKAGE)
        old["spatial_tempo.py"] = b"SPATIAL = 0\n"
        archive, digest = self.archive(old)
        report = self.verify(archive, digest)
        self.assertEqual("STALE", report["verdict"])
        self.assertEqual(["spatial_tempo.py"], report["stale_paths"])
        self.assertNotIn("spatial_tempo.py", fresh.CORE_PATHS)

    def test_wrong_authenticated_digest_invalid(self):
        archive, _ = self.archive()
        report = self.verify(archive, "0" * 64)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("archive sha256", report["problems"][0])

    def test_expected_commit_drift_invalid(self):
        archive, digest = self.archive()
        report = self.verify(archive, digest, commit="0" * 40)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("checkout HEAD drift", report["problems"][0])

    def test_midrun_head_move_with_changed_core_cannot_rebind_expected_commit(self):
        moved_package = dict(PACKAGE)
        moved_package["titan_runtime.py"] = b"RUNTIME = 2\n"
        archive, digest = self.archive(moved_package)
        (self.live / "titan_runtime.py").write_bytes(moved_package["titan_runtime.py"])
        run(
            "git",
            "add",
            "revenue/kaggriculture/cloud-execution-lab/titan_runtime.py",
            cwd=self.root,
        )
        run("git", "commit", "-qm", "moved core", cwd=self.root)
        moved_commit = run("git", "rev-parse", "HEAD", cwd=self.root)
        run("git", "reset", "--hard", self.commit, cwd=self.root)

        original = fresh._read_archive_core

        def move_head_after_archive(*args, **kwargs):
            result = original(*args, **kwargs)
            run("git", "reset", "--hard", moved_commit, cwd=self.root)
            return result

        fresh._read_archive_core = move_head_after_archive
        try:
            report = self.verify(archive, digest)
        finally:
            fresh._read_archive_core = original

        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("not byte-identical to expected commit", report["problems"][0])

    def test_midrun_head_move_with_identical_package_invalid(self):
        archive, digest = self.archive()
        marker = self.root / "UNRELATED.txt"
        marker.write_text("different commit, same production package\n", encoding="utf-8")
        run("git", "add", "UNRELATED.txt", cwd=self.root)
        run("git", "commit", "-qm", "unrelated commit", cwd=self.root)
        moved_commit = run("git", "rev-parse", "HEAD", cwd=self.root)
        run("git", "reset", "--hard", self.commit, cwd=self.root)

        original = fresh._read_archive_core

        def move_head_after_archive(*args, **kwargs):
            result = original(*args, **kwargs)
            run("git", "reset", "--hard", moved_commit, cwd=self.root)
            return result

        fresh._read_archive_core = move_head_after_archive
        try:
            report = self.verify(archive, digest)
        finally:
            fresh._read_archive_core = original

        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("HEAD changed during verification", report["problems"][0])

    def test_midrun_worktree_mutation_after_first_pass_invalid(self):
        archive, digest = self.archive()
        original = fresh._publisher_source_map
        calls = 0

        def mutate_before_terminal_reread(*args, **kwargs):
            nonlocal calls
            result = original(*args, **kwargs)
            calls += 1
            if calls == 2:
                (self.live / "scheduler.py").write_bytes(b"DIRTY AFTER SNAPSHOT\n")
            return result

        fresh._publisher_source_map = mutate_before_terminal_reread
        try:
            report = self.verify(archive, digest)
        finally:
            fresh._publisher_source_map = original

        self.assertEqual(2, calls)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("live file changed during verification", report["problems"][0])

    def test_noncanonical_live_dir_decoy_invalid(self):
        decoy = self.root / "revenue/kaggriculture/tracked-decoy"
        for name, data in PACKAGE.items():
            if name == "seed_retry.py":
                continue
            path = decoy / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.write_publisher(SOURCES, target=decoy)
        run("git", "add", ".", cwd=self.root)
        run("git", "commit", "-qm", "tracked decoy", cwd=self.root)

        (self.live / "titan_runtime.py").write_bytes(b"RUNTIME = 2\n")
        run("git", "add", ".", cwd=self.root)
        run("git", "commit", "-qm", "canonical newer", cwd=self.root)
        self.commit = run("git", "rev-parse", "HEAD", cwd=self.root)

        archive, digest = self.archive()
        report = self.verify(
            archive,
            digest,
            live_dir="revenue/kaggriculture/tracked-decoy",
        )
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("must be canonical", report["problems"][0])

    def test_dirty_live_file_invalid(self):
        archive, digest = self.archive()
        (self.live / "scheduler.py").write_bytes(b"DIRTY\n")
        report = self.verify(archive, digest)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("not byte-identical to expected commit", report["problems"][0])

    def test_dirty_publisher_invalid(self):
        archive, digest = self.archive()
        (self.live / "build_integrated.py").write_text("RUNTIME=[]\ndef source_files(): return {}\n")
        report = self.verify(archive, digest)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("publisher is not byte-identical", report["problems"][0])

    def test_side_effecting_publisher_contract_rejected_before_execution(self):
        archive, digest = self.archive()
        pwn = self.live / "PWNED"
        (self.live / "build_integrated.py").write_text(
            "from pathlib import Path\n"
            "ROOT=Path(__file__).resolve().parent\n"
            "RUNTIME=[]\n"
            "def source_files():\n"
            "    ROOT.joinpath('PWNED').write_text('bad')\n"
            f"    return {repr(dict(SOURCES))}\n",
            encoding="utf-8",
        )
        run("git", "add", "revenue/kaggriculture/cloud-execution-lab/build_integrated.py", cwd=self.root)
        run("git", "commit", "-qm", "side-effecting publisher", cwd=self.root)
        bad_commit = run("git", "rev-parse", "HEAD", cwd=self.root)
        report = self.verify(archive, digest, commit=bad_commit)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("may not execute expression statements", report["problems"][0])
        self.assertFalse(pwn.exists())

    def test_str_alias_side_effect_bypass_rejected_before_execution(self):
        archive, digest = self.archive()
        sentinel = self.live / "sentinel"
        sentinel.write_text("keep me\n", encoding="utf-8")
        (self.live / "build_integrated.py").write_text(
            "from pathlib import Path\n"
            "ROOT=Path(__file__).resolve().parent\n"
            "RUNTIME=[]\n"
            "def source_files():\n"
            "    str=(ROOT/'sentinel').unlink\n"
            "    str()\n"
            f"    return {repr(dict(SOURCES))}\n",
            encoding="utf-8",
        )
        run("git", "add", ".", cwd=self.root)
        run("git", "commit", "-qm", "alias side effect publisher", cwd=self.root)
        bad_commit = run("git", "rev-parse", "HEAD", cwd=self.root)
        report = self.verify(archive, digest, commit=bad_commit)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("unsafe attribute read", report["problems"][0])
        self.assertTrue(sentinel.exists())
        self.assertEqual("keep me\n", sentinel.read_text(encoding="utf-8"))

    def test_structural_interpreter_supports_canonical_publisher_grammar(self):
        reference = self.live / "reference/titan-current/demo.py"
        reference.parent.mkdir(parents=True, exist_ok=True)
        reference.write_bytes(b"DEMO=1\n")
        publisher = (
            "from pathlib import Path\n"
            "ROOT=Path(__file__).resolve().parent\n"
            "RUNTIME=['main.py','titan_runtime.py','scheduler.py','frozen_selected.py',"
            "'TITAN-CONFIG.json',*['reference/static/'+f for f in ['a.py']]]\n"
            "def source_files():\n"
            "    mapping={p:p for p in RUNTIME if p not in ('never.py',)}\n"
            "    mapping['spatial_tempo.py']='spatial_tempo.py'\n"
            "    mapping['seed_retry.py']='../cloud-committed-seed-retry/seed_retry.py'\n"
            "    for directory in ('reference/titan-current',):\n"
            "        for p in (ROOT/directory).rglob('*'):\n"
            "            if p.is_file() and '__pycache__' not in p.parts:\n"
            "                name=str(p.relative_to(ROOT));mapping[name]=name\n"
            "    for name in ('scheduler.py',):\n"
            "        mapping['checks/'+name]=name\n"
            "    return mapping\n"
        )
        (self.live / "build_integrated.py").write_text(publisher, encoding="utf-8")
        run("git", "add", ".", cwd=self.root)
        run("git", "commit", "-qm", "canonical grammar publisher", cwd=self.root)
        commit = run("git", "rev-parse", "HEAD", cwd=self.root)
        mapping = fresh._publisher_source_map(
            self.root,
            Path(fresh.CANONICAL_LIVE_DIR),
            commit,
        )
        self.assertEqual("reference/titan-current/demo.py", mapping["reference/titan-current/demo.py"])
        self.assertEqual("reference/static/a.py", mapping["reference/static/a.py"])
        self.assertEqual("scheduler.py", mapping["checks/scheduler.py"])
        self.assertEqual("../cloud-committed-seed-retry/seed_retry.py", mapping["seed_retry.py"])

    def test_publisher_rglob_parent_escape_rejected(self):
        archive, digest = self.archive()
        (self.live / "build_integrated.py").write_text(
            "from pathlib import Path\n"
            "ROOT=Path(__file__).resolve().parent\n"
            "RUNTIME=[]\n"
            "def source_files():\n"
            f"    mapping={repr(dict(SOURCES))}\n"
            "    for p in (ROOT/'..').rglob('*'):\n"
            "        mapping[str(p.relative_to(ROOT))]=str(p.relative_to(ROOT))\n"
            "    return mapping\n",
            encoding="utf-8",
        )
        run("git", "add", ".", cwd=self.root)
        run("git", "commit", "-qm", "escaping publisher", cwd=self.root)
        bad_commit = run("git", "rev-parse", "HEAD", cwd=self.root)
        report = self.verify(archive, digest, commit=bad_commit)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("rglob path is not normalized", report["problems"][0])

    def test_missing_publisher_member_invalid(self):
        members = dict(PACKAGE)
        members.pop("scheduler.py")
        archive, digest = self.archive(members)
        report = self.verify(archive, digest)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("missing core member", report["problems"][0])

    def test_source_manifest_remap_invalid(self):
        source_paths = dict(SOURCES)
        source_paths["spatial_tempo.py"] = "scheduler.py"
        archive, digest = self.archive(source_paths=source_paths)
        report = self.verify(archive, digest)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("canonical publisher source map", report["problems"][0])
        self.assertIn("remapped=spatial_tempo.py", report["problems"][0])

    def test_unmapped_archive_member_invalid(self):
        archive, digest = self.archive(extra_unmapped={"rogue.py": b"ROGUE=1\n"})
        report = self.verify(archive, digest)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("archive member set disagrees", report["problems"][0])

    def test_duplicate_member_invalid(self):
        archive, digest = self.archive(duplicate="main.py")
        report = self.verify(archive, digest)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("duplicate archive member", report["problems"][0])

    def test_symlink_source_mapped_member_invalid(self):
        archive, digest = self.archive(symlink="scheduler.py")
        report = self.verify(archive, digest)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("not a regular file", report["problems"][0])

    def test_live_symlink_invalid(self):
        archive, digest = self.archive()
        target = self.live / "scheduler.real"
        target.write_bytes((self.live / "scheduler.py").read_bytes())
        (self.live / "scheduler.py").unlink()
        (self.live / "scheduler.py").symlink_to(target.name)
        report = self.verify(archive, digest)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("symlink live path forbidden", report["problems"][0])

    def test_archive_uncompressed_size_bound_invalid(self):
        archive, digest = self.archive()
        original = fresh.MAX_EXTRACTED_BYTES
        fresh.MAX_EXTRACTED_BYTES = 1
        try:
            report = self.verify(archive, digest)
        finally:
            fresh.MAX_EXTRACTED_BYTES = original
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("uncompressed size", report["problems"][0])

    def test_archive_member_count_bound_invalid(self):
        path = self.root / "candidate.tar.gz"
        with tarfile.open(path, "w:gz") as tf:
            for index in range(fresh.MAX_TAR_MEMBERS + 1):
                info = tarfile.TarInfo(f"junk/{index}")
                info.size = 0
                tf.addfile(info, io.BytesIO(b""))
            info = tarfile.TarInfo("SOURCE.json")
            source = b'{"runtime":{}}\n'
            info.size = len(source)
            tf.addfile(info, io.BytesIO(source))
        report = self.verify(path, sha256(path.read_bytes()))
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("member count", report["problems"][0])

    def test_type_poisoned_digest_and_commit_invalid(self):
        archive, digest = self.archive()
        r1 = self.verify(archive, "ABC")
        self.assertEqual("INVALID", r1["verdict"])
        r2 = fresh.verify_freshness(
            repo_root=self.root,
            live_dir="revenue/kaggriculture/cloud-execution-lab",
            archive=archive,
            expected_archive_sha256=digest,
            expected_commit="not-a-sha",
        )
        self.assertEqual("INVALID", r2["verdict"])


if __name__ == "__main__":
    unittest.main()
