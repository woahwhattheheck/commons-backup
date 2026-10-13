# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import hashlib
import json
import tempfile
import unittest

import grain_debt_audit as g

EXPECTED_OPERATING_STOCK_BLOB = "781aa90da0d85d0ba23c665e29d6087d182c085e"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def event(reason=None, *, sale=5, changed=False, certified=False, step=401, **feed):
    diagnostics = {}
    if reason is not None:
        diagnostics["feed_stock"] = {
            "reason": reason, "changed": changed, "certified": certified, **feed
        }
    return {
        "step": step,
        "returned_action": {"farmer": ["PASS"], "hands": [], "market": [["SELL", "WHEAT", sale]]},
        "diagnostics": diagnostics,
    }


class GrainDebtAuditTests(unittest.TestCase):
    def test_cap_witness_matches_live_boundary(self):
        self.assertEqual(g.cap_witness(stock=5, offered=5, required=3), {
            "coverable": True, "permitted_sale": 2, "withheld_units": 3, "cap_bypass": True
        })

    def test_two_unit_reservation_does_not_cross_cap(self):
        self.assertEqual(g.cap_witness(stock=5, offered=5, required=2)["withheld_units"], 2)
        self.assertFalse(g.cap_witness(stock=5, offered=5, required=2)["cap_bypass"])

    def test_uncoverable_obligation_is_not_mislabeled_cap(self):
        row = g.cap_witness(stock=1, offered=1, required=2)
        self.assertFalse(row["coverable"])
        self.assertFalse(row["cap_bypass"])

    def test_cap_reason_with_returned_sale_is_target_event(self):
        row = g.classify_event(event(g.CAP_REASON))
        self.assertEqual(row["classification"], "CAP_BYPASS_RETURNED_SALE")
        self.assertEqual(row["returned_wheat_sale"], 5)

    def test_changed_certified_reservation_is_not_bypass(self):
        row = g.classify_event(event("reserve_reachable_feed", sale=2, changed=True, certified=True,
                                     required_wheat=3, withheld_units=3))
        self.assertEqual(row["classification"], "GUARD_RESERVED_FEED")

    def test_certified_covered_is_separate(self):
        row = g.classify_event(event("feed_prefix_already_covered", certified=True))
        self.assertEqual(row["classification"], "FEED_ALREADY_COVERED")

    def test_binding_gap_is_visible(self):
        row = g.classify_event(event("no_matching_completed_unit_snapshot"))
        self.assertEqual(row["classification"], "BINDING_GAP_RETURNED_SALE")

    def test_no_returned_sale_takes_precedence(self):
        row = g.classify_event(event(g.CAP_REASON, sale=0))
        self.assertEqual(row["classification"], "NO_RETURNED_WHEAT_SALE")

    def test_only_executable_prefix_is_counted(self):
        action = {"market": [["SELL", "WHEAT", 1]] + [[] for _ in range(9)] + [["SELL", "WHEAT", 99]]}
        self.assertEqual(g.wheat_sale_quantity(action), 1)

    def test_malformed_sale_fails_closed(self):
        with self.assertRaises(ValueError):
            g.wheat_sale_quantity({"market": [["SELL", "WHEAT", "5"]]})

    def test_summary_does_not_claim_starvation(self):
        out = g.summarize([
            event(g.CAP_REASON, step=401),
            event("reserve_reachable_feed", sale=2, changed=True, certified=True, step=402),
            event("feed_prefix_already_covered", sale=1, certified=True, step=403),
        ])
        self.assertEqual(out["cap_bypass"]["events"], 1)
        self.assertEqual(out["cap_bypass"]["steps"], [401])
        self.assertEqual(out["cap_bypass"]["causal_status"], "REQUIRES_DOWNSTREAM_FEED_OUTCOME_CORRELATION")
        self.assertFalse(out["policy_mutation"])

    def test_cli_jsonl_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "events.jsonl"
            target = Path(td) / "out.json"
            source.write_text(json.dumps(event(g.CAP_REASON)) + "\n", encoding="utf-8")
            self.assertEqual(g.main([str(source), "--output", str(target)]), 0)
            result = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(result["cap_bypass"]["events"], 1)

    def test_repository_source_contract_if_checkout_present(self):
        here = Path(__file__).resolve().parent
        # operating-stock-prefix -> gameplay -> repairs -> v4 -> candidates -> cloud-execution-lab
        root = here.parents[4] if len(here.parents) > 4 else None
        source = None if root is None else root / "operating_stock.py"
        runtime = None if root is None else root / "titan_runtime.py"
        config = None if root is None else root / "TITAN-CONFIG.json"
        if source is None or not source.is_file() or not runtime.is_file() or not config.is_file():
            self.skipTest("full repository checkout unavailable")
        data = source.read_bytes()
        self.assertEqual(git_blob(data), EXPECTED_OPERATING_STOCK_BLOB)
        text = data.decode()
        self.assertIn("if withheld > 2:raise ValueError('feed_reservation_exceeds_two_units')", text)
        self.assertIn("permitted = min(stock, max(0, stock + returned_wheat - required))", text)
        runtime_text = runtime.read_text(encoding="utf-8")
        self.assertIn("returned = self._feed_stock_selected(obs, cfg or {}, returned)", runtime_text)
        self.assertIn("from operating_stock import protect_feed_stock", runtime_text)
        cfg = json.loads(config.read_text(encoding="utf-8"))
        self.assertIs(cfg.get("operating_stock"), True)


if __name__ == "__main__":
    unittest.main()
