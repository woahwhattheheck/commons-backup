from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import adapter


class OutputAliasTests(unittest.TestCase):
    def _args(self, detections: Path, config: Path, output: Path) -> list[str]:
        return [
            "--detections", str(detections),
            "--config", str(config),
            "--output", str(output),
            "--max-search-radius", "8.5",
            "--zlo", "0", "--zhi", "10",
            "--ylo", "0", "--yhi", "10",
            "--xlo", "0", "--xhi", "10",
        ]

    def _files(self, root: Path) -> tuple[Path, Path]:
        detections = root / "detections.csv"
        with detections.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=adapter.INPUT_COLUMNS)
            writer.writeheader()
            writer.writerow({"dataset": "demo", "detection_id": 1, "t": 0, "z": 1, "y": 2, "x": 3})
        config = root / "config.json"
        config.write_bytes(b'{"sentinel":"keep-config-bytes"}\n')
        return detections, config

    def _assert_rejected_unchanged(self, alias: str) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            detections, config = self._files(root)
            before_detections = detections.read_bytes()
            before_config = config.read_bytes()
            output = detections if alias == "detections" else config
            with patch("adapter.solve_all", side_effect=AssertionError("solver must not run")):
                with self.assertRaises(SystemExit) as raised:
                    adapter.main(self._args(detections, config, output))
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(detections.read_bytes(), before_detections)
            self.assertEqual(config.read_bytes(), before_config)

    def test_output_cannot_alias_detections(self):
        self._assert_rejected_unchanged("detections")

    def test_output_cannot_alias_configuration(self):
        self._assert_rejected_unchanged("config")

    def _assert_hardlink_rejected_unchanged(self, alias: str) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            detections, config = self._files(root)
            before_detections = detections.read_bytes()
            before_config = config.read_bytes()
            source = detections if alias == "detections" else config
            output = root / "submission.csv"
            os.link(source, output)
            self.assertNotEqual(output.resolve(), source.resolve())
            self.assertTrue(output.samefile(source))
            with patch("adapter.solve_all", side_effect=AssertionError("solver must not run")):
                with self.assertRaises(SystemExit) as raised:
                    adapter.main(self._args(detections, config, output))
            self.assertEqual(raised.exception.code, 2)
            self.assertEqual(detections.read_bytes(), before_detections)
            self.assertEqual(config.read_bytes(), before_config)

    def test_output_hardlink_cannot_alias_detections(self):
        self._assert_hardlink_rejected_unchanged("detections")

    def test_output_hardlink_cannot_alias_configuration(self):
        self._assert_hardlink_rejected_unchanged("config")


if __name__ == "__main__":
    unittest.main(verbosity=2)
