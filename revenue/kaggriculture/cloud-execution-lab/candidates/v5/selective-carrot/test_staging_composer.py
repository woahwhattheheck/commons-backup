import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import staging_composer as sc


def h(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class ComposerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.base = {
            "main.py": b"base-main\n",
            "r04_full_router.py": b"router-0\n",
            "TITAN-CONFIG.json": b"{}\n",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def manifest(self, cid, replacements, *, depends=None, conflicts=None, overlap=None):
        folder = self.root / cid
        folder.mkdir()
        specs = {}
        for member, (pre, body) in replacements.items():
            source = member.replace("/", "__") + ".replacement"
            (folder / source).write_bytes(body)
            specs[member] = {
                "source": source,
                "preimage_sha256": h(pre),
                "postimage_sha256": h(body),
            }
        obj = {
            "schema": sc.COMPONENT_SCHEMA,
            "component_id": cid,
            "baseline_archive_sha256": sc.BASELINE_SHA256,
            "depends_on": depends or [],
            "conflicts_with": conflicts or [],
            "overlap_after": overlap or {},
            "replacements": specs,
            "kaggle_submission_hold": True,
        }
        path = folder / "COMPONENT.json"
        path.write_text(json.dumps(obj), encoding="utf-8")
        return path

    def load(self, *paths):
        return [sc.load_component(path) for path in paths]

    def test_read_regular_preserves_ctrl_z_and_following_binary_bytes(self):
        raw = b"gzip-prefix\x1aarchive-after-dos-eof\x00\xff"
        path = self.root / "candidate.tar.gz"
        path.write_bytes(raw)
        self.assertEqual(sc.read_regular(path), raw)

    def test_one_component_preserves_untouched_members(self):
        path = self.manifest("p01", {"main.py": (self.base["main.py"], b"main-1\n")})
        files, applied = sc.compose_files(self.base, self.load(path))
        self.assertEqual(files["main.py"], b"main-1\n")
        self.assertEqual(files["r04_full_router.py"], self.base["r04_full_router.py"])
        self.assertEqual(files["TITAN-CONFIG.json"], self.base["TITAN-CONFIG.json"])
        self.assertEqual([x["component_id"] for x in applied], ["p01"])

    def test_preimage_drift_fails_closed(self):
        path = self.manifest("p01", {"main.py": (b"wrong\n", b"main-1\n")})
        with self.assertRaisesRegex(sc.ComposerError, "preimage mismatch"):
            sc.compose_files(self.base, self.load(path))

    def test_postimage_drift_fails_at_load(self):
        path = self.manifest("p01", {"main.py": (self.base["main.py"], b"main-1\n")})
        obj = json.loads(path.read_text())
        obj["replacements"]["main.py"]["postimage_sha256"] = "0" * 64
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(sc.ComposerError, "postimage mismatch"):
            sc.load_component(path)

    def test_undeclared_overlap_fails(self):
        a = self.manifest("a", {"r04_full_router.py": (b"router-0\n", b"router-a\n")})
        b = self.manifest("b", {"r04_full_router.py": (b"router-a\n", b"router-b\n")})
        with self.assertRaisesRegex(sc.ComposerError, "without exact declaration"):
            sc.compose_files(self.base, self.load(a, b))

    def test_declared_overlap_chains_exact_postimage(self):
        a = self.manifest("a", {"r04_full_router.py": (b"router-0\n", b"router-a\n")})
        b = self.manifest(
            "b", {"r04_full_router.py": (b"router-a\n", b"router-b\n")},
            depends=["a"], overlap={"r04_full_router.py": "a"},
        )
        files, _ = sc.compose_files(self.base, self.load(a, b))
        self.assertEqual(files["r04_full_router.py"], b"router-b\n")

    def test_wrong_overlap_owner_fails(self):
        a = self.manifest("a", {"r04_full_router.py": (b"router-0\n", b"router-a\n")})
        b = self.manifest(
            "b", {"r04_full_router.py": (b"router-a\n", b"router-b\n")},
            overlap={"r04_full_router.py": "other"},
        )
        with self.assertRaisesRegex(sc.ComposerError, "without exact declaration"):
            sc.compose_files(self.base, self.load(a, b))

    def test_overlap_declared_on_untouched_member_fails(self):
        a = self.manifest(
            "a", {"main.py": (b"base-main\n", b"main-a\n")},
            overlap={"main.py": "old"},
        )
        with self.assertRaisesRegex(sc.ComposerError, "untouched member"):
            sc.compose_files(self.base, self.load(a))

    def test_dependency_must_precede(self):
        b = self.manifest("b", {"main.py": (b"base-main\n", b"main-b\n")}, depends=["a"])
        with self.assertRaisesRegex(sc.ComposerError, "unsatisfied dependency"):
            sc.compose_files(self.base, self.load(b))

    def test_conflicts_are_symmetric_at_compose_time(self):
        a = self.manifest("a", {"main.py": (b"base-main\n", b"main-a\n")}, conflicts=["b"])
        b = self.manifest("b", {"TITAN-CONFIG.json": (b"{}\n", b'{"x":1}\n')})
        with self.assertRaisesRegex(sc.ComposerError, "conflicts"):
            sc.compose_files(self.base, self.load(a, b))

    def test_duplicate_component_id_fails(self):
        a = self.manifest("same", {"main.py": (b"base-main\n", b"main-a\n")})
        first = sc.load_component(a)
        second = dict(first)
        with self.assertRaisesRegex(sc.ComposerError, "duplicate component_id"):
            sc.compose_files(self.base, [first, second])

    def test_member_traversal_fails(self):
        path = self.manifest("p01", {"main.py": (b"base-main\n", b"main-a\n")})
        obj = json.loads(path.read_text())
        spec = obj["replacements"].pop("main.py")
        obj["replacements"]["../main.py"] = spec
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(sc.ComposerError, "noncanonical member"):
            sc.load_component(path)

    def test_source_traversal_fails(self):
        path = self.manifest("p01", {"main.py": (b"base-main\n", b"main-a\n")})
        obj = json.loads(path.read_text())
        obj["replacements"]["main.py"]["source"] = "../escape"
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(sc.ComposerError, "noncanonical replacement source"):
            sc.load_component(path)

    def test_source_symlink_fails(self):
        path = self.manifest("p01", {"main.py": (b"base-main\n", b"main-a\n")})
        obj = json.loads(path.read_text())
        target = path.parent / obj["replacements"]["main.py"]["source"]
        target.unlink()
        real = path.parent / "real"
        real.write_bytes(b"main-a\n")
        try:
            target.symlink_to(real.name)
        except OSError as exc:
            if getattr(exc, "winerror", None) == 1314:
                self.skipTest("Windows process lacks symlink privilege")
            raise
        with self.assertRaisesRegex(sc.ComposerError, "crosses symlink"):
            sc.load_component(path)

    def test_strict_json_duplicate_key_and_nan_fail(self):
        with self.assertRaisesRegex(sc.ComposerError, "duplicate JSON key"):
            sc._strict_json(b'{"a":1,"a":2}', "x")
        with self.assertRaisesRegex(sc.ComposerError, "non-finite"):
            sc._strict_json(b'{"a":NaN}', "x")

    def test_deterministic_archive_bytes(self):
        left = sc.archive_bytes(dict(self.base))
        right = sc.archive_bytes(dict(reversed(list(self.base.items()))))
        self.assertEqual(left, right)
        self.assertEqual(sc.archive_members(left), self.base)

    def test_compose_rejects_wrong_production_baseline(self):
        path = self.manifest("p01", {"main.py": (b"base-main\n", b"main-a\n")})
        with self.assertRaisesRegex(sc.ComposerError, "exact production-v3"):
            sc.compose(sc.archive_bytes(self.base), self.load(path))

    def test_compose_receipt_on_bound_baseline(self):
        path = self.manifest("p01", {"main.py": (b"base-main\n", b"main-a\n")})
        components = self.load(path)
        raw = sc.archive_bytes(self.base)
        with patch.object(sc, "BASELINE_SHA256", h(raw)):
            packed, receipt = sc.compose(raw, components)
        self.assertEqual(receipt["candidate_archive_sha256"], h(packed))
        self.assertEqual(receipt["member_count"], 3)
        self.assertTrue(receipt["kaggle_submission_hold"])

    def test_publish_pair_collision_rolls_back_owned_archive(self):
        out = self.root / "candidate.tar.gz"
        receipt = self.root / "receipt.json"
        receipt.write_bytes(b"sentinel")
        with self.assertRaises(FileExistsError):
            sc.publish_pair(out, receipt, b"archive", b"receipt")
        self.assertFalse(out.exists())
        self.assertEqual(receipt.read_bytes(), b"sentinel")

    def test_publish_pair_write_failure_rolls_back_both_owned_outputs(self):
        out = self.root / "candidate.tar.gz"
        receipt = self.root / "receipt.json"
        import publication_custody as pc
        original = pc._write_all
        calls = 0

        def fail_second(fd, raw):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected receipt write failure")
            return original(fd, raw)

        with patch.object(pc, "_write_all", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "injected receipt write failure"):
                sc.publish_pair(out, receipt, b"archive", b"receipt")
        self.assertFalse(out.exists())
        self.assertFalse(receipt.exists())

    def test_publish_pair_alias_rejected_before_creation(self):
        out = self.root / "same-output"
        with self.assertRaisesRegex(sc.ComposerError, "must differ"):
            sc.publish_pair(out, out, b"archive", b"receipt")
        self.assertFalse(out.exists())

    def test_no_components_fails(self):
        with self.assertRaisesRegex(sc.ComposerError, "at least one component"):
            sc.compose_files(self.base, [])


if __name__ == "__main__":
    unittest.main()
