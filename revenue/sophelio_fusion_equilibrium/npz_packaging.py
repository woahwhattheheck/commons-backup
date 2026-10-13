"""Deterministic NPZ primitives for the Sophelio submission contract."""
from __future__ import annotations
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Iterable, Mapping, Sequence
import zipfile
import numpy as np
try:
    from .contract import ContractError, GRID_SHAPE, Prediction, BundleReceipt, SCALARS, contract_snapshot
except ImportError:
    from contract import ContractError, GRID_SHAPE, Prediction, BundleReceipt, SCALARS, contract_snapshot

def _npy_bytes(arr: np.ndarray) -> bytes:
    bio = BytesIO()
    np.lib.format.write_array(bio, np.asarray(arr), allow_pickle=False)
    return bio.getvalue()


def write_deterministic_npz(path: Path | str, arrays: Mapping[str, np.ndarray]) -> str:
    """Write byte-deterministic NPZ (sorted keys + fixed ZIP timestamps)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for key in sorted(arrays):
            if not key or "/" in key or "\\" in key or key.startswith("."):
                raise ContractError(f"unsafe npz key {key!r}")
            info = zipfile.ZipInfo(f"{key}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            zf.writestr(info, _npy_bytes(np.asarray(arrays[key])))
    return sha256(p.read_bytes()).hexdigest()


def prediction_arrays(predictions: Sequence[Prediction]) -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {}
    for i, pred in enumerate(predictions):
        prefix = f"shot_{i:04d}"
        arrays[f"{prefix}_psirz"] = np.asarray(pred.psirz, dtype=np.float32)
        arrays[f"{prefix}_q95"] = np.asarray(pred.q95, dtype=np.float32)
        arrays[f"{prefix}_betaN"] = np.asarray(pred.betaN, dtype=np.float32)
    return arrays


def validate_prediction_arrays(
    arrays: Mapping[str, np.ndarray], expected_lengths: Sequence[int], machine: str
) -> None:
    if machine not in {"DIII-D", "MAST"}:
        raise ContractError(f"unknown machine {machine}")
    expected: set[str] = set()
    for i, t in enumerate(expected_lengths):
        if int(t) <= 0:
            raise ContractError("shot length must be positive")
        prefix = f"shot_{i:04d}"
        expected.update(f"{prefix}_{s}" for s in ("psirz", *SCALARS))
        for suffix, shape in (
            ("psirz", (int(t), *GRID_SHAPE)),
            ("q95", (int(t),)),
            ("betaN", (int(t),)),
        ):
            key = f"{prefix}_{suffix}"
            if key not in arrays:
                raise ContractError(f"missing {key}")
            a = np.asarray(arrays[key])
            if a.shape != shape:
                raise ContractError(f"{key} shape {a.shape}, expected {shape}")
            if not np.issubdtype(a.dtype, np.floating):
                raise ContractError(f"{key} must be floating")
            if not np.isfinite(a).all():
                raise ContractError(f"{key} contains NaN/Inf")
    extra = set(arrays).difference(expected)
    if extra:
        raise ContractError(f"unexpected submission keys: {sorted(extra)[:5]}")


def read_npz_strict(path: Path | str) -> dict[str, np.ndarray]:
    p = Path(path)
    if not p.is_file():
        raise ContractError(f"missing npz {p}")
    with np.load(p, allow_pickle=False) as z:
        return {k: np.array(z[k], copy=True) for k in z.files}


def compile_submission_npz(
    path: Path | str,
    predictions: Sequence[Prediction],
    expected_lengths: Sequence[int],
    machine: str,
) -> str:
    arrays = prediction_arrays(predictions)
    validate_prediction_arrays(arrays, expected_lengths, machine)
    digest = write_deterministic_npz(path, arrays)
    # Reopen exact written bytes and validate again; never trust only memory.
    validate_prediction_arrays(read_npz_strict(path), expected_lengths, machine)
    return digest


def _canonical_json_bytes(obj: object) -> bytes:
    import json
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def source_digest(paths: Iterable[Path | str]) -> str:
    """Hash named source files with path names included for publication receipts."""
    h = sha256()
    for raw in sorted((Path(p) for p in paths), key=lambda p: p.as_posix()):
        h.update(raw.as_posix().encode("utf-8") + b"\0")
        h.update(raw.read_bytes())
        h.update(b"\0")
    return h.hexdigest()
