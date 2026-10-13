"""Deterministic synthetic acceptance matrix for the benchmark core."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from typing import Any

from .benchmark import SCHEMA, RUN_SCHEMA, build_board, score_run, verify_board, verify_receipt


def _h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def synthetic_suite() -> dict[str, Any]:
    tasks = []
    specs = [
        ("claims-triage", "Claims triage", "claims", ["LOW", "HIGH"]),
        ("underwriting", "Underwriting judgment", "underwriting", ["DECLINE", "REFER", "ACCEPT"]),
        ("fraud-flag", "Fraud flagging", "fraud", ["CLEAR", "FLAG"]),
    ]
    weights = ["0.400000000000", "0.350000000000", "0.250000000000"]
    for ti, (task_id, title, domain, labels) in enumerate(specs):
        items = []
        for i in range(8):
            items.append({
                "item_id": f"item-{i:02d}", "prompt_sha256": _h(f"{task_id}:prompt:{i}"),
                "gold_label": labels[(i + ti) % len(labels)], "source_ref": f"synthetic://{task_id}/{i}",
            })
        tasks.append({"task_id": task_id, "title": title, "domain": domain, "labels": labels, "weight": weights[ti], "items": items})
    return {
        "schema": SCHEMA, "suite_id": "cas-synthetic-perception", "version": "2026.09.synthetic.1",
        "title": "Synthetic P&C perception acceptance fixture", "dataset_license": "CC0-1.0-SYNTHETIC",
        "provenance_url": "https://example.invalid/synthetic-only", "dataset_sha256": _h("cas-synthetic-dataset-v1"),
        "metric_policy": {"primary_metric": "accuracy", "probability_floor": "0.000001", "bootstrap_replicates": 120, "confidence_level": "0.950000", "bootstrap_seed": "cas-synthetic-bootstrap-v1"},
        "tasks": tasks,
    }


def synthetic_run(model_index: int, suite: dict[str, Any] | None = None) -> dict[str, Any]:
    suite = synthetic_suite() if suite is None else suite
    quality = [95, 88, 80, 72, 64, 56, 48][model_index]
    predictions = []
    for task in suite["tasks"]:
        labels = task["labels"]
        for i, item in enumerate(task["items"]):
            gold = item["gold_label"]
            correct = ((i * 17 + model_index * 11 + len(task["task_id"])) % 100) < quality
            chosen = gold if correct else labels[(labels.index(gold) + 1) % len(labels)]
            if len(labels) == 2:
                hi, lo = "0.850000", "0.150000"
                probs = {label: (hi if label == chosen else lo) for label in labels}
            else:
                probs = {label: ("0.800000" if label == chosen else "0.100000") for label in labels}
            predictions.append({"task_id": task["task_id"], "item_id": item["item_id"], "probabilities": probs})
    return {
        "schema": RUN_SCHEMA, "run_id": f"synthetic-model-{model_index}", "suite_id": suite["suite_id"],
        "suite_version": suite["version"], "dataset_sha256": suite["dataset_sha256"],
        "model": {"provider": "synthetic", "model_id": f"model-{model_index}", "model_version": "fixture-v1", "config_sha256": _h(f"config:{model_index}")},
        "adapter_version": "synthetic-adapter-v1", "prompt_policy_sha256": _h("prompt-policy-v1"), "predictions": predictions,
    }


def run_acceptance() -> dict[str, Any]:
    suite = synthetic_suite()
    runs = [synthetic_run(i, suite) for i in range(7)]
    receipts = [score_run(suite, r) for r in runs]
    board = build_board(suite, receipts)
    clean = runs[0]
    replay = deepcopy(clean); replay["predictions"] = list(reversed(replay["predictions"])) + [deepcopy(replay["predictions"][0])]
    replay_receipt = score_run(suite, replay)
    missing = deepcopy(clean); missing["run_id"] = "missing-case"; missing["predictions"].pop()
    unknown = deepcopy(clean); unknown["run_id"] = "unknown-case"; extra = deepcopy(unknown["predictions"][0]); extra["item_id"] = "unknown-item"; unknown["predictions"].append(extra)
    conflict = deepcopy(clean); conflict["run_id"] = "conflict-case"; extra = deepcopy(conflict["predictions"][0]); labels = sorted(extra["probabilities"]); extra["probabilities"] = {labels[0]: "0.200000", labels[1]: "0.800000"} if len(labels) == 2 else {labels[0]: "0.800000", labels[1]: "0.100000", labels[2]: "0.100000"}; conflict["predictions"].append(extra)
    wrong_dataset = deepcopy(clean); wrong_dataset["run_id"] = "wrong-dataset"; wrong_dataset["dataset_sha256"] = _h("wrong")
    hostile = [score_run(suite, x) for x in (missing, unknown, conflict, wrong_dataset)]
    return {
        "schema": "cas-actuarial-llm-benchmark-acceptance/v1",
        "ready_models": sum(r["status"] == "READY" for r in receipts),
        "board_entries": board["entry_count"],
        "board_order": [e["model"]["model_id"] for e in board["entries"]],
        "replay_order_invariant": receipts[0] == replay_receipt,
        "receipt_verifies": verify_receipt(receipts[0], suite, clean),
        "board_verifies": verify_board(board, suite, receipts),
        "hostile_statuses": [r["status"] for r in hostile],
        "hostile_reasons": [r["reasons"] for r in hostile],
        "suite_digest": receipts[0]["suite_digest"],
        "board_sha256": board["board_sha256"],
        "acceptance_sha256": _h(json.dumps({"receipts": receipts, "board": board}, sort_keys=True, separators=(",", ":"))),
    }


if __name__ == "__main__":
    print(json.dumps(run_acceptance(), sort_keys=True, indent=2))
