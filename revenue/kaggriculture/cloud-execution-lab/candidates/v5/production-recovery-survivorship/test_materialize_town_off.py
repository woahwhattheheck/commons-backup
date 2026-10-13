# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import materialize_town_off as m

EXACT_CONFIG = b'''{
  "consumer": "frozen",
  "seed": true,
  "funding": true,
  "terminal_route": false,
  "committed": true,
  "budget_seconds": 1.0,
  "reserve_seconds": 0.01,
  "terminal_history": false,
  "redundant_hire": true,
  "fourth_quadrant": false,
  "market_pressure": true,
  "committed_seed_retry": false,
  "operating_stock": true,
  "idle_fertilizer": true,
  "crop_release": true,
  "early_capital": true,
  "town_procurement": true
}
'''


class TownSurvivorshipTest(unittest.TestCase):
    def baseline(self):
        return {
            "TITAN-CONFIG.json": EXACT_CONFIG,
            "main.py": b"print('retained')\n",
            "reference/x.txt": b"x\n",
        }

    def test_exact_config_identity(self):
        self.assertEqual(m.digest(EXACT_CONFIG), m.BASELINE_CONFIG_SHA256)
        baseline = self.baseline()
        treatment = m.treatment_members(baseline)
        changed = [name for name, body in baseline.items() if body != treatment[name]]
        self.assertEqual(changed, ["TITAN-CONFIG.json"])
        self.assertEqual(m.digest(treatment["TITAN-CONFIG.json"]), m.TREATMENT_CONFIG_SHA256)
        config = json.loads(treatment["TITAN-CONFIG.json"])
        self.assertIs(config["town_procurement"], False)
        self.assertEqual(treatment["main.py"], baseline["main.py"])
        self.assertEqual(treatment["reference/x.txt"], baseline["reference/x.txt"])

    def test_wrong_config_is_rejected(self):
        baseline = self.baseline()
        baseline["TITAN-CONFIG.json"] = EXACT_CONFIG.replace(
            b'"town_procurement": true', b'"town_procurement": false'
        )
        with self.assertRaisesRegex(ValueError, "exact production-recovery config"):
            m.treatment_members(baseline)

    def test_receipt_binds_only_config_delta(self):
        baseline = self.baseline()
        treatment = m.treatment_members(baseline)
        packed = m.archive_bytes(treatment)
        receipt = m.receipt_for(baseline, treatment, packed)
        self.assertEqual(receipt["changed_members"], ["TITAN-CONFIG.json"])
        self.assertEqual(receipt["baseline_config_sha256"], m.BASELINE_CONFIG_SHA256)
        self.assertEqual(receipt["treatment"]["config_sha256"], m.TREATMENT_CONFIG_SHA256)
        self.assertEqual(receipt["treatment"]["archive_sha256"], m.digest(packed))
        self.assertEqual(receipt["native_economics_status"], "PENDING_BASE_PRODUCTION_PANEL")
        self.assertTrue(receipt["kaggle_submission_hold"])

    def test_archive_bytes_are_deterministic_and_canonical(self):
        treatment = m.treatment_members(self.baseline())
        first = m.archive_bytes(treatment)
        second = m.archive_bytes(treatment)
        self.assertEqual(first, second)
        parsed = m.parse_archive_bytes(first, m.digest(first))
        self.assertEqual(parsed, treatment)

    def test_parser_rejects_nonregular_member(self):
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w:gz") as archive:
            info = tarfile.TarInfo("bad-link")
            info.type = tarfile.SYMTYPE
            info.linkname = "TITAN-CONFIG.json"
            archive.addfile(info)
        payload = raw.getvalue()
        with self.assertRaisesRegex(ValueError, "Noncanonical archive member"):
            m.parse_archive_bytes(payload, m.digest(payload))

    def test_parser_rejects_wrong_identity(self):
        payload = m.archive_bytes(self.baseline())
        with self.assertRaisesRegex(ValueError, "Archive identity mismatch"):
            m.parse_archive_bytes(payload, "0" * 64)

    def test_pair_publication_rolls_back_first_reservation_if_receipt_is_taken(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "town-off.tar.gz"
            receipt = Path(temp) / "town-off.json"
            receipt.write_bytes(b"sentinel")
            with self.assertRaises(FileExistsError):
                m._publish_pair(out, b"candidate", receipt, {"schema": "test"})
            self.assertFalse(out.exists())
            self.assertEqual(receipt.read_bytes(), b"sentinel")

    def test_pair_publication_writes_both_reserved_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "town-off.tar.gz"
            receipt = Path(temp) / "town-off.json"
            payload = b"candidate"
            document = {"schema": "test", "archive_sha256": m.digest(payload)}
            m._publish_pair(out, payload, receipt, document)
            self.assertEqual(out.read_bytes(), payload)
            self.assertEqual(json.loads(receipt.read_text()), document)

    def test_pair_publication_rolls_back_both_on_receipt_write_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "town-off.tar.gz"
            receipt = Path(temp) / "town-off.json"
            with mock.patch.object(m.json, "dump", side_effect=OSError("receipt write failed")):
                with self.assertRaisesRegex(OSError, "receipt write failed"):
                    m._publish_pair(out, b"candidate", receipt, {"schema": "test"})
            self.assertFalse(out.exists())
            self.assertFalse(receipt.exists())


if __name__ == "__main__":
    unittest.main()
