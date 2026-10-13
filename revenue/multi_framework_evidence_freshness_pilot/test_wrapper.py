from __future__ import annotations

import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from revenue.multi_framework_evidence_freshness import gate
from revenue.multi_framework_evidence_freshness.golden import build_golden_input

from . import cli
from .wrapper import (
    MAX_EVIDENCE_OBJECTS,
    PRICE_STATUS,
    compile_diagnostic,
    render_buyer_page,
    verify_diagnostic,
)

FIXED_NOW = dt.datetime(2026, 9, 16, 22, 30, 0, tzinfo=dt.timezone.utc)


class WrapperTests(unittest.TestCase):
    def test_golden_compiles_and_verifies(self) -> None:
        with mock.patch.object(gate, "_now_utc", return_value=FIXED_NOW):
            envelope = compile_diagnostic(build_golden_input())
            digest = verify_diagnostic(envelope)
        self.assertEqual(digest, envelope["diagnostic_sha256"])
        counts = envelope["diagnostic"]["summary"]["counts"]
        self.assertEqual(sum(counts.values()), 400)
        self.assertEqual(counts["REUSABLE"], 240)
        self.assertEqual(counts["STALE"], 50)
        self.assertEqual(counts["SCOPE_MISMATCH"], 40)
        self.assertEqual(counts["MISSING_OWNER"], 35)
        self.assertEqual(counts["INCOMPLETE"], 35)
        self.assertEqual(envelope["diagnostic"]["offer"]["status"], PRICE_STATUS)
        self.assertEqual(envelope["diagnostic"]["offer"]["diagnostic_cents"], 350000)
        self.assertEqual(envelope["diagnostic"]["offer"]["integration_sprint_cents"], 1000000)
        self.assertEqual(envelope["diagnostic"]["scope"]["max_evidence_objects"], MAX_EVIDENCE_OBJECTS)
        page = render_buyer_page(envelope)
        self.assertIn("Evidence Freshness Diagnostic", page)
        self.assertIn("PROPOSED_NOT_ACCEPTED", page)
        self.assertIn("$3,500", page)
        self.assertIn("$10,000", page)
        self.assertTrue(all(v is False for v in envelope["diagnostic"]["authority"].values()))

    def test_order_invariance(self) -> None:
        raw = build_golden_input()
        # Engine receipts/projections include evaluated_at; pin the clock so
        # order-invariance is not confused with a wall-clock second boundary.
        with mock.patch.object(gate, "_now_utc", return_value=FIXED_NOW):
            a = compile_diagnostic(copy.deepcopy(raw))
            altered = copy.deepcopy(raw)
            altered["evidence"] = list(reversed(altered["evidence"]))
            b = compile_diagnostic(altered)
            self.assertEqual(a["diagnostic"]["summary"]["counts"], b["diagnostic"]["summary"]["counts"])
            self.assertEqual(a["diagnostic"]["binding"]["input_sha256"], b["diagnostic"]["binding"]["input_sha256"])
            self.assertEqual(a["diagnostic"]["binding"]["projection_sha256"], b["diagnostic"]["binding"]["projection_sha256"])
            self.assertEqual(verify_diagnostic(a), a["diagnostic_sha256"])
            self.assertEqual(verify_diagnostic(b), b["diagnostic_sha256"])

    def test_cli_roundtrip(self) -> None:
        raw = build_golden_input()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "in.json"
            out = root / "diag.json"
            md = root / "page.md"
            src.write_text(json.dumps(raw), encoding="utf-8")
            with mock.patch.object(gate, "_now_utc", return_value=FIXED_NOW):
                self.assertEqual(cli.main(["compile", str(src), str(out), str(md)]), 0)
                self.assertEqual(cli.main(["verify", str(out)]), 0)
            self.assertTrue(md.read_text(encoding="utf-8").startswith("# Evidence Freshness Diagnostic"))


if __name__ == "__main__":
    unittest.main()
