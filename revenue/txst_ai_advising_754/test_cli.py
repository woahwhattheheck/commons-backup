from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from . import cli


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = {
            "opportunity_id": "754-TXST-2027-RFP-513-VPGOI",
            "requested_posture": "AUTO",
            "owner_claims": {
                "legal_entity": "UNKNOWN",
                "higher_ed_references": "UNKNOWN",
                "named_key_personnel": "UNKNOWN",
                "insurance": "UNKNOWN",
                "financial_capacity": "UNKNOWN",
                "student_data_privacy": "UNKNOWN",
                "security": "UNKNOWN",
                "accessibility": "UNKNOWN",
                "integration_experience": "UNKNOWN",
                "implementation_support": "UNKNOWN",
                "ai_governance": "UNKNOWN",
            },
            "partner_claims": {"status": "NONE", "cures": []},
            "commercial": {"pricing_status": "OWNER_DECISION_REQUIRED", "staffing_status": "OWNER_DECISION_REQUIRED"},
        }

    def test_compile_and_verify_current_hold(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / "candidate.json"
            report = root / "report.json"
            candidate.write_text(json.dumps(self.candidate), encoding="utf-8")
            with mock.patch("revenue.txst_ai_advising_754.qualification._now_utc") as now:
                from datetime import datetime, timezone
                now.return_value = datetime(2026, 9, 16, 22, 30, tzinfo=timezone.utc)
                self.assertEqual(cli.main(["compile", "--candidate", str(candidate), "--out", str(report)]), 0)
                payload = json.loads(report.read_text(encoding="utf-8"))
                self.assertEqual(payload["state"], "HOLD_OFFICIAL_PACKET_REQUIRED")
                self.assertEqual(cli.main(["verify", "--candidate", str(candidate), "--report", str(report)]), 0)

    def test_compile_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / "candidate.json"
            report = root / "report.json"
            candidate.write_text(json.dumps(self.candidate), encoding="utf-8")
            report.write_text("occupied", encoding="utf-8")
            self.assertEqual(cli.main(["compile", "--candidate", str(candidate), "--out", str(report)]), 2)
            self.assertEqual(report.read_text(encoding="utf-8"), "occupied")

    def test_input_symlink_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "target.json"
            link = root / "link.json"
            target.write_text(json.dumps(self.candidate), encoding="utf-8")
            link.symlink_to(target)
            self.assertEqual(cli.main(["compile", "--candidate", str(link), "--out", str(root / "out.json")]), 2)

    def test_regular_file_swap_before_open_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / "candidate.json"
            replacement = root / "replacement.json"
            candidate.write_text(json.dumps(self.candidate), encoding="utf-8")
            replacement.write_text(json.dumps(self.candidate), encoding="utf-8")
            real_open = cli.os.open
            swapped = False

            def swapping_open(path, flags, *args):
                nonlocal swapped
                if not swapped and Path(path) == candidate:
                    swapped = True
                    cli.os.replace(replacement, candidate)
                return real_open(path, flags, *args)

            with mock.patch.object(cli.os, "open", side_effect=swapping_open):
                self.assertEqual(
                    cli.main(["compile", "--candidate", str(candidate), "--out", str(root / "out.json")]),
                    2,
                )
            self.assertFalse((root / "out.json").exists())


if __name__ == "__main__":
    unittest.main()
