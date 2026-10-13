from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import assemble_requirements
import matrix


HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / "requirements.json.gz.b64"


class AssemblyTests(unittest.TestCase):
    def test_payload_materializes_exact_valid_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "requirements.json"
            digest = assemble_requirements.assemble(PAYLOAD, output)
            self.assertEqual(digest, assemble_requirements.EXPECTED_SHA256)
            receipt = matrix.build_receipt(matrix.load_matrix(output))
            self.assertEqual(receipt["counts"], {"PASS": 0, "RED": 0, "UNKNOWN": 13})

    def test_tampered_payload_is_rejected_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = root / "payload.b64"
            payload.write_bytes(PAYLOAD.read_bytes()[:-8] + b"AAAAAAAA")
            output = root / "requirements.json"
            with self.assertRaises(assemble_requirements.AssemblyError):
                assemble_requirements.assemble(payload, output)
            self.assertFalse(output.exists())

    def test_symlink_output_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.json"
            target.write_text("{}", encoding="utf-8")
            output = root / "requirements.json"
            try:
                output.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(assemble_requirements.AssemblyError, "symlink"):
                assemble_requirements.assemble(PAYLOAD, output)
            self.assertEqual(target.read_text(encoding="utf-8"), "{}")


if __name__ == "__main__":
    unittest.main()
