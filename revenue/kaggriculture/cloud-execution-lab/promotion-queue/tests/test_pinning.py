# SPDX-License-Identifier: Apache-2.0
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pq.pinning import PinStore, canonical_json, sha256_bytes


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


class PinningTests(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.store = PinStore(Path(self.td.name) / "pins")

    def tearDown(self):
        self.td.cleanup()

    def test_pin_is_deterministic_for_identical_bytes(self):
        root = Path(self.td.name)
        first = self.store.pin(
            {
                "artifact": _write(root / "a.bin", b"candidate-bytes"),
                "games": _write(root / "g.jsonl", b"{}\n"),
            }
        )
        # same bytes, different file names -> same pin id and digest
        second = self.store.pin(
            {
                "artifact": _write(root / "a2.bin", b"candidate-bytes"),
                "games": _write(root / "g2.jsonl", b"{}\n"),
            }
        )
        self.assertEqual(first["pin_id"], second["pin_id"])
        self.assertEqual(first["input_digest"], second["input_digest"])

    def test_different_bytes_give_different_pins(self):
        root = Path(self.td.name)
        first = self.store.pin({"artifact": _write(root / "a.bin", b"v1")})
        second = self.store.pin({"artifact": _write(root / "a.bin", b"v2")})
        self.assertNotEqual(first["pin_id"], second["pin_id"])
        self.assertNotEqual(first["input_digest"], second["input_digest"])

    def test_blob_is_content_addressed_and_idempotent(self):
        root = Path(self.td.name)
        rec1 = self.store.put_blob(_write(root / "a.bin", b"bytes"))
        rec2 = self.store.put_blob(_write(root / "b.bin", b"bytes"))
        self.assertEqual(rec1["sha256"], rec2["sha256"])
        self.assertEqual(rec1["stored_as"], rec2["stored_as"])
        self.assertEqual(self.store.blob_path(rec1["sha256"]).read_bytes(), b"bytes")

    def test_verify_pin_detects_tampered_blob(self):
        root = Path(self.td.name)
        manifest = self.store.pin({"artifact": _write(root / "a.bin", b"original")})
        digest = manifest["inputs"]["artifact"]["sha256"]
        # tamper with the stored blob bytes
        (self.store.blobs / digest).write_bytes(b"tampered")
        ok, problems = self.store.verify_pin(manifest["pin_id"])
        self.assertFalse(ok)
        self.assertTrue(any("artifact" in p for p in problems))

    def test_verify_pin_detects_tampered_manifest(self):
        root = Path(self.td.name)
        manifest = self.store.pin({"artifact": _write(root / "a.bin", b"original")})
        path = self.store.pins / f"{manifest['pin_id']}.json"
        import json
        doc = json.loads(path.read_text())
        doc["input_digest"] = "0" * 64
        path.write_text(json.dumps(doc))
        ok, problems = self.store.verify_pin(manifest["pin_id"])
        self.assertFalse(ok)
        self.assertTrue(any("input_digest" in p for p in problems))

    def test_canonical_json_is_stable(self):
        value = {"b": [3, 2, 1], "a": {"z": 1, "y": 2}}
        self.assertEqual(canonical_json(value), canonical_json(dict(value)))
        self.assertEqual(
            sha256_bytes(canonical_json(value)),
            sha256_bytes(canonical_json(value)),
        )

    def test_pin_missing_input_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.store.pin({"artifact": Path(self.td.name) / "nope.bin"})


if __name__ == "__main__":
    unittest.main()
