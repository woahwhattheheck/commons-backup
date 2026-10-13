from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "verify_payload_packet.py"
spec = importlib.util.spec_from_file_location("verify_payload_packet", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def identity(data: bytes) -> dict[str, object]:
    return {
        "size": len(data),
        "git_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def manifest(members, packet="defensive-guard") -> bytes:
    return json.dumps({"schema": mod.SCHEMA, "packet": packet, "members": members},
                      sort_keys=True, separators=(",", ":")).encode()


class PayloadVerifierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "packet"
        self.root.mkdir()
        self.manifest_path = Path(self.tmp.name) / "manifest.json"

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, rel: str, data: bytes) -> dict[str, object]:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {"path": rel, **identity(data)}

    def run_main(self, raw: bytes | None = None):
        if raw is not None:
            self.manifest_path.write_bytes(raw)
        out = io.StringIO()
        with redirect_stdout(out):
            code = mod.main([str(self.manifest_path), str(self.root)])
        return code, json.loads(out.getvalue())

    def test_accepts_exact_nested_packet_and_receipt_is_deterministic(self):
        a = self.add("src/r04_defensive_guards.py", b"print('guard')\n")
        b = self.add("tests/test_v4_defensive_guards.py", b"# exact\n")
        raw = manifest([b, a])
        code1, receipt1 = self.run_main(raw)
        code2, receipt2 = self.run_main(raw)
        self.assertEqual(0, code1)
        self.assertEqual(receipt1, receipt2)
        self.assertTrue(receipt1["packet_verified"])
        self.assertEqual(["src/r04_defensive_guards.py", "tests/test_v4_defensive_guards.py"],
                         [row["path"] for row in receipt1["members"]])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt1["manifest_sha256"])

    def test_rejects_size_git_and_sha256_mismatch_together(self):
        row = self.add("a.py", b"abc")
        row = dict(row, size=9, git_blob="0" * 40, sha256="1" * 64)
        code, receipt = self.run_main(manifest([row]))
        self.assertEqual(1, code)
        self.assertEqual("packet_mismatch", receipt["error_kind"])
        self.assertIn('"fields": ["size", "git_blob", "sha256"]', receipt["error"])

    def test_rejects_missing_and_extra_members(self):
        a = self.add("a", b"a")
        (self.root / "extra").write_bytes(b"x")
        b = {"path": "missing", **identity(b"m")}
        code, receipt = self.run_main(manifest([a, b]))
        self.assertEqual(1, code)
        self.assertIn('"extras": ["extra"]', receipt["error"])
        self.assertIn('"missing": ["missing"]', receipt["error"])

    def test_rejects_traversal_absolute_backslash_and_noncanonical_paths(self):
        good = identity(b"x")
        for bad in ("../x", "/x", "a\\b", "a//b", "a/./b"):
            with self.subTest(path=bad):
                raw = manifest([{"path": bad, **good}])
                code, receipt = self.run_main(raw)
                self.assertEqual(2, code)
                self.assertEqual("invalid_evidence", receipt["error_kind"])

    def test_rejects_duplicate_and_casefold_colliding_paths(self):
        row1 = {"path": "A.py", **identity(b"x")}
        row2 = {"path": "a.py", **identity(b"y")}
        raw = manifest([row1, row2])
        code, receipt = self.run_main(raw)
        self.assertEqual(2, code)
        self.assertIn("case-folding", receipt["error"])
        raw_obj = {"schema": mod.SCHEMA, "packet": "x", "members": [row1, row1]}
        code, receipt = self.run_main(json.dumps(raw_obj).encode())
        self.assertEqual(2, code)
        self.assertIn("duplicate member path", receipt["error"])

    def test_rejects_bool_size_unknown_keys_and_uppercase_digests(self):
        base = {"path": "a", **identity(b"x")}
        variants = [
            dict(base, size=True),
            dict(base, surprise="x"),
            dict(base, git_blob=str(base["git_blob"]).upper()),
            dict(base, sha256=str(base["sha256"]).upper()),
        ]
        for row in variants:
            with self.subTest(row=row):
                code, receipt = self.run_main(manifest([row]))
                self.assertEqual(2, code)
                self.assertEqual("invalid_evidence", receipt["error_kind"])

    def test_rejects_duplicate_json_keys_and_nonfinite_json(self):
        raw = b'{"schema":"titan-v4-payload-packet/v1","schema":"x","packet":"p","members":[]}'
        code, receipt = self.run_main(raw)
        self.assertEqual(2, code)
        self.assertIn("duplicate", receipt["error"])
        raw = b'{"schema":"titan-v4-payload-packet/v1","packet":"p","members":NaN}'
        code, receipt = self.run_main(raw)
        self.assertEqual(2, code)
        self.assertIn("non-finite", receipt["error"])

    def test_rejects_symlink_file_and_symlink_directory(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlink unsupported")
        target = Path(self.tmp.name) / "outside"
        target.write_bytes(b"secret")
        os.symlink(target, self.root / "link")
        code, receipt = self.run_main(manifest([{"path": "link", **identity(b"secret")}]))
        self.assertEqual(2, code)
        self.assertIn("symlink", receipt["error"])

        (self.root / "link").unlink()
        d = Path(self.tmp.name) / "outside-dir"
        d.mkdir()
        (d / "x").write_bytes(b"x")
        os.symlink(d, self.root / "dir")
        code, receipt = self.run_main(manifest([{"path": "dir/x", **identity(b"x")}]))
        self.assertEqual(2, code)
        self.assertIn("symlink", receipt["error"])

    def test_rejects_nonregular_entry(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("fifo unsupported")
        os.mkfifo(self.root / "pipe")
        code, receipt = self.run_main(manifest([{"path": "pipe", **identity(b"")}]))
        self.assertEqual(2, code)
        self.assertIn("non-regular", receipt["error"])

    def test_optimized_mode_has_same_accept_and_reject_semantics(self):
        good = self.add("a", b"abc")
        raw = manifest([good])
        self.manifest_path.write_bytes(raw)
        normal = subprocess.run([sys.executable, str(MODULE_PATH), str(self.manifest_path), str(self.root)],
                                capture_output=True, text=True, check=False)
        optimized = subprocess.run([sys.executable, "-O", str(MODULE_PATH), str(self.manifest_path), str(self.root)],
                                   capture_output=True, text=True, check=False)
        self.assertEqual(normal.returncode, optimized.returncode)
        self.assertEqual(json.loads(normal.stdout), json.loads(optimized.stdout))

        (self.root / "a").write_bytes(b"changed")
        normal = subprocess.run([sys.executable, str(MODULE_PATH), str(self.manifest_path), str(self.root)],
                                capture_output=True, text=True, check=False)
        optimized = subprocess.run([sys.executable, "-O", str(MODULE_PATH), str(self.manifest_path), str(self.root)],
                                   capture_output=True, text=True, check=False)
        self.assertEqual(1, normal.returncode)
        self.assertEqual(normal.returncode, optimized.returncode)
        self.assertEqual(json.loads(normal.stdout), json.loads(optimized.stdout))


if __name__ == "__main__":
    unittest.main()
