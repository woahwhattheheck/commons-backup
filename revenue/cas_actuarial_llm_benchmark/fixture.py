# SPDX-License-Identifier: MPL-2.0
"""Synthetic acceptance fixture for the CAS actuarial LLM benchmark evidence core."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


MODELS = [
    ("commercial-openai", "commercial", "openai"),
    ("commercial-anthropic", "commercial", "anthropic"),
    ("commercial-google", "commercial", "google"),
    ("open-model-a", "open", "community-a"),
    ("open-model-b", "open", "community-b"),
    ("open-model-c", "open", "community-c"),
]


def _task(
    *,
    task_id: str,
    task_type: str,
    labels: list[str],
) -> dict[str, Any]:
    version = "v1"
    dataset_sha256 = _sha(f"{task_id}-dataset-v1")
    split_sha256 = _sha(f"{task_id}-split-v1")
    evaluation_protocol_sha256 = _sha("fixed-evaluation-protocol-v1")
    records = [
        {"item_id": f"item-{index:03d}", "truth": labels[index % len(labels)]}
        for index in range(12)
    ]
    universe_payload = {
        "task_id": task_id,
        "task_version": version,
        "dataset_sha256": dataset_sha256,
        "split_sha256": split_sha256,
        "records": records,
    }
    return {
        "task_id": task_id,
        "version": version,
        "task_type": task_type,
        "labels": labels,
        "dataset": {
            "sha256": dataset_sha256,
            "split_sha256": split_sha256,
            "license_status": "confirmed_publishable",
            "license_reference": "synthetic-fixture-publication-authority-v1",
            "provenance": "Synthetic records generated for repository acceptance testing only.",
            "source_uri": f"https://example.invalid/cas-fixture/{task_id}-v1",
        },
        "evaluation_protocol_sha256": evaluation_protocol_sha256,
        "evaluation_universe": {
            "sha256": _digest(universe_payload),
            "records": records,
        },
    }


def synthetic_evidence() -> dict[str, Any]:
    tasks = [
        _task(
            task_id="claim-triage",
            task_type="binary",
            labels=["routine", "escalate"],
        ),
        _task(
            task_id="risk-segmentation",
            task_type="multiclass",
            labels=["low", "medium", "high"],
        ),
    ]
    models = [
        {
            "model_id": model_id,
            "model_version": "fixture-2026-09",
            "model_class": model_class,
            "provider": provider,
            "artifact_sha256": _sha(f"{model_id}-artifact"),
        }
        for model_id, model_class, provider in MODELS
    ]
    runs: list[dict[str, Any]] = []
    for model_index, (model_id, _model_class, _provider) in enumerate(MODELS):
        model = models[model_index]
        for task in tasks:
            labels = task["labels"]
            records = []
            for index, universe_record in enumerate(task["evaluation_universe"]["records"]):
                truth = universe_record["truth"]
                correct = (index + model_index) % 5 != 0
                prediction = truth if correct else labels[(labels.index(truth) + 1) % len(labels)]
                if len(labels) == 2:
                    probabilities = {
                        label: ("0.80" if label == prediction else "0.20")
                        for label in labels
                    }
                else:
                    probabilities = {
                        label: ("0.70" if label == prediction else "0.15")
                        for label in labels
                    }
                records.append(
                    {
                        "item_id": universe_record["item_id"],
                        "truth": truth,
                        "prediction": prediction,
                        "probabilities": probabilities,
                    }
                )
            runs.append(
                {
                    "run_id": f"{model_id}-{task['task_id']}-v1",
                    "model_id": model_id,
                    "model_version": model["model_version"],
                    "model_artifact_sha256": model["artifact_sha256"],
                    "task_id": task["task_id"],
                    "task_version": task["version"],
                    "dataset_sha256": task["dataset"]["sha256"],
                    "split_sha256": task["dataset"]["split_sha256"],
                    "protocol_sha256": task["evaluation_protocol_sha256"],
                    "records": records,
                }
            )
    return {
        "schema_version": 1,
        "governance": {
            "update_policy": "versioned_no_silent_mutation",
            "task_authority": "qualified_actuarial_reviewer",
            "benchmark_license": "MPL-2.0",
        },
        "tasks": tasks,
        "models": models,
        "runs": runs,
    }
