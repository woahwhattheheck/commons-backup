"""Competition-only grouped OOF training and train-only calibration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .artifact import apply_calibrator, probability_logit
from .contract import (
    FEATURE_NAMES, FEATURE_VERSION, RUNTIME_COMMIT, SCHEMA_VERSION,
    ModelContractError, sha256_json,
)

def binary_log_loss(y_true: Sequence[int] | np.ndarray, probabilities: Sequence[float] | np.ndarray) -> float:
    y = np.asarray(y_true, dtype=np.int64)
    p = np.asarray(probabilities, dtype=np.float64)
    if y.ndim != 1 or p.ndim != 1 or len(y) != len(p) or len(y) == 0:
        raise ModelContractError("log loss inputs must be non-empty aligned vectors")
    if not np.isin(y, [0, 1]).all():
        raise ModelContractError("labels must be binary 0/1")
    if not np.isfinite(p).all():
        raise ModelContractError("probabilities must be finite")
    p = np.clip(p, 1e-7, 1.0 - 1e-7)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _validate_training_matrix(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    features = np.asarray(X, dtype=np.float64)
    labels = np.asarray(y, dtype=np.int64)
    if features.ndim != 2 or labels.ndim != 1 or len(features) != len(labels):
        raise ModelContractError("X must be 2D and y a same-length 1D vector")
    if len(labels) < 12:
        raise ModelContractError("training requires at least 12 rows")
    if not np.isfinite(features).all():
        raise ModelContractError("training features contain NaN or infinity")
    if not np.isin(labels, [0, 1]).all() or len(np.unique(labels)) != 2:
        raise ModelContractError("training labels must contain both binary classes")
    return features, labels


def _build_splits(
    X: np.ndarray,
    y: np.ndarray,
    groups: Sequence[object] | np.ndarray | None,
    *,
    n_splits: int,
    seed: int,
) -> tuple[list[tuple[np.ndarray, np.ndarray]], dict]:
    if not isinstance(n_splits, int) or n_splits < 2:
        raise ModelContractError("n_splits must be an integer >=2")
    if n_splits > min(int(np.sum(y == 0)), int(np.sum(y == 1))):
        raise ModelContractError("n_splits exceeds the smallest class count")

    if groups is None:
        from sklearn.model_selection import StratifiedKFold

        splitter = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
        splits = [(train, valid) for train, valid in splitter.split(X, y)]
        mode = {
            "kind": "stratified_fallback",
            "group_authority_supplied": False,
            "warning": "No local group/site/patient authority was supplied; leakage across latent groups cannot be ruled out.",
        }
    else:
        from sklearn.model_selection import StratifiedGroupKFold

        group_arr = np.asarray(groups, dtype=object)
        if group_arr.ndim != 1 or len(group_arr) != len(y):
            raise ModelContractError("groups must be a same-length 1D vector")
        if any(g is None or str(g).strip() == "" for g in group_arr):
            raise ModelContractError("group authority contains blank/missing values")
        if len(set(map(str, group_arr.tolist()))) < n_splits:
            raise ModelContractError("fewer unique groups than n_splits")
        splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
        splits = [(train, valid) for train, valid in splitter.split(X, y, group_arr)]
        for fold, (train, valid) in enumerate(splits):
            train_groups = set(map(str, group_arr[train].tolist()))
            valid_groups = set(map(str, group_arr[valid].tolist()))
            overlap = train_groups.intersection(valid_groups)
            if overlap:
                raise ModelContractError(f"group leakage in fold {fold}: {sorted(overlap)[:3]}")
        mode = {
            "kind": "stratified_group",
            "group_authority_supplied": True,
            "unique_group_count": len(set(map(str, group_arr.tolist()))),
        }

    seen = np.zeros(len(y), dtype=np.int64)
    for fold, (train, valid) in enumerate(splits):
        if len(train) == 0 or len(valid) == 0:
            raise ModelContractError(f"fold {fold} is empty")
        if set(train.tolist()).intersection(valid.tolist()):
            raise ModelContractError(f"row overlap inside fold {fold}")
        seen[valid] += 1
        if len(np.unique(y[train])) != 2:
            raise ModelContractError(f"fold {fold} training partition lacks both classes")
    if not np.all(seen == 1):
        raise ModelContractError("validation folds do not partition rows exactly once")
    return splits, mode




def _fit_platt(raw_probabilities: np.ndarray, labels: np.ndarray, *, seed: int) -> dict:
    from sklearn.linear_model import LogisticRegression

    x = probability_logit(raw_probabilities).reshape(-1, 1)
    if len(np.unique(labels)) != 2:
        raise ModelContractError("Platt calibration requires both classes")
    model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000, random_state=seed)
    model.fit(x, labels)
    coef = float(model.coef_[0, 0])
    intercept = float(model.intercept_[0])
    if not math.isfinite(coef) or not math.isfinite(intercept):
        raise ModelContractError("calibrator produced non-finite parameters")
    return {"kind": "platt_logit", "coef": coef, "intercept": intercept}

@dataclass(frozen=True)
class _BranchSpec:
    name: str
    c: float
    class_weight: str | None


BRANCH_SPECS = (
    _BranchSpec("logreg_c025", 0.25, None),
    _BranchSpec("logreg_c1", 1.0, None),
    _BranchSpec("logreg_c4_balanced", 4.0, "balanced"),
)


def _fit_branch(X: np.ndarray, y: np.ndarray, spec: _BranchSpec, *, seed: int) -> tuple[object, object]:
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    transformed = scaler.fit_transform(X)
    model = LogisticRegression(
        C=spec.c,
        solver="lbfgs",
        max_iter=2000,
        class_weight=spec.class_weight,
        random_state=seed,
    )
    model.fit(transformed, y)
    return scaler, model


def _serialize_branch(name: str, scaler: object, model: object) -> dict:
    mean = np.asarray(scaler.mean_, dtype=np.float64)
    scale = np.asarray(scaler.scale_, dtype=np.float64)
    coef = np.asarray(model.coef_[0], dtype=np.float64)
    intercept = float(model.intercept_[0])
    if not (np.isfinite(mean).all() and np.isfinite(scale).all() and np.isfinite(coef).all() and math.isfinite(intercept)):
        raise ModelContractError("branch parameters contain non-finite values")
    if np.any(scale <= 0):
        raise ModelContractError("branch scaler contains non-positive scale")
    return {
        "name": name,
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "coef": coef.tolist(),
        "intercept": intercept,
    }


def train_feature_model(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: Sequence[str],
    *,
    groups: Sequence[object] | np.ndarray | None = None,
    n_splits: int = 4,
    seed: int = 20260913,
) -> tuple[dict, dict]:
    """Train deterministic OOF-selected branches and train-only calibration.

    Returned artifact contains no row identifiers, paths, labels, groups, or OOF predictions.
    The receipt contains only aggregate loss/fold facts and is safe to keep locally; callers remain
    responsible for deciding whether even aggregate dataset facts may be published.
    """

    features, labels = _validate_training_matrix(X, y)
    names = tuple(str(name) for name in feature_names)
    if len(names) != features.shape[1] or any(not name for name in names) or len(set(names)) != len(names):
        raise ModelContractError("feature_names must be unique and match X width")
    if names != FEATURE_NAMES:
        raise ModelContractError("training feature_names must equal the fixed public feature schema")
    splits, split_receipt = _build_splits(features, labels, groups, n_splits=n_splits, seed=seed)

    oof_by_branch: dict[str, np.ndarray] = {}
    branch_losses: dict[str, float] = {}
    for offset, spec in enumerate(BRANCH_SPECS):
        oof = np.full(len(labels), np.nan, dtype=np.float64)
        for fold, (train_idx, valid_idx) in enumerate(splits):
            scaler, model = _fit_branch(features[train_idx], labels[train_idx], spec, seed=seed + offset * 100 + fold)
            oof[valid_idx] = model.predict_proba(scaler.transform(features[valid_idx]))[:, 1]
        if not np.isfinite(oof).all():
            raise ModelContractError(f"branch {spec.name} did not fill all OOF rows")
        oof_by_branch[spec.name] = oof
        branch_losses[spec.name] = binary_log_loss(labels, oof)

    loss_vec = np.asarray([branch_losses[spec.name] for spec in BRANCH_SPECS], dtype=np.float64)
    centered = loss_vec - float(loss_vec.min())
    weights = np.exp(-8.0 * centered)
    weights /= weights.sum()
    raw_ensemble = sum(weights[index] * oof_by_branch[spec.name] for index, spec in enumerate(BRANCH_SPECS))
    raw_loss = binary_log_loss(labels, raw_ensemble)

    calibrated_oof = np.full(len(labels), np.nan, dtype=np.float64)
    for fold, (train_idx, valid_idx) in enumerate(splits):
        calibrator = _fit_platt(raw_ensemble[train_idx], labels[train_idx], seed=seed + 5000 + fold)
        calibrated_oof[valid_idx] = apply_calibrator(raw_ensemble[valid_idx], calibrator)
    if not np.isfinite(calibrated_oof).all():
        raise ModelContractError("cross-fitted calibration did not fill all OOF rows")
    calibrated_loss = binary_log_loss(labels, calibrated_oof)
    final_calibrator = _fit_platt(raw_ensemble, labels, seed=seed + 9000)

    serialized_branches: list[dict] = []
    for offset, spec in enumerate(BRANCH_SPECS):
        scaler, model = _fit_branch(features, labels, spec, seed=seed + 10000 + offset)
        branch = _serialize_branch(spec.name, scaler, model)
        branch["weight"] = float(weights[offset])
        serialized_branches.append(branch)

    model_core = {
        "schema": SCHEMA_VERSION,
        "feature_version": FEATURE_VERSION,
        "runtime_commit": RUNTIME_COMMIT,
        "feature_names": list(names),
        "branches": serialized_branches,
        "calibrator": final_calibrator,
        "inference_contract": {
            "one_scan_at_a_time": True,
            "test_set_fitting": False,
            "output": "finite_probability_[0,1]",
        },
        "privacy_contract": {
            "contains_training_rows": False,
            "contains_row_identifiers": False,
            "contains_groups_or_sites": False,
            "contains_paths": False,
        },
    }
    artifact = {**model_core, "model_sha256": sha256_json(model_core)}
    receipt_core = {
        "schema": "dat-parkinsons-local-model-v2/train-receipt-v1",
        "seed": seed,
        "n_splits": n_splits,
        "split": split_receipt,
        "row_count": int(len(labels)),
        "feature_count": int(features.shape[1]),
        "class_counts": {"0": int(np.sum(labels == 0)), "1": int(np.sum(labels == 1))},
        "branch_oof_log_loss": {name: float(branch_losses[name]) for name in sorted(branch_losses)},
        "ensemble_raw_oof_log_loss": raw_loss,
        "ensemble_crossfit_calibrated_oof_log_loss": calibrated_loss,
        "selection_authority": "OOF_ONLY_NO_LEADERBOARD",
        "calibration_authority": "OOF_TRAIN_ONLY_CROSSFIT_FOR_EVALUATION",
        "model_sha256": artifact["model_sha256"],
    }
    receipt = {**receipt_core, "receipt_sha256": sha256_json(receipt_core)}
    return artifact, receipt
