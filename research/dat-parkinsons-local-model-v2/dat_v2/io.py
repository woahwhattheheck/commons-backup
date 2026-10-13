"""Strict local-only I/O helpers.

NIfTI loading is lazy so the public/synthetic test suite does not require nibabel. Real
competition data must stay in the participant's rule-compliant local environment and should
never be copied into logs, git, Slack, or hosted assistants.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from .core import ModelContractError, canonical_json, validate_model_artifact

MAX_JSON_BYTES = 16 * 1024 * 1024


def _reject_constant(value: str) -> None:
    raise ModelContractError(f"non-finite JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ModelContractError("duplicate JSON object key")
        result[key] = value
    return result


def parse_json_strict(text: str) -> object:
    try:
        return json.loads(text, parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    except ModelContractError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ModelContractError("invalid strict JSON") from exc


def load_nifti_array(path: Path) -> np.ndarray:
    path = Path(path)
    if not path.is_file():
        raise ModelContractError("scan path is not a regular file")
    name = path.name.lower()
    if not (name.endswith(".nii") or name.endswith(".nii.gz")):
        raise ModelContractError("scan path must be .nii or .nii.gz")
    try:
        import nibabel as nib
    except ImportError as exc:
        raise RuntimeError("nibabel is required in the organizer/local runtime to load NIfTI scans") from exc
    image = nib.load(str(path))
    image = nib.as_closest_canonical(image)
    array = image.get_fdata(dtype=np.float32, caching="unchanged")
    if np.asarray(array).ndim != 3:
        raise ModelContractError("NIfTI image must resolve to one 3D volume")
    return np.asarray(array, dtype=np.float32)


def read_training_manifest(
    path: Path,
    *,
    uid_column: str,
    label_column: str,
    path_column: str,
    group_column: str | None,
) -> list[dict]:
    """Read an explicit local CSV schema without guessing organizer-private column names."""
    manifest = Path(path)
    if not manifest.is_file():
        raise ModelContractError("training manifest does not exist")
    columns = [uid_column, label_column, path_column] + ([group_column] if group_column else [])
    if any(type(value) is not str or not value.strip() for value in columns):
        raise ModelContractError("manifest column names must be explicit non-empty strings")
    if len(set(columns)) != len(columns):
        raise ModelContractError("manifest column roles must use distinct columns")

    rows: list[dict] = []
    seen_uid: set[str] = set()
    with manifest.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ModelContractError("training manifest has no header")
        missing = [column for column in columns if column not in reader.fieldnames]
        if missing:
            raise ModelContractError("training manifest is missing an explicitly requested column")
        for row in reader:
            uid = (row.get(uid_column) or "").strip()
            scan_text = (row.get(path_column) or "").strip()
            label_text = (row.get(label_column) or "").strip()
            group_text = (row.get(group_column) or "").strip() if group_column else None
            if not uid or uid in seen_uid:
                raise ModelContractError("manifest UID values must be non-empty and unique")
            seen_uid.add(uid)
            if label_text not in {"0", "1"}:
                raise ModelContractError("manifest labels must be literal 0 or 1")
            scan_path = Path(scan_text)
            if not scan_path.is_absolute():
                scan_path = (manifest.parent / scan_path).resolve()
            if not scan_path.is_file():
                raise ModelContractError("manifest scan path is not a regular file")
            if group_column and not group_text:
                raise ModelContractError("group column was requested but a row is blank")
            rows.append({"uid": uid, "label": int(label_text), "path": scan_path, "group": group_text})
    if not rows:
        raise ModelContractError("training manifest is empty")
    return rows


def write_model_json(path: Path, artifact: dict) -> None:
    validate_model_artifact(artifact)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(artifact) + "\n")
    except FileExistsError:
        raise FileExistsError(f"refusing to overwrite model artifact: {destination}") from None


def load_model_json(path: Path) -> dict:
    source = Path(path)
    if not source.is_file():
        raise ModelContractError("model artifact is not a regular file")
    if source.stat().st_size > MAX_JSON_BYTES:
        raise ModelContractError("model artifact exceeds bounded JSON size")
    model = parse_json_strict(source.read_text(encoding="utf-8"))
    if not isinstance(model, dict):
        raise ModelContractError("model artifact must be a JSON object")
    validate_model_artifact(model)
    return model
