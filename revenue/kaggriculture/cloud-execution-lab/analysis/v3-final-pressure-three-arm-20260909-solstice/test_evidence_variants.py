from __future__ import annotations

import io
from pathlib import Path
import tarfile
import tempfile
import unittest

import evidence
import variants


class EvidenceVariantTests(unittest.TestCase):
    def test_pressure_config_patch_changes_only_boolean_token(self):
        original = b'{\n  "other": 7,\n  "market_pressure": true,\n  "name": "true"\n}\n'
        changed = variants.patch_pressure_off_config(original)
        self.assertEqual(
            changed,
            b'{\n  "other": 7,\n  "market_pressure": false,\n  "name": "true"\n}\n',
        )
        parsed = evidence.strict_json_bytes(changed, label="changed")
        self.assertIs(parsed["market_pressure"], False)
        self.assertEqual(parsed["other"], 7)

    def test_pressure_config_patch_rejects_duplicate_key(self):
        original = b'{"market_pressure": true, "market_pressure": true}'
        with self.assertRaises(evidence.EvidenceError):
            variants.patch_pressure_off_config(original)

    def test_legacy_patch_is_exact_and_one_shot(self):
        source = (
            b"def build():\n"
            b"    return FinalPressureAgent(features, "
            b"fourth_quadrant_admission=admission)\n"
        )
        changed = variants.patch_legacy_entrypoint(source)
        self.assertIn(variants.LEGACY_TO, changed)
        self.assertNotIn(variants.LEGACY_FROM, changed)
        with self.assertRaises(evidence.EvidenceError):
            variants.patch_legacy_entrypoint(changed)

    def test_prepare_variants_proves_single_path_deltas(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "runtime"
            destination = Path(directory) / "variants"
            base.mkdir()
            (base / "TITAN-CONFIG.json").write_text(
                '{\n  "market_pressure": true,\n  "early_capital": true\n}\n',
                encoding="utf-8",
            )
            (base / "main.py").write_text(
                "def build():\n"
                "    return FinalPressureAgent(features, "
                "fourth_quadrant_admission=admission)\n",
                encoding="utf-8",
            )
            (base / "stable.txt").write_text(
                "unchanged\n", encoding="utf-8"
            )
            rows, canonical = variants.prepare_variants(base, destination)
            self.assertEqual(
                [row["name"] for row in rows], list(variants.VARIANTS)
            )
            self.assertEqual(
                rows[0]["changed_paths"], ["TITAN-CONFIG.json"]
            )
            self.assertEqual(rows[1]["changed_paths"], ["main.py"])
            self.assertEqual(rows[2]["changed_paths"], [])
            self.assertEqual(rows[0]["main_sha256"], rows[2]["main_sha256"])
            self.assertEqual(
                rows[1]["config_sha256"], rows[2]["config_sha256"]
            )
            self.assertEqual(canonical["tree_file_count"], 3)
            self.assertEqual(
                (destination / "final_boundary" / "TITAN-CONFIG.json")
                .read_bytes(),
                (base / "TITAN-CONFIG.json").read_bytes(),
            )

    def test_safe_extract_rejects_symlink_and_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for name, configure in (
                (
                    "link.tar.gz",
                    lambda info: setattr(info, "type", tarfile.SYMTYPE),
                ),
                ("traversal.tar.gz", lambda info: None),
            ):
                archive = directory / name
                with tarfile.open(archive, "w:gz") as bundle:
                    member_name = (
                        "../../escape"
                        if name.startswith("traversal")
                        else "link"
                    )
                    info = tarfile.TarInfo(member_name)
                    info.size = 0
                    configure(info)
                    if info.issym():
                        info.linkname = "target"
                    bundle.addfile(info, io.BytesIO(b""))
                with self.assertRaises(evidence.EvidenceError):
                    evidence.safe_extract(
                        archive, directory / (name + ".out")
                    )

    def test_safe_extract_rejects_alias_and_type_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            alias = directory / "alias.tar.gz"
            with tarfile.open(alias, "w:gz") as bundle:
                for name in ("a/b.txt", "a//b.txt"):
                    data = b"x"
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    bundle.addfile(info, io.BytesIO(data))
            with self.assertRaises(evidence.EvidenceError):
                evidence.safe_extract(alias, directory / "alias-out")

            collision = directory / "collision.tar.gz"
            with tarfile.open(collision, "w:gz") as bundle:
                file_info = tarfile.TarInfo("node")
                file_info.size = 0
                bundle.addfile(file_info, io.BytesIO(b""))
                directory_info = tarfile.TarInfo("node/")
                directory_info.type = tarfile.DIRTYPE
                bundle.addfile(directory_info)
            with self.assertRaises(evidence.EvidenceError):
                evidence.safe_extract(
                    collision, directory / "collision-out"
                )

    def test_safe_extract_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            archive = directory / "good.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                data = b"payload"
                info = tarfile.TarInfo("a/b.txt")
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))
            members = evidence.safe_extract(archive, directory / "out")
            self.assertEqual(members, ["a/b.txt"])
            self.assertEqual(
                (directory / "out/a/b.txt").read_bytes(), b"payload"
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
