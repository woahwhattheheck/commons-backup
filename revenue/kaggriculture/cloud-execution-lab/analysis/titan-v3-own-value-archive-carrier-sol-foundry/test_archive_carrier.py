# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

from archive_carrier import ArchiveCarrierError, materialize_pair, probe_entry, verify_pair
from verify_panel_binding import PanelBindingError, verify


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_tar(entries: list[tuple[tarfile.TarInfo, bytes]]) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", mtime=0, filename="") as gz:
        with tarfile.open(fileobj=gz, mode="w") as archive:
            for info, data in entries:
                if info.isreg():
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))
                else:
                    archive.addfile(info)
    return output.getvalue()


def regular(name: str, data: bytes) -> tuple[tarfile.TarInfo, bytes]:
    info = tarfile.TarInfo(name)
    info.mode = 0o644
    info.mtime = 0
    return info, data


class Fixture:
    def __init__(self, root: Path):
        self.root = root
        self.lab = root / "cloud-execution-lab"
        self.case = self.lab / "analysis" / "case"
        self.pointer = self.lab / "runtime" / "integrated-selected" / "CURRENT-ARCHIVE.json"
        self.current_source = self.lab / "runtime" / "integrated-selected" / "CURRENT-SOURCE.json"
        self.archive = self.lab / "exports" / "titan-current.tar.gz"
        self.overlay = self.case / "own_value_objective.py"
        self.guard = Path(__file__).resolve().with_name("archive_runtime_guard.py")
        self.output = root / "out" / "carrier"
        self.lab.mkdir(parents=True)
        self.case.mkdir(parents=True)
        self.pointer.parent.mkdir(parents=True)
        self.archive.parent.mkdir(parents=True)
        self.overlay.write_text(
            """\
from pathlib import Path

def install(*, module=None, expected_root=None):
    if Path(module.__file__).resolve() != Path(expected_root).resolve() / 'selected_sell_core.py':
        raise RuntimeError('wrong selected core')
    module.PATCHED = True
    return {
        'changed_field': 'MarketPath.score[0]',
        'actual_git_blob': 'a',
        'expected_git_blob': 'a',
        'canonical_files_modified': False,
    }
""",
            encoding="utf-8",
        )
        self.runtime = {
            "TITAN-CONFIG.json": b"{}\n",
            "main.py": (
                b"import observed_clone, scheduler, selected_sell_core, titan_runtime\n"
                b"def agent(observation, configuration=None):\n"
                b"    return {'patched': selected_sell_core.PATCHED, 'detached': observed_clone.detached_json_value(3)}\n"
            ),
            "observed_clone.py": b"def detached_json_value(value):\n    return value\n",
            "scheduler.py": b"from observed_clone import detached_json_value\nVALUE=detached_json_value(1)\n",
            "selected_sell_core.py": b"PATCHED=False\n",
            "titan_runtime.py": b"RUNTIME='fixture'\n",
        }
        self.publish()

    def source_bytes(self) -> bytes:
        source = {
            "entrypoint": "main.py::agent",
            "config": "TITAN-CONFIG.json",
            "runtime": {
                name: {
                    "source_path": name,
                    "sha256": sha256(data),
                    "bytes": len(data),
                }
                for name, data in sorted(self.runtime.items())
            },
        }
        return (json.dumps(source, indent=2, sort_keys=True) + "\n").encode("utf-8")

    def archive_bytes(self, extra_entries: list[tuple[tarfile.TarInfo, bytes]] | None = None) -> bytes:
        source = self.source_bytes()
        members = {**self.runtime, "SOURCE.json": source}
        entries = [regular(name, members[name]) for name in sorted(members)]
        if extra_entries:
            entries.extend(extra_entries)
        return build_tar(entries)

    def publish(self, archive_bytes: bytes | None = None, *, runtime_files: object | None = None) -> None:
        source = self.source_bytes()
        data = self.archive_bytes() if archive_bytes is None else archive_bytes
        self.archive.write_bytes(data)
        self.current_source.write_bytes(source)
        pointer = {
            "path": "exports/titan-current.tar.gz",
            "entrypoint": "main.py::agent",
            "config": "TITAN-CONFIG.json",
            "sha256": sha256(data),
            "bytes": len(data),
            "runtime_files": len(self.runtime) if runtime_files is None else runtime_files,
            "source_manifest": "runtime/integrated-selected/CURRENT-SOURCE.json",
            "source_manifest_sha256": sha256(source),
        }
        self.pointer.write_text(json.dumps(pointer, indent=2) + "\n", encoding="utf-8")

    def materialize(self):
        return materialize_pair(
            lab_root=self.lab,
            pointer_path=self.pointer,
            overlay_path=self.overlay,
            guard_path=self.guard,
            output_root=self.output,
            git_head="fixture-head",
        )


def call_entry(path: Path) -> dict:
    code = r'''
import importlib.util, json, sys
from pathlib import Path
p=Path(sys.argv[1]).resolve(); sys.path.insert(0, str(p.parent))
s=importlib.util.spec_from_file_location('_fixture_entry', p)
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
print(json.dumps(m.agent({}, {}), sort_keys=True))
'''
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", code, str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": __import__("os").defpath, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"},
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr)
    return json.loads(completed.stdout)


class ArchiveCarrierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = Fixture(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_materializes_equal_closures_and_isolated_overlay(self):
        receipt = self.fixture.materialize()
        self.assertTrue(receipt["canonical_runtime_equal"])
        self.assertEqual(
            receipt["control"]["runtime_tree_sha256"],
            receipt["candidate"]["runtime_tree_sha256"],
        )
        control = call_entry(self.fixture.output / "control" / "control_entry.py")
        candidate = call_entry(self.fixture.output / "candidate" / "candidate_entry.py")
        self.assertEqual(control, {"detached": 3, "patched": False})
        self.assertEqual(candidate, {"detached": 3, "patched": True})

    def test_probe_binds_external_root_module_inside_each_arena(self):
        self.fixture.materialize()
        for mode in ("control", "candidate"):
            result = probe_entry(self.fixture.output / mode / f"{mode}_entry.py")
            self.assertEqual(result["module_origins"]["observed_clone"], "observed_clone.py")
            self.assertEqual(result["runtime_receipt"]["runtime_files"], len(self.fixture.runtime))
        self.assertIsNone(probe_entry(self.fixture.output / "control" / "control_entry.py")["install_receipt"])
        self.assertEqual(
            probe_entry(self.fixture.output / "candidate" / "candidate_entry.py")["install_receipt"]["changed_field"],
            "MarketPath.score[0]",
        )

    def test_raw_main_without_mapped_module_reproduces_predecessor_failure(self):
        raw = Path(self.temp.name) / "raw"
        raw.mkdir()
        (raw / "main.py").write_bytes(self.fixture.runtime["main.py"])
        code = "import importlib.util,sys; p=sys.argv[1]; s=importlib.util.spec_from_file_location('raw',p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)"
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code, str(raw / "main.py")],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("observed_clone", completed.stderr)

    def test_runtime_tamper_fails_at_worker_load(self):
        self.fixture.materialize()
        path = self.fixture.output / "control" / "observed_clone.py"
        path.write_text("def detached_json_value(value): return 999\n", encoding="utf-8")
        with self.assertRaises(ArchiveCarrierError):
            probe_entry(self.fixture.output / "control" / "control_entry.py")

    def test_overlay_tamper_fails_at_worker_load(self):
        self.fixture.materialize()
        path = self.fixture.output / "candidate" / "own_value_objective.py"
        path.write_text(path.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
        with self.assertRaises(ArchiveCarrierError):
            probe_entry(self.fixture.output / "candidate" / "candidate_entry.py")

    def test_unexpected_file_fails_at_worker_load(self):
        self.fixture.materialize()
        (self.fixture.output / "control" / "injected.py").write_text("X=1\n", encoding="utf-8")
        with self.assertRaises(ArchiveCarrierError):
            probe_entry(self.fixture.output / "control" / "control_entry.py")

    def test_post_probe_pair_revalidation_passes(self):
        self.fixture.materialize()
        probe_entry(self.fixture.output / "control" / "control_entry.py")
        probe_entry(self.fixture.output / "candidate" / "candidate_entry.py")
        result = verify_pair(self.fixture.output)
        self.assertTrue(result["canonical_runtime_equal"])
        self.assertEqual(set(result["arms"]), {"control", "candidate"})

    def test_pair_revalidation_rejects_entrypoint_tamper(self):
        self.fixture.materialize()
        path = self.fixture.output / "control" / "control_entry.py"
        path.write_text(path.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
        with self.assertRaisesRegex(ArchiveCarrierError, "entrypoint drift"):
            verify_pair(self.fixture.output)

    def test_pair_revalidation_rejects_top_level_injection(self):
        self.fixture.materialize()
        (self.fixture.output / "outside.txt").write_text("drift", encoding="utf-8")
        with self.assertRaisesRegex(ArchiveCarrierError, "top-level drift"):
            verify_pair(self.fixture.output)

    def test_archive_sha_mismatch_fails_without_output(self):
        pointer = json.loads(self.fixture.pointer.read_text(encoding="utf-8"))
        pointer["sha256"] = "0" * 64
        self.fixture.pointer.write_text(json.dumps(pointer), encoding="utf-8")
        with self.assertRaises(ArchiveCarrierError):
            self.fixture.materialize()
        self.assertFalse(self.fixture.output.exists())

    def test_repository_source_manifest_mismatch_fails(self):
        self.fixture.current_source.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ArchiveCarrierError, "CURRENT-SOURCE"):
            self.fixture.materialize()

    def test_bool_runtime_count_is_rejected(self):
        self.fixture.publish(runtime_files=True)
        with self.assertRaisesRegex(ArchiveCarrierError, "runtime file count"):
            self.fixture.materialize()

    def test_traversal_member_is_rejected(self):
        bad = self.fixture.archive_bytes([regular("../escape.py", b"X=1\n")])
        self.fixture.publish(bad)
        with self.assertRaisesRegex(ArchiveCarrierError, "canonical relative path"):
            self.fixture.materialize()

    def test_symlink_member_is_rejected(self):
        info = tarfile.TarInfo("zzz-link")
        info.type = tarfile.SYMTYPE
        info.linkname = "main.py"
        info.mode = 0o777
        info.mtime = 0
        bad = self.fixture.archive_bytes([(info, b"")])
        self.fixture.publish(bad)
        with self.assertRaisesRegex(ArchiveCarrierError, "regular file"):
            self.fixture.materialize()

    def test_duplicate_member_is_rejected(self):
        bad = self.fixture.archive_bytes([regular("main.py", self.fixture.runtime["main.py"])])
        self.fixture.publish(bad)
        with self.assertRaisesRegex(ArchiveCarrierError, "duplicates member"):
            self.fixture.materialize()

    def test_duplicate_pointer_key_is_rejected(self):
        pointer = self.fixture.pointer.read_text(encoding="utf-8")
        duplicate = pointer.rstrip()[:-1] + ', "bytes": 1}\n'
        self.fixture.pointer.write_text(duplicate, encoding="utf-8")
        with self.assertRaisesRegex(ArchiveCarrierError, "duplicate key"):
            self.fixture.materialize()

    def test_nonfinite_pointer_constant_is_rejected(self):
        pointer = json.loads(self.fixture.pointer.read_text(encoding="utf-8"))
        text = json.dumps(pointer).replace(str(pointer["bytes"]), "NaN", 1)
        self.fixture.pointer.write_text(text, encoding="utf-8")
        with self.assertRaisesRegex(ArchiveCarrierError, "non-finite JSON"):
            self.fixture.materialize()

    def test_existing_output_root_is_not_overwritten(self):
        self.fixture.output.mkdir(parents=True)
        marker = self.fixture.output / "keep.txt"
        marker.write_text("preserve", encoding="utf-8")
        with self.assertRaisesRegex(ArchiveCarrierError, "already exists"):
            self.fixture.materialize()
        self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")


class PanelBindingTests(unittest.TestCase):
    @staticmethod
    def fixture():
        control_sha = "1" * 64
        candidate_sha = "2" * 64
        tree = "3" * 64
        receipt = {
            "schema_version": 1,
            "operation": "op",
            "archive": {
                "sha256": "4" * 64,
                "source_manifest_sha256": "5" * 64,
                "runtime_tree_sha256": tree,
            },
            "control": {
                "runtime_tree_sha256": tree,
                "entry_sha256": control_sha,
                "entrypoint": "control/control_entry.py::agent",
                "overlay_installed": False,
            },
            "candidate": {
                "runtime_tree_sha256": tree,
                "entry_sha256": candidate_sha,
                "entrypoint": "candidate/candidate_entry.py::agent",
                "overlay_installed": True,
            },
            "canonical_runtime_equal": True,
            "canonical_repository_modified": False,
        }
        control = {
            "progress": {"state": "complete", "planned_games": 1, "recorded_games": 1},
            "candidate": {"entry": "control_entry.py", "callable": "agent", "sha256": control_sha},
            "games": [{"status": "complete", "failure": None}],
        }
        candidate = {
            "progress": {"state": "complete", "planned_games": 1, "recorded_games": 1},
            "candidate": {"entry": "candidate_entry.py", "callable": "agent", "sha256": candidate_sha},
            "games": [{"status": "complete", "failure": None}],
        }
        return receipt, control, candidate

    def test_accepts_exact_entrypoint_and_runtime_binding(self):
        receipt, control, candidate = self.fixture()
        result = verify(receipt, control, candidate)
        self.assertTrue(result["entrypoint_binding_complete"])
        self.assertEqual(result["control_games"], 1)

    def test_rejects_report_entrypoint_drift(self):
        receipt, control, candidate = self.fixture()
        candidate["candidate"]["sha256"] = "9" * 64
        with self.assertRaisesRegex(PanelBindingError, "candidate report is bound"):
            verify(receipt, control, candidate)

    def test_rejects_runtime_tree_mismatch(self):
        receipt, control, candidate = self.fixture()
        receipt["candidate"]["runtime_tree_sha256"] = "9" * 64
        with self.assertRaisesRegex(PanelBindingError, "candidate runtime tree"):
            verify(receipt, control, candidate)

    def test_rejects_incomplete_panel(self):
        receipt, control, candidate = self.fixture()
        candidate["progress"]["state"] = "running"
        with self.assertRaisesRegex(PanelBindingError, "not a complete"):
            verify(receipt, control, candidate)

    def test_rejects_complete_snapshot_with_failed_cell(self):
        receipt, control, candidate = self.fixture()
        control["games"][0] = {"status": "failed", "failure": {"kind": "crash"}}
        with self.assertRaisesRegex(PanelBindingError, "game 0 is not complete"):
            verify(receipt, control, candidate)

    def test_rejects_entry_name_drift(self):
        receipt, control, candidate = self.fixture()
        control["candidate"]["entry"] = "main.py"
        with self.assertRaisesRegex(PanelBindingError, "report entry"):
            verify(receipt, control, candidate)

    def test_rejects_bool_cardinality(self):
        receipt, control, candidate = self.fixture()
        control["progress"]["planned_games"] = True
        with self.assertRaisesRegex(PanelBindingError, "planned_games"):
            verify(receipt, control, candidate)


if __name__ == "__main__":
    unittest.main()
