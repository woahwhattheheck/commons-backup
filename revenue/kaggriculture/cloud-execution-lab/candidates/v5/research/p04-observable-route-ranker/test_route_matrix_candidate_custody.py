#!/usr/bin/env python3
import gzip
import hashlib
import importlib.util
import io
import json
import tarfile
import tempfile
import types
import unittest
from pathlib import Path

import route_matrix_candidate_custody as custody


def manifest(files, archive):
    return {
        "candidate_archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files": {name: hashlib.sha256(body).hexdigest() for name, body in files.items()},
    }


def noncanonical_archive(name, body):
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(body)
        archive.addfile(info, io.BytesIO(body))
    packed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=packed, mtime=0) as zipped:
        zipped.write(raw.getvalue())
    return packed.getvalue()


class CandidateCustody(unittest.TestCase):
    def fixture(self, root):
        payload = root / "payload"
        payload.mkdir()
        files = {
            "main.py": b"def agent(observation, configuration): return {}\n",
            "r04_full_router.py": b"ROUTE_STEP=144\nFINAL_PLAN_STEP=648\n",
        }
        for name, body in files.items():
            (payload / name).write_bytes(body)
        archive = root / "candidate.tar.gz"
        archive.write_bytes(custody._build_delivery_module().archive_bytes(files))
        return payload, archive, files, manifest(files, archive)

    def test_helper_sha256_pins_match_merged_helpers(self):
        source = Path(custody.__file__).resolve()
        selective = source.parents[2] / "selective-carrot"
        kaggriculture = source.parents[5]
        helpers = {
            selective / "build_delivery.py": custody.BUILD_DELIVERY_SHA256,
            selective / "publication_custody.py": custody.PUBLICATION_CUSTODY_SHA256,
            kaggriculture / "cloud-pack" / "official.py": custody.OFFICIAL_FILE_LOADER_SHA256,
            kaggriculture / "cloud-pack" / "upstream" / "manifest.json":
                custody.OFFICIAL_UPSTREAM_MANIFEST_SHA256,
        }
        for path, expected in helpers.items():
            with self.subTest(path=path):
                self.assertEqual(64, len(expected))
                self.assertEqual(expected, custody.core.sha256_file(path))

    def test_exact_module_executes_captured_bytes_not_reopened_path(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "helper.py"
            original = b"VALUE = 'captured'\n"
            path.write_bytes(original)
            expected = hashlib.sha256(original).hexdigest()
            capture = custody._capture_regular_bytes

            def capture_then_swap(value, label):
                source_path, body = capture(value, label)
                Path(value).write_text("VALUE = 'swapped'\n", encoding="utf-8")
                return source_path, body

            custody._capture_regular_bytes = capture_then_swap
            try:
                module = custody._load_exact_module(
                    "test_captured_helper", path, expected
                )
            finally:
                custody._capture_regular_bytes = capture
                custody.sys.modules.pop("test_captured_helper", None)
            self.assertEqual(module.VALUE, "captured")
            self.assertEqual(path.read_text(encoding="utf-8"), "VALUE = 'swapped'\n")

    def test_exact_module_rejects_original_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target.py"
            link = root / "link.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            expected = hashlib.sha256(target.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "must not be a symlink"):
                custody._load_exact_module("test_symlink_helper", link, expected)

    def test_capture_binds_canonical_archive_manifest_and_exact_tree(self):
        with tempfile.TemporaryDirectory() as td:
            payload, archive, files, m = self.fixture(Path(td))
            captured, authority = custody.capture_candidate(payload, archive, m)
            self.assertEqual(captured, files)
            self.assertEqual(authority["candidate_archive_sha256"], m["candidate_archive_sha256"])
            self.assertTrue(authority["archive_root_byte_identity"])

    def test_archive_a_root_b_split_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            payload, archive, files_b, _ = self.fixture(Path(td))
            files_a = dict(files_b)
            files_a["r04_full_router.py"] = b"ROUTE_STEP=144\nFORCED_PLAN=3\n"
            archive.write_bytes(custody._build_delivery_module().archive_bytes(files_a))
            split_manifest = manifest(files_b, archive)
            with self.assertRaisesRegex(ValueError, "archive member SHA map"):
                custody.capture_candidate(payload, archive, split_manifest)

    def test_noncanonical_archive_member_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            payload, archive, files, _ = self.fixture(Path(td))
            archive.write_bytes(noncanonical_archive("../main.py", files["main.py"]))
            bad = manifest(files, archive)
            with self.assertRaisesRegex(ValueError, "Noncanonical archive member"):
                custody.capture_candidate(payload, archive, bad)

    def test_wrong_plan_tree_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            payload, archive, _, m = self.fixture(Path(td))
            (payload / "r04_full_router.py").write_bytes(b"wrong plan\n")
            with self.assertRaisesRegex(ValueError, "member SHA256 drift"):
                custody.capture_candidate(payload, archive, m)

    def test_extra_and_symlink_members_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            payload, archive, _, m = self.fixture(Path(td))
            (payload / "extra.py").write_text("x=1\n")
            with self.assertRaisesRegex(ValueError, "member set drift"):
                custody.capture_candidate(payload, archive, m)
            (payload / "extra.py").unlink()
            try:
                (payload / "linked.py").symlink_to(payload / "main.py")
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(ValueError, "contains symlink"):
                custody.capture_candidate(payload, archive, m)

    def fake_official(self, root):
        loader = root / "official.py"
        upstream = root / "upstream"
        upstream.mkdir()
        marker = upstream / "marker.txt"
        marker.write_text("captured-marker", encoding="utf-8")
        loader.write_text(
            "from pathlib import Path\n"
            "HERE = Path(__file__).resolve().parent\n"
            "def make_agent(path):\n"
            "    marker = (HERE / 'upstream' / 'marker.txt').read_text()\n"
            "    namespace = {}\n"
            "    exec(Path(path).read_text(), namespace)\n"
            "    fn = namespace['agent']\n"
            "    def call(observation, configuration):\n"
            "        result = dict(fn(observation, configuration))\n"
            "        result['marker'] = marker\n"
            "        return result\n"
            "    return call\n",
            encoding="utf-8",
        )
        upstream_manifest = {
            "ref": custody.core.ENGINE_REF,
            "files": {
                "marker.txt": {
                    "sha256": hashlib.sha256(marker.read_bytes()).hexdigest()
                }
            },
        }
        manifest_path = upstream / "manifest.json"
        manifest_path.write_text(
            json.dumps(upstream_manifest, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        return loader, marker, manifest_path

    def test_adapter_executes_only_captured_candidate_and_loader_closure(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            loader, marker, manifest_path = self.fake_official(root)
            old_loader = custody.OFFICIAL_FILE_LOADER_SHA256
            old_manifest = custody.OFFICIAL_UPSTREAM_MANIFEST_SHA256
            custody.OFFICIAL_FILE_LOADER_SHA256 = hashlib.sha256(loader.read_bytes()).hexdigest()
            custody.OFFICIAL_UPSTREAM_MANIFEST_SHA256 = hashlib.sha256(
                manifest_path.read_bytes()
            ).hexdigest()
            captured = {
                "main.py": b"def agent(observation, configuration): return {'value': 'captured'}\n"
            }
            try:
                adapter, authority = custody.private_snapshot(captured, loader)
            finally:
                custody.OFFICIAL_FILE_LOADER_SHA256 = old_loader
                custody.OFFICIAL_UPSTREAM_MANIFEST_SHA256 = old_manifest

            loader.write_text("raise RuntimeError('swapped loader')\n", encoding="utf-8")
            marker.write_text("swapped-marker", encoding="utf-8")
            self.assertNotIn(str(loader), adapter.decode("utf-8"))
            self.assertFalse(authority["caller_paths_embedded"])

            adapter_path = root / "adapter.py"
            adapter_path.write_bytes(adapter)
            spec = importlib.util.spec_from_file_location("captured_adapter_test", adapter_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            try:
                self.assertEqual(
                    module.agent({}, {}),
                    {"value": "captured", "marker": "captured-marker"},
                )
            finally:
                module._custody.cleanup()

    def test_actor_private_adapter_blocks_direct_swap_and_unlinks_after_ready(self):
        class FakeActor:
            def __init__(self, spec, cache, loader, rng_seed, startup_timeout=10.0):
                self.spec = spec
                self.directory = tempfile.TemporaryDirectory(prefix="kag-eval-agent-")
                path = Path(self.directory.name) / spec.partition("::")[0]
                try:
                    path.write_bytes(b"swapped")
                    self.swap_blocked = False
                except PermissionError:
                    self.swap_blocked = True
                self.loaded = path.read_bytes()
                self.ready = {"kind": "ready"}

            def report(self):
                return {"loaded_sha256": hashlib.sha256(self.loaded).hexdigest()}

        fake = types.SimpleNamespace(Actor=FakeActor)
        adapter = b"agent = lambda observation, configuration: {}\n"
        private_actor, expected = custody._private_actor_class(fake, adapter)
        actor = private_actor(
            custody._PRIVATE_CANDIDATE_SPEC, Path("."), Path("."), 7
        )
        try:
            self.assertTrue(actor.swap_blocked)
            self.assertEqual(actor.loaded, adapter)
            self.assertFalse((Path(actor.directory.name) / "candidate-adapter.py").exists())
            report = actor.report()
            self.assertEqual(report["candidate_adapter_sha256"], expected)
            self.assertEqual(report["candidate_adapter_expected_sha256"], expected)
            self.assertTrue(report["candidate_adapter_actor_private"])
            self.assertTrue(report["candidate_adapter_removed_after_ready"])
        finally:
            actor.directory.cleanup()

    def test_shared_publication_primitive_is_loadable_and_effective(self):
        publish = custody.shared_publication()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            row, receipt = root / "row.jsonl", root / "receipt.json"
            publish(((row, b"row\n"), (receipt, b"receipt\n")))
            self.assertEqual(row.read_bytes(), b"row\n")
            self.assertEqual(receipt.read_bytes(), b"receipt\n")
            with self.assertRaises(FileExistsError):
                publish(((row, b"new\n"), (receipt, b"new\n")))


if __name__ == "__main__":
    unittest.main()
