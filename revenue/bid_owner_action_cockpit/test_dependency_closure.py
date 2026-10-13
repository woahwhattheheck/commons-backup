from __future__ import annotations

import copy
import unittest
from datetime import datetime, timezone

from .core import ValidationError, compile_cockpit

NOW = datetime(2026, 9, 14, 1, 30, 0, tzinfo=timezone.utc)
HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_D = "d" * 64
POLICY = {
    "max_source_age_minutes": 1440,
    "critical_window_minutes": 60,
    "high_window_minutes": 120,
}


def gate(gate_id: str, status: str, prerequisites=()):
    return {
        "id": gate_id,
        "action_key": gate_id.upper(),
        "action_label": f"Action {gate_id}",
        "requirement_sha256": HASH_A,
        "generation": 1,
        "category": "LEGAL",
        "status": status,
        "blocking": True,
        "owner_required": True,
        "evidence": [{"ref": f"evidence-{gate_id}", "sha256": HASH_D}] if status == "PROVEN" else [],
        "prerequisites": list(prerequisites),
    }


def packet(gates):
    return {
        "schema_version": 1,
        "snapshot_id": "dependency-closure",
        "opportunities": [{
            "id": "opp-1",
            "owner_ref": "owner-1",
            "route_state": "PRIME",
            "deadline_utc": None,
            "source": {
                "packet_id": "source-1",
                "packet_sha256": HASH_B,
                "captured_at": "2026-09-14T01:00:00Z",
                "complete": True,
            },
            "gates": gates,
        }],
    }


class DependencyClosureTests(unittest.TestCase):
    def compile(self, gates):
        return compile_cockpit(packet(gates), POLICY, as_of=NOW)

    def test_proven_gate_with_missing_prerequisite_is_rejected(self):
        gates = [
            gate("a", "MISSING"),
            gate("b", "PROVEN", ["a"]),
            gate("c", "MISSING", ["b"]),
        ]
        with self.assertRaisesRegex(ValidationError, r"gate b PROVEN with unmet prerequisites: \['a'\]"):
            self.compile(gates)

    def test_deep_proven_chain_cannot_hide_unmet_root(self):
        gates = [
            gate("a", "HOLD"),
            gate("b", "PROVEN", ["a"]),
            gate("c", "PROVEN", ["b"]),
            gate("d", "MISSING", ["c"]),
        ]
        with self.assertRaisesRegex(ValidationError, r"gate b PROVEN with unmet prerequisites"):
            self.compile(gates)

    def test_all_proven_chain_can_unlock_downstream_missing_gate(self):
        gates = [
            gate("a", "PROVEN"),
            gate("b", "PROVEN", ["a"]),
            gate("c", "MISSING", ["b"]),
        ]
        out = self.compile(gates)
        row = next(row for row in out["rows"] if row["action_key"] == "C")
        self.assertEqual("OWNER_ACTION_NOW", row["state"])
        self.assertEqual(["OWNER_REQUIRED_MISSING"], row["reason_codes"])

    def test_not_applicable_does_not_satisfy_proven_dependency(self):
        na = gate("a", "NOT_APPLICABLE")
        na["blocking"] = False
        gates = [na, gate("b", "PROVEN", ["a"])]
        with self.assertRaisesRegex(ValidationError, r"gate b PROVEN with unmet prerequisites"):
            self.compile(gates)

    def test_rejection_is_gate_order_invariant(self):
        original = [
            gate("a", "MISSING"),
            gate("b", "PROVEN", ["a"]),
            gate("c", "MISSING", ["b"]),
        ]
        for ordered in (original, list(reversed(copy.deepcopy(original)))):
            with self.subTest(order=[g["id"] for g in ordered]):
                with self.assertRaisesRegex(ValidationError, r"gate b PROVEN with unmet prerequisites"):
                    self.compile(ordered)


if __name__ == "__main__":
    unittest.main()
