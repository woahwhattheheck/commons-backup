from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import adapter


class AtomicOutputTests(unittest.TestCase):
    def _row(self) -> dict[str, object]:
        return {
            "id": 0,
            "dataset": "demo",
            "row_type": "node",
            "node_id": 0,
            "t": 0,
            "z": 1,
            "y": 2,
            "x": 3,
            "source_id": -1,
            "target_id": -1,
        }

    def test_malformed_row_preserves_existing_output_and_cleans_staging_file(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "submission.csv"
            before = b"known-good-submission\n"
            output.write_bytes(before)
            malformed = self._row()
            del malformed["target_id"]

            with self.assertRaises(adapter.AdapterError):
                adapter.write_submission(output, [self._row(), malformed])

            self.assertEqual(output.read_bytes(), before)
            self.assertEqual(list(root.glob(".submission.csv.*.tmp")), [])

    def test_valid_write_atomically_replaces_existing_output(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            output = root / "submission.csv"
            output.write_bytes(b"stale\n")

            adapter.write_submission(output, [self._row()])

            self.assertEqual(
                output.read_bytes(),
                (
                    b"id,dataset,row_type,node_id,t,z,y,x,source_id,target_id\r\n"
                    b"0,demo,node,0,0,1,2,3,-1,-1\r\n"
                ),
            )
            self.assertEqual(list(root.glob(".submission.csv.*.tmp")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
