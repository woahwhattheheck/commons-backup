"""Local-only manifest -> features -> grouped OOF -> calibrated model runner.

This module is public code. Competition rows, labels, derived features, fitted parameters,
and generated artifacts must remain in the participant's rule-compliant local environment.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .contract import ModelContractError, canonical_json
from .core import feature_matrix, train_feature_model
from .io import load_nifti_array, read_training_manifest, write_model_json


def _write_receipt_exclusive(path: Path, receipt: dict) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(receipt) + "\n")
    except FileExistsError:
        raise FileExistsError(f"refusing to overwrite training receipt: {destination}") from None


def train_from_manifest(
    manifest: Path,
    *,
    uid_column: str,
    label_column: str,
    path_column: str,
    group_column: str | None,
    model_output: Path,
    receipt_output: Path,
    n_splits: int = 4,
    seed: int = 20260913,
) -> tuple[dict, dict]:
    rows = read_training_manifest(
        manifest,
        uid_column=uid_column,
        label_column=label_column,
        path_column=path_column,
        group_column=group_column,
    )
    matrix, feature_names = feature_matrix(load_nifti_array(row["path"]) for row in rows)
    labels = np.asarray([row["label"] for row in rows], dtype=np.int64)
    groups = [row["group"] for row in rows] if group_column else None
    artifact, receipt = train_feature_model(
        matrix,
        labels,
        feature_names,
        groups=groups,
        n_splits=n_splits,
        seed=seed,
    )
    write_model_json(model_output, artifact)
    _write_receipt_exclusive(receipt_output, receipt)
    return artifact, receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the public DaT V2 feature model locally")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--uid-column", required=True)
    parser.add_argument("--label-column", required=True)
    parser.add_argument("--path-column", required=True)
    parser.add_argument("--group-column")
    parser.add_argument("--model-output", type=Path, required=True)
    parser.add_argument("--receipt-output", type=Path, required=True)
    parser.add_argument("--n-splits", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260913)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        artifact, receipt = train_from_manifest(
            args.manifest,
            uid_column=args.uid_column,
            label_column=args.label_column,
            path_column=args.path_column,
            group_column=args.group_column,
            model_output=args.model_output,
            receipt_output=args.receipt_output,
            n_splits=args.n_splits,
            seed=args.seed,
        )
    except (ModelContractError, FileExistsError, OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(f"training failed closed: {exc}") from exc
    print(canonical_json({
        "model_sha256": artifact["model_sha256"],
        "receipt_sha256": receipt["receipt_sha256"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
