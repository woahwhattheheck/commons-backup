from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

FORMAT = "vesuvius-ct-ridge-snap/v1"
CALIBRATION_FORMAT = "vesuvius-real-derived-calibration/v1"
RECEIPT_FORMAT = "vesuvius-ct-ridge-receipt/v1"
BUNDLE_FORMAT = "vesuvius-ct-ridge-bundle/v1"
MAX_VOLUME_VOXELS = 512 * 1024 * 1024
MAX_POINTS = 100_000
MAX_OFFSET_VOXELS = 6
MAX_BUNDLE_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class AuditConfig:
    max_offset: int = 3
    normal_radius: int = 2
    point_stride: int = 1
    block_size: int = 8
    min_peak_z: float = 2.5
    min_peak_delta: float = 0.05
    min_consensus: float = 0.75
    consensus_tolerance: float = 0.5
    min_global_review_fraction: float = 0.30
    max_points: int = 50_000

    def validate(self) -> "AuditConfig":
        if type(self.max_offset) is not int or not (1 <= self.max_offset <= MAX_OFFSET_VOXELS):
            raise ContractError("max_offset must be an int in [1, 6]")
        if type(self.normal_radius) is not int or not (1 <= self.normal_radius <= 6):
            raise ContractError("normal_radius must be an int in [1, 6]")
        if type(self.point_stride) is not int or self.point_stride < 1:
            raise ContractError("point_stride must be a positive int")
        if type(self.block_size) is not int or self.block_size < 2:
            raise ContractError("block_size must be an int >= 2")
        if type(self.max_points) is not int or not (1 <= self.max_points <= MAX_POINTS):
            raise ContractError(f"max_points must be in [1, {MAX_POINTS}]")
        for name in ("min_peak_z", "min_peak_delta", "min_consensus", "consensus_tolerance", "min_global_review_fraction"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(float(value)):
                raise ContractError(f"{name} must be finite")
        if not (0.0 <= self.min_consensus <= 1.0):
            raise ContractError("min_consensus must be in [0,1]")
        if not (0.0 <= self.min_global_review_fraction <= 1.0):
            raise ContractError("min_global_review_fraction must be in [0,1]")
        return self


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError(f"value is not strict canonical JSON: {exc}") from exc


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: os.PathLike[str] | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_relpath(raw: str) -> Path:
    if type(raw) is not str or not raw or raw != raw.strip():
        raise ContractError("paths must be non-empty exact strings")
    if "\\" in raw or "\x00" in raw:
        raise ContractError("paths must use canonical POSIX separators without NUL")
    p = Path(raw)
    if p.is_absolute() or ".." in p.parts:
        raise ContractError("paths must be relative and traversal-free")
    return p


def sha256_tree(root: os.PathLike[str] | str) -> str:
    root_p = Path(root)
    if not root_p.is_dir():
        raise ContractError("zarr path must be a directory")
    rows: list[dict[str, Any]] = []
    for path in sorted(root_p.rglob("*"), key=lambda p: p.relative_to(root_p).as_posix()):
        st = path.lstat()
        if stat.S_ISLNK(st.st_mode) or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
            raise ContractError("zarr trees may contain only directories and regular files")
        if path.is_file():
            rows.append({"path": path.relative_to(root_p).as_posix(), "size": st.st_size, "sha256": sha256_file(path)})
    return sha256_bytes(canonical_json_bytes(rows))


def _require_digest(value: Any, field: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ContractError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def validate_volume_spec(spec: Mapping[str, Any], field: str) -> dict[str, str]:
    if type(spec) is not dict:
        raise ContractError(f"{field} must be an object")
    if set(spec) != {"kind", "path", "sha256"}:
        raise ContractError(f"{field} must contain exactly kind/path/sha256")
    kind = spec["kind"]
    if kind not in ("npy", "zarr"):
        raise ContractError(f"{field}.kind must be npy or zarr")
    raw_path = spec["path"]
    path = _safe_relpath(raw_path).as_posix()
    if path != raw_path:
        raise ContractError(f"{field}.path must be canonical POSIX relative form")
    digest = _require_digest(spec["sha256"], f"{field}.sha256")
    return {"kind": kind, "path": path, "sha256": digest}


def _validate_region(region: Any, field: str) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    if type(region) is not list or len(region) != 3:
        raise ContractError(f"{field} must be a 3-axis half-open box")
    out: list[tuple[int, int]] = []
    for axis in region:
        if type(axis) is not list or len(axis) != 2 or type(axis[0]) is not int or type(axis[1]) is not int:
            raise ContractError(f"{field} axes must be [start,end] integer pairs")
        if not (0 <= axis[0] < axis[1]):
            raise ContractError(f"{field} bounds must satisfy 0 <= start < end")
        out.append((axis[0], axis[1]))
    return (out[0], out[1], out[2])


def boxes_overlap(a: Sequence[Sequence[int]], b: Sequence[Sequence[int]]) -> bool:
    return all(max(int(a[i][0]), int(b[i][0])) < min(int(a[i][1]), int(b[i][1])) for i in range(3))


def assert_disjoint_regions(train_regions: Sequence[Any], eval_regions: Sequence[Any]) -> None:
    train = [_validate_region(x, f"train_regions[{i}]") for i, x in enumerate(train_regions)]
    evals = [_validate_region(x, f"eval_regions[{i}]") for i, x in enumerate(eval_regions)]
    for i, a in enumerate(train):
        for j, b in enumerate(evals):
            if boxes_overlap(a, b):
                raise ContractError(f"train/eval spatial overlap: train[{i}] vs eval[{j}]")


def validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if type(manifest) is not dict:
        raise ContractError("manifest must be an object")
    required = {"format", "ct", "labels", "train_regions", "eval_regions"}
    if set(manifest) != required:
        raise ContractError(f"manifest keys must be exactly {sorted(required)}")
    if manifest["format"] != FORMAT:
        raise ContractError(f"manifest format must be {FORMAT}")
    ct = validate_volume_spec(manifest["ct"], "ct")
    labels = validate_volume_spec(manifest["labels"], "labels")
    if type(manifest["train_regions"]) is not list or type(manifest["eval_regions"]) is not list:
        raise ContractError("train_regions/eval_regions must be lists")
    assert_disjoint_regions(manifest["train_regions"], manifest["eval_regions"])
    return {"format": FORMAT, "ct": ct, "labels": labels, "train_regions": manifest["train_regions"], "eval_regions": manifest["eval_regions"]}


def _verify_volume_digest(spec: Mapping[str, str], root: Path) -> Path:
    path = root / _safe_relpath(spec["path"])
    if spec["kind"] == "npy":
        if not path.is_file() or path.is_symlink():
            raise ContractError(f"missing regular npy file: {spec['path']}")
        actual = sha256_file(path)
    else:
        actual = sha256_tree(path)
    if actual != spec["sha256"]:
        raise ContractError(f"digest mismatch for {spec['path']}")
    return path


def load_volume(spec: Mapping[str, str], root: os.PathLike[str] | str) -> np.ndarray:
    root_p = Path(root)
    path = _verify_volume_digest(spec, root_p)
    if spec["kind"] == "npy":
        arr = np.load(path, allow_pickle=False, mmap_mode="r")
        if arr.ndim != 3:
            raise ContractError("volumes must be 3-D")
        if int(np.prod(arr.shape, dtype=np.int64)) > MAX_VOLUME_VOXELS:
            raise ContractError("volume exceeds bounded voxel ceiling")
        return arr
    try:
        import zarr  # type: ignore
    except ImportError as exc:
        raise ContractError("zarr input requires the optional zarr package") from exc
    z = zarr.open(str(path), mode="r")
    if getattr(z, "ndim", None) != 3:
        raise ContractError("volumes must be 3-D")
    shape = getattr(z, "shape", None)
    if type(shape) not in (tuple, list) or len(shape) != 3 or any(type(x) is not int or x < 0 for x in shape):
        raise ContractError("zarr volume shape is invalid")
    if int(np.prod(shape, dtype=np.int64)) > MAX_VOLUME_VOXELS:
        raise ContractError("volume exceeds bounded voxel ceiling")
    return np.asarray(z)


def load_inputs(manifest: Mapping[str, Any], root: os.PathLike[str] | str) -> tuple[np.ndarray, np.ndarray, dict[str, str]]:
    clean = validate_manifest(manifest)
    ct = np.asarray(load_volume(clean["ct"], root))
    labels = np.asarray(load_volume(clean["labels"], root))
    if ct.shape != labels.shape:
        raise ContractError("ct and labels must have identical shapes")
    if ct.dtype.kind not in "fiu" or not np.isfinite(ct).all():
        raise ContractError("ct must be finite numeric data")
    if labels.dtype.kind not in "biu":
        raise ContractError("labels must be bool/integer")
    unique = np.unique(labels)
    if unique.size > 2 or any(int(x) not in (0, 1) for x in unique.tolist()):
        raise ContractError("labels must contain only 0/1")
    return ct.astype(np.float32, copy=False), labels.astype(bool, copy=False), {"ct_sha256": clean["ct"]["sha256"], "labels_sha256": clean["labels"]["sha256"]}


def _stable_normal(mask: np.ndarray, point: np.ndarray, radius: int) -> np.ndarray | None:
    z, y, x = (int(v) for v in point)
    slices = tuple(slice(max(0, c - radius), min(mask.shape[i], c + radius + 1)) for i, c in enumerate((z, y, x)))
    local = np.argwhere(mask[slices])
    if local.shape[0] < 3:
        return None
    origin = np.array([s.start for s in slices], dtype=np.float64)
    coords = local.astype(np.float64) + origin
    centered = coords - coords.mean(axis=0, keepdims=True)
    cov = centered.T @ centered / max(1, centered.shape[0] - 1)
    vals, vecs = np.linalg.eigh(cov)
    if not np.isfinite(vals).all() or not np.isfinite(vecs).all():
        return None
    normal = vecs[:, int(np.argmin(vals))]
    norm = float(np.linalg.norm(normal))
    if norm <= 1e-12:
        return None
    normal = normal / norm
    pivot = int(np.argmax(np.abs(normal)))
    if normal[pivot] < 0:
        normal = -normal
    return normal.astype(np.float32)


def _nearest_profile(ct: np.ndarray, point: np.ndarray, normal: np.ndarray, offsets: np.ndarray) -> np.ndarray | None:
    coords = np.rint(point[None, :] + offsets[:, None] * normal[None, :]).astype(np.int64)
    if np.any(coords < 0) or any(np.any(coords[:, i] >= ct.shape[i]) for i in range(3)):
        return None
    return ct[coords[:, 0], coords[:, 1], coords[:, 2]].astype(np.float64)


def _peak_candidate(profile: np.ndarray, offsets: np.ndarray) -> tuple[float, float, float]:
    if profile.shape != offsets.shape or profile.size < 3:
        raise ContractError("invalid profile")
    median = float(np.median(profile))
    mad = float(np.median(np.abs(profile - median)))
    order = sorted(range(profile.size), key=lambda i: (-float(profile[i]), abs(float(offsets[i])), float(offsets[i])))
    best = order[0]
    second = order[1]
    peak_delta = float(profile[best] - profile[second])
    robust_scale = max(1e-6, 1.4826 * mad)
    peak_z = float((profile[best] - median) / robust_scale)
    return float(offsets[best]), peak_z, peak_delta


def _iter_points(mask: np.ndarray, stride: int, max_points: int) -> np.ndarray:
    total_positive = int(np.count_nonzero(mask))
    if total_positive == 0:
        return np.empty((0, 3), dtype=np.int64)
    eligible = (total_positive + stride - 1) // stride
    if eligible <= max_points:
        target_ranks = np.arange(eligible, dtype=np.int64) * stride
    else:
        target_ranks = np.linspace(0, eligible - 1, num=max_points, dtype=np.int64) * stride
    result = np.empty((target_ranks.size, 3), dtype=np.int64)
    target_pos = 0
    positive_seen = 0
    flat_seen = 0
    iterator = np.nditer(mask, flags=["external_loop", "buffered"], op_flags=["readonly"], order="C", buffersize=1 << 20)
    for chunk in iterator:
        chunk_arr = np.asarray(chunk)
        local_positive = np.flatnonzero(chunk_arr)
        next_positive = positive_seen + int(local_positive.size)
        while target_pos < target_ranks.size and int(target_ranks[target_pos]) < next_positive:
            rank_in_chunk = int(target_ranks[target_pos]) - positive_seen
            flat_index = flat_seen + int(local_positive[rank_in_chunk])
            result[target_pos] = np.unravel_index(flat_index, mask.shape, order="C")
            target_pos += 1
        positive_seen = next_positive
        flat_seen += int(chunk_arr.size)
    if target_pos != target_ranks.size:
        raise ContractError("internal point-selection accounting mismatch")
    return result


def audit_surface(ct: np.ndarray, labels: np.ndarray, config: AuditConfig | None = None) -> dict[str, Any]:
    cfg = (config or AuditConfig()).validate()
    ct = np.asarray(ct)
    labels = np.asarray(labels)
    if ct.ndim != 3 or labels.ndim != 3 or ct.shape != labels.shape:
        raise ContractError("ct/labels must be same-shape 3-D arrays")
    if ct.dtype.kind not in "fiu" or not np.isfinite(ct).all():
        raise ContractError("ct must be finite numeric data")
    if labels.dtype.kind not in "biu":
        raise ContractError("labels must be bool/integer")
    uniq = np.unique(labels)
    if uniq.size > 2 or any(int(x) not in (0, 1) for x in uniq.tolist()):
        raise ContractError("labels must contain only 0/1")
    mask = labels.astype(bool, copy=False)
    points = _iter_points(mask, cfg.point_stride, cfg.max_points)
    offsets_axis = np.arange(-cfg.max_offset, cfg.max_offset + 1, dtype=np.float32)
    normals = np.zeros(ct.shape + (3,), dtype=np.float32)
    proposed = np.full(ct.shape, np.nan, dtype=np.float32)
    confidence = np.zeros(ct.shape, dtype=np.float32)
    preliminary = np.zeros(ct.shape, dtype=bool)
    rows: list[tuple[tuple[int, int, int], float, float]] = []
    for p in points:
        n = _stable_normal(mask, p, cfg.normal_radius)
        if n is None:
            continue
        prof = _nearest_profile(ct, p.astype(np.float32), n, offsets_axis)
        if prof is None:
            continue
        offset, peak_z, peak_delta = _peak_candidate(prof, offsets_axis)
        idx = tuple(int(v) for v in p)
        normals[idx] = n
        proposed[idx] = offset
        score = min(100.0, max(0.0, peak_z))
        confidence[idx] = np.float32(score)
        if peak_z >= cfg.min_peak_z and peak_delta >= cfg.min_peak_delta:
            preliminary[idx] = True
            rows.append((idx, offset, score))
    blocks: dict[tuple[int, int, int], list[tuple[tuple[int, int, int], float, float]]] = {}
    for row in rows:
        idx = row[0]
        key = tuple(v // cfg.block_size for v in idx)
        blocks.setdefault(key, []).append(row)
    accepted = np.zeros(ct.shape, dtype=bool)
    block_receipts: list[dict[str, Any]] = []
    for key in sorted(blocks):
        block = blocks[key]
        vals = np.array([r[1] for r in block], dtype=np.float64)
        med = float(np.median(vals))
        agree = np.abs(vals - med) <= cfg.consensus_tolerance
        fraction = float(np.mean(agree)) if agree.size else 0.0
        block_receipts.append({"block": list(key), "preliminary_points": len(block), "median_offset": med, "consensus_fraction": fraction})
        if fraction >= cfg.min_consensus:
            for ok, row in zip(agree.tolist(), block):
                if ok:
                    accepted[row[0]] = True
    audited = int(points.shape[0])
    accepted_count = int(accepted.sum())
    preliminary_count = int(preliminary.sum())
    accepted_fraction = float(accepted_count / audited) if audited else 0.0
    decision = "REVIEW" if accepted_count and accepted_fraction >= cfg.min_global_review_fraction else "ABSTAIN"
    accepted_values = proposed[accepted]
    summary = {"decision": decision, "audited_points": audited, "preliminary_points": preliminary_count, "accepted_points": accepted_count, "accepted_fraction": accepted_fraction, "median_accepted_offset": float(np.median(accepted_values)) if accepted_count else None, "max_abs_accepted_offset": float(np.max(np.abs(accepted_values))) if accepted_count else None, "candidate_application_default": False, "topology_preserved_claim": False}
    return {"format": FORMAT, "config": {"max_offset": cfg.max_offset, "normal_radius": cfg.normal_radius, "point_stride": cfg.point_stride, "block_size": cfg.block_size, "min_peak_z": float(cfg.min_peak_z), "min_peak_delta": float(cfg.min_peak_delta), "min_consensus": float(cfg.min_consensus), "consensus_tolerance": float(cfg.consensus_tolerance), "min_global_review_fraction": float(cfg.min_global_review_fraction), "max_points": cfg.max_points}, "normals": normals, "proposed_offset": proposed, "confidence": confidence, "preliminary": preliminary, "accepted": accepted, "blocks": block_receipts, "summary": summary}


def apply_review_candidate(labels: np.ndarray, audit: Mapping[str, Any], *, enabled: bool = False) -> tuple[np.ndarray, dict[str, Any]]:
    mask = np.asarray(labels).astype(bool, copy=False)
    if not enabled:
        return mask.copy(), {"enabled": False, "moved": 0, "topology_preserved_claim": False}
    normals = np.asarray(audit["normals"])
    offsets = np.asarray(audit["proposed_offset"])
    accepted = np.asarray(audit["accepted"]).astype(bool)
    if normals.shape != mask.shape + (3,) or offsets.shape != mask.shape or accepted.shape != mask.shape:
        raise ContractError("audit arrays do not match labels")
    candidate = mask.copy()
    moves: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = []
    for p in np.argwhere(accepted):
        idx = tuple(int(v) for v in p)
        off = float(offsets[idx])
        if not math.isfinite(off):
            continue
        dest = np.rint(p.astype(np.float64) + off * normals[idx].astype(np.float64)).astype(np.int64)
        if np.any(dest < 0) or any(int(dest[i]) >= mask.shape[i] for i in range(3)):
            continue
        dst = tuple(int(v) for v in dest)
        if dst != idx:
            moves.append((idx, dst))
    for src, _ in moves:
        candidate[src] = False
    for _, dst in moves:
        candidate[dst] = True
    return candidate, {"enabled": True, "moved": len(moves), "topology_preserved_claim": False}


def load_calibration(path: os.PathLike[str] | str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    required = {"format", "source_repository", "source_commit", "dataset", "sample_count", "median_signed_offset_vox", "q10_signed_offset_vox", "q90_signed_offset_vox", "local_review_flags", "default_decision", "evidence_boundary"}
    if type(data) is not dict or set(data) != required:
        raise ContractError("calibration has unexpected schema")
    if data["format"] != CALIBRATION_FORMAT or data["default_decision"] != "ABSTAIN":
        raise ContractError("calibration format/default decision mismatch")
    if type(data["sample_count"]) is not int or data["sample_count"] <= 0:
        raise ContractError("invalid calibration sample_count")
    if type(data["local_review_flags"]) is not int or not (0 <= data["local_review_flags"] <= data["sample_count"]):
        raise ContractError("invalid local_review_flags")
    for name in ("median_signed_offset_vox", "q10_signed_offset_vox", "q90_signed_offset_vox"):
        if type(data[name]) not in (int, float) or not math.isfinite(float(data[name])):
            raise ContractError(f"invalid {name}")
    if not (data["q10_signed_offset_vox"] <= data["median_signed_offset_vox"] <= data["q90_signed_offset_vox"]):
        raise ContractError("calibration quantiles are inconsistent")
    return data


def deterministic_npz_bytes(arrays: Mapping[str, np.ndarray]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(arrays):
            if type(name) is not str or not name or "/" in name or "\\" in name:
                raise ContractError("array names must be simple strings")
            payload = io.BytesIO()
            np.save(payload, np.asarray(arrays[name]), allow_pickle=False)
            info = zipfile.ZipInfo(f"{name}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, payload.getvalue(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return out.getvalue()


def write_metrics_csv(path: os.PathLike[str] | str, summary: Mapping[str, Any]) -> None:
    fields = ["decision", "audited_points", "preliminary_points", "accepted_points", "accepted_fraction", "median_accepted_offset", "max_abs_accepted_offset", "candidate_application_default", "topology_preserved_claim"]
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerow({k: summary.get(k) for k in fields})


def build_receipt(*, manifest: Mapping[str, Any], input_digests: Mapping[str, str], audit: Mapping[str, Any], calibration: Mapping[str, Any], artifacts: Mapping[str, str]) -> dict[str, Any]:
    clean = validate_manifest(manifest)
    for key in ("ct_sha256", "labels_sha256"):
        _require_digest(input_digests[key], key)
    for path, digest in artifacts.items():
        _safe_relpath(path)
        _require_digest(digest, f"artifact {path}")
    body = {"format": RECEIPT_FORMAT, "authority": "LOCAL_AUDIT_ONLY", "manifest_sha256": sha256_bytes(canonical_json_bytes(clean)), "input_digests": dict(sorted(input_digests.items())), "audit_config": audit["config"], "audit_summary": audit["summary"], "calibration_sha256": sha256_bytes(canonical_json_bytes(calibration)), "artifacts": dict(sorted(artifacts.items())), "raw_dataset059_execution_claim": False, "topology_preserved_claim": False, "prize_or_submission_claim": False}
    receipt = dict(body)
    receipt["receipt_sha256"] = sha256_bytes(canonical_json_bytes(body))
    return receipt


def verify_receipt(receipt: Mapping[str, Any]) -> bool:
    required = {"format", "authority", "manifest_sha256", "input_digests", "audit_config", "audit_summary", "calibration_sha256", "artifacts", "raw_dataset059_execution_claim", "topology_preserved_claim", "prize_or_submission_claim", "receipt_sha256"}
    if type(receipt) is not dict or set(receipt) != required or receipt.get("format") != RECEIPT_FORMAT:
        return False
    if receipt.get("authority") != "LOCAL_AUDIT_ONLY":
        return False
    if any(receipt.get(key) is not False for key in ("raw_dataset059_execution_claim", "topology_preserved_claim", "prize_or_submission_claim")):
        return False
    try:
        _require_digest(receipt["manifest_sha256"], "manifest_sha256")
        _require_digest(receipt["calibration_sha256"], "calibration_sha256")
        inputs = receipt["input_digests"]
        if type(inputs) is not dict or set(inputs) != {"ct_sha256", "labels_sha256"}:
            return False
        for key, value in inputs.items():
            _require_digest(value, key)
        config = receipt["audit_config"]
        if type(config) is not dict:
            return False
        AuditConfig(**config).validate()
        summary = receipt["audit_summary"]
        summary_keys = {"decision", "audited_points", "preliminary_points", "accepted_points", "accepted_fraction", "median_accepted_offset", "max_abs_accepted_offset", "candidate_application_default", "topology_preserved_claim"}
        if type(summary) is not dict or set(summary) != summary_keys:
            return False
        if summary["decision"] not in ("ABSTAIN", "REVIEW"):
            return False
        for key in ("audited_points", "preliminary_points", "accepted_points"):
            if type(summary[key]) is not int or summary[key] < 0:
                return False
        if summary["preliminary_points"] > summary["audited_points"] or summary["accepted_points"] > summary["preliminary_points"]:
            return False
        fraction = summary["accepted_fraction"]
        if type(fraction) not in (int, float) or not math.isfinite(float(fraction)) or not (0.0 <= float(fraction) <= 1.0):
            return False
        expected_fraction = (summary["accepted_points"] / summary["audited_points"]) if summary["audited_points"] else 0.0
        if not math.isclose(float(fraction), float(expected_fraction), rel_tol=0.0, abs_tol=1e-12):
            return False
        if summary["candidate_application_default"] is not False or summary["topology_preserved_claim"] is not False:
            return False
        for key in ("median_accepted_offset", "max_abs_accepted_offset"):
            value = summary[key]
            if value is not None and (type(value) not in (int, float) or not math.isfinite(float(value))):
                return False
        artifacts = receipt["artifacts"]
        if type(artifacts) is not dict or not artifacts:
            return False
        for raw_name, value in artifacts.items():
            name = _safe_relpath(raw_name).as_posix()
            if name != raw_name or name == "bundle-manifest.json":
                return False
            _require_digest(value, f"artifact {raw_name}")
        digest = _require_digest(receipt["receipt_sha256"], "receipt_sha256")
        body = dict(receipt)
        body.pop("receipt_sha256")
        return digest == sha256_bytes(canonical_json_bytes(body))
    except (ContractError, TypeError, ValueError):
        return False


def build_bundle_bytes(files: Mapping[str, bytes]) -> tuple[bytes, dict[str, Any]]:
    if not files:
        raise ContractError("bundle requires files")
    manifest_rows = []
    for raw_name in sorted(files):
        name = _safe_relpath(raw_name).as_posix()
        if name != raw_name or name == "bundle-manifest.json":
            raise ContractError("bundle member name is invalid/reserved")
        payload = files[raw_name]
        if type(payload) is not bytes:
            raise ContractError("bundle payloads must be bytes")
        manifest_rows.append({"path": name, "size": len(payload), "sha256": sha256_bytes(payload)})
    manifest = {"format": BUNDLE_FORMAT, "files": manifest_rows}
    archive_files = dict(files)
    archive_files["bundle-manifest.json"] = canonical_json_bytes(manifest) + b"\n"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(archive_files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, archive_files[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return out.getvalue(), manifest


def verify_bundle_bytes(data: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
        infos = zf.infolist()
        names = [i.filename for i in infos]
        if len(names) != len(set(names)) or "bundle-manifest.json" not in names:
            raise ContractError("bundle has duplicate/missing manifest members")
        total_uncompressed = 0
        for info in infos:
            canonical = _safe_relpath(info.filename).as_posix()
            if canonical != info.filename:
                raise ContractError("bundle member path is not canonical")
            mode = (info.external_attr >> 16) & 0o170000
            if mode and mode != stat.S_IFREG:
                raise ContractError("bundle contains non-regular member")
            if info.file_size > 256 * 1024 * 1024:
                raise ContractError("bundle member exceeds size ceiling")
            total_uncompressed += int(info.file_size)
            if total_uncompressed > MAX_BUNDLE_UNCOMPRESSED_BYTES:
                raise ContractError("bundle exceeds total uncompressed size ceiling")
        manifest_bytes = zf.read("bundle-manifest.json")
        try:
            manifest = json.loads(manifest_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ContractError("bundle manifest is not valid JSON") from exc
        if type(manifest) is not dict or set(manifest) != {"format", "files"} or manifest.get("format") != BUNDLE_FORMAT or type(manifest.get("files")) is not list:
            raise ContractError("invalid bundle manifest")
        if manifest_bytes != canonical_json_bytes(manifest) + b"\n":
            raise ContractError("bundle manifest is not canonical JSON")
        expected: dict[str, dict[str, Any]] = {}
        for i, row in enumerate(manifest["files"]):
            if type(row) is not dict or set(row) != {"path", "size", "sha256"}:
                raise ContractError(f"invalid bundle manifest row {i}")
            raw_name = row["path"]
            canonical = _safe_relpath(raw_name).as_posix()
            if canonical != raw_name or raw_name == "bundle-manifest.json":
                raise ContractError(f"invalid bundle manifest path at row {i}")
            if raw_name in expected:
                raise ContractError("bundle manifest contains duplicate file rows")
            if type(row["size"]) is not int or not (0 <= row["size"] <= 256 * 1024 * 1024):
                raise ContractError(f"invalid bundle manifest size at row {i}")
            _require_digest(row["sha256"], f"bundle manifest row {i} sha256")
            expected[raw_name] = row
        actual_names = set(names) - {"bundle-manifest.json"}
        if actual_names != set(expected):
            raise ContractError("bundle membership mismatch")
        payloads: dict[str, bytes] = {}
        for name in sorted(actual_names):
            payload = zf.read(name)
            row = expected[name]
            if row["size"] != len(payload) or row["sha256"] != sha256_bytes(payload):
                raise ContractError(f"bundle member mismatch: {name}")
            payloads[name] = payload
        if "receipt.json" in payloads:
            try:
                receipt = json.loads(payloads["receipt.json"])
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ContractError("receipt.json is not valid JSON") from exc
            if payloads["receipt.json"] != canonical_json_bytes(receipt) + b"\n" or not verify_receipt(receipt):
                raise ContractError("receipt.json failed semantic verification")
            for artifact_name, digest in receipt["artifacts"].items():
                if artifact_name not in payloads or sha256_bytes(payloads[artifact_name]) != digest:
                    raise ContractError(f"receipt artifact binding mismatch: {artifact_name}")
        return manifest
