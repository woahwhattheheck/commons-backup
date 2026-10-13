# SPDX-License-Identifier: MPL-2.0
"""Public evaluation and snapshot-verification API for the CAS benchmark core."""

from __future__ import annotations

import hashlib
from typing import Any

from ._schema import (
    BenchmarkInputError,
    _REQUIRED_COMMERCIAL,
    _SHA256_RE,
    _canon,
    _digest,
    _metrics,
    _model,
    _plain_key,
    _record_manifest_payload,
    _run,
    _task,
)


def evaluate_benchmark(evidence: dict[str, Any]) -> dict[str, Any]:
    """Validate benchmark evidence and return a content-addressed snapshot."""
    if not isinstance(evidence, dict):
        raise BenchmarkInputError("evidence must be an object")
    schema_version = evidence.get("schema_version")
    if type(schema_version) is not int or schema_version != 1:
        raise BenchmarkInputError("schema_version must be integer 1")

    governance = evidence.get("governance")
    if not isinstance(governance, dict):
        raise BenchmarkInputError("governance must be an object")
    if governance.get("update_policy") != "versioned_no_silent_mutation":
        raise BenchmarkInputError("update_policy must be versioned_no_silent_mutation")
    if governance.get("task_authority") != "qualified_actuarial_reviewer":
        raise BenchmarkInputError(
            "task_authority must remain with qualified_actuarial_reviewer"
        )
    if governance.get("benchmark_license") != "MPL-2.0":
        raise BenchmarkInputError("benchmark_license must be MPL-2.0")

    tasks_raw = evidence.get("tasks")
    models_raw = evidence.get("models")
    runs_raw = evidence.get("runs")
    if not isinstance(tasks_raw, list) or not tasks_raw:
        raise BenchmarkInputError("tasks must be a non-empty list")
    if not isinstance(models_raw, list) or not models_raw:
        raise BenchmarkInputError("models must be a non-empty list")
    if not isinstance(runs_raw, list):
        raise BenchmarkInputError("runs must be a list")

    tasks = [_task(raw) for raw in tasks_raw]
    models = [_model(raw) for raw in models_raw]
    task_keys = [(task["task_id"], task["version"]) for task in tasks]
    if len(task_keys) != len(set(task_keys)):
        raise BenchmarkInputError("task id/version pairs must be unique")
    model_ids = [model["model_id"] for model in models]
    if len(model_ids) != len(set(model_ids)):
        raise BenchmarkInputError("model_id values must be unique")

    commercial = {
        model["provider"] for model in models if model["model_class"] == "commercial"
    }
    missing_commercial = sorted(_REQUIRED_COMMERCIAL - commercial)
    open_models = [model for model in models if model["model_class"] == "open"]
    if missing_commercial:
        raise BenchmarkInputError(
            "commercial roster must include provider families: "
            + ",".join(missing_commercial)
        )
    if len({model["model_id"] for model in open_models}) < 3:
        raise BenchmarkInputError("roster must include at least three distinct open models")

    task_by_key = {(task["task_id"], task["version"]): task for task in tasks}
    model_by_id = {model["model_id"]: model for model in models}
    normalized_runs: list[dict[str, Any]] = []
    run_pairs: set[tuple[str, str, str]] = set()
    run_ids: set[str] = set()
    for raw in runs_raw:
        if not isinstance(raw, dict):
            raise BenchmarkInputError("each run must be an object")
        task = task_by_key.get((raw.get("task_id"), raw.get("task_version")))
        if task is None:
            raise BenchmarkInputError("run references unknown task id/version")
        model = model_by_id.get(raw.get("model_id"))
        if model is None:
            raise BenchmarkInputError("run references unknown model_id")
        normalized = _run(raw, task, model)
        if normalized["run_id"] in run_ids:
            raise BenchmarkInputError("run_id values must be unique")
        run_ids.add(normalized["run_id"])
        pair = (model["model_id"], task["task_id"], task["version"])
        if pair in run_pairs:
            raise BenchmarkInputError("model/task pair must appear exactly once")
        run_pairs.add(pair)

        manifest_payload = _record_manifest_payload(
            task=task,
            model=model,
            protocol_sha256=normalized["protocol_sha256"],
            records=normalized["records"],
        )
        normalized_runs.append(
            {
                "run_id": normalized["run_id"],
                "model_id": model["model_id"],
                "model_version": model["model_version"],
                "model_class": model["model_class"],
                "provider": model["provider"],
                "task_id": task["task_id"],
                "task_version": task["version"],
                "dataset_sha256": task["dataset"]["sha256"],
                "split_sha256": task["dataset"]["split_sha256"],
                "protocol_sha256": normalized["protocol_sha256"],
                "evaluation_universe_sha256": normalized[
                    "evaluation_universe_sha256"
                ],
                "records": manifest_payload["records"],
                "record_manifest_sha256": normalized["record_manifest_sha256"],
                "record_count": len(normalized["records"]),
                "metrics": _metrics(task, normalized["records"]),
            }
        )

    expected_pairs = {
        (model["model_id"], task["task_id"], task["version"])
        for model in models
        for task in tasks
    }
    missing_pairs = sorted(expected_pairs - run_pairs)
    if missing_pairs:
        raise BenchmarkInputError(
            f"benchmark matrix incomplete: {len(missing_pairs)} model/task runs missing"
        )

    normalized_runs.sort(
        key=lambda row: (row["task_id"], row["task_version"], row["model_id"])
    )
    safe_tasks = sorted(tasks, key=lambda task: (task["task_id"], task["version"]))
    safe_models = sorted(models, key=lambda model: model["model_id"])
    snapshot = {
        "schema_version": 1,
        "status": "PROPOSAL_TECHNICAL_EVIDENCE_READY",
        "authority": {
            "actuarial_task_validity": False,
            "cas_submission": False,
            "model_provider_action": False,
            "contract": False,
            "payment": False,
            "recognized_revenue": False,
        },
        "governance": {
            "update_policy": governance["update_policy"],
            "task_authority": governance["task_authority"],
            "benchmark_license": governance["benchmark_license"],
        },
        "tasks": safe_tasks,
        "models": safe_models,
        "runs": normalized_runs,
        "signals": {
            "task_count": len(tasks),
            "model_count": len(models),
            "commercial_provider_families": sorted(commercial),
            "open_model_count": len(open_models),
            "run_count": len(normalized_runs),
            "evaluation_item_count": sum(
                task["evaluation_universe"]["record_count"] for task in tasks
            ),
            "matrix_complete": True,
            "shared_evaluation_universe_enforced": True,
            "record_manifests_bound": True,
            "all_datasets_confirmed_publishable": True,
        },
    }
    snapshot["snapshot_sha256"] = _digest(snapshot)
    return snapshot


def verify_snapshot(snapshot: dict[str, Any]) -> bool:
    """Verify the complete safe snapshot contract from retained canonical evidence."""
    if not isinstance(snapshot, dict):
        return False
    if set(snapshot) != {
        "schema_version",
        "status",
        "authority",
        "governance",
        "tasks",
        "models",
        "runs",
        "signals",
        "snapshot_sha256",
    }:
        return False
    if type(snapshot.get("schema_version")) is not int or snapshot["schema_version"] != 1:
        return False
    if snapshot.get("status") != "PROPOSAL_TECHNICAL_EVIDENCE_READY":
        return False

    expected_authority = {
        "actuarial_task_validity": False,
        "cas_submission": False,
        "model_provider_action": False,
        "contract": False,
        "payment": False,
        "recognized_revenue": False,
    }
    authority = snapshot.get("authority")
    if authority != expected_authority:
        return False
    if any(type(value) is not bool for value in authority.values()):
        return False

    expected_governance = {
        "update_policy": "versioned_no_silent_mutation",
        "task_authority": "qualified_actuarial_reviewer",
        "benchmark_license": "MPL-2.0",
    }
    if snapshot.get("governance") != expected_governance:
        return False

    tasks = snapshot.get("tasks")
    models = snapshot.get("models")
    runs = snapshot.get("runs")
    if not isinstance(tasks, list) or not tasks:
        return False
    if not isinstance(models, list) or not models:
        return False
    if not isinstance(runs, list):
        return False

    normalized_tasks: list[dict[str, Any]] = []
    task_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        for task in tasks:
            if not isinstance(task, dict):
                return False
            universe = task.get("evaluation_universe")
            if not isinstance(universe, dict):
                return False
            if set(universe) != {"sha256", "record_count", "records"}:
                return False
            if type(universe.get("record_count")) is not int or universe["record_count"] <= 0:
                return False
            records = universe.get("records")
            if not isinstance(records, list) or len(records) != universe["record_count"]:
                return False
            raw_task = {
                "task_id": task.get("task_id"),
                "version": task.get("version"),
                "task_type": task.get("task_type"),
                "labels": task.get("labels"),
                "dataset": task.get("dataset"),
                "evaluation_protocol_sha256": task.get("evaluation_protocol_sha256"),
                "evaluation_universe": {
                    "sha256": universe.get("sha256"),
                    "records": records,
                },
            }
            normalized = _task(raw_task)
            if normalized != task:
                return False
            key = (normalized["task_id"], normalized["version"])
            if key in task_by_key:
                return False
            task_by_key[key] = normalized
            normalized_tasks.append(normalized)
    except (BenchmarkInputError, KeyError, TypeError):
        return False
    if normalized_tasks != sorted(
        normalized_tasks, key=lambda task: (task["task_id"], task["version"])
    ):
        return False

    normalized_models: list[dict[str, Any]] = []
    model_by_id: dict[str, dict[str, Any]] = {}
    try:
        for model in models:
            normalized = _model(model)
            if normalized != model:
                return False
            if normalized["model_id"] in model_by_id:
                return False
            model_by_id[normalized["model_id"]] = normalized
            normalized_models.append(normalized)
    except (BenchmarkInputError, TypeError):
        return False
    if normalized_models != sorted(normalized_models, key=lambda model: model["model_id"]):
        return False

    commercial = {
        model["provider"]
        for model in normalized_models
        if model["model_class"] == "commercial"
    }
    open_models = [
        model for model in normalized_models if model["model_class"] == "open"
    ]
    if _REQUIRED_COMMERCIAL - commercial:
        return False
    if len({model["model_id"] for model in open_models}) < 3:
        return False

    expected_run_keys = {
        "run_id",
        "model_id",
        "model_version",
        "model_class",
        "provider",
        "task_id",
        "task_version",
        "dataset_sha256",
        "split_sha256",
        "protocol_sha256",
        "evaluation_universe_sha256",
        "records",
        "record_manifest_sha256",
        "record_count",
        "metrics",
    }
    run_ids: set[str] = set()
    run_pairs: set[tuple[str, str, str]] = set()
    try:
        for run in runs:
            if not isinstance(run, dict) or set(run) != expected_run_keys:
                return False
            run_id = _plain_key(run.get("run_id"), "run_id")
            if run_id in run_ids:
                return False
            run_ids.add(run_id)
            model = model_by_id.get(run.get("model_id"))
            task = task_by_key.get((run.get("task_id"), run.get("task_version")))
            if model is None or task is None:
                return False
            if (
                run.get("model_version") != model["model_version"]
                or run.get("model_class") != model["model_class"]
                or run.get("provider") != model["provider"]
                or run.get("dataset_sha256") != task["dataset"]["sha256"]
                or run.get("split_sha256") != task["dataset"]["split_sha256"]
                or run.get("protocol_sha256") != task["evaluation_protocol_sha256"]
                or run.get("evaluation_universe_sha256")
                != task["evaluation_universe"]["sha256"]
            ):
                return False
            if type(run.get("record_count")) is not int:
                return False
            if run["record_count"] != task["evaluation_universe"]["record_count"]:
                return False

            raw_run = {
                "run_id": run_id,
                "task_id": task["task_id"],
                "task_version": task["version"],
                "dataset_sha256": run.get("dataset_sha256"),
                "split_sha256": run.get("split_sha256"),
                "model_id": model["model_id"],
                "model_version": model["model_version"],
                "model_artifact_sha256": model["artifact_sha256"],
                "protocol_sha256": run.get("protocol_sha256"),
                "records": run.get("records"),
            }
            normalized_run = _run(raw_run, task, model)
            canonical_manifest = _record_manifest_payload(
                task=task,
                model=model,
                protocol_sha256=normalized_run["protocol_sha256"],
                records=normalized_run["records"],
            )
            if canonical_manifest["records"] != run["records"]:
                return False
            if normalized_run["evaluation_universe_sha256"] != run["evaluation_universe_sha256"]:
                return False
            if normalized_run["record_manifest_sha256"] != run.get(
                "record_manifest_sha256"
            ):
                return False
            if len(normalized_run["records"]) != run["record_count"]:
                return False
            if _metrics(task, normalized_run["records"]) != run.get("metrics"):
                return False

            pair = (model["model_id"], task["task_id"], task["version"])
            if pair in run_pairs:
                return False
            run_pairs.add(pair)
    except (BenchmarkInputError, KeyError, TypeError):
        return False

    expected_pairs = {
        (model["model_id"], task["task_id"], task["version"])
        for model in normalized_models
        for task in normalized_tasks
    }
    if run_pairs != expected_pairs:
        return False
    if runs != sorted(
        runs, key=lambda run: (run["task_id"], run["task_version"], run["model_id"])
    ):
        return False

    signals = snapshot.get("signals")
    expected_signals = {
        "task_count": len(normalized_tasks),
        "model_count": len(normalized_models),
        "commercial_provider_families": sorted(commercial),
        "open_model_count": len(open_models),
        "run_count": len(runs),
        "evaluation_item_count": sum(
            task["evaluation_universe"]["record_count"] for task in normalized_tasks
        ),
        "matrix_complete": True,
        "shared_evaluation_universe_enforced": True,
        "record_manifests_bound": True,
        "all_datasets_confirmed_publishable": True,
    }
    if signals != expected_signals:
        return False
    for name in (
        "matrix_complete",
        "shared_evaluation_universe_enforced",
        "record_manifests_bound",
        "all_datasets_confirmed_publishable",
    ):
        if type(signals[name]) is not bool:
            return False
    for name in (
        "task_count",
        "model_count",
        "open_model_count",
        "run_count",
        "evaluation_item_count",
    ):
        if type(signals[name]) is not int:
            return False

    claimed = snapshot.get("snapshot_sha256")
    if not isinstance(claimed, str) or not _SHA256_RE.fullmatch(claimed):
        return False
    body = dict(snapshot)
    body.pop("snapshot_sha256", None)
    return hashlib.sha256(_canon(body)).hexdigest() == claimed
