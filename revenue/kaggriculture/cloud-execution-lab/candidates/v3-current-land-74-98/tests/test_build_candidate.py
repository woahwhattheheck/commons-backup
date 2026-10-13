# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from build_candidate import SourceMember, _gzip_bytes, _tar_bytes, build_candidate, read_archive, sha256


class CandidateBuildContracts(unittest.TestCase):
    def fixture(self, directory: Path) -> tuple[Path, str, str, str]:
        files = {
            "main.py": SourceMember(b"def agent(o, c=None): return {}\n", 0o644),
            "TITAN-CONFIG.json": SourceMember(b"{}\n", 0o644),
            "module.py": SourceMember(b"VALUE = 7\n", 0o644),
            "sub/data.txt": SourceMember(b"stable\n", 0o600),
        }
        archive = directory / "base.tar.gz"
        archive.write_bytes(_gzip_bytes(_tar_bytes(files)))
        return archive, sha256(archive.read_bytes()), sha256(files["main.py"].data), sha256(files["TITAN-CONFIG.json"].data)

    def test_deterministic_build_and_exact_delta(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base, base_sha, main_sha, config_sha = self.fixture(root)
            first, second = root / "one.tar.gz", root / "two.tar.gz"
            args = dict(expected_archive_sha256=base_sha, expected_main_sha256=main_sha,
                        expected_config_sha256=config_sha)
            report1 = build_candidate(base, first, **args)
            report2 = build_candidate(base, second, **args)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(report1["candidate_archive_sha256"], report2["candidate_archive_sha256"])
            before, after = read_archive(base), read_archive(first)
            self.assertEqual(set(before) - set(after), set())
            self.assertEqual(set(after) - set(before), {"canonical_main.py", "land_overlay.py", "LAND-74-98.json"})
            self.assertEqual(after["canonical_main.py"].data, before["main.py"].data)
            self.assertEqual(after["module.py"].data, before["module.py"].data)
            self.assertEqual(after["sub/data.txt"].data, before["sub/data.txt"].data)
            self.assertNotEqual(after["main.py"].data, before["main.py"].data)
            self.assertEqual(report1["changed_existing_members"], ["main.py"])

    def test_wrong_pins_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base, base_sha, main_sha, config_sha = self.fixture(root)
            with self.assertRaisesRegex(ValueError, "archive SHA-256 mismatch"):
                build_candidate(base, root / "out.tar.gz", expected_archive_sha256="0" * 64,
                                expected_main_sha256=main_sha, expected_config_sha256=config_sha)
            with self.assertRaisesRegex(ValueError, "main.py SHA-256 mismatch"):
                build_candidate(base, root / "out.tar.gz", expected_archive_sha256=base_sha,
                                expected_main_sha256="0" * 64, expected_config_sha256=config_sha)


    def test_safe_name_preserves_dot_prefixed_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dotfile.tar.gz"
            files = {".policy": SourceMember(b"strict\n", 0o600)}
            path.write_bytes(_gzip_bytes(_tar_bytes(files)))
            members = read_archive(path)
            self.assertIn(".policy", members)
            self.assertEqual(members[".policy"].data, b"strict\n")

    def test_backslash_member_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unsafe-backslash.tar.gz"
            raw = io.BytesIO()
            with tarfile.open(fileobj=raw, mode="w") as archive:
                info = tarfile.TarInfo("..\\escape")
                payload = b"x"
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            path.write_bytes(_gzip_bytes(raw.getvalue()))
            with self.assertRaisesRegex(ValueError, "unsafe archive member"):
                read_archive(path)

    def test_unsafe_tar_member_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unsafe.tar.gz"
            raw = io.BytesIO()
            with tarfile.open(fileobj=raw, mode="w") as archive:
                info = tarfile.TarInfo("../escape")
                payload = b"x"
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            path.write_bytes(_gzip_bytes(raw.getvalue()))
            with self.assertRaisesRegex(ValueError, "unsafe archive member"):
                read_archive(path)


if __name__ == "__main__":
    unittest.main()
