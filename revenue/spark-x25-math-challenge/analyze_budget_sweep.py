#!/usr/bin/env python3
"""Analyze a matched Spark-X2.5 GSM8K token-budget sweep from raw run evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError(f"expected JSON object: {path}")
    return obj


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"expected JSON object at {path}:{lineno}")
            rows.append(obj)
    return rows


def parse_run_spec(spec: str) -> tuple[int, Path]:
    if "=" not in spec:
        raise argparse.ArgumentTypeError("--run must be BUDGET=RUN_DIRECTORY")
    raw_budget, raw_path = spec.split("=", 1)
    try:
        budget = int(raw_budget)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid budget in {spec!r}") from exc
    if budget <= 0:
        raise argparse.ArgumentTypeError("budget must be positive")
    return budget, Path(raw_path)


def finish_reason(row: dict[str, Any]) -> str:
    raw = row.get("raw_response")
    if not isinstance(raw, dict):
        return "missing"
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return "missing"
    value = choices[0].get("finish_reason")
    return "missing" if value is None else str(value)


def prediction_key(row: dict[str, Any]) -> str:
    value = row.get("prediction_value")
    return "<UNPARSEABLE>" if value is None else str(value)


def percent(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        metavar="BUDGET=DIR",
        help="One completed eval_gsm8k.py run directory; repeat for each token budget.",
    )
    parser.add_argument("--output-dir", default="budget-analysis")
    parser.add_argument(
        "--extension-threshold",
        type=float,
        default=0.05,
        help="Recommend a larger budget if the largest-budget length-stop rate exceeds this fraction.",
    )
    args = parser.parse_args()

    if not (0.0 <= args.extension_threshold <= 1.0):
        parser.error("--extension-threshold must be between 0 and 1")

    parsed_specs = [parse_run_spec(spec) for spec in args.run]
    if len(parsed_specs) < 2:
        parser.error("provide at least two --run budgets")
    budgets = [budget for budget, _ in parsed_specs]
    if len(set(budgets)) != len(budgets):
        parser.error("duplicate token budget")
    parsed_specs.sort(key=lambda item: item[0])

    out_dir = Path(args.output_dir)
    if out_dir.exists():
        raise SystemExit(f"refusing to overwrite existing output directory: {out_dir}")
    out_dir.mkdir(parents=True)

    runs: dict[int, dict[str, Any]] = {}
    reference_contract: dict[str, Any] | None = None
    reference_indices: list[int] | None = None

    for budget, run_dir in parsed_specs:
        manifest_path = run_dir / "manifest.json"
        raw_path = run_dir / "raw.jsonl"
        summary_path = run_dir / "summary.json"
        for path in (manifest_path, raw_path, summary_path):
            if not path.is_file():
                raise FileNotFoundError(path)

        manifest = load_json(manifest_path)
        summary = load_json(summary_path)
        rows = load_jsonl(raw_path)

        observed_hash = sha256_file(raw_path)
        recorded_hash = summary.get("raw_jsonl_sha256")
        if recorded_hash != observed_hash:
            raise ValueError(
                f"raw evidence hash mismatch for budget {budget}: "
                f"summary={recorded_hash!r} observed={observed_hash}"
            )

        dataset = manifest.get("dataset")
        generation = manifest.get("generation")
        model = manifest.get("model")
        if not isinstance(dataset, dict) or not isinstance(generation, dict) or not isinstance(model, dict):
            raise ValueError(f"malformed manifest for budget {budget}")

        indices = dataset.get("indices")
        if not isinstance(indices, list) or not all(isinstance(x, int) for x in indices):
            raise ValueError(f"manifest indices missing/malformed for budget {budget}")
        if len(rows) != len(indices):
            raise ValueError(
                f"row count {len(rows)} != manifest index count {len(indices)} for budget {budget}"
            )
        observed_indices = [row.get("dataset_index") for row in rows]
        if observed_indices != indices:
            raise ValueError(f"raw row order does not match manifest indices for budget {budget}")

        manifest_budget = generation.get("max_tokens")
        if manifest_budget != budget:
            raise ValueError(
                f"budget label {budget} != manifest max_tokens {manifest_budget!r}"
            )

        contract = {
            "model_id": model.get("id"),
            "model_revision": model.get("revision"),
            "dataset_id": dataset.get("id"),
            "dataset_config": dataset.get("config"),
            "dataset_split": dataset.get("split"),
            "dataset_revision": dataset.get("revision"),
            "sample_size": dataset.get("sample_size"),
            "sample_seed": dataset.get("sample_seed"),
            "prompt_mode": generation.get("prompt_mode"),
            "generation_seed": generation.get("generation_seed"),
            "temperature": generation.get("temperature"),
            "top_p": generation.get("top_p"),
        }
        if reference_contract is None:
            reference_contract = contract
            reference_indices = indices
        elif contract != reference_contract:
            raise ValueError(
                f"matched-sweep contract differs at budget {budget}: "
                f"{contract!r} != {reference_contract!r}"
            )
        if indices != reference_indices:
            raise ValueError(f"sample indices differ at budget {budget}")

        correct = sum(bool(row.get("correct")) for row in rows)
        parsed = sum(row.get("prediction_value") is not None for row in rows)
        reasons = Counter(finish_reason(row) for row in rows)
        completion_tokens = [
            int((row.get("usage") or {}).get("completion_tokens") or 0) for row in rows
        ]
        latencies = [float(row.get("latency_seconds") or 0.0) for row in rows]

        runs[budget] = {
            "dir": str(run_dir),
            "manifest": manifest,
            "summary": summary,
            "rows": rows,
            "raw_jsonl_sha256": observed_hash,
            "n": len(rows),
            "correct": correct,
            "accuracy": correct / len(rows) if rows else 0.0,
            "parsed": parsed,
            "parse_rate": parsed / len(rows) if rows else 0.0,
            "finish_reasons": dict(sorted(reasons.items())),
            "length_stops": reasons.get("length", 0),
            "length_stop_rate": reasons.get("length", 0) / len(rows) if rows else 0.0,
            "completion_tokens_total": sum(completion_tokens),
            "completion_tokens_mean": statistics.fmean(completion_tokens) if completion_tokens else 0.0,
            "completion_tokens_median": statistics.median(completion_tokens) if completion_tokens else 0.0,
            "latency_seconds_total": sum(latencies),
            "latency_seconds_mean": statistics.fmean(latencies) if latencies else 0.0,
        }

    ordered_budgets = sorted(runs)
    adjacent: list[dict[str, Any]] = []
    for low, high in zip(ordered_budgets, ordered_budgets[1:]):
        low_rows = runs[low]["rows"]
        high_rows = runs[high]["rows"]
        counts = Counter()
        changed_examples: dict[str, list[int]] = {
            "wrong_to_right": [],
            "right_to_wrong": [],
            "prediction_changed": [],
        }
        for left, right in zip(low_rows, high_rows):
            left_ok = bool(left.get("correct"))
            right_ok = bool(right.get("correct"))
            if not left_ok and right_ok:
                counts["wrong_to_right"] += 1
                changed_examples["wrong_to_right"].append(int(right["dataset_index"]))
            if left_ok and not right_ok:
                counts["right_to_wrong"] += 1
                changed_examples["right_to_wrong"].append(int(right["dataset_index"]))
            if prediction_key(left) != prediction_key(right):
                counts["prediction_changed"] += 1
                changed_examples["prediction_changed"].append(int(right["dataset_index"]))
        adjacent.append(
            {
                "from_budget": low,
                "to_budget": high,
                "wrong_to_right": counts["wrong_to_right"],
                "right_to_wrong": counts["right_to_wrong"],
                "prediction_changed": counts["prediction_changed"],
                "example_dataset_indices": {
                    key: values[:8] for key, values in changed_examples.items()
                },
            }
        )

    largest_budget = ordered_budgets[-1]
    n_items = runs[largest_budget]["n"]
    stabilization_counts: Counter[int | str] = Counter()
    per_item: list[dict[str, Any]] = []
    for pos in range(n_items):
        series = [
            (budget, prediction_key(runs[budget]["rows"][pos]))
            for budget in ordered_budgets
        ]
        max_prediction = series[-1][1]
        stabilization_budget: int | None = None
        for i, (budget, _) in enumerate(series):
            if all(pred == max_prediction for _, pred in series[i:]):
                stabilization_budget = budget
                break
        if stabilization_budget is None:
            stabilization_counts["none"] += 1
        else:
            stabilization_counts[stabilization_budget] += 1
        per_item.append(
            {
                "dataset_index": int(runs[largest_budget]["rows"][pos]["dataset_index"]),
                "gold_value": runs[largest_budget]["rows"][pos].get("gold_value"),
                "series": [
                    {
                        "budget": budget,
                        "prediction": prediction_key(runs[budget]["rows"][pos]),
                        "correct": bool(runs[budget]["rows"][pos].get("correct")),
                        "finish_reason": finish_reason(runs[budget]["rows"][pos]),
                        "completion_tokens": int(
                            (runs[budget]["rows"][pos].get("usage") or {}).get("completion_tokens")
                            or 0
                        ),
                    }
                    for budget in ordered_budgets
                ],
                "stabilization_budget_to_largest_prediction": stabilization_budget,
            }
        )

    max_length_rate = runs[largest_budget]["length_stop_rate"]
    extension_recommended = max_length_rate > args.extension_threshold
    suggested_next_budget = largest_budget * 2 if extension_recommended else None

    result = {
        "schema_version": 1,
        "contract": reference_contract,
        "indices": reference_indices,
        "budgets": ordered_budgets,
        "per_budget": {
            str(budget): {
                key: value
                for key, value in runs[budget].items()
                if key not in {"manifest", "summary", "rows"}
            }
            for budget in ordered_budgets
        },
        "adjacent_transitions": adjacent,
        "stabilization_counts": {
            str(key): value
            for key, value in sorted(
                stabilization_counts.items(), key=lambda item: str(item[0])
            )
        },
        "per_item": per_item,
        "extension_rule": {
            "largest_budget": largest_budget,
            "length_stop_rate": max_length_rate,
            "threshold": args.extension_threshold,
            "extension_recommended": extension_recommended,
            "suggested_next_budget": suggested_next_budget,
        },
    }

    summary_path = out_dir / "budget_sweep_summary.json"
    summary_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines = [
        "# Spark-X2.5 reasoning-token budget frontier",
        "",
        f"Matched items: {n_items}",
        f"Prompt mode: `{reference_contract['prompt_mode']}`",
        f"Model revision: `{reference_contract['model_revision']}`",
        f"Dataset revision: `{reference_contract['dataset_revision']}`",
        "",
        "| max_tokens | accuracy | parse rate | length-stop rate | mean completion tokens | mean latency (s) |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for budget in ordered_budgets:
        run = runs[budget]
        lines.append(
            f"| {budget} | {percent(run['accuracy'])} | {percent(run['parse_rate'])} | "
            f"{percent(run['length_stop_rate'])} | {run['completion_tokens_mean']:.1f} | "
            f"{run['latency_seconds_mean']:.3f} |"
        )

    lines.extend(["", "## Adjacent-budget answer changes", ""])
    for item in adjacent:
        lines.append(
            f"- {item['from_budget']}→{item['to_budget']}: "
            f"{item['wrong_to_right']} wrong→right, "
            f"{item['right_to_wrong']} right→wrong, "
            f"{item['prediction_changed']} prediction changes."
        )

    lines.extend(["", "## Predeclared extension rule", ""])
    if extension_recommended:
        lines.append(
            f"Largest budget {largest_budget} still had a {percent(max_length_rate)} length-stop "
            f"rate, above the {percent(args.extension_threshold)} threshold; run the same matched "
            f"sample at max_tokens={suggested_next_budget} before final analysis."
        )
    else:
        lines.append(
            f"Largest budget {largest_budget} had a {percent(max_length_rate)} length-stop rate, "
            f"not above the {percent(args.extension_threshold)} threshold; no larger-budget "
            "extension is required by the predeclared rule."
        )

    lines.extend(
        [
            "",
            "The JSON summary contains per-item prediction trajectories, stabilization budgets, "
            "raw-evidence hashes, finish reasons, and deterministic example indices for manual "
            "complete-reasoning inspection.",
            "",
        ]
    )
    (out_dir / "budget_sweep_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(result["extension_rule"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
