"""Crunch-compatible source seam for the 2026 real-time structural-break task."""

from __future__ import annotations

import json
import os
from typing import Iterable, List, Optional, Tuple

from detector import DETECTOR_VERSION, OnlineBreakDetector

MODEL_FILENAME = "zvk_r6m8_model.json"
MODEL_SCHEMA_VERSION = 1

# The public organizer quickstarter supports process parallelism. This detector has
# no mutable global inference state, so independent worker processes are safe.
INFER_PARALLELISM = 4


def train(
    datasets: List[Tuple[int, List[float], List[float], Optional[int]]],
    model_directory_path: str,
):
    """Write a transparent no-pretraining artifact.

    This v1 detector deliberately learns no hidden/pretrained parameters. Keeping
    train() present and source-visible matches the organizer's reward-eligibility
    contract and leaves an explicit seam for a later supervised calibration stage.
    """
    del datasets
    os.makedirs(model_directory_path, exist_ok=True)
    payload = {
        "schemaVersion": MODEL_SCHEMA_VERSION,
        "detectorVersion": DETECTOR_VERSION,
        "pretrained": False,
        "learnedParameters": False,
    }
    path = os.path.join(model_directory_path, MODEL_FILENAME)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")


def _load_model_contract(model_directory_path: str) -> None:
    path = os.path.join(model_directory_path, MODEL_FILENAME)
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    expected = {
        "schemaVersion": MODEL_SCHEMA_VERSION,
        "detectorVersion": DETECTOR_VERSION,
        "pretrained": False,
        "learnedParameters": False,
    }
    if payload != expected:
        raise ValueError("model contract mismatch")


def infer(
    datasets: Iterable[Tuple[List[float], Iterable[float]]],
    model_directory_path: str,
):
    """Yield one causal score per currently released online observation."""
    _load_model_contract(model_directory_path)

    yield  # Organizer runner readiness handshake.

    for x_historical, x_online in datasets:
        detector = OnlineBreakDetector(x_historical)
        for point in x_online:
            yield float(detector.update(point))
