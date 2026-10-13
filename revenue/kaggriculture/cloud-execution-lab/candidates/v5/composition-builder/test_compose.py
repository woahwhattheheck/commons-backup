from __future__ import annotations

import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

import compose


def h(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_tar(path: Path, files: dict[str, bytes]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.GNU_FORMAT) as archive:
                for name, data in files.items():
                    info = tarfile.TarInfo(name)
                    info.mode = 0o644
                    info.mtime = 1
                    info.size = len(data)
                    archive.addfile(info, io.BytesIO(data))


def read_tar(path: Path) -> dict[str, bytes]:
    out = {}
    with tarfile.open(path, "r:gz") as archive:
        for member in archive.getmembers():
            handle = archive.extractfile(member)
            if handle is None:
                raise AssertionError(f"test archive member is unreadable: {member.name}")
            out[member.name] = handle.read()
    return out


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = self.root / "src"
        self.src.mkdir()
        self.base = self.root / "base.tar.gz"
        config = {"consumer": "frozen", "funding": False, "worker": False}
        self.base_files = {
            "TITAN-CONFIG.json": (json.dumps(config, indent=2) + "\n").encode(),
            "seller.py": b"seller-base\n",
            "worker.py": b"worker-base\n",
        }
        write_tar(self.base, self.base_files)
        (self.src / "seller.py").write_bytes(b"seller-a\n")
        (self.src / "worker.py").write_bytes(b"worker-b\n")

    def tearDown(self):
        self.tmp.cleanup()

    def manifest(self, *, components=None):
        if components is None:
            components = {
                "joint": {
                    "files": [{
                        "archive_path": "seller.py",
                        "source_path": "seller.py",
                        "preimage_sha256": h(self.base_files["seller.py"]),
                        "sha256": h(b"seller-a\n"),
                    }],
                    "config": {"funding": True},
                },
                "worker": {
                    "files": [{
                        "archive_path": "worker.py",
                        "source_path": "worker.py",
                        "preimage_sha256": h(self.base_files["worker.py"]),
                        "sha256": h(b"worker-b\n"),
                    }],
                    "config": {"worker": True},
                },
            }
        data = {
            "schema": compose.SCHEMA,
            "baseline": {"sha256": compose.sha256_file(self.base), "member_count": 3},
            "components": components,
        }
        path = self.root / "manifest.json"
        path.write_text(json.dumps(data))
        return path

    def test_builds_control_components_and_pair_with_activation(self):
        out = self.root / "out"
        receipt = compose.build(
            baseline=self.base,
            source_root=self.src,
            manifest_path=self.manifest(),
            output=out,
        )
        self.assertEqual(set(receipt["variants"]), {"control", "joint", "worker", "joint+worker"})
        control = read_tar(out / "control.tar.gz")
        joint = read_tar(out / "joint.tar.gz")
        worker = read_tar(out / "worker.tar.gz")
        pair = read_tar(out / "joint-plus-worker.tar.gz")
        self.assertEqual(control, self.base_files)
        self.assertEqual(joint["seller.py"], b"seller-a\n")
        self.assertEqual(joint["worker.py"], b"worker-base\n")
        self.assertEqual(worker["seller.py"], b"seller-base\n")
        self.assertEqual(worker["worker.py"], b"worker-b\n")
        self.assertEqual(pair["seller.py"], b"seller-a\n")
        self.assertEqual(pair["worker.py"], b"worker-b\n")
        self.assertTrue(json.loads(pair["TITAN-CONFIG.json"])["funding"])
        self.assertTrue(json.loads(pair["TITAN-CONFIG.json"])["worker"])
        self.assertEqual(
            receipt["variants"]["joint+worker"]["changed_members"],
            ["TITAN-CONFIG.json", "seller.py", "worker.py"],
        )
        seller_identity = receipt["components"]["joint"]["files"][0]
        self.assertEqual(seller_identity["preimage_sha256"], h(b"seller-base\n"))
        self.assertEqual(seller_identity["sha256"], h(b"seller-a\n"))

    def test_component_names_cannot_collide_with_variant_namespace(self):
        valid = json.loads(self.manifest().read_text())["components"]
        for bad_name in ("control", "a+b", "Upper", "a" * 65):
            with self.subTest(name=bad_name):
                components = {bad_name: valid["joint"], "worker": valid["worker"]}
                path = self.manifest(components=components)
                out = self.root / ("out-name-" + hashlib.sha256(bad_name.encode()).hexdigest()[:8])
                with self.assertRaisesRegex(compose.CompositionError, "invalid component name"):
                    compose.build(
                        baseline=self.base,
                        source_root=self.src,
                        manifest_path=path,
                        output=out,
                    )
                self.assertFalse(out.exists())

    def test_stale_source_hash_fails_closed(self):
        data = json.loads(self.manifest().read_text())
        data["components"]["joint"]["files"][0]["sha256"] = "0" * 64
        path = self.root / "stale.json"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(compose.CompositionError, "stale source"):
            compose.build(
                baseline=self.base,
                source_root=self.src,
                manifest_path=path,
                output=self.root / "out",
            )

    def test_missing_preimage_hash_fails_closed_before_output(self):
        data = json.loads(self.manifest().read_text())
        del data["components"]["joint"]["files"][0]["preimage_sha256"]
        path = self.root / "missing-preimage.json"
        path.write_text(json.dumps(data))
        out = self.root / "out-missing-preimage"
        with self.assertRaisesRegex(compose.CompositionError, "preimage_sha256"):
            compose.build(
                baseline=self.base,
                source_root=self.src,
                manifest_path=path,
                output=out,
            )
        self.assertFalse(out.exists())

    def test_noncanonical_preimage_hash_fails_closed_before_output(self):
        data = json.loads(self.manifest().read_text())
        data["components"]["joint"]["files"][0]["preimage_sha256"] = "A" * 64
        path = self.root / "bad-preimage.json"
        path.write_text(json.dumps(data))
        out = self.root / "out-bad-preimage"
        with self.assertRaisesRegex(compose.CompositionError, "64 lowercase hex"):
            compose.build(
                baseline=self.base,
                source_root=self.src,
                manifest_path=path,
                output=out,
            )
        self.assertFalse(out.exists())

    def test_baseline_path_mutation_after_auth_cannot_change_parsed_archive(self):
        out = self.root / "out-captured-baseline"
        tampered = dict(self.base_files)
        tampered["TITAN-CONFIG.json"] = (
            json.dumps({"consumer": "attacker", "funding": False, "worker": False}, indent=2) + "\n"
        ).encode()
        real_reader = compose._read_archive_bytes

        def mutate_live_path_after_capture(data: bytes):
            # Simulate a checkout/path swap after the authenticated bytes are captured.
            write_tar(self.base, tampered)
            return real_reader(data)

        with mock.patch.object(compose, "_read_archive_bytes", side_effect=mutate_live_path_after_capture):
            compose.build(
                baseline=self.base,
                source_root=self.src,
                manifest_path=self.manifest(),
                output=out,
            )

        # Execution/materialization must come from the captured authenticated archive,
        # not from the path that was swapped immediately before tar parsing.
        control = read_tar(out / "control.tar.gz")
        self.assertEqual(control, self.base_files)
        self.assertNotEqual(read_tar(self.base), self.base_files)

    def test_drifted_baseline_member_is_rejected_even_when_archive_sha_matches(self):
        drifted = self.root / "drifted.tar.gz"
        drifted_files = dict(self.base_files)
        drifted_files["seller.py"] = b"seller-drifted\n"
        write_tar(drifted, drifted_files)

        data = json.loads(self.manifest().read_text())
        data["baseline"]["sha256"] = compose.sha256_file(drifted)
        # The component still declares the baseline member it was actually reviewed against.
        self.assertEqual(
            data["components"]["joint"]["files"][0]["preimage_sha256"],
            h(b"seller-base\n"),
        )
        path = self.root / "drifted-manifest.json"
        path.write_text(json.dumps(data))
        out = self.root / "out-drifted"

        with self.assertRaisesRegex(compose.CompositionError, "baseline preimage mismatch"):
            compose.build(
                baseline=drifted,
                source_root=self.src,
                manifest_path=path,
                output=out,
            )
        self.assertFalse(out.exists())

    def test_nonregular_target_member_fails_before_output(self):
        nonregular = self.root / "nonregular.tar.gz"
        with nonregular.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
                with tarfile.open(fileobj=zipped, mode="w", format=tarfile.GNU_FORMAT) as archive:
                    for name in ("TITAN-CONFIG.json", "worker.py"):
                        data = self.base_files[name]
                        info = tarfile.TarInfo(name)
                        info.mode = 0o644
                        info.mtime = 1
                        info.size = len(data)
                        archive.addfile(info, io.BytesIO(data))
                    directory = tarfile.TarInfo("seller.py")
                    directory.type = tarfile.DIRTYPE
                    directory.mode = 0o755
                    directory.mtime = 1
                    archive.addfile(directory)

        data = json.loads(self.manifest().read_text())
        data["baseline"]["sha256"] = compose.sha256_file(nonregular)
        data["components"]["joint"]["files"][0]["preimage_sha256"] = h(b"")
        path = self.root / "nonregular-manifest.json"
        path.write_text(json.dumps(data))
        out = self.root / "out-nonregular"
        with self.assertRaisesRegex(compose.CompositionError, "non-regular archive member"):
            compose.build(
                baseline=nonregular,
                source_root=self.src,
                manifest_path=path,
                output=out,
            )
        self.assertFalse(out.exists())

    def test_components_disagreeing_on_same_preimage_fail_before_output(self):
        (self.src / "seller-b.py").write_bytes(b"seller-a\n")
        components = {
            "a": {
                "files": [{
                    "archive_path": "seller.py",
                    "source_path": "seller.py",
                    "preimage_sha256": h(b"seller-base\n"),
                    "sha256": h(b"seller-a\n"),
                }],
                "config": {},
            },
            "b": {
                "files": [{
                    "archive_path": "seller.py",
                    "source_path": "seller-b.py",
                    "preimage_sha256": h(b"other-base\n"),
                    "sha256": h(b"seller-a\n"),
                }],
                "config": {},
            },
        }
        out = self.root / "out-preimage-conflict"
        with self.assertRaisesRegex(compose.CompositionError, "disagree on baseline preimage"):
            compose.build(
                baseline=self.base,
                source_root=self.src,
                manifest_path=self.manifest(components=components),
                output=out,
            )
        self.assertFalse(out.exists())

    def test_incompatible_same_member_fails_closed(self):
        (self.src / "seller-b.py").write_bytes(b"seller-b\n")
        components = {
            "a": {
                "files": [{
                    "archive_path": "seller.py",
                    "source_path": "seller.py",
                    "preimage_sha256": h(b"seller-base\n"),
                    "sha256": h(b"seller-a\n"),
                }],
                "config": {},
            },
            "b": {
                "files": [{
                    "archive_path": "seller.py",
                    "source_path": "seller-b.py",
                    "preimage_sha256": h(b"seller-base\n"),
                    "sha256": h(b"seller-b\n"),
                }],
                "config": {},
            },
        }
        out = self.root / "out-postimage-conflict"
        with self.assertRaisesRegex(compose.CompositionError, "conflict on seller.py"):
            compose.build(
                baseline=self.base,
                source_root=self.src,
                manifest_path=self.manifest(components=components),
                output=out,
            )
        self.assertFalse(out.exists())

    def test_config_conflict_fails_closed(self):
        components = {
            "a": {
                "files": [{
                    "archive_path": "seller.py",
                    "source_path": "seller.py",
                    "preimage_sha256": h(b"seller-base\n"),
                    "sha256": h(b"seller-a\n"),
                }],
                "config": {"funding": True},
            },
            "b": {
                "files": [{
                    "archive_path": "worker.py",
                    "source_path": "worker.py",
                    "preimage_sha256": h(b"worker-base\n"),
                    "sha256": h(b"worker-b\n"),
                }],
                "config": {"funding": False},
            },
        }
        out = self.root / "out-config-conflict"
        with self.assertRaisesRegex(compose.CompositionError, "conflict on config"):
            compose.build(
                baseline=self.base,
                source_root=self.src,
                manifest_path=self.manifest(components=components),
                output=out,
            )
        self.assertFalse(out.exists())

    def test_path_escape_fails_closed(self):
        data = json.loads(self.manifest().read_text())
        data["components"]["joint"]["files"][0]["source_path"] = "../seller.py"
        path = self.root / "escape.json"
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(compose.CompositionError, "unsafe source_path"):
            compose.build(
                baseline=self.base,
                source_root=self.src,
                manifest_path=path,
                output=self.root / "out",
            )

    def test_source_symlink_escape_fails_closed_even_with_matching_hash(self):
        outside = self.root / "outside-seller.py"
        outside.write_bytes(b"outside-but-hash-matches\n")
        link = self.src / "linked-seller.py"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")

        data = json.loads(self.manifest().read_text())
        entry = data["components"]["joint"]["files"][0]
        entry["source_path"] = "linked-seller.py"
        entry["sha256"] = h(b"outside-but-hash-matches\n")
        path = self.root / "symlink-escape.json"
        path.write_text(json.dumps(data))

        with self.assertRaisesRegex(compose.CompositionError, "source escapes source root"):
            compose.build(
                baseline=self.base,
                source_root=self.src,
                manifest_path=path,
                output=self.root / "out",
            )


if __name__ == "__main__":
    unittest.main()
