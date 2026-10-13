from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from realized_fertilizer import (  # noqa: E402
    CERTIFICATE_SCHEMA,
    TRACE_SCHEMA,
    canonical_sha256,
    certify_realized_fertilizer,
)

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64

FIELDS = {
    "fertilizer_actions": 0,
    "produced_units": 0,
    "harvested_units": 0,
    "deposited_units": 0,
    "sold_units": 0,
    "cash": 50,
    "discarded_units": 0,
    "worker_ticks_used": 0,
    "travel_steps": 0,
    "watering_actions": 0,
    "harvest_actions": 0,
    "deposit_actions": 0,
    "sale_actions": 0,
    "protected_obligation_misses": 0,
    "protected_stock_shortfall_units": 0,
    "carry_units": 0,
    "shed_units": 2,
}


def snapshot(tick: int, **updates: int) -> dict[str, int]:
    row = {"tick": tick, **FIELDS}
    row.update(updates)
    return row


def identity() -> dict[str, object]:
    return {
        "engine_sha256": A,
        "evaluator_sha256": B,
        "opponent_sha256": C,
        "start_state_sha256": D,
        "counterfactual_protocol_sha256": E,
        "protected_commitments_sha256": F,
        "seed": 718,
        "controlled_player": 0,
        "horizon_tick": 10,
        "worker_tick_budget": 20,
        "product": "WHEAT",
    }


def control_trace() -> dict[str, object]:
    return {
        "schema": TRACE_SCHEMA,
        "variant": "control",
        "policy_sha256": A,
        "identity": identity(),
        "capacity": {"carry_units": 2, "shed_units": 4},
        "snapshots": [
            snapshot(0),
            snapshot(3, produced_units=1, worker_ticks_used=2, travel_steps=1, watering_actions=1),
            snapshot(5, produced_units=1, harvested_units=1, worker_ticks_used=4, travel_steps=2, watering_actions=1, harvest_actions=1, carry_units=1),
            snapshot(7, produced_units=1, harvested_units=1, deposited_units=1, worker_ticks_used=6, travel_steps=3, watering_actions=1, harvest_actions=1, deposit_actions=1, shed_units=3),
            snapshot(9, produced_units=1, harvested_units=1, deposited_units=1, sold_units=1, cash=56, worker_ticks_used=8, travel_steps=4, watering_actions=1, harvest_actions=1, deposit_actions=1, sale_actions=1),
            snapshot(10, produced_units=1, harvested_units=1, deposited_units=1, sold_units=1, cash=56, worker_ticks_used=8, travel_steps=4, watering_actions=1, harvest_actions=1, deposit_actions=1, sale_actions=1),
        ],
    }


def candidate_trace() -> dict[str, object]:
    return {
        "schema": TRACE_SCHEMA,
        "variant": "fertilized",
        "policy_sha256": B,
        "identity": identity(),
        "capacity": {"carry_units": 2, "shed_units": 4},
        "snapshots": [
            snapshot(0),
            snapshot(1, fertilizer_actions=1, worker_ticks_used=1),
            snapshot(3, fertilizer_actions=1, produced_units=2, worker_ticks_used=3, travel_steps=1, watering_actions=1),
            snapshot(5, fertilizer_actions=1, produced_units=2, harvested_units=2, worker_ticks_used=5, travel_steps=2, watering_actions=1, harvest_actions=1, carry_units=2),
            snapshot(7, fertilizer_actions=1, produced_units=2, harvested_units=2, deposited_units=2, worker_ticks_used=7, travel_steps=3, watering_actions=1, harvest_actions=1, deposit_actions=1, shed_units=4),
            snapshot(9, fertilizer_actions=1, produced_units=2, harvested_units=2, deposited_units=2, sold_units=2, cash=62, worker_ticks_used=9, travel_steps=4, watering_actions=1, harvest_actions=1, deposit_actions=1, sale_actions=1),
            snapshot(10, fertilizer_actions=1, produced_units=2, harvested_units=2, deposited_units=2, sold_units=2, cash=62, worker_ticks_used=9, travel_steps=4, watering_actions=1, harvest_actions=1, deposit_actions=1, sale_actions=1),
        ],
    }


def value_at(trace: dict[str, object], tick: int, field: str) -> int:
    value = 0
    for row in trace["snapshots"]:  # type: ignore[index]
        if row["tick"] > tick:
            break
        value = row[field]
    return value


class RealizedFertilizerCertificateTests(unittest.TestCase):
    def test_certifies_complete_realized_cycle(self) -> None:
        certificate = certify_realized_fertilizer(control_trace(), candidate_trace())
        self.assertEqual(certificate["schema"], CERTIFICATE_SCHEMA)
        self.assertEqual(certificate["decision"], "CERTIFIED")
        self.assertEqual(certificate["reasons"], [])
        self.assertEqual(certificate["deltas"]["sold_units"], 1)
        self.assertEqual(certificate["deltas"]["cash"], 6)
        self.assertEqual(certificate["milestones"], {"fertilizer_tick": 1, "production_tick": 3, "harvest_tick": 5, "deposit_tick": 7, "sale_tick": 9})

    def test_rejects_local_yield_without_realization(self) -> None:
        control = control_trace()
        candidate = candidate_trace()
        for row in candidate["snapshots"]:  # type: ignore[index]
            tick = row["tick"]
            for field in ("harvested_units", "deposited_units", "sold_units", "cash"):
                row[field] = value_at(control, tick, field)
        certificate = certify_realized_fertilizer(control, candidate)
        self.assertEqual(certificate["decision"], "REJECTED")
        self.assertIn("no-additional-harvest", certificate["reasons"])
        self.assertIn("no-additional-deposit", certificate["reasons"])
        self.assertIn("no-additional-sale", certificate["reasons"])
        self.assertIn("nonpositive-net-cash", certificate["reasons"])

    def test_rejects_nonpositive_net_cash_after_costs(self) -> None:
        control = control_trace()
        candidate = candidate_trace()
        for row in candidate["snapshots"]:  # type: ignore[index]
            if row["tick"] >= 9:
                row["cash"] = 56
        certificate = certify_realized_fertilizer(control, candidate)
        self.assertIn("nonpositive-net-cash", certificate["reasons"])

    def test_rejects_extra_discard(self) -> None:
        candidate = candidate_trace()
        candidate["snapshots"][-1]["discarded_units"] = 1  # type: ignore[index]
        certificate = certify_realized_fertilizer(control_trace(), candidate)
        self.assertIn("extra-discarded-output", certificate["reasons"])

    def test_rejects_protected_obligation_regression(self) -> None:
        candidate = candidate_trace()
        candidate["snapshots"][-1]["protected_obligation_misses"] = 1  # type: ignore[index]
        certificate = certify_realized_fertilizer(control_trace(), candidate)
        self.assertIn("protected-obligation-regression", certificate["reasons"])

    def test_rejects_protected_stock_regression(self) -> None:
        candidate = candidate_trace()
        candidate["snapshots"][-1]["protected_stock_shortfall_units"] = 1  # type: ignore[index]
        certificate = certify_realized_fertilizer(control_trace(), candidate)
        self.assertIn("protected-stock-regression", certificate["reasons"])

    def test_rejects_unattributable_sale_chain(self) -> None:
        candidate = candidate_trace()
        for row in candidate["snapshots"]:  # type: ignore[index]
            if row["tick"] >= 9:
                row["sold_units"] = 3
                row["cash"] = 68
                row["shed_units"] = 1
        certificate = certify_realized_fertilizer(control_trace(), candidate)
        self.assertIn("extra-output-chain-not-attributable", certificate["reasons"])

    def test_capacity_overflow_fails_closed(self) -> None:
        candidate = candidate_trace()
        candidate["snapshots"][4]["shed_units"] = 5  # type: ignore[index]
        certificate = certify_realized_fertilizer(control_trace(), candidate)
        self.assertEqual(certificate["decision"], "REJECTED")
        self.assertTrue(certificate["reasons"][0].startswith("invalid-candidate:"))

    def test_identity_mismatch_rejects_pair(self) -> None:
        candidate = candidate_trace()
        candidate["identity"]["engine_sha256"] = "0" * 64  # type: ignore[index]
        certificate = certify_realized_fertilizer(control_trace(), candidate)
        self.assertIn("identity-mismatch", certificate["reasons"])
        self.assertIsNone(certificate["identity"])

    def test_start_snapshot_mismatch_rejects_pair(self) -> None:
        candidate = candidate_trace()
        candidate["snapshots"][0]["cash"] = 49  # type: ignore[index]
        certificate = certify_realized_fertilizer(control_trace(), candidate)
        self.assertIn("start-state-metrics-mismatch", certificate["reasons"])

    def test_truncated_horizon_fails_closed(self) -> None:
        candidate = candidate_trace()
        candidate["snapshots"].pop()  # type: ignore[union-attr]
        certificate = certify_realized_fertilizer(control_trace(), candidate)
        self.assertTrue(certificate["reasons"][0].startswith("invalid-candidate:"))
        self.assertIn("terminal tick 9", certificate["reasons"][0])

    def test_boolean_integer_fails_closed(self) -> None:
        candidate = candidate_trace()
        candidate["snapshots"][1]["fertilizer_actions"] = True  # type: ignore[index]
        certificate = certify_realized_fertilizer(control_trace(), candidate)
        self.assertTrue(certificate["reasons"][0].startswith("invalid-candidate:"))
        self.assertIn("booleans are rejected", certificate["reasons"][0])

    def test_unknown_key_fails_closed(self) -> None:
        candidate = candidate_trace()
        candidate["snapshots"][1]["surprise"] = 1  # type: ignore[index]
        certificate = certify_realized_fertilizer(control_trace(), candidate)
        self.assertTrue(certificate["reasons"][0].startswith("invalid-candidate:"))
        self.assertIn("extra=surprise", certificate["reasons"][0])

    def test_unaccounted_action_fails_closed(self) -> None:
        candidate = candidate_trace()
        candidate["snapshots"][1]["worker_ticks_used"] = 0  # type: ignore[index]
        certificate = certify_realized_fertilizer(control_trace(), candidate)
        self.assertTrue(certificate["reasons"][0].startswith("invalid-candidate:"))
        self.assertIn("action counters exceed worker_ticks_used", certificate["reasons"][0])

    def test_certificate_hash_is_deterministic_and_self_verifiable(self) -> None:
        first = certify_realized_fertilizer(control_trace(), candidate_trace())
        second = certify_realized_fertilizer(control_trace(), candidate_trace())
        self.assertEqual(first, second)
        claimed = first.pop("certificate_sha256")
        self.assertEqual(claimed, canonical_sha256(first))

    def test_cli_writes_certified_json_and_returns_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control_path = root / "control.json"
            candidate_path = root / "candidate.json"
            output_path = root / "certificate.json"
            control_path.write_text(json.dumps(control_trace()), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate_trace()), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(HERE / "realized_fertilizer.py"), "--control", str(control_path), "--candidate", str(candidate_path), "--output", str(output_path)], check=False, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8"))["decision"], "CERTIFIED")

    def test_cli_returns_one_for_valid_but_unrealized_pair(self) -> None:
        control = control_trace()
        candidate = candidate_trace()
        for row in candidate["snapshots"]:  # type: ignore[index]
            tick = row["tick"]
            row["sold_units"] = value_at(control, tick, "sold_units")
            row["cash"] = value_at(control, tick, "cash")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control_path = root / "control.json"
            candidate_path = root / "candidate.json"
            control_path.write_text(json.dumps(control), encoding="utf-8")
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            completed = subprocess.run([sys.executable, str(HERE / "realized_fertilizer.py"), "--control", str(control_path), "--candidate", str(candidate_path)], check=False, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(json.loads(completed.stdout)["decision"], "REJECTED")


if __name__ == "__main__":
    unittest.main()
