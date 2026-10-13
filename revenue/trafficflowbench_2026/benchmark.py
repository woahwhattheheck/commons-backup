from __future__ import annotations

import hashlib
import json

from .contract import UPSTREAM, authority_ceiling, canonical_json_bytes
from .methods import projected_ridge_odme, queue_wave_forecast, reconstruct_state
from .scoring import queue_iou, state_regime_score


def _link_error(A, counts, flow):
    return sum(abs(sum(a * x for a, x in zip(row, flow)) - c) for row, c in zip(A, counts))


def synthetic_evidence() -> dict[str, object]:
    truth_speed, truth_flow = [42.0], [2500.0]
    baseline_state = state_regime_score(truth_speed, truth_flow, [88.0], [1000.0], [2])["S_state"]
    state_pred = reconstruct_state(
        historical_speed_kmh=88,
        historical_flow_vph=1000,
        observed_neighbors=[(40, 2450), (44, 2550)],
        lanes=2,
        free_speed_kmh=100,
        capacity_per_lane_vph=1800,
    )
    method_state = state_regime_score(truth_speed, truth_flow, [state_pred[0]], [state_pred[1]], [2])["S_state"]

    history = [[95, 92, 90], [92, 86, 82], [88, 76, 69], [82, 67, 55]]
    truth_queue = [[0, 1, 1], [1, 1, 1], [1, 1, 1]]
    wave = queue_wave_forecast(history, [100, 100, 100], horizons=3)
    persistence = [0, 0, 1]
    wave_iou = sum(queue_iou(t, p) for t, p in zip(truth_queue, wave)) / 3
    persistence_iou = sum(queue_iou(t, persistence) for t in truth_queue) / 3

    A = [[1.0, 1.0, 0.0], [0.0, 1.0, 1.0], [1.0, 0.0, 1.0]]
    counts = [50.0, 30.0, 40.0]
    prior = [10.0, 10.0, 10.0]
    solved = projected_ridge_odme(A, counts, prior, iterations=2500)
    prior_error = _link_error(A, counts, prior)
    solved_error = _link_error(A, counts, solved)

    report: dict[str, object] = {
        "schema": "trafficflowbench-local-synthetic-evidence/v1",
        "upstreamCommit": UPSTREAM["commit"],
        "evidenceClass": "LOCAL_SYNTHETIC",
        "task1": {
            "historicalMeanStateScore": baseline_state,
            "visibleNeighborFdStateScore": method_state,
            "absoluteLift": method_state - baseline_state,
        },
        "task2": {
            "persistenceMeanIoU": persistence_iou,
            "queueWaveMeanIoU": wave_iou,
            "absoluteLift": wave_iou - persistence_iou,
        },
        "task4": {
            "splitLocalPriorLinkL1": prior_error,
            "projectedRidgeLinkL1": solved_error,
            "relativeError": solved_error / prior_error,
        },
        "authority": authority_ceiling(),
    }
    report["receiptSha256"] = hashlib.sha256(canonical_json_bytes(report)).hexdigest()
    return report


def main() -> None:
    print(json.dumps(synthetic_evidence(), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
