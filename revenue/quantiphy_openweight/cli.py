#!/usr/bin/env python3
"""CLI for the QuantiPhy open-weight public-validation carrier."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

try:
    from .toolkit import (
        QuantiPhyError,
        apply_recipe,
        build_recipe,
        canonical_json_bytes,
        file_sha256,
        read_csv_rows,
        score_prediction_rows,
        validate_prediction_rows,
        write_submission,
    )
except ImportError:  # direct script execution
    from toolkit import (  # type: ignore
        QuantiPhyError,
        apply_recipe,
        build_recipe,
        canonical_json_bytes,
        file_sha256,
        read_csv_rows,
        score_prediction_rows,
        validate_prediction_rows,
        write_submission,
    )


def _named_predictions(values: Sequence[str]) -> tuple[list[str], list[list[dict[str, str]]], list[str]]:
    names: list[str] = []
    rows: list[list[dict[str, str]]] = []
    paths: list[str] = []
    for value in values:
        if "=" not in value:
            raise QuantiPhyError("--prediction must be NAME=PATH")
        name, path = value.split("=", 1)
        if not name or not path:
            raise QuantiPhyError("--prediction must be NAME=PATH")
        names.append(name)
        paths.append(path)
        rows.append(read_csv_rows(path))
    if len(set(names)) != len(names):
        raise QuantiPhyError("prediction names must be unique")
    return names, rows, paths


def _print_json(value: object) -> None:
    print(canonical_json_bytes(value).decode("utf-8"), end="")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QuantiPhy public-validation scoring and ensemble selection")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate an organizer-shaped prediction CSV")
    validate.add_argument("prediction")
    validate.add_argument("--categories", action="store_true", help="require category metadata")
    validate.add_argument("--allow-zero", action="store_true")

    score = sub.add_parser("score", help="mirror the public QuantiPhy MRA scorer")
    score.add_argument("--ground-truth", required=True)
    score.add_argument("--prediction", required=True)

    select = sub.add_parser("select", help="CV-select model/ensemble and fit category scales")
    select.add_argument("--ground-truth", required=True)
    select.add_argument("--prediction", action="append", required=True, metavar="NAME=PATH")
    select.add_argument("--folds", type=int, default=5)
    select.add_argument("--recipe-out", required=True)

    ensemble = sub.add_parser("ensemble", help="apply a frozen recipe and write a submission-shaped CSV")
    ensemble.add_argument("--recipe", required=True)
    ensemble.add_argument("--prediction", action="append", required=True, metavar="NAME=PATH")
    ensemble.add_argument("--output", required=True)
    ensemble.add_argument("--manifest-out")

    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            result = validate_prediction_rows(
                read_csv_rows(args.prediction),
                require_categories=args.categories,
                reject_zero=not args.allow_zero,
            )
            result["sha256"] = file_sha256(args.prediction)
            _print_json(result)
            return 0

        if args.command == "score":
            result = score_prediction_rows(read_csv_rows(args.ground_truth), read_csv_rows(args.prediction))
            result["ground_truth_sha256"] = file_sha256(args.ground_truth)
            result["prediction_sha256"] = file_sha256(args.prediction)
            _print_json(result)
            return 0

        if args.command == "select":
            names, prediction_rows, prediction_paths = _named_predictions(args.prediction)
            truth_rows = read_csv_rows(args.ground_truth)
            recipe = build_recipe(truth_rows, prediction_rows, prediction_names=names, fold_count=args.folds)
            recipe["provenance"] = {
                "ground_truth_sha256": file_sha256(args.ground_truth),
                "prediction_sha256": {name: file_sha256(path) for name, path in zip(names, prediction_paths)},
            }
            recipe_path = Path(args.recipe_out)
            recipe_path.parent.mkdir(parents=True, exist_ok=True)
            recipe_path.write_bytes(canonical_json_bytes(recipe))
            _print_json({"ok": True, "recipe": str(recipe_path), "recipe_sha256": file_sha256(recipe_path), **recipe})
            return 0

        if args.command == "ensemble":
            recipe = json.loads(Path(args.recipe).read_text(encoding="utf-8"))
            names, prediction_rows, prediction_paths = _named_predictions(args.prediction)
            output_rows = apply_recipe(recipe, prediction_rows, prediction_names=names)
            submission = write_submission(output_rows, args.output)
            manifest = {
                "schema_version": 1,
                "recipe_sha256": file_sha256(args.recipe),
                "inputs": {name: {"path": path, "sha256": file_sha256(path)} for name, path in zip(names, prediction_paths)},
                "output": submission,
                "claims": {
                    "inference_performed": False,
                    "competition_submission_performed": False,
                    "hidden_ground_truth_used": False,
                },
            }
            manifest_path = Path(args.manifest_out or (str(args.output) + ".manifest.json"))
            manifest_path.write_bytes(canonical_json_bytes(manifest))
            _print_json({"ok": True, "submission": submission, "manifest": str(manifest_path), "manifest_sha256": file_sha256(manifest_path)})
            return 0
    except (OSError, json.JSONDecodeError, QuantiPhyError) as exc:
        _print_json({"ok": False, "error": str(exc)})
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
