from __future__ import annotations

import argparse
import json

from cuhkx import (
    ContractError,
    HierarchicalPrior,
    ensemble_predictions,
    evaluate,
    grouped_subject_folds,
    read_prediction_csv,
    read_qa_csv,
    write_evidence,
    write_submission,
)


def cmd_validate(args: argparse.Namespace) -> int:
    rows = read_qa_csv(args.csv, training=args.training)
    payload = {"rows": len(rows), "training": args.training}
    if args.training:
        folds = grouped_subject_folds(rows, folds=args.folds)
        payload["folds"] = [{"train": len(t), "validation": len(v)} for t, v in folds]
    print(json.dumps(payload, sort_keys=True))
    return 0


def cmd_prior_cv(args: argparse.Namespace) -> int:
    rows = read_qa_csv(args.train, training=True)
    folds = grouped_subject_folds(rows, args.folds)
    reports = []
    weighted_correct = 0.0
    total = 0
    for i, (train_idx, val_idx) in enumerate(folds):
        train = [rows[j] for j in train_idx]
        val = [rows[j] for j in val_idx]
        model = HierarchicalPrior(args.min_signature_support).fit(train)
        report = evaluate(val, model.predict(val))
        reports.append({"fold": i, **report})
        weighted_correct += report["exact_accuracy"] * report["n"]
        total += report["n"]
    print(json.dumps({"n": total, "exact_accuracy": weighted_correct / total, "folds": reports}, sort_keys=True, indent=2))
    return 0


def cmd_prior_submission(args: argparse.Namespace) -> int:
    train = read_qa_csv(args.train, training=True)
    test = read_qa_csv(args.test, training=False)
    model = HierarchicalPrior(args.min_signature_support).fit(train)
    preds = model.predict(test)
    result = {
        "submission": write_submission(test, preds, args.output),
        "evidence": write_evidence(preds, args.evidence),
    }
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


def cmd_ensemble(args: argparse.Namespace) -> int:
    test = read_qa_csv(args.test, training=False)
    components = [read_prediction_csv(path) for path in args.predictions]
    weights = [float(v) for v in args.weights.split(",")] if args.weights else None
    preds = ensemble_predictions(test, components, weights)
    result = {
        "submission": write_submission(test, preds, args.output),
        "evidence": write_evidence(preds, args.evidence),
    }
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CUHK-X large-model reproducibility harness")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("validate")
    p.add_argument("csv")
    p.add_argument("--training", action="store_true")
    p.add_argument("--folds", type=int, default=5)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("prior-cv")
    p.add_argument("train")
    p.add_argument("--folds", type=int, default=5)
    p.add_argument("--min-signature-support", type=int, default=3)
    p.set_defaults(func=cmd_prior_cv)

    p = sub.add_parser("prior-submission")
    p.add_argument("train")
    p.add_argument("test")
    p.add_argument("output")
    p.add_argument("--evidence", default="prediction_evidence.json")
    p.add_argument("--min-signature-support", type=int, default=3)
    p.set_defaults(func=cmd_prior_submission)

    p = sub.add_parser("ensemble")
    p.add_argument("test")
    p.add_argument("output")
    p.add_argument("predictions", nargs="+")
    p.add_argument("--weights", help="comma-separated positive weights")
    p.add_argument("--evidence", default="prediction_evidence.json")
    p.set_defaults(func=cmd_ensemble)
    return parser


def main() -> int:
    try:
        args = build_parser().parse_args()
        return args.func(args)
    except ContractError as exc:
        raise SystemExit(f"contract error: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
