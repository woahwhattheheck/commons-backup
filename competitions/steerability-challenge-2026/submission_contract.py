#!/usr/bin/env python3
"""Fail-closed validator for a pre-registration Steerability submission *plan*.

This validates our public packaging intent, not organizer-private `.spipe` execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "steerability-submission-plan/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_SURFACES = {"input", "structure", "state", "output"}


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _require_text(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value.strip()


def _normalize_pipeline(pipeline: Any) -> list[dict[str, Any]]:
    if not isinstance(pipeline, list) or not pipeline:
        raise ValueError("pipeline must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    for idx, step in enumerate(pipeline):
        if not isinstance(step, Mapping):
            raise ValueError(f"pipeline[{idx}] must be an object")
        surface = _require_text(step, "surface")
        if surface not in ALLOWED_SURFACES:
            raise ValueError(f"pipeline[{idx}].surface unsupported: {surface}")
        name = _require_text(step, "name")
        config = step.get("config", {})
        if not isinstance(config, Mapping):
            raise ValueError(f"pipeline[{idx}].config must be an object")
        canonical_config = {}
        for key, value in sorted(config.items()):
            if key.endswith("artifact_ref"):
                canonical_config[key] = "<MODEL_ARTIFACT>"
            else:
                canonical_config[key] = value
        normalized.append({"surface": surface, "name": name, "config": canonical_config})
    return normalized


def validate_plan(plan: Mapping[str, Any], *, expected_models: int | None = 3) -> dict[str, Any]:
    if not isinstance(plan, Mapping):
        raise ValueError("plan must be a JSON object")
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must equal {SCHEMA_VERSION}")
    disclosure = _require_text(plan, "coding_agent_disclosure")
    if len(disclosure) < 20:
        raise ValueError("coding_agent_disclosure is implausibly short")
    models = plan.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("models must be a non-empty list")
    if expected_models is not None and len(models) != expected_models:
        raise ValueError(f"expected exactly {expected_models} model slots, got {len(models)}")

    seen_models: set[str] = set()
    seen_paths: set[str] = set()
    pipeline_fingerprint: str | None = None
    artifact_count = 0
    normalized_models: list[dict[str, Any]] = []
    for idx, model in enumerate(models):
        if not isinstance(model, Mapping):
            raise ValueError(f"models[{idx}] must be an object")
        model_id = _require_text(model, "model_id")
        if model_id in seen_models:
            raise ValueError(f"duplicate model_id {model_id}")
        seen_models.add(model_id)
        spipe_path = _require_text(model, "spipe_path")
        if not spipe_path.endswith(".spipe") or Path(spipe_path).is_absolute() or ".." in Path(spipe_path).parts:
            raise ValueError(f"unsafe or non-.spipe path: {spipe_path}")
        if spipe_path in seen_paths:
            raise ValueError(f"duplicate spipe_path {spipe_path}")
        seen_paths.add(spipe_path)
        normalized_pipeline = _normalize_pipeline(model.get("pipeline"))
        fingerprint = digest(normalized_pipeline)
        if pipeline_fingerprint is None:
            pipeline_fingerprint = fingerprint
        elif pipeline_fingerprint != fingerprint:
            raise ValueError("pipeline structure/config must be equivalent across model slots")

        artifacts = model.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise ValueError(f"models[{idx}].artifacts must be non-empty")
        artifact_paths: set[str] = set()
        normalized_artifacts: list[dict[str, str]] = []
        for j, artifact in enumerate(artifacts):
            if not isinstance(artifact, Mapping):
                raise ValueError(f"models[{idx}].artifacts[{j}] must be an object")
            path = _require_text(artifact, "path")
            if Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError(f"unsafe artifact path {path}")
            if path in artifact_paths:
                raise ValueError(f"duplicate artifact path {path} in {model_id}")
            artifact_paths.add(path)
            sha = _require_text(artifact, "sha256").lower()
            if not SHA256_RE.fullmatch(sha):
                raise ValueError(f"invalid sha256 for {path}")
            source = _require_text(artifact, "source")
            license_name = _require_text(artifact, "license")
            normalized_artifacts.append({"path": path, "sha256": sha, "source": source, "license": license_name})
            artifact_count += 1
        normalized_models.append({
            "model_id": model_id,
            "spipe_path": spipe_path,
            "pipeline_fingerprint": fingerprint,
            "artifacts": normalized_artifacts,
        })

    authority = plan.get("authority")
    if not isinstance(authority, Mapping):
        raise ValueError("authority must be an object")
    forbidden_true = [
        key for key in ("registered", "submitted", "private_eval_access", "prize_awarded", "payment_received")
        if authority.get(key) is not False
    ]
    if forbidden_true:
        raise ValueError(f"public foundation authority must remain explicitly false: {forbidden_true}")

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "coding_agent_disclosure": disclosure,
        "model_count": len(models),
        "artifact_count": artifact_count,
        "pipeline_fingerprint": pipeline_fingerprint,
        "models": normalized_models,
        "authority": {k: authority[k] for k in sorted(authority)},
    }
    receipt = {
        "kind": "submission_plan_validation",
        "plan_digest": digest(plan),
        "normalized_digest": digest(normalized),
        "model_count": len(models),
        "artifact_count": artifact_count,
        "pipeline_fingerprint": pipeline_fingerprint,
    }
    receipt["receipt_sha256"] = digest(receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--expected-models", type=int, default=3)
    args = parser.parse_args(argv)
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    receipt = validate_plan(plan, expected_models=args.expected_models)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
