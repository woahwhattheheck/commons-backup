from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from event_trace_builder import (  # noqa: E402
    EVENT_BUILD_RECEIPT_SCHEMA,
    EVENT_STREAM_SCHEMA,
    EventBuildError,
    compile_event_stream,
)
from realized_fertilizer import TRACE_SCHEMA, canonical_sha256, validate_trace  # noqa: E402

A = "a" * 64
B = "b" * 64
C = "c" * 64
D = "d" * 64
E = "e" * 64
F = "f" * 64

INITIAL = {
    "tick": 0,
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


def event_stream() -> dict[str, object]:
    return {
        "schema": EVENT_STREAM_SCHEMA,
        "variant": "fertilized",
        "policy_sha256": B,
        "identity": identity(),
        "capacity": {"carry_units": 2, "shed_units": 4},
        "initial_snapshot": dict(INITIAL),
        "events": [
            {
                "tick": 1,
                "deltas": {"fertilizer_actions": 1, "worker_ticks_used": 1},
                "cash_delta": 0,
                "gauges": {},
            },
            {
                "tick": 3,
                "deltas": {
                    "produced_units": 2,
                    "worker_ticks_used": 2,
                    "travel_steps": 1,
                    "watering_actions": 1,
                },
                "cash_delta": 0,
                "gauges": {},
            },
            {
                "tick": 5,
                "deltas": {
                    "harvested_units": 2,
                    "worker_ticks_used": 2,
                    "travel_steps": 1,
                    "harvest_actions": 1,
                },
                "cash_delta": 0,
                "gauges": {"carry_units": 2},
            },
            {
                "tick": 7,
                "deltas": {
                    "deposited_units": 2,
                    "worker_ticks_used": 2,
                    "travel_steps": 1,
                    "deposit_actions": 1,
                },
                "cash_delta": 0,
                "gauges": {"carry_units": 0, "shed_units": 4},
            },
            {
                "tick": 9,
                "deltas": {
                    "sold_units": 2,
                    "worker_ticks_used": 2,
                    "travel_steps": 1,
                    "sale_actions": 1,
                },
                "cash_delta": 12,
                "gauges": {"shed_units": 2},
            },
        ],
    }


class EventTraceBuilderTests(unittest.TestCase):
    def test_compiles_valid_stream_and_carries_to_exact_horizon(self) -> None:
        receipt = compile_event_stream(event_stream())
        self.assertEqual(receipt["schema"], EVENT_BUILD_RECEIPT_SCHEMA)
        self.assertEqual(receipt["event_count"], 5)
        trace = receipt["trace"]
        self.assertEqual(trace["schema"], TRACE_SCHEMA)
        self.assertEqual(trace["variant"], "fertilized")
        self.assertEqual(
            [row["tick"] for row in trace["snapshots"]],
            [0, 1, 3, 5, 7, 9, 10],
        )
        self.assertEqual(trace["snapshots"][-1]["cash"], 62)
        self.assertEqual(trace["snapshots"][-1]["sold_units"], 2)
        self.assertEqual(trace["snapshots"][-1]["shed_units"], 2)
        validate_trace(trace, expected_variant="fertilized")

    def test_same_tick_events_are_coalesced(self) -> None:
        stream = event_stream()
        stream["events"] = [
            {
                "tick": 1,
                "deltas": {"fertilizer_actions": 1},
                "cash_delta": 0,
                "gauges": {},
            },
            {
                "tick": 1,
                "deltas": {"worker_ticks_used": 1},
                "cash_delta": -1,
                "gauges": {},
            },
        ]
        receipt = compile_event_stream(stream)
        snapshots = receipt["trace"]["snapshots"]
        self.assertEqual([row["tick"] for row in snapshots], [0, 1, 10])
        self.assertEqual(snapshots[1]["fertilizer_actions"], 1)
        self.assertEqual(snapshots[1]["worker_ticks_used"], 1)
        self.assertEqual(snapshots[1]["cash"], 49)

    def test_empty_event_stream_carries_initial_state_to_horizon(self) -> None:
        stream = event_stream()
        stream["events"] = []
        receipt = compile_event_stream(stream)
        snapshots = receipt["trace"]["snapshots"]
        self.assertEqual([row["tick"] for row in snapshots], [0, 10])
        self.assertEqual(snapshots[0]["cash"], snapshots[-1]["cash"])
        self.assertEqual(receipt["event_count"], 0)

    def test_out_of_order_events_are_rejected(self) -> None:
        stream = event_stream()
        stream["events"][1]["tick"] = 0
        with self.assertRaisesRegex(EventBuildError, "ordered by nondecreasing tick"):
            compile_event_stream(stream)

    def test_event_after_horizon_is_rejected(self) -> None:
        stream = event_stream()
        stream["events"][-1]["tick"] = 11
        with self.assertRaisesRegex(EventBuildError, "exceeds horizon_tick"):
            compile_event_stream(stream)

    def test_event_at_initial_tick_is_rejected_as_ambiguous(self) -> None:
        stream = event_stream()
        stream["events"][0]["tick"] = 0
        with self.assertRaisesRegex(EventBuildError, "initial_snapshot.tick are ambiguous"):
            compile_event_stream(stream)

    def test_negative_counter_delta_is_rejected(self) -> None:
        stream = event_stream()
        stream["events"][0]["deltas"]["fertilizer_actions"] = -1
        with self.assertRaisesRegex(EventBuildError, "must be >= 0"):
            compile_event_stream(stream)

    def test_boolean_counter_delta_is_rejected(self) -> None:
        stream = event_stream()
        stream["events"][0]["deltas"]["fertilizer_actions"] = True
        with self.assertRaisesRegex(EventBuildError, "booleans are rejected"):
            compile_event_stream(stream)

    def test_unknown_event_and_delta_keys_are_rejected(self) -> None:
        stream = event_stream()
        stream["events"][0]["surprise"] = 1
        with self.assertRaisesRegex(EventBuildError, "extra=surprise"):
            compile_event_stream(stream)

        stream = event_stream()
        stream["events"][0]["deltas"]["mystery_actions"] = 1
        with self.assertRaisesRegex(EventBuildError, "extra=mystery_actions"):
            compile_event_stream(stream)

    def test_noop_event_is_rejected(self) -> None:
        stream = event_stream()
        stream["events"] = [
            {"tick": 1, "deltas": {}, "cash_delta": 0, "gauges": {}}
        ]
        with self.assertRaisesRegex(EventBuildError, "must change at least one"):
            compile_event_stream(stream)

    def test_capacity_overflow_is_rejected_by_shared_trace_validator(self) -> None:
        stream = event_stream()
        stream["events"][2]["gauges"]["carry_units"] = 3
        with self.assertRaisesRegex(EventBuildError, "compiled trace rejected"):
            compile_event_stream(stream)

    def test_action_without_accounted_worker_tick_is_rejected(self) -> None:
        stream = event_stream()
        stream["events"][0]["deltas"].pop("worker_ticks_used")
        with self.assertRaisesRegex(
            EventBuildError, "action counters exceed worker_ticks_used"
        ):
            compile_event_stream(stream)

    def test_receipt_is_deterministic_and_self_hashing(self) -> None:
        first = compile_event_stream(event_stream())
        second = compile_event_stream(copy.deepcopy(event_stream()))
        self.assertEqual(first, second)
        claimed = first.pop("receipt_sha256")
        self.assertEqual(claimed, canonical_sha256(first))
        self.assertEqual(second["trace_sha256"], canonical_sha256(second["trace"]))

    def test_cli_writes_receipt_and_plain_trace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "events.json"
            receipt_path = root / "receipt.json"
            trace_path = root / "trace.json"
            source.write_text(json.dumps(event_stream()), encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    str(HERE / "event_trace_builder.py"),
                    str(source),
                    "--output",
                    str(receipt_path),
                    "--trace-output",
                    str(trace_path),
                    "--pretty",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["trace"], trace)
            self.assertEqual(trace["snapshots"][-1]["tick"], 10)
            validate_trace(trace, expected_variant="fertilized")

    def test_cli_returns_two_for_invalid_stream(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "events.json"
            invalid = event_stream()
            invalid["events"][0]["deltas"]["fertilizer_actions"] = -1
            source.write_text(json.dumps(invalid), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(HERE / "event_trace_builder.py"), str(source)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("must be >= 0", completed.stderr)


if __name__ == "__main__":
    unittest.main()
