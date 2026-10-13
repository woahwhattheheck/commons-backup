"""Deterministic, buyer-neutral benchmark scoring core for objective classification tasks."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import math
import random
import re
from typing import Any, Iterable, Mapping

SCHEMA = "cas-actuarial-llm-benchmark-core/v1"
RUN_SCHEMA = "cas-actuarial-llm-benchmark-run/v1"
RECEIPT_SCHEMA = "cas-actuarial-llm-benchmark-receipt/v1"
BOARD_SCHEMA = "cas-actuarial-llm-benchmark-board/v1"
AUTHORITY = "REPRODUCIBILITY_ONLY_NO_ACTUARIAL_VALIDATION"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
DEC_RE = re.compile(r"^(?:0|1)(?:\.\d{1,18})?$|^0\.\d{1,18}$")
METRICS = ("accuracy", "macro_f1", "brier", "log_loss")


class BenchmarkError(ValueError):
    pass


def _canon(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise BenchmarkError("value must be canonical JSON") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _exact(value: Any, keys: set[str], field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise BenchmarkError(f"{field} must contain exactly {sorted(keys)}")
    return value


def _text(value: Any, field: str, limit: int = 512) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > limit:
        raise BenchmarkError(f"{field} must be a bounded non-empty string")
    return value


def _id(value: Any, field: str) -> str:
    value = _text(value, field, 128)
    if not ID_RE.fullmatch(value):
        raise BenchmarkError(f"{field} is not a canonical identifier")
    return value


def _hash(value: Any, field: str) -> str:
    value = _text(value, field, 64)
    if not HASH_RE.fullmatch(value):
        raise BenchmarkError(f"{field} must be lowercase sha256")
    return value


def _decimal(value: Any, field: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not DEC_RE.fullmatch(value):
        raise BenchmarkError(f"{field} must be a canonical decimal string in [0,1]")
    try:
        out = Decimal(value)
    except InvalidOperation as exc:
        raise BenchmarkError(f"{field} is not a decimal") from exc
    if out < 0 or out > 1 or (positive and out <= 0):
        raise BenchmarkError(f"{field} is outside allowed range")
    return out


def _int(value: Any, field: str, lo: int, hi: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not lo <= value <= hi:
        raise BenchmarkError(f"{field} must be integer in [{lo},{hi}]")
    return value


def _fmt(value: Decimal) -> str:
    with localcontext() as ctx:
        ctx.prec = 50
        q = value.quantize(Decimal("0.000000000001"))
    return format(q, "f")


def _normalize_suite(raw: Mapping[str, Any]) -> dict[str, Any]:
    obj = _exact(dict(raw) if isinstance(raw, Mapping) else raw, {
        "schema", "suite_id", "version", "title", "dataset_license", "provenance_url",
        "dataset_sha256", "metric_policy", "tasks",
    }, "suite")
    if obj["schema"] != SCHEMA:
        raise BenchmarkError("unsupported suite schema")
    metric = _exact(obj["metric_policy"], {
        "primary_metric", "probability_floor", "bootstrap_replicates", "confidence_level", "bootstrap_seed",
    }, "suite.metric_policy")
    primary = _text(metric["primary_metric"], "primary_metric", 32)
    if primary not in METRICS:
        raise BenchmarkError("unsupported primary metric")
    floor = _decimal(metric["probability_floor"], "probability_floor", positive=True)
    confidence = _decimal(metric["confidence_level"], "confidence_level", positive=True)
    if not Decimal("0.5") <= confidence < 1:
        raise BenchmarkError("confidence_level must be in [0.5,1)")
    tasks_raw = obj["tasks"]
    if not isinstance(tasks_raw, list) or not 1 <= len(tasks_raw) <= 128:
        raise BenchmarkError("tasks must contain 1..128 entries")
    tasks = []
    task_ids: set[str] = set()
    weight_sum = Decimal(0)
    all_item_keys: set[tuple[str, str]] = set()
    for pos, task_raw in enumerate(tasks_raw):
        task = _exact(task_raw, {"task_id", "title", "domain", "labels", "weight", "items"}, f"tasks[{pos}]")
        task_id = _id(task["task_id"], "task_id")
        if task_id in task_ids:
            raise BenchmarkError("duplicate task_id")
        task_ids.add(task_id)
        labels = task["labels"]
        if not isinstance(labels, list) or not 2 <= len(labels) <= 32:
            raise BenchmarkError("labels must contain 2..32 values")
        labels_n = [_id(x, "label") for x in labels]
        if len(set(labels_n)) != len(labels_n):
            raise BenchmarkError("duplicate label")
        labels_n = sorted(labels_n)
        weight = _decimal(task["weight"], "task.weight", positive=True)
        weight_sum += weight
        items_raw = task["items"]
        if not isinstance(items_raw, list) or not 1 <= len(items_raw) <= 100_000:
            raise BenchmarkError("task.items must be non-empty")
        items = []
        item_ids: set[str] = set()
        for item_raw in items_raw:
            item = _exact(item_raw, {"item_id", "prompt_sha256", "gold_label", "source_ref"}, "item")
            item_id = _id(item["item_id"], "item.item_id")
            if item_id in item_ids:
                raise BenchmarkError("duplicate item_id inside task")
            item_ids.add(item_id)
            gold = _id(item["gold_label"], "item.gold_label")
            if gold not in labels_n:
                raise BenchmarkError("gold_label outside task labels")
            key = (task_id, item_id)
            if key in all_item_keys:
                raise BenchmarkError("duplicate task/item identity")
            all_item_keys.add(key)
            items.append({
                "item_id": item_id,
                "prompt_sha256": _hash(item["prompt_sha256"], "item.prompt_sha256"),
                "gold_label": gold,
                "source_ref": _text(item["source_ref"], "item.source_ref", 512),
            })
        tasks.append({
            "task_id": task_id, "title": _text(task["title"], "task.title", 256),
            "domain": _text(task["domain"], "task.domain", 128), "labels": labels_n,
            "weight": _fmt(weight), "items": sorted(items, key=lambda x: x["item_id"]),
        })
    if weight_sum != Decimal(1):
        raise BenchmarkError("task weights must sum exactly to 1")
    return {
        "schema": SCHEMA,
        "suite_id": _id(obj["suite_id"], "suite_id"),
        "version": _text(obj["version"], "version", 128),
        "title": _text(obj["title"], "title", 256),
        "dataset_license": _text(obj["dataset_license"], "dataset_license", 128),
        "provenance_url": _text(obj["provenance_url"], "provenance_url", 1024),
        "dataset_sha256": _hash(obj["dataset_sha256"], "dataset_sha256"),
        "metric_policy": {
            "primary_metric": primary,
            "probability_floor": _fmt(floor),
            "bootstrap_replicates": _int(metric["bootstrap_replicates"], "bootstrap_replicates", 50, 5000),
            "confidence_level": _fmt(confidence),
            "bootstrap_seed": _id(metric["bootstrap_seed"], "bootstrap_seed"),
        },
        "tasks": sorted(tasks, key=lambda x: x["task_id"]),
    }


def _normalize_run(raw: Mapping[str, Any]) -> dict[str, Any]:
    obj = _exact(dict(raw) if isinstance(raw, Mapping) else raw, {
        "schema", "run_id", "suite_id", "suite_version", "dataset_sha256", "model",
        "adapter_version", "prompt_policy_sha256", "predictions",
    }, "run")
    if obj["schema"] != RUN_SCHEMA:
        raise BenchmarkError("unsupported run schema")
    model = _exact(obj["model"], {"provider", "model_id", "model_version", "config_sha256"}, "run.model")
    preds_raw = obj["predictions"]
    if not isinstance(preds_raw, list) or not 1 <= len(preds_raw) <= 500_000:
        raise BenchmarkError("predictions must be non-empty")
    variants: dict[tuple[str, str], dict[bytes, dict[str, Any]]] = defaultdict(dict)
    for p_raw in preds_raw:
        p = _exact(p_raw, {"task_id", "item_id", "probabilities"}, "prediction")
        task_id, item_id = _id(p["task_id"], "prediction.task_id"), _id(p["item_id"], "prediction.item_id")
        probs_raw = p["probabilities"]
        if not isinstance(probs_raw, dict) or not 2 <= len(probs_raw) <= 32:
            raise BenchmarkError("probabilities must contain 2..32 labels")
        probs: dict[str, str] = {}
        total = Decimal(0)
        for label, value in probs_raw.items():
            label_n = _id(label, "probability.label")
            d = _decimal(value, f"probability.{label_n}")
            probs[label_n] = _fmt(d)
            total += d
        if total != Decimal(1):
            raise BenchmarkError("probabilities must sum exactly to 1")
        norm = {"task_id": task_id, "item_id": item_id, "probabilities": dict(sorted(probs.items()))}
        variants[(task_id, item_id)][_canon(norm)] = norm
    predictions = []
    conflicts = []
    for key in sorted(variants):
        group = variants[key]
        if len(group) > 1:
            conflicts.append(f"{key[0]}:{key[1]}")
        predictions.append(group[min(group)])
    return {
        "schema": RUN_SCHEMA,
        "run_id": _id(obj["run_id"], "run_id"),
        "suite_id": _id(obj["suite_id"], "run.suite_id"),
        "suite_version": _text(obj["suite_version"], "run.suite_version", 128),
        "dataset_sha256": _hash(obj["dataset_sha256"], "run.dataset_sha256"),
        "model": {
            "provider": _text(model["provider"], "model.provider", 128),
            "model_id": _id(model["model_id"], "model.model_id"),
            "model_version": _text(model["model_version"], "model.model_version", 128),
            "config_sha256": _hash(model["config_sha256"], "model.config_sha256"),
        },
        "adapter_version": _text(obj["adapter_version"], "adapter_version", 128),
        "prompt_policy_sha256": _hash(obj["prompt_policy_sha256"], "prompt_policy_sha256"),
        "predictions": predictions,
        "prediction_conflicts": conflicts,
    }


def _task_metric(task: Mapping[str, Any], pred_by_item: Mapping[str, Mapping[str, str]], indices: list[int] | None = None) -> dict[str, Decimal]:
    items = task["items"]
    chosen = list(range(len(items))) if indices is None else indices
    labels = task["labels"]
    floor = Decimal("0")  # replaced by caller for log-loss
    correct = Decimal(0)
    brier = Decimal(0)
    log_terms: list[Decimal] = []
    tp = {label: 0 for label in labels}; fp = {label: 0 for label in labels}; fn = {label: 0 for label in labels}
    rows: list[tuple[Mapping[str, Any], Mapping[str, str]]] = []
    for idx in chosen:
        item = items[idx]
        probs = pred_by_item[item["item_id"]]
        predicted = sorted(labels, key=lambda l: (-Decimal(probs[l]), l))[0]
        gold = item["gold_label"]
        if predicted == gold:
            correct += 1; tp[gold] += 1
        else:
            fp[predicted] += 1; fn[gold] += 1
        for label in labels:
            target = Decimal(1) if label == gold else Decimal(0)
            delta = Decimal(probs[label]) - target
            brier += delta * delta
        rows.append((item, probs))
    n = Decimal(len(chosen))
    f1s = []
    for label in labels:
        denom = 2 * tp[label] + fp[label] + fn[label]
        f1s.append(Decimal(0) if denom == 0 else Decimal(2 * tp[label]) / Decimal(denom))
    return {
        "accuracy": correct / n,
        "macro_f1": sum(f1s, Decimal(0)) / Decimal(len(labels)),
        "brier": brier / n,
        "_row_count": n,
        "_rows": rows,  # type: ignore[dict-item]
    }


def _metrics_for_task(task: Mapping[str, Any], pred_by_item: Mapping[str, Mapping[str, str]], floor: Decimal, indices: list[int] | None = None) -> dict[str, Decimal]:
    base = _task_metric(task, pred_by_item, indices)
    rows = base.pop("_rows")  # type: ignore[assignment]
    base.pop("_row_count", None)
    with localcontext() as ctx:
        ctx.prec = 50
        losses = []
        for item, probs in rows:  # type: ignore[misc]
            p = max(Decimal(probs[item["gold_label"]]), floor)
            losses.append(-p.ln())
        base["log_loss"] = sum(losses, Decimal(0)) / Decimal(len(losses))
    return base


def _weighted(metrics_by_task: Mapping[str, Mapping[str, Decimal]], task_map: Mapping[str, Mapping[str, Any]]) -> dict[str, Decimal]:
    out = {m: Decimal(0) for m in METRICS}
    for task_id, metrics in metrics_by_task.items():
        weight = Decimal(task_map[task_id]["weight"])
        for metric in METRICS:
            out[metric] += weight * metrics[metric]
    return out


def _quantile(values: list[Decimal], q: Decimal) -> Decimal:
    if not values:
        raise BenchmarkError("empty quantile input")
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    pos = q * Decimal(len(vals) - 1)
    lo = int(pos); hi = min(lo + 1, len(vals) - 1)
    frac = pos - Decimal(lo)
    return vals[lo] * (Decimal(1) - frac) + vals[hi] * frac


def _bootstrap(suite: Mapping[str, Any], run: Mapping[str, Any], pred_lookup: Mapping[str, Mapping[str, Mapping[str, str]]]) -> dict[str, dict[str, str]]:
    reps = suite["metric_policy"]["bootstrap_replicates"]
    confidence = Decimal(suite["metric_policy"]["confidence_level"])
    alpha = (Decimal(1) - confidence) / Decimal(2)
    seed_material = f"{suite['metric_policy']['bootstrap_seed']}:{_sha(suite)}:{_sha(run)}"
    rng = random.Random(int(hashlib.sha256(seed_material.encode()).hexdigest(), 16))
    floor = Decimal(suite["metric_policy"]["probability_floor"])
    task_map = {t["task_id"]: t for t in suite["tasks"]}
    samples = {m: [] for m in METRICS}
    for _ in range(reps):
        per_task = {}
        for task in suite["tasks"]:
            n = len(task["items"])
            indices = [rng.randrange(n) for _ in range(n)]
            per_task[task["task_id"]] = _metrics_for_task(task, pred_lookup[task["task_id"]], floor, indices)
        agg = _weighted(per_task, task_map)
        for metric in METRICS:
            samples[metric].append(agg[metric])
    return {
        metric: {"lower": _fmt(_quantile(values, alpha)), "upper": _fmt(_quantile(values, Decimal(1) - alpha))}
        for metric, values in samples.items()
    }


def score_run(suite_raw: Mapping[str, Any], run_raw: Mapping[str, Any]) -> dict[str, Any]:
    suite = _normalize_suite(suite_raw)
    run = _normalize_run(run_raw)
    reasons: set[str] = set()
    if run["suite_id"] != suite["suite_id"]: reasons.add("SUITE_ID_MISMATCH")
    if run["suite_version"] != suite["version"]: reasons.add("SUITE_VERSION_MISMATCH")
    if run["dataset_sha256"] != suite["dataset_sha256"]: reasons.add("DATASET_DIGEST_MISMATCH")
    if run["prediction_conflicts"]: reasons.add("PREDICTION_IDENTITY_CONFLICT")
    expected: dict[tuple[str, str], Mapping[str, Any]] = {}
    task_map = {t["task_id"]: t for t in suite["tasks"]}
    for task in suite["tasks"]:
        for item in task["items"]:
            expected[(task["task_id"], item["item_id"])] = item
    seen = {(p["task_id"], p["item_id"]): p for p in run["predictions"]}
    missing = sorted(f"{t}:{i}" for t, i in expected if (t, i) not in seen)
    unknown = sorted(f"{t}:{i}" for t, i in seen if (t, i) not in expected)
    if missing: reasons.add("MISSING_PREDICTIONS")
    if unknown: reasons.add("UNKNOWN_PREDICTIONS")
    for key, pred in seen.items():
        if key not in expected: continue
        labels = task_map[key[0]]["labels"]
        if sorted(pred["probabilities"]) != labels:
            reasons.add("LABEL_SET_MISMATCH")
    metrics_json = None
    per_task_json = None
    ci_json = None
    if not reasons:
        floor = Decimal(suite["metric_policy"]["probability_floor"])
        lookup: dict[str, dict[str, Mapping[str, str]]] = defaultdict(dict)
        for p in run["predictions"]:
            lookup[p["task_id"]][p["item_id"]] = p["probabilities"]
        per_task_d = {t["task_id"]: _metrics_for_task(t, lookup[t["task_id"]], floor) for t in suite["tasks"]}
        metrics_d = _weighted(per_task_d, task_map)
        metrics_json = {m: _fmt(metrics_d[m]) for m in METRICS}
        per_task_json = {tid: {m: _fmt(vals[m]) for m in METRICS} for tid, vals in sorted(per_task_d.items())}
        ci_json = _bootstrap(suite, run, lookup)
    core = {
        "schema": RECEIPT_SCHEMA,
        "authority": AUTHORITY,
        "status": "READY" if not reasons else "HOLD",
        "reasons": sorted(reasons),
        "suite_id": suite["suite_id"], "suite_version": suite["version"], "run_id": run["run_id"],
        "model": deepcopy(run["model"]),
        "suite_digest": _sha(suite), "run_digest": _sha(run),
        "expected_item_count": len(expected), "prediction_count": len(run["predictions"]),
        "missing_items": missing[:100], "unknown_items": unknown[:100],
        "prediction_conflicts": run["prediction_conflicts"][:100],
        "metrics": metrics_json, "per_task": per_task_json, "confidence_intervals": ci_json,
    }
    return {**core, "receipt_sha256": _sha(core)}


def verify_receipt(receipt: Mapping[str, Any], suite: Mapping[str, Any], run: Mapping[str, Any], *, require_ready: bool = True) -> bool:
    try:
        expected = score_run(suite, run)
        if expected != dict(receipt):
            return False
        if require_ready and expected["status"] != "READY":
            return False
        core = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
        return receipt.get("receipt_sha256") == _sha(core)
    except (BenchmarkError, KeyError, TypeError, ValueError):
        return False


def build_board(suite_raw: Mapping[str, Any], receipts: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    suite = _normalize_suite(suite_raw)
    suite_digest = _sha(suite)
    rows: dict[str, dict[str, Any]] = {}
    for receipt_raw in receipts:
        receipt = dict(receipt_raw)
        if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("authority") != AUTHORITY:
            raise BenchmarkError("unsupported receipt in board")
        if receipt.get("status") != "READY" or receipt.get("suite_digest") != suite_digest:
            raise BenchmarkError("board accepts only READY receipts for this exact suite")
        run_id = _id(receipt.get("run_id"), "receipt.run_id")
        core = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
        if receipt.get("receipt_sha256") != _sha(core):
            raise BenchmarkError("receipt hash mismatch")
        if run_id in rows and rows[run_id] != receipt:
            raise BenchmarkError("conflicting duplicate run_id")
        rows[run_id] = receipt
    if not rows:
        raise BenchmarkError("board requires at least one READY receipt")
    primary = suite["metric_policy"]["primary_metric"]
    def rank_key(r: Mapping[str, Any]) -> tuple[Any, ...]:
        m = r["metrics"]
        primary_val = Decimal(m[primary])
        first = primary_val if primary in {"brier", "log_loss"} else -primary_val
        return (first, -Decimal(m["accuracy"]), -Decimal(m["macro_f1"]), Decimal(m["log_loss"]), Decimal(m["brier"]), r["model"]["model_id"], r["run_id"])
    ordered = sorted(rows.values(), key=rank_key)
    entries = []
    for rank, r in enumerate(ordered, 1):
        entries.append({
            "rank": rank, "run_id": r["run_id"], "model": r["model"], "metrics": r["metrics"],
            "confidence_intervals": r["confidence_intervals"], "receipt_sha256": r["receipt_sha256"],
        })
    core = {
        "schema": BOARD_SCHEMA, "authority": AUTHORITY, "suite_id": suite["suite_id"],
        "suite_version": suite["version"], "suite_digest": suite_digest,
        "primary_metric": primary, "entry_count": len(entries), "entries": entries,
    }
    return {**core, "board_sha256": _sha(core)}


def verify_board(board: Mapping[str, Any], suite: Mapping[str, Any], receipts: Iterable[Mapping[str, Any]]) -> bool:
    try:
        return build_board(suite, receipts) == dict(board)
    except (BenchmarkError, KeyError, TypeError, ValueError):
        return False
