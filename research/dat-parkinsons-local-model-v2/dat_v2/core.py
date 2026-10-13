"""Public facade for deterministic DaT V2 features, training and inference."""

from __future__ import annotations

from typing import Mapping

import numpy as np

from .contract import (
    FEATURE_NAMES,
    FEATURE_VERSION,
    MAX_INPUT_VOXELS,
    MAX_WORKING_AXIS,
    RUNTIME_COMMIT,
    SCHEMA_VERSION,
    ModelContractError,
    canonical_json,
    sha256_json,
)
from .features import extract_features, feature_matrix, prepare_volume, robust_normalize
from .artifact import apply_calibrator, predict_feature_matrix, validate_model_artifact
from .training import binary_log_loss, train_feature_model


def predict_volume(volume: np.ndarray, artifact: Mapping[str, object]) -> float:
    vector, names = extract_features(volume)
    if list(names) != artifact.get("feature_names"):
        raise ModelContractError("feature schema does not match model artifact")
    return float(predict_feature_matrix(vector, artifact)[0])


__all__ = [
    "FEATURE_NAMES", "FEATURE_VERSION", "MAX_INPUT_VOXELS", "MAX_WORKING_AXIS",
    "RUNTIME_COMMIT", "SCHEMA_VERSION", "ModelContractError", "canonical_json",
    "sha256_json", "robust_normalize", "prepare_volume", "extract_features",
    "feature_matrix", "binary_log_loss", "apply_calibrator", "train_feature_model",
    "validate_model_artifact", "predict_feature_matrix", "predict_volume",
]
