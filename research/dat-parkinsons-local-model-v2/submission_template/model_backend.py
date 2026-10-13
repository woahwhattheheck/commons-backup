# SPDX-License-Identifier: MIT
"""Single-scan backend for a locally trained DaT V2 model artifact."""
from pathlib import Path

from dat_v2.core import predict_volume
from dat_v2.io import load_model_json, load_nifti_array

_MODEL = load_model_json(Path(__file__).with_name("model.json"))


def predict_probability(scan_path: Path) -> float:
    """Predict one scan independently; never fits or adapts on test data."""
    volume = load_nifti_array(Path(scan_path))
    return float(predict_volume(volume, _MODEL))
