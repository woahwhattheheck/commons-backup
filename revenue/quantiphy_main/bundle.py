"""Deterministic submission bundle, verifier, and create-exclusive output."""
from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Mapping

from .common import (
    GROUND_TRUTH, MANIFEST_SCHEMA, MAX_SAFE_INT, QuantiPhyMainError,
    _hex, _int, _obj, canonical_bytes, canonical_sha, row_key, sha256_bytes,
    strict_json_loads, validate_dataset, validate_receipts,
)
from .recipe import _selected_inference_cost, _verify_recipe_integrity, apply_recipe

def build_submission_bundle(dataset_raw: Any, receipts_raw: Any, recipe_raw: Any) -> tuple[bytes, dict[str, Any]]:
    """Compile a competition-shaped submission from an unlabeled inference set.

    Ground truth is refused here so a hidden/test-label file cannot be accidentally
    normalized into a submission path. Public validation remains a fit-time input to
    ``build_recipe`` only.
    """
    recipe = _obj(recipe_raw, "recipe")
    _verify_recipe_integrity(recipe)
    dataset = validate_dataset(dataset_raw, require_truth=False)
    if any(GROUND_TRUTH in row for row in dataset):
        raise QuantiPhyMainError("submission input must not contain ground truth")
    receipts = validate_receipts(receipts_raw, dataset)
    predicted = apply_recipe(dataset, receipts, recipe)
    selected_cost = _selected_inference_cost(dataset, receipts, recipe)
    budget = _int(recipe.get("budget_microusd"), "recipe.budget_microusd", 0, MAX_SAFE_INT)
    if selected_cost > budget:
        raise QuantiPhyMainError(f"selected inference cost exceeds recipe budget: {selected_cost} > {budget}")

    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=["video_id", "question", "parsed_value"], lineterminator="\n")
    writer.writeheader()
    for row in sorted(predicted, key=row_key):
        writer.writerow({"video_id": row["video_id"], "question": row["question"], "parsed_value": row["parsed_value"]})
    submission = out.getvalue().encode("utf-8")
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "recipe": recipe,
        "fit_dataset_sha256": recipe.get("dataset_sha256"),
        "fit_receipts_sha256": recipe.get("receipts_sha256"),
        "inference_dataset_sha256": canonical_sha(dataset),
        "inference_receipts_sha256": canonical_sha(receipts),
        "submission_sha256": sha256_bytes(submission),
        "submission_bytes": len(submission),
        "selected_inference_cost_microusd": selected_cost,
        "observed_inference_total_cost_microusd": sum(_int(r["cost_microusd"], "cost_microusd") for r in receipts),
        "readiness": "BLOCKED_EXTERNAL_GATES",
        "external_gates": [
            "competition_registration_and_terms",
            "authorized_real_provider_or_model_inference",
            "explicit_submission_authorization",
        ],
        "authority": recipe["authority"],
    }
    manifest["manifest_sha256"] = canonical_sha(manifest)
    return submission, manifest

def verify_submission_bundle(dataset_raw: Any, receipts_raw: Any, manifest_raw: Any, submission: bytes) -> bool:
    manifest = _obj(manifest_raw, "manifest")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise QuantiPhyMainError("manifest schema invalid")
    claimed = manifest.get("manifest_sha256")
    _hex(claimed, "manifest.manifest_sha256")
    stripped = dict(manifest)
    stripped.pop("manifest_sha256", None)
    if canonical_sha(stripped) != claimed:
        raise QuantiPhyMainError("manifest self-digest mismatch")
    recipe = _obj(manifest.get("recipe"), "manifest.recipe")
    expected_submission, expected_manifest = build_submission_bundle(dataset_raw, receipts_raw, recipe)
    if expected_submission != submission:
        raise QuantiPhyMainError("submission does not exactly recompile")
    if canonical_bytes(expected_manifest) != canonical_bytes(manifest):
        raise QuantiPhyMainError("manifest does not exactly recompile")
    return True


def write_bundle_exclusive(dest: str | Path, dataset_raw: Any, receipts_raw: Any, recipe_raw: Any) -> dict[str, Any]:
    root = Path(dest)
    if root.exists() or root.is_symlink():
        raise QuantiPhyMainError("destination already exists")
    root.mkdir(parents=False, exist_ok=False)
    created: list[Path] = []
    try:
        submission, manifest = build_submission_bundle(dataset_raw, receipts_raw, recipe_raw)
        files = {
            "submission.csv": submission,
            "manifest.json": canonical_bytes(manifest),
        }
        for name, data in files.items():
            path = root / name
            with path.open("xb") as handle:
                handle.write(data)
            created.append(path)
        return manifest
    except Exception:
        for path in reversed(created):
            try:
                path.unlink()
            except OSError:
                pass
        try:
            root.rmdir()
        except OSError:
            pass
        raise


def load_json_file(path: str | Path, *, max_bytes: int = 16 * 1024 * 1024) -> Any:
    p = Path(path)
    if p.is_symlink() or not p.is_file():
        raise QuantiPhyMainError("input must be a regular non-symlink file")
    if p.stat().st_size > max_bytes:
        raise QuantiPhyMainError("input too large")
    data = p.read_bytes()
    if len(data) > max_bytes:
        raise QuantiPhyMainError("input too large")
    return strict_json_loads(data)
