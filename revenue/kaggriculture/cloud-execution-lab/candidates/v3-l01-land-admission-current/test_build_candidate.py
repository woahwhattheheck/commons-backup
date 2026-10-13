# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import io
import json
import runpy
import tarfile
import tempfile
import unittest
from pathlib import Path

from build_candidate import (
    ENTRYPOINT_NEEDLE,
    ENTRYPOINT_REPLACEMENT,
    SOURCE_MEMBER,
    build,
    patch_entrypoint,
)

LANE = Path(__file__).resolve().parent
LAB = LANE.parents[1]


def current_shape_main() -> str:
    return (
        "_INSTANCE = None\n\n"
        "def _new_instance(root, feature_data):\n"
        "    def FinalPressureAgent(*args, **kwargs):\n"
        "        return object()\n"
        "    features = feature_data\n"
        "    admission = None\n"
        + ENTRYPOINT_NEEDLE
        + "\n"
        "def agent(step):\n"
        "    global _INSTANCE\n"
        "    replace = _INSTANCE is None or step == 0\n"
        "    if step < 0 and replace:\n"
        "        _INSTANCE = _new_instance(None, {})\n"
        "    try:\n"
        "        if replace:\n"
        "            _INSTANCE = _new_instance(None, {})\n"
        "    except TimeoutError:\n"
        "        _INSTANCE = None\n"
        "    return _INSTANCE\n"
    )


def make_lab(
    root: Path,
    *,
    include_embedded_source: bool = True,
    embedded_source: bytes | None = None,
    runtime_files: int = 2,
) -> tuple[Path, Path, str]:
    lab = root / "lab"
    export = lab / "exports"
    runtime = lab / "runtime/integrated-selected"
    export.mkdir(parents=True)
    runtime.mkdir(parents=True)

    source_main = current_shape_main()
    package = root / "package"
    package.mkdir()
    (package / "main.py").write_text(source_main, encoding="utf-8")
    (package / "TITAN-CONFIG.json").write_text("{}\n", encoding="utf-8")

    source_bytes = b'{"schema":"test"}\n'
    source_manifest = runtime / "CURRENT-SOURCE.json"
    source_manifest.write_bytes(source_bytes)
    if include_embedded_source:
        (package / SOURCE_MEMBER).write_bytes(
            source_bytes if embedded_source is None else embedded_source
        )

    archive = export / "titan-current.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        handle.add(package / "main.py", arcname="main.py")
        handle.add(
            package / "TITAN-CONFIG.json",
            arcname="TITAN-CONFIG.json",
        )
        if include_embedded_source:
            handle.add(package / SOURCE_MEMBER, arcname=SOURCE_MEMBER)

    manifest = {
        "path": "exports/titan-current.tar.gz",
        "entrypoint": "main.py::agent",
        "config": "TITAN-CONFIG.json",
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "bytes": archive.stat().st_size,
        "runtime_files": runtime_files,
        "source_manifest": "runtime/integrated-selected/CURRENT-SOURCE.json",
        "source_manifest_sha256": hashlib.sha256(source_bytes).hexdigest(),
    }
    (runtime / "CURRENT-ARCHIVE.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    mechanism = root / "land_admission.py"
    mechanism.write_text(
        "def wrap(value):\n    return value\n",
        encoding="utf-8",
    )
    return lab, mechanism, source_main


class BuildCandidateTests(unittest.TestCase):
    def test_committed_archive_runtime_count_excludes_source_manifest(self):
        committed = json.loads(
            (LAB / "runtime/integrated-selected/CURRENT-ARCHIVE.json").read_text(
                encoding="utf-8"
            )
        )
        archive = LAB / committed["path"]
        self.assertEqual(
            hashlib.sha256(archive.read_bytes()).hexdigest(),
            committed["sha256"],
        )
        self.assertEqual(archive.stat().st_size, committed["bytes"])
        with tarfile.open(archive, "r:gz") as handle:
            regular = [
                member.name for member in handle.getmembers() if member.isfile()
            ]
        runtime = [name for name in regular if name != SOURCE_MEMBER]
        self.assertEqual([SOURCE_MEMBER], [name for name in regular if name == SOURCE_MEMBER])
        self.assertEqual(committed["runtime_files"], len(runtime))
        self.assertEqual(len(regular), 110)
        self.assertEqual(committed["runtime_files"], 109)

    def test_release_generator_counts_mapping_not_embedded_source(self):
        source = (LAB / "build_integrated.py").read_text(encoding="utf-8")
        compact = source.replace(" ", "")
        self.assertIn("'runtime_files':len(mapping)", compact)
        self.assertNotIn("'runtime_files':len(blobs)", compact)

    def test_current_release_receipt_separates_runtime_and_source_manifest(self):
        builder = runpy.run_path(str(LAB / "build_integrated.py"))
        data, _source, rendered = builder["render"]()
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as handle:
            regular = [member.name for member in handle.getmembers() if member.isfile()]

        committed = json.loads(
            (LAB / "runtime/integrated-selected/CURRENT-ARCHIVE.json").read_text(
                encoding="utf-8"
            )
        )
        embedded = [name for name in regular if name == SOURCE_MEMBER]
        runtime = [name for name in regular if name != SOURCE_MEMBER]
        self.assertEqual([SOURCE_MEMBER], embedded)
        self.assertEqual(rendered["runtime_files"], len(runtime))
        self.assertEqual(len(regular), rendered["runtime_files"] + 1)
        self.assertEqual(committed, rendered)
        self.assertEqual(
            hashlib.sha256(
                (LAB / committed["path"]).read_bytes()
            ).hexdigest(),
            committed["sha256"],
        )

    def test_real_selected_main_has_one_constructor_hook(self):
        committed = json.loads(
            (LAB / "runtime/integrated-selected/CURRENT-ARCHIVE.json").read_text(
                encoding="utf-8"
            )
        )
        with tarfile.open(LAB / committed["path"], "r:gz") as handle:
            source = handle.extractfile("main.py").read().decode("utf-8")
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "main.py"
            path.write_text(source, encoding="utf-8")
            receipt = patch_entrypoint(path)
            patched = path.read_text(encoding="utf-8")
        self.assertEqual(source.count("_INSTANCE = _new_instance"), 0)
        self.assertEqual(patched.count("_INSTANCE = _new_instance"), 0)
        self.assertEqual(source.count("instance = _new_instance"), 1)
        self.assertEqual(patched.count("instance = _new_instance"), 1)
        self.assertEqual(source.count("def _new_instance"), 1)
        self.assertEqual(patched.count("def _new_instance"), 1)
        self.assertEqual(receipt["insertion_count"], 1)
        self.assertEqual(receipt["hook_surface"], "_new_instance.return")
        self.assertEqual(patched.count(ENTRYPOINT_REPLACEMENT), 1)
        self.assertNotIn(ENTRYPOINT_NEEDLE.rstrip("\n"), patched.splitlines())
        compile(patched, "main.py", "exec")

    def test_build_is_archive_bound_and_wraps_every_reconstruction(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            lab, mechanism, source_main = make_lab(root)

            receipt = build(lab, root / "out", mechanism)
            baseline = (root / "out/baseline/main.py").read_text(encoding="utf-8")
            candidate = (root / "out/land/main.py").read_text(encoding="utf-8")
            self.assertEqual(baseline, source_main)
            self.assertEqual(candidate.count(ENTRYPOINT_REPLACEMENT), 1)
            self.assertNotIn(ENTRYPOINT_NEEDLE.rstrip("\n"), candidate.splitlines())
            self.assertEqual(
                candidate.count(
                    "from land_admission import wrap as _wrap_land_admission"
                ),
                1,
            )
            self.assertEqual(candidate.count("_INSTANCE = _new_instance"), 2)
            self.assertEqual(receipt["hook_surface"], "_new_instance.return")
            self.assertEqual(receipt["baseline_regular_files"], 3)
            self.assertEqual(receipt["baseline_runtime_files"], 2)
            self.assertEqual(receipt["candidate_regular_files"], 4)
            self.assertEqual(receipt["candidate_runtime_files"], 3)
            self.assertEqual(
                receipt["embedded_source_sha256"],
                receipt["source_manifest_sha256"],
            )
            self.assertNotEqual(
                receipt["baseline_tree_sha256"],
                receipt["candidate_tree_sha256"],
            )

    def test_missing_embedded_source_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            lab, mechanism, _ = make_lab(root, include_embedded_source=False)
            with self.assertRaisesRegex(ValueError, "exactly one root SOURCE.json"):
                build(lab, root / "out", mechanism)

    def test_wrong_embedded_source_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            lab, mechanism, _ = make_lab(
                root,
                embedded_source=b'{"schema":"wrong"}\n',
            )
            with self.assertRaisesRegex(ValueError, "embedded source manifest mismatch"):
                build(lab, root / "out", mechanism)

    def test_receipt_runtime_count_excludes_embedded_source(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            lab, mechanism, _ = make_lab(root, runtime_files=3)
            with self.assertRaisesRegex(
                ValueError,
                "archive runtime file count mismatch: 2 != 3",
            ):
                build(lab, root / "out", mechanism)

    def test_patch_rejects_constructor_drift_without_writing(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "main.py"
            source = "def _new_instance():\n    return object()\n"
            path.write_text(source, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "constructor hook site"):
                patch_entrypoint(path)
            self.assertEqual(path.read_text(encoding="utf-8"), source)


if __name__ == "__main__":
    unittest.main()
