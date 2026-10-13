from __future__ import annotations

import json
from copy import deepcopy

from observer import SCHEMA_VERSION, default_policy, choose_action, verify_decision
from replay import run_replay


def fixture_snapshot(tick: int = 10):
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_id": "SYNTHETIC-DEMO-001",
        "tick_index": tick,
        "timestamp_utc": "2026-09-15T00:00:00Z",
        "tick_seconds": 900,
        "remaining_budget": 100,
        "current_target_id": "TARGET-A",
        "recent_observations": [
            {"tick_index": tick - 3, "target_id": "TARGET-A", "tags": ["GALAXY"], "success": True},
            {"tick_index": tick - 1, "target_id": "TARGET-B", "tags": ["TRANSIENT"], "success": False},
        ],
        "candidates": [
            {
                "target_id": "TARGET-A", "tags": ["GALAXY"], "observation_cost": 10, "switch_cost": 4,
                "now": {"available": True, "science_value": 70000, "visibility_ppm": 900000, "weather_success_ppm": 900000},
                "forecast": [
                    {"offset_ticks": 1, "available": True, "science_value": 70000, "visibility_ppm": 850000, "weather_success_ppm": 800000},
                    {"offset_ticks": 2, "available": False, "science_value": 70000, "visibility_ppm": 300000, "weather_success_ppm": 500000},
                    {"offset_ticks": 3, "available": False, "science_value": 70000, "visibility_ppm": 100000, "weather_success_ppm": 300000},
                ],
            },
            {
                "target_id": "TARGET-B", "tags": ["TRANSIENT"], "observation_cost": 11, "switch_cost": 4,
                "now": {"available": True, "science_value": 95000, "visibility_ppm": 980000, "weather_success_ppm": 650000},
                "forecast": [
                    {"offset_ticks": 1, "available": True, "science_value": 110000, "visibility_ppm": 990000, "weather_success_ppm": 920000},
                    {"offset_ticks": 2, "available": True, "science_value": 105000, "visibility_ppm": 900000, "weather_success_ppm": 850000},
                    {"offset_ticks": 3, "available": True, "science_value": 90000, "visibility_ppm": 800000, "weather_success_ppm": 700000},
                ],
            },
            {
                "target_id": "TARGET-C", "tags": ["CALIBRATION", "STAR"], "observation_cost": 8, "switch_cost": 2,
                "now": {"available": True, "science_value": 50000, "visibility_ppm": 1000000, "weather_success_ppm": 990000},
                "forecast": [
                    {"offset_ticks": 1, "available": True, "science_value": 50000, "visibility_ppm": 1000000, "weather_success_ppm": 990000},
                    {"offset_ticks": 2, "available": True, "science_value": 50000, "visibility_ppm": 1000000, "weather_success_ppm": 990000},
                    {"offset_ticks": 3, "available": True, "science_value": 50000, "visibility_ppm": 1000000, "weather_success_ppm": 990000},
                ],
            },
        ],
    }


def replay_fixture():
    policy = default_policy()
    snapshots = []
    outcomes = []
    for offset in range(4):
        s = fixture_snapshot(10 + offset)
        minute = offset * 15
        s["timestamp_utc"] = f"2026-09-15T{minute // 60:02d}:{minute % 60:02d}:00Z"
        s["recent_observations"] = [] if s["tick_index"] == 0 else [
            {"tick_index": s["tick_index"] - 1, "target_id": "TARGET-A", "tags": ["GALAXY"], "success": True}
        ]
        snapshots.append(s)
        for c in s["candidates"]:
            outcomes.append({
                "tick_index": s["tick_index"], "target_id": c["target_id"],
                "success": c["target_id"] != "TARGET-B" or offset > 0,
                "science_yield": c["now"]["science_value"],
            })
    return snapshots, outcomes, policy


def self_test():
    snapshot = fixture_snapshot()
    policy = default_policy()
    receipt = choose_action(snapshot, policy)
    assert receipt["causal_boundary"] == "CURRENT_OBSERVATIONS_PLUS_EXPLICIT_FORECASTS_ONLY"
    assert receipt["official_score_claimed"] is False
    assert verify_decision(receipt, snapshot, policy)
    snapshots, outcomes, policy = replay_fixture()
    report = run_replay(snapshots, outcomes, policy)
    assert report["foundation_evaluation_only"] is True
    assert report["official_score_claimed"] is False
    return receipt, report


if __name__ == "__main__":
    decision, report = self_test()
    print(json.dumps({
        "decision": decision["action"],
        "planned_schedule": decision["planned_schedule"],
        "decision_receipt": decision["receipt_sha256"],
        "replay_receipt": report["receipt_sha256"],
        "foundation_evaluation_only": report["foundation_evaluation_only"],
    }, sort_keys=True))
