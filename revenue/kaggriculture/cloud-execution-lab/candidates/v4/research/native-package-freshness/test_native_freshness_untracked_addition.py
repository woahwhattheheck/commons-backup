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
STATIC = {
    **CORE,
    "spatial_tempo.py": b"SPATIAL = 1\n",
    "seed_retry.py": b"SEED_RETRY = 1\n",
    "reference/titan-current/base.py": b"BASE=1\n",
}
SOURCES = {
    **{name: name for name in STATIC if name != "seed_retry.py"},
    "seed_retry.py": "../cloud-committed-seed-retry/seed_retry.py",
}
RELEASE = {
    "release": "TITAN",
    "upstream_snapshot": "fixture-upstream",
    "components": [],
}
INJECTED = "reference/titan-current/injected.py"
INJECTED_BYTES = b"INJECTED=1\n"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


class UntrackedAdditionFreshnessTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        run("git", "init", "-q", cwd=self.root)
        run("git", "config", "user.email", "test@example.invalid", cwd=self.root)
        run("git", "config", "user.name", "test", cwd=self.root)
        self.live = self.root / fresh.CANONICAL_LIVE_DIR
        self.live.mkdir(parents=True)
        for name, data in STATIC.items():
            if name == "seed_retry.py":
                path = self.root / "revenue/kaggriculture/cloud-committed-seed-retry/seed_retry.py"
            else:
                path = self.live / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)

        release_path = self.live / fresh.RELEASE_METADATA
        release_path.parent.mkdir(parents=True, exist_ok=True)
        release_path.write_text(
            json.dumps(RELEASE, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.live / "build_integrated.py").write_text(
            "from pathlib import Path\n"
            "ROOT=Path(__file__).resolve().parent\n"
            "RUNTIME=['main.py','titan_runtime.py','scheduler.py','frozen_selected.py','TITAN-CONFIG.json']\n"
            "def source_files():\n"
            "    mapping={p:p for p in RUNTIME}\n"
            "    mapping['spatial_tempo.py']='spatial_tempo.py'\n"
            "    mapping['seed_retry.py']='../cloud-committed-seed-retry/seed_retry.py'\n"
            "    for directory in ('reference/titan-current',):\n"
            "        for p in (ROOT/directory).rglob('*'):\n"
            "            if p.is_file() and '__pycache__' not in p.parts:\n"
            "                name=str(p.relative_to(ROOT));mapping[name]=name\n"
            "    return mapping\n",
            encoding="utf-8",
        )
        (self.root / ".gitignore").write_text(
            fresh.CANONICAL_LIVE_DIR + "/" + INJECTED + "\n",
            encoding="utf-8",
        )
        run("git", "add", ".", cwd=self.root)
        run("git", "commit", "-qm", "dynamic source enumeration", cwd=self.root)
        self.commit = run("git", "rev-parse", "HEAD", cwd=self.root)

        self.injected = self.live / INJECTED
        self.injected.write_bytes(INJECTED_BYTES)
        self.assertEqual(
            INJECTED,
            self.injected.relative_to(self.live).as_posix(),
        )
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", str(self.injected.relative_to(self.root))],
            cwd=self.root,
        )
        self.assertEqual(0, ignored.returncode)

    def tearDown(self):
        self.td.cleanup()

    def make_archive(self, *, include_injected):
        package = dict(STATIC)
        sources = dict(SOURCES)
        if include_injected:
            package[INJECTED] = INJECTED_BYTES
            sources[INJECTED] = INJECTED
        runtime = {
            name: {
                "source_path": sources[name],
                "sha256": sha256(data),
                "bytes": len(data),
            }
            for name, data in package.items()
        }
        manifest = dict(RELEASE)
        manifest.update(
            entrypoint="main.py::agent",
            config="TITAN-CONFIG.json",
            default=json.loads(CORE["TITAN-CONFIG.json"].decode("utf-8")),
            runtime=runtime,
        )
        source = (json.dumps(manifest, sort_keys=True) + "\n").encode()
        path = self.root / ("with-injected.tar.gz" if include_injected else "without-injected.tar.gz")
        with tarfile.open(path, "w:gz") as tf:
            for name, data in package.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
            info = tarfile.TarInfo("SOURCE.json")
            info.size = len(source)
            tf.addfile(info, io.BytesIO(source))
        return path, sha256(path.read_bytes())

    def verify(self, *, include_injected):
        archive, digest = self.make_archive(include_injected=include_injected)
        return fresh.verify_freshness(
            repo_root=self.root,
            live_dir=fresh.CANONICAL_LIVE_DIR,
            archive=archive,
            expected_archive_sha256=digest,
            expected_commit=self.commit,
        )

    def test_ignored_untracked_dynamic_addition_omitted_from_package_is_invalid(self):
        report = self.verify(include_injected=False)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn(
            "SOURCE.json runtime does not match canonical publisher source map",
            report["problems"][0],
        )
        self.assertIn("publisher_only=" + INJECTED, report["problems"][0])

    def test_ignored_untracked_dynamic_addition_in_package_is_invalid(self):
        report = self.verify(include_injected=True)
        self.assertEqual("INVALID", report["verdict"])
        self.assertIn("git binding failed", report["problems"][0])


if __name__ == "__main__":
    unittest.main()
