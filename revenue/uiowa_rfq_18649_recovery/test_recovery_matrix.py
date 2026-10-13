"""Independent support-logic matrix; all input records are fictional.

Run: python -m unittest discover -s revenue/uiowa_rfq_18649_recovery -p 'test*.py'
Also run with real python -O. No network or deployment action is performed.
Source builder: ZZ-QUARTZ-17. Matrix reviewer: ZZ-QUARTZ-731 / GPT-6 Astra Pro.
"""
import copy
import importlib.util
import itertools
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("quartz731_recovery_matrix", ROOT / "recovery.py")
recovery = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(recovery)

FACTORS = (
    "procedure_available", "decision_available", "execution_available",
    "service_evidence_available", "data_evidence_available", "rollback_compatible",
    "actually_executed", "service_pass", "data_pass", "strategy_matches",
)
EVIDENCE_IDS = ("CFG-01-PROC", "CFG-01-DEC", "CFG-01-RUN", "CFG-01-SERVICE", "CFG-01-DATA")


class RecoverySupportMatrixTests(unittest.TestCase):
    def test_all_1024_support_combinations(self):
        original = json.loads((ROOT / "example.json").read_text(encoding="utf-8"))
        base = copy.deepcopy(original)
        base["scenarios"] = [next(s for s in base["scenarios"] if s["id"] == "CFG-01")]
        base["evidence"] = [e for e in base["evidence"] if e["scenario_id"] == "CFG-01"]
        scenario = base["scenarios"][0]
        scenario["change_kind"] = "data_migration"
        base["evidence"].append({
            "id": "CFG-01-DATA", "scenario_id": "CFG-01", "kind": "verification",
            "available": True, "recorded_at": "2026-09-18T10:16:00Z",
            "summary": "Fictional data-reconciliation record for this independent matrix.",
        })
        scenario["attempts"][0]["verification"].append({
            "aspect": "data", "result": "pass", "at": "2026-09-18T10:16:00Z",
            "evidence_refs": ["CFG-01-DATA"],
        })
        observed_positive = 0
        cases = 0
        for flags in itertools.product((False, True), repeat=len(FACTORS)):
            with self.subTest(**dict(zip(FACTORS, flags))):
                packet = copy.deepcopy(base)
                ledger = {e["id"]: e for e in packet["evidence"]}
                for evidence_id, available in zip(EVIDENCE_IDS, flags[:5]):
                    ledger[evidence_id]["available"] = available
                scenario = packet["scenarios"][0]
                attempt = scenario["attempts"][0]
                scenario["decision"]["rollback_compatible"] = flags[5]
                attempt["mode"] = "executed_rehearsal" if flags[6] else "tabletop"
                for check in attempt["verification"]:
                    check["result"] = "pass" if flags[7 if check["aspect"] == "service" else 8] else "unknown"
                scenario["decision"]["strategy"] = "rollback" if flags[9] else "forward_repair"
                report = recovery.assess(packet)["scenarios"][0]
                supported = report["state"] == "evidence_supported"
                self.assertEqual(supported, all(flags), report)
                if supported:
                    self.assertEqual(report["attempts"][0]["minutes"]["failure_to_verified_recovery"], 16.0)
                observed_positive += supported
                cases += 1
        self.assertEqual(cases, 1024)
        self.assertEqual(observed_positive, 1)
        self.assertEqual(json.loads((ROOT / "example.json").read_text(encoding="utf-8")), original)


if __name__ == "__main__":
    unittest.main()
