"""Competition-only JSON artifact validation and pure-NumPy inference."""

from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np

from .contract import (
    BRANCH_NAMES,
    FEATURE_NAMES,
    FEATURE_VERSION,
    RUNTIME_COMMIT,
    SCHEMA_VERSION,
    ModelContractError,
    sha256_json,
)

def _sigmoid(logits: np.ndarray | float) -> np.ndarray:
    x = np.asarray(logits, dtype=np.float64)
    x = np.clip(x, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-x))


def _logit(probabilities: np.ndarray | Sequence[float]) -> np.ndarray:
    p = np.clip(np.asarray(probabilities, dtype=np.float64), 1e-6, 1.0 - 1e-6)
    return np.log(p / (1.0 - p))




def probability_logit(probabilities: np.ndarray | Sequence[float]) -> np.ndarray:
    return _logit(probabilities)


def apply_calibrator(raw_probabilities: np.ndarray | Sequence[float], calibrator: Mapping[str, object]) -> np.ndarray:
    if calibrator.get("kind") != "platt_logit":
        raise ModelContractError("unsupported calibrator kind")
    coef = float(calibrator["coef"])
    intercept = float(calibrator["intercept"])
    if not math.isfinite(coef) or not math.isfinite(intercept):
        raise ModelContractError("calibrator parameters must be finite")
    return _sigmoid(_logit(raw_probabilities) * coef + intercept)


def _predict_serialized_branch(X: np.ndarray, branch: Mapping[str, object]) -> np.ndarray:
    features = np.asarray(X, dtype=np.float64)
    mean = np.asarray(branch["mean"], dtype=np.float64)
    scale = np.asarray(branch["scale"], dtype=np.float64)
    coef = np.asarray(branch["coef"], dtype=np.float64)
    intercept = float(branch["intercept"])
    if features.ndim == 1:
        features = features.reshape(1, -1)
    if features.ndim != 2 or features.shape[1] != len(mean) or len(mean) != len(scale) or len(mean) != len(coef):
        raise ModelContractError("feature/model dimensionality mismatch")
    if not (np.isfinite(features).all() and np.isfinite(mean).all() and np.isfinite(scale).all() and np.isfinite(coef).all() and math.isfinite(intercept)):
        raise ModelContractError("non-finite feature/model value")
    if np.any(scale <= 0):
        raise ModelContractError("model scaler contains non-positive scale")
    logits = ((features - mean) / scale) @ coef + intercept
    return _sigmoid(logits)


def validate_model_artifact(artifact: Mapping[str, object]) -> None:
    if not isinstance(artifact, Mapping):
        raise ModelContractError("model artifact must be an object")
    expected_top = {
        "schema", "feature_version", "runtime_commit", "feature_names", "branches",
        "calibrator", "inference_contract", "privacy_contract", "model_sha256",
    }
    if set(artifact) != expected_top:
        raise ModelContractError("model artifact has missing or unknown top-level fields")
    if artifact.get("schema") != SCHEMA_VERSION or artifact.get("feature_version") != FEATURE_VERSION:
        raise ModelContractError("model schema/version mismatch")
    if artifact.get("runtime_commit") != RUNTIME_COMMIT:
        raise ModelContractError("runtime commit mismatch")
    names = artifact.get("feature_names")
    branches = artifact.get("branches")
    calibrator = artifact.get("calibrator")
    if not isinstance(names, list) or tuple(names) != FEATURE_NAMES:
        raise ModelContractError("feature_names do not equal the fixed public schema")
    if not isinstance(branches, list) or len(branches) != len(BRANCH_NAMES):
        raise ModelContractError("model must contain the exact public branch set")
    expected_branch_names = list(BRANCH_NAMES)
    weights = []
    for index, branch in enumerate(branches):
        if not isinstance(branch, Mapping):
            raise ModelContractError("branch must be an object")
        if set(branch) != {"name", "mean", "scale", "coef", "intercept", "weight"}:
            raise ModelContractError("branch has missing or unknown fields")
        if branch.get("name") != expected_branch_names[index]:
            raise ModelContractError("branch identity/order differs from public contract")
        if len(branch.get("mean", [])) != len(names) or len(branch.get("scale", [])) != len(names) or len(branch.get("coef", [])) != len(names):
            raise ModelContractError("branch width mismatch")
        weight = float(branch.get("weight", float("nan")))
        if not math.isfinite(weight) or weight < 0:
            raise ModelContractError("branch weight must be finite and non-negative")
        weights.append(weight)
        _predict_serialized_branch(np.zeros((1, len(names))), branch)
    if not math.isclose(sum(weights), 1.0, rel_tol=1e-9, abs_tol=1e-9):
        raise ModelContractError("branch weights must sum to 1")
    if not isinstance(calibrator, Mapping) or set(calibrator) != {"kind", "coef", "intercept"}:
        raise ModelContractError("calibrator has missing or unknown fields")
    apply_calibrator(np.asarray([0.5]), calibrator)
    inference = artifact.get("inference_contract")
    if not isinstance(inference, Mapping) or dict(inference) != {
        "one_scan_at_a_time": True,
        "test_set_fitting": False,
        "output": "finite_probability_[0,1]",
    }:
        raise ModelContractError("inference contract is missing or altered")
    privacy = artifact.get("privacy_contract")
    if not isinstance(privacy, Mapping) or dict(privacy) != {
        "contains_training_rows": False,
        "contains_row_identifiers": False,
        "contains_groups_or_sites": False,
        "contains_paths": False,
    }:
        raise ModelContractError("artifact privacy contract is missing or unsafe")
    digest = artifact.get("model_sha256")
    if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ModelContractError("model_sha256 missing or malformed")
    core = {key: value for key, value in artifact.items() if key != "model_sha256"}
    if sha256_json(core) != digest:
        raise ModelContractError("model_sha256 does not match artifact contents")


def predict_feature_matrix(X: np.ndarray, artifact: Mapping[str, object]) -> np.ndarray:
    validate_model_artifact(artifact)
    features = np.asarray(X, dtype=np.float64)
    if features.ndim == 1:
        features = features.reshape(1, -1)
    names = artifact["feature_names"]
    if features.ndim != 2 or features.shape[1] != len(names):
        raise ModelContractError("inference feature width mismatch")
    raw = np.zeros(features.shape[0], dtype=np.float64)
    for branch in artifact["branches"]:
        raw += float(branch["weight"]) * _predict_serialized_branch(features, branch)
    calibrated = apply_calibrator(raw, artifact["calibrator"])
    if not np.isfinite(calibrated).all() or np.any(calibrated < 0) or np.any(calibrated > 1):
        raise ModelContractError("model produced invalid probability")
    return calibrated
