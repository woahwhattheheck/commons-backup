# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest

import build_current as build
import paired_current as paired


HERE = Path(__file__).resolve().parent
LAB_ROOT = HERE.parents[2]


def git_blob_bytes(data: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def current_pointer_and_archive():
    pointer_path = LAB_ROOT / "runtime/integrated-selected/CURRENT-ARCHIVE.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    return pointer, LAB_ROOT / pointer["path"]


def extract_regular_members(archive: Path, destination: Path) -> None:
    destination.mkdir()
    with tarfile.open(archive, "r:*") as package:
        for member in package:
            rel = PurePosixPath(member.name)
            if (
                not member.name
                or "\\" in member.name
                or rel.is_absolute()
                or ".." in rel.parts
                or str(rel) != member.name.rstrip("/")
            ):
                raise AssertionError(f"unsafe CURRENT archive member: {member.name!r}")
            if member.isdir():
                continue
            if not member.isfile():
                raise AssertionError(
                    f"non-file CURRENT archive member: {member.name!r}"
                )
            stream = package.extractfile(member)
            if stream is None:
                raise AssertionError(f"unreadable CURRENT member: {member.name!r}")
            target = destination.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise AssertionError(f"duplicate CURRENT member: {member.name!r}")
            target.write_bytes(stream.read())


def load_candidate_entry(candidate: Path):
    saved = {name: sys.modules.get(name) for name in ("baseline_main", "selective_carrot")}
    sys.modules.pop("baseline_main", None)
    sys.modules.pop("selective_carrot", None)
    sys.path.insert(0, str(candidate))
    name = "_titan_v5_selective_carrot_retry_test"
    sys.modules.pop(name, None)
    try:
        spec = importlib.util.spec_from_file_location(name, candidate / "main.py")
        if spec is None or spec.loader is None:
            raise ImportError(candidate / "main.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module, saved, name
    except BaseException:
        sys.path.remove(str(candidate))
        for module_name, prior in saved.items():
            if prior is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = prior
        sys.modules.pop(name, None)
        raise


def unload_candidate_entry(candidate: Path, saved, name: str) -> None:
    sys.path.remove(str(candidate))
    for module_name, prior in saved.items():
        if prior is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = prior
    sys.modules.pop(name, None)


class CurrentV5SelectiveCarrotCarrierTests(unittest.TestCase):
    def test_pins_reject_pre_overflow_predecessor_blobs(self):
        """Parent/helper pins must follow live blobs after later source rotation.

        `187159d9` advanced lab/main.py after the carrot parent pin froze at
        9cf8feaa. `69fa421d` rotated joint-liquidity paired.py after the
        shared-helper pin froze at fbc5e320. Naming those predecessor blobs is
        not a current-V5 identity.
        """
        self.assertNotEqual(
            build.EXPECTED_PARENT_MAIN_BLOB,
            "9cf8feaa9a755ffdf85d8878baa07b1fc7940192",
        )
        self.assertNotEqual(
            paired.EXPECTED_SHARED_HELPER_GIT_BLOB,
            "fbc5e320b8a2ee63af11dc9856c956a679823409",
        )
        self.assertEqual(
            build.git_blob(LAB_ROOT / "main.py"),
            build.EXPECTED_PARENT_MAIN_BLOB,
        )
        helper = LAB_ROOT / "candidates/v5/joint-liquidity-bench/paired.py"
        self.assertEqual(
            paired.git_blob_bytes(helper.read_bytes()),
            paired.EXPECTED_SHARED_HELPER_GIT_BLOB,
        )

    def test_source_pins_match_canonical_tree(self):
        self.assertEqual(
            build.git_blob(LAB_ROOT / "main.py"), build.EXPECTED_PARENT_MAIN_BLOB
        )
        self.assertEqual(
            build.git_blob(HERE / "selective_carrot.py"),
            build.EXPECTED_SELECTIVE_BLOB,
        )
        self.assertEqual(
            build.git_blob(HERE / "current_entry.py"), build.EXPECTED_ENTRY_BLOB
        )
        snapshots = build._source_snapshots()
        self.assertEqual(snapshots["parent"], (LAB_ROOT / "main.py").read_bytes())
        self.assertEqual(snapshots["entry"], (HERE / "current_entry.py").read_bytes())
        self.assertEqual(
            snapshots["selective"], (HERE / "selective_carrot.py").read_bytes()
        )

    def test_shared_harness_helper_is_externally_pinned_before_exec(self):
        helper_path = (
            LAB_ROOT / "candidates/v5/joint-liquidity-bench/paired.py"
        )
        raw = helper_path.read_bytes()
        self.assertEqual(
            paired.git_blob_bytes(raw), paired.EXPECTED_SHARED_HELPER_GIT_BLOB
        )
        helper, authority = paired.load_authenticated_shared_helper(helper_path)
        self.assertEqual(
            authority["git_blob"], paired.EXPECTED_SHARED_HELPER_GIT_BLOB
        )
        self.assertEqual(authority["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertTrue(helper.__file__.startswith("<authenticated:"))
        self.assertTrue(hasattr(helper, "snapshot_harness"))

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            tampered = root / "paired.py"
            tampered.write_bytes(raw + b"\n# stable malicious drift\n")
            with self.assertRaisesRegex(ValueError, "shared harness helper Git blob drift"):
                paired.load_authenticated_shared_helper(tampered)
            self.assertEqual(list(root.iterdir()), [tampered])

            kg_root = root / "kg"
            caller_helper = (
                kg_root
                / "cloud-execution-lab/candidates/v5/joint-liquidity-bench/paired.py"
            )
            caller_helper.parent.mkdir(parents=True)
            caller_helper.write_bytes(raw + b"\n# caller-selected stable drift\n")
            engine_dir = root / "engine"
            engine_dir.mkdir()
            evidence = root / "evidence"
            with self.assertRaisesRegex(ValueError, "shared harness helper Git blob drift"):
                paired.main(
                    [
                        "--kg-root",
                        str(kg_root),
                        "--engine-dir",
                        str(engine_dir),
                        "--output",
                        str(evidence),
                        "--seeds",
                        "1909129999",
                    ]
                )
            self.assertFalse(evidence.exists())

    def test_current_archive_packages_the_pinned_parent_main(self):
        pointer, archive = current_pointer_and_archive()
        self.assertEqual(pointer["path"], "exports/titan-current.tar.gz")
        self.assertEqual(archive.stat().st_size, pointer["bytes"])
        raw = archive.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), pointer["sha256"])
        memory_members = paired.archive_members_bytes(raw)
        self.assertEqual(
            git_blob_bytes(memory_members["main.py"]), build.EXPECTED_PARENT_MAIN_BLOB
        )
        with tarfile.open(archive, "r:*") as package:
            member = package.getmember("main.py")
            self.assertTrue(member.isfile())
            stream = package.extractfile(member)
            self.assertIsNotNone(stream)
            main_bytes = stream.read()
        self.assertEqual(main_bytes, memory_members["main.py"])

    def test_runner_first_action_divergence_is_exact(self):
        control = [{"market": []}, {"market": [{"action": "SELL", "qty": 1}]}]
        same = [dict(row) for row in control]
        changed = [control[0], {"market": [{"action": "SELL", "qty": 2}]}]
        shorter = [control[0]]
        self.assertIsNone(paired.first_action_divergence(control, same))
        self.assertEqual(
            paired.first_action_divergence(control, changed),
            {"step": 1, "control": control[1], "treatment": changed[1]},
        )
        self.assertEqual(
            paired.first_action_divergence(control, shorter),
            {
                "step": 1,
                "control": control[1],
                "treatment": {"_stream_end": True},
            },
        )

    def test_real_current_package_materializes_both_profiles(self):
        pointer, archive = current_pointer_and_archive()
        self.assertEqual(
            hashlib.sha256(archive.read_bytes()).hexdigest(), pointer["sha256"]
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            baseline = root / "current"
            extract_regular_members(archive, baseline)
            control_digest = build.package_digest(baseline)
            for cap in (4, 12):
                out = root / f"cap{cap}"
                receipt = build.build_candidate(baseline, out, cap)
                self.assertEqual(receipt["max_active"], cap)
                self.assertEqual(receipt["control_package_sha256"], control_digest)
                self.assertEqual(
                    build.git_blob(out / "baseline_main.py"),
                    build.EXPECTED_PARENT_MAIN_BLOB,
                )
                self.assertEqual(
                    build.git_blob(out / "main.py"), build.EXPECTED_ENTRY_BLOB
                )
                self.assertEqual(
                    build.git_blob(out / "selective_carrot.py"),
                    build.EXPECTED_SELECTIVE_BLOB,
                )
                profile = json.loads(
                    (out / "CARROT-CAPACITY.json").read_text(encoding="utf-8")
                )
                self.assertEqual(profile["max_active"], cap)
                self.assertEqual(
                    profile["control_package_sha256"], control_digest
                )

    def test_step_zero_retry_requires_positive_retry_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            baseline = root / "baseline"
            baseline.mkdir()
            shutil.copyfile(LAB_ROOT / "main.py", baseline / "main.py")
            candidate = root / "candidate"
            build.build_candidate(baseline, candidate, 4)
            entry, saved, name = load_candidate_entry(candidate)
            try:
                entry.baseline._SPATIAL_RECOVERY = None
                entry.baseline._INSTANCE = None
                self.assertTrue(entry._choice_match_reset(0))
                self.assertFalse(entry._choice_match_reset(1))

                entry.baseline._INSTANCE = SimpleNamespace(_entrypoint_last_step=0)
                self.assertFalse(entry._choice_match_reset(0))
                self.assertFalse(entry._choice_match_reset(1))

                entry.baseline._INSTANCE = SimpleNamespace(_entrypoint_last_step=37)
                self.assertTrue(entry._choice_match_reset(0))

                entry.baseline._INSTANCE = None
                entry.baseline._SPATIAL_RECOVERY = {"last_step": 37, "state": {}}
                self.assertTrue(entry._choice_match_reset(0))

                entry.baseline._SPATIAL_RECOVERY = {"last_step": 0, "state": {}}
                self.assertFalse(entry._choice_match_reset(0))
            finally:
                unload_candidate_entry(candidate, saved, name)

    def test_profile_hashes_are_exact_lowercase_hex(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            baseline = root / "baseline"
            baseline.mkdir()
            shutil.copyfile(LAB_ROOT / "main.py", baseline / "main.py")
            candidate = root / "candidate"
            build.build_candidate(baseline, candidate, 4)
            entry, saved, name = load_candidate_entry(candidate)
            try:
                self.assertEqual(
                    entry._require_hex({"digest": "a" * 40}, "digest", 40),
                    "a" * 40,
                )
                for bad in (
                    "a" * 39,
                    "a" * 41,
                    "A" * 40,
                    "g" * 40,
                    "a" * 64,
                    7,
                    None,
                ):
                    with self.assertRaises(RuntimeError):
                        entry._require_hex({"digest": bad}, "digest", 40)
            finally:
                unload_candidate_entry(candidate, saved, name)

    def test_materializes_cap4_and_cap12_from_one_implementation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            baseline = root / "baseline"
            baseline.mkdir()
            shutil.copyfile(LAB_ROOT / "main.py", baseline / "main.py")
            (baseline / "marker.txt").write_text("current-v5\n", encoding="utf-8")
            control_digest = build.package_digest(baseline)

            receipts = []
            for cap in (4, 12):
                out = root / f"cap{cap}"
                receipt = build.build_candidate(baseline, out, cap)
                receipts.append(receipt)
                self.assertEqual(receipt["max_active"], cap)
                self.assertEqual(receipt["control_package_sha256"], control_digest)
                self.assertNotEqual(
                    receipt["candidate_package_sha256"], control_digest
                )
                self.assertEqual(
                    (out / "baseline_main.py").read_bytes(),
                    (LAB_ROOT / "main.py").read_bytes(),
                )
                self.assertEqual(
                    (out / "selective_carrot.py").read_bytes(),
                    (HERE / "selective_carrot.py").read_bytes(),
                )
                self.assertEqual(
                    (out / "main.py").read_bytes(),
                    (HERE / "current_entry.py").read_bytes(),
                )
                self.assertEqual(
                    (out / "marker.txt").read_text(encoding="utf-8"),
                    "current-v5\n",
                )
                profile = json.loads(
                    (out / "CARROT-CAPACITY.json").read_text(encoding="utf-8")
                )
                self.assertEqual(profile["max_active"], cap)
                self.assertEqual(
                    profile["control_package_sha256"], control_digest
                )
                self.assertEqual(
                    profile["entry_git_blob"], build.EXPECTED_ENTRY_BLOB
                )
                self.assertEqual(
                    profile["entry_git_blob"],
                    build.git_blob(HERE / "current_entry.py"),
                )

            self.assertEqual(
                receipts[0]["selective_carrot_git_blob"],
                receipts[1]["selective_carrot_git_blob"],
            )
            self.assertEqual(
                receipts[0]["entry_git_blob"], receipts[1]["entry_git_blob"]
            )
            self.assertNotEqual(
                receipts[0]["candidate_package_sha256"],
                receipts[1]["candidate_package_sha256"],
            )

    def test_rejects_non_profile_capacity_and_parent_drift(self):
        for value in (True, 0, 8, 13):
            with self.assertRaises(ValueError):
                build._capacity(value)

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            baseline = root / "baseline"
            baseline.mkdir()
            source = (LAB_ROOT / "main.py").read_text(encoding="utf-8")
            (baseline / "main.py").write_text(source + "\n", encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, "expected exact current-V5 parent main.py"
            ):
                build.build_candidate(baseline, root / "out", 4)

    def test_output_cannot_alias_baseline(self):
        with tempfile.TemporaryDirectory() as folder:
            baseline = Path(folder) / "baseline"
            baseline.mkdir()
            shutil.copyfile(LAB_ROOT / "main.py", baseline / "main.py")
            with self.assertRaisesRegex(ValueError, "outside baseline root"):
                build.build_candidate(baseline, baseline / "out", 4)


if __name__ == "__main__":
    unittest.main()
