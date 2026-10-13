# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import weed_evidence_certifier as gate
from weed_test_fixtures import *  # noqa: F403

class CliTests(unittest.TestCase):
    def test_cli_round_trip_and_quarantine_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "spatial.py").write_bytes(LEGACY_SPATIAL)
            (root / "runtime.py").write_bytes(LEGACY_RUNTIME)
            (root / "main.py").write_bytes(FIXED_ENTRYPOINT)
            (root / "config.json").write_bytes(LEGACY_CONFIG)
            receipt = root / "receipt.json"
            claim = root / "claim.json"
            decision = root / "decision.json"
            self.assertEqual(
                gate.main(
                    [
                        "certify",
                        "--spatial",
                        str(root / "spatial.py"),
                        "--runtime",
                        str(root / "runtime.py"),
                        "--entrypoint",
                        str(root / "main.py"),
                        "--config",
                        str(root / "config.json"),
                        "--revision",
                        "fixture",
                        "--output",
                        str(receipt),
                    ]
                ),
                0,
            )
            self.assertEqual(
                gate.main(
                    [
                        "make-claim",
                        "--receipt",
                        str(receipt),
                        "--claim-id",
                        "legacy-as-w0",
                        "--declared",
                        "W0",
                        "--label",
                        "R0P0O0",
                        "--output",
                        str(claim),
                    ]
                ),
                0,
            )
            self.assertEqual(
                gate.main(
                    [
                        "gate",
                        "--receipt",
                        str(receipt),
                        "--claim",
                        str(claim),
                        "--spatial",
                        str(root / "spatial.py"),
                        "--runtime",
                        str(root / "runtime.py"),
                        "--entrypoint",
                        str(root / "main.py"),
                        "--config",
                        str(root / "config.json"),
                        "--revision",
                        "fixture",
                        "--output",
                        str(decision),
                    ]
                ),
                2,
            )
            self.assertEqual(json.loads(decision.read_text())["decision"], "QUARANTINE")


if __name__ == "__main__":
    unittest.main()
