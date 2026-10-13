from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from revenue.road_barbados_ocr_v2.engine import (
    RoadV2Error,
    admit_pseudo_labels,
    aggregate_metric,
    build_profile,
    build_receipt,
    canonical_bytes,
    compile_submission,
    csv_text_map,
    edit_distance,
    ensemble,
    loads_strict,
    normalize_transcript,
    sha256_hex,
    validate_manifest,
    verify_receipt,
)
from revenue.road_barbados_ocr_v2.package import build as build_package


def manifest() -> dict:
    models = []
    for mid, rev in (("alpha", "v1"), ("beta", "v2"), ("gamma", "v3")):
        models.append({
            "model_id": mid,
            "base_name": f"Synthetic {mid}",
            "base_source": f"public/{mid}",
            "base_revision": rev,
            "base_license": "Apache-2.0",
            "commercial_use_compatible": True,
            "openly_available": True,
            "adaptation_data": "challenge_only",
            "external_training_data": False,
            "hosted_api": False,
            "automl": False,
            "weights_sha256": sha256_hex(f"weights-{mid}".encode()),
        })
    return {
        "schema_version": 1,
        "challenge": "road-barbados-historic-handwriting-2026",
        "models": models,
        "authority": {
            "manual_test_labels": False,
            "external_data": False,
            "hosted_inference": False,
            "automl": False,
            "submit_to_zindi": False,
            "claim_score_rank_award_payment": False,
        },
    }


def labels() -> dict[str, str]:
    return {
        "tr1": "Mary Ann Clarke",
        "tr2": "Bridgetown Barbados",
        "tr3": "twenty four acres",
        "tr4": "Parish of Saint Michael",
    }


def oof() -> dict[str, dict[str, str]]:
    l = labels()
    return {
        "alpha": dict(l),
        "beta": {**l, "tr2": "Bridgetown Barbadoes"},
        "gamma": {**l, "tr3": "twenty four acre"},
    }


def preds() -> dict[str, dict[str, str]]:
    return {
        "alpha": {"te2": "Saint George Parish", "te1": "John Thomas"},
        "beta": {"te1": "John Thomas", "te2": "Saint George Parish"},
        "gamma": {"te1": "John Tomas", "te2": "Saint George Parish"},
    }


def artifacts():
    m = manifest(); l = labels(); p = build_profile(m, l, oof()); chosen, audit = ensemble(m, p, l, preds())
    pseudo = admit_pseudo_labels(audit, chosen, min_support_models=2, min_support_ppm=500_000, min_agreement_ppm=800_000)
    sample = b"ID,transcription\nte2,\nte1,\n"; sub = compile_submission(sample, chosen)
    dig = {k: sha256_hex(canonical_bytes(v)) for k, v in preds().items()}
    receipt = build_receipt(m, p, audit, pseudo, sample_raw=sample, submission_raw=sub, input_prediction_digests=dig)
    return m, l, p, chosen, audit, pseudo, sample, sub, receipt

