from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import rasterio
from scipy.ndimage import gaussian_filter, maximum_filter

try:
    from .gems_solver import (
        ALPHA,
        BETA,
        CRS,
        RES_M,
        GemsError,
        distance_weighted_tversky,
    )
except ImportError:  # direct script execution
    from gems_solver import (
        ALPHA,
        BETA,
        CRS,
        RES_M,
        GemsError,
        distance_weighted_tversky,
    )

V2_VERSION = 2
DEFAULT_DIRECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 0),
    (1, 1),
    (1, -1),
    (1, 2),
    (1, -2),
    (2, 1),
    (2, -1),
)


@dataclass(frozen=True)
class StructureConfig:
    radius_steps: int = 2
    decay: float = 0.25
    min_side_support: float = 0.18
    seed_floor: float = 0.04
    seed_neighborhood: float = 0.25
    coherence_power: float = 1.0
    blend: float = 0.50

    def validate(self) -> None:
        if not (1 <= int(self.radius_steps) <= 5):
            raise GemsError("radius_steps must be in [1,5]")
        for name in (
            "decay",
            "min_side_support",
            "seed_floor",
            "seed_neighborhood",
            "coherence_power",
            "blend",
        ):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise GemsError(f"{name} must be finite")
        if self.decay < 0:
            raise GemsError("decay must be non-negative")
        if not (0 <= self.min_side_support <= 1):
            raise GemsError("min_side_support must be in [0,1]")
        if not (0 <= self.seed_floor <= 1):
            raise GemsError("seed_floor must be in [0,1]")
        if not (0 <= self.seed_neighborhood <= 1):
            raise GemsError("seed_neighborhood must be in [0,1]")
        if self.coherence_power < 0:
            raise GemsError("coherence_power must be non-negative")
        if not (0 <= self.blend <= 1):
            raise GemsError("blend must be in [0,1]")


def _probability_with_mask(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    arr = np.asarray(values)
    if arr.ndim != 2:
        raise GemsError("probability raster must be 2-D")
    if not np.issubdtype(arr.dtype, np.number):
        raise GemsError("probability raster must be numeric")
    arr = arr.astype(np.float64, copy=False)
    valid = np.isfinite(arr)
    if valid.any() and np.any((arr[valid] < 0) | (arr[valid] > 1)):
        raise GemsError("finite probabilities must be in [0,1]")
    filled = np.where(valid, arr, 0.0)
    return filled, valid


def _truth(values: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    arr = np.asarray(values)
    if arr.ndim != 2 or arr.shape != shape:
        raise GemsError("truth must be a 2-D raster matching probabilities")
    if not np.all(np.isin(np.unique(arr), [0, 1, False, True])):
        raise GemsError("truth must be binary")
    return arr.astype(bool)


def _shift_zero(arr: np.ndarray, dy: int, dx: int) -> np.ndarray:
    out = np.zeros_like(arr, dtype=np.float64)
    h, w = arr.shape
    dst_y0, dst_y1 = max(0, -dy), min(h, h - dy)
    dst_x0, dst_x1 = max(0, -dx), min(w, w - dx)
    if dst_y0 >= dst_y1 or dst_x0 >= dst_x1:
        return out
    src_y0, src_y1 = dst_y0 + dy, dst_y1 + dy
    src_x0, src_x1 = dst_x0 + dx, dst_x1 + dx
    out[dst_y0:dst_y1, dst_x0:dst_x1] = arr[src_y0:src_y1, src_x0:src_x1]
    return out


def directional_structure(
    probability: np.ndarray,
    *,
    radius_steps: int = 2,
    decay: float = 0.25,
    directions: Iterable[tuple[int, int]] = DEFAULT_DIRECTIONS,
) -> dict[str, np.ndarray]:
    """Measure two-sided line support without fabricating unsupported endpoints.

    Each orientation receives the geometric mean of the strongest decayed
    probability found on each side of a pixel. The winning orientation and
    the margin over the second-best orientation define structure support and
    coherence. No output in this function is itself a prediction.
    """
    p, valid = _probability_with_mask(probability)
    radius_steps = int(radius_steps)
    if radius_steps < 1 or radius_steps > 5:
        raise GemsError("radius_steps must be in [1,5]")
    if not math.isfinite(decay) or decay < 0:
        raise GemsError("decay must be finite and non-negative")

    dirs = tuple((int(dy), int(dx)) for dy, dx in directions)
    if not dirs or any((dy == 0 and dx == 0) for dy, dx in dirs):
        raise GemsError("directions must contain non-zero integer vectors")

    scores: list[np.ndarray] = []
    side_minima: list[np.ndarray] = []
    for dy, dx in dirs:
        forward = np.zeros_like(p)
        backward = np.zeros_like(p)
        for step in range(1, radius_steps + 1):
            weight = math.exp(-decay * (step - 1))
            np.maximum(forward, _shift_zero(p, step * dy, step * dx) * weight, out=forward)
            np.maximum(backward, _shift_zero(p, -step * dy, -step * dx) * weight, out=backward)
        side = np.minimum(forward, backward)
        score = np.sqrt(np.maximum(forward * backward, 0.0))
        scores.append(score)
        side_minima.append(side)

    stack = np.stack(scores, axis=0)
    side_stack = np.stack(side_minima, axis=0)
    order = np.argsort(stack, axis=0)
    best_index = order[-1]
    best = np.take_along_axis(stack, best_index[None, ...], axis=0)[0]
    best_side = np.take_along_axis(side_stack, best_index[None, ...], axis=0)[0]
    second = (
        np.take_along_axis(stack, order[-2][None, ...], axis=0)[0]
        if len(dirs) > 1
        else np.zeros_like(best)
    )
    coherence = np.clip((best - second) / (best + 1e-12), 0.0, 1.0)
    best = np.where(valid, best, 0.0)
    best_side = np.where(valid, best_side, 0.0)
    coherence = np.where(valid, coherence, 0.0)
    best_index = np.where(valid, best_index, -1)
    return {
        "support": best,
        "side_support": best_side,
        "coherence": coherence,
        "direction_index": best_index.astype(np.int16),
    }


def apply_structure(probability: np.ndarray, config: StructureConfig) -> np.ndarray:
    """Blend line-continuity evidence into a probability raster.

    The decoder can bridge only pixels that have bilateral line support within
    the configured bounded radius and either non-trivial base probability or a
    nearby strong seed. This prevents one-sided extrapolation from extending a
    fault indefinitely into blank space.
    """
    config.validate()
    p, valid = _probability_with_mask(probability)
    if config.blend == 0:
        return np.where(valid, p, np.nan).astype(np.float32)

    structure = directional_structure(
        p,
        radius_steps=config.radius_steps,
        decay=config.decay,
    )
    support = structure["support"]
    side = structure["side_support"]
    coherence = structure["coherence"]
    if config.coherence_power == 0:
        coherent = np.ones_like(coherence)
    else:
        coherent = np.power(coherence, config.coherence_power)

    # A seed can be the pixel itself or an immediate local observation, but
    # line evidence must still be bilateral and bounded by radius_steps.
    local_seed = maximum_filter(p, size=3, mode="constant", cval=0.0)
    admitted = (
        (side >= config.min_side_support)
        & ((p >= config.seed_floor) | (local_seed >= config.seed_neighborhood))
        & valid
    )
    candidate = np.where(admitted, support * coherent, 0.0)

    # Noisy-or raises confidence without ever lowering the base classifier.
    propagated = 1.0 - (1.0 - p) * (1.0 - candidate)
    out = (1.0 - config.blend) * p + config.blend * propagated
    out = np.clip(out, 0.0, 1.0)
    return np.where(valid, out, np.nan).astype(np.float32)


def default_grid() -> tuple[StructureConfig, ...]:
    configs: list[StructureConfig] = [StructureConfig(blend=0.0)]
    for radius in (1, 2, 3):
        for blend in (0.25, 0.50, 0.75):
            for threshold in (0.12, 0.20):
                configs.append(
                    StructureConfig(
                        radius_steps=radius,
                        decay=0.25,
                        min_side_support=threshold,
                        seed_floor=0.03,
                        seed_neighborhood=0.22,
                        coherence_power=0.75,
                        blend=blend,
                    )
                )
    return tuple(configs)


def _finite_metric_inputs(
    probability: np.ndarray, truth: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    p, valid = _probability_with_mask(probability)
    g = _truth(truth, p.shape)
    if not valid.any():
        raise GemsError("validation probability contains no finite pixels")
    # Existing V1 metric requires a finite dense array. Null cells are excluded
    # by evaluating the smallest enclosing valid mask as zero-weight candidate
    # pixels and disallowing truth on null cells.
    if np.any(g & ~valid):
        raise GemsError("truth may not mark a fault on a null prediction pixel")
    dense = np.where(valid, p, 0.0)
    return dense, g, valid


def _array_digest(arr: np.ndarray) -> str:
    a = np.ascontiguousarray(arr)
    h = hashlib.sha256()
    h.update(str(a.dtype).encode("ascii"))
    h.update(b"\0")
    h.update(json.dumps(list(a.shape), separators=(",", ":")).encode("ascii"))
    h.update(b"\0")
    h.update(a.tobytes(order="C"))
    return h.hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def select_config(
    validation_probability: np.ndarray,
    validation_truth: np.ndarray,
    *,
    configs: Iterable[StructureConfig] | None = None,
    radius_px: float = 3.0,
    holdout_role: str = "validation",
) -> dict[str, Any]:
    if holdout_role != "validation":
        raise GemsError("structure selection requires holdout_role='validation'")
    base, truth, valid = _finite_metric_inputs(validation_probability, validation_truth)
    candidates = tuple(configs) if configs is not None else default_grid()
    if not candidates:
        raise GemsError("at least one candidate configuration is required")
    for cfg in candidates:
        cfg.validate()

    scored: list[dict[str, Any]] = []
    for cfg in candidates:
        candidate = apply_structure(validation_probability, cfg)
        dense = np.where(valid, candidate, 0.0)
        metric = distance_weighted_tversky(dense, truth, radius_px=radius_px)
        scored.append({"config": asdict(cfg), "score": float(metric["score"])})

    # Stable tie-break prefers the earlier candidate, with the mandatory
    # default grid placing the no-op baseline first.
    best_idx = max(range(len(scored)), key=lambda i: (scored[i]["score"], -i))
    selected = scored[best_idx]
    baseline_score = float(
        distance_weighted_tversky(base, truth, radius_px=radius_px)["score"]
    )
    body = {
        "schema": "doe-gems-structure-selection/v1",
        "version": V2_VERSION,
        "holdout_role": holdout_role,
        "radius_px": float(radius_px),
        "validation_probability_sha256": _array_digest(
            np.asarray(validation_probability)
        ),
        "validation_truth_sha256": _array_digest(np.asarray(validation_truth)),
        "baseline_score": baseline_score,
        "selected": selected,
        "candidates": scored,
        "authority": {
            "official_data": False,
            "leaderboard": False,
            "submission": False,
            "prize": False,
        },
    }
    body["receipt_sha256"] = hashlib.sha256(canonical_json(body)).hexdigest()
    return body


def verify_selection(
    validation_probability: np.ndarray,
    validation_truth: np.ndarray,
    receipt: dict[str, Any],
    *,
    configs: Iterable[StructureConfig] | None = None,
) -> bool:
    try:
        if receipt.get("schema") != "doe-gems-structure-selection/v1":
            return False
        radius_px = float(receipt["radius_px"])
        recomputed = select_config(
            validation_probability,
            validation_truth,
            configs=configs,
            radius_px=radius_px,
            holdout_role=str(receipt["holdout_role"]),
        )
        return canonical_json(recomputed) == canonical_json(receipt)
    except (GemsError, KeyError, TypeError, ValueError):
        return False


def receipt_integrity_valid(receipt: dict[str, Any]) -> bool:
    if not isinstance(receipt, dict):
        return False
    expected = receipt.get("receipt_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    body = dict(receipt)
    body.pop("receipt_sha256", None)
    return hashlib.sha256(canonical_json(body)).hexdigest() == expected


def selected_config(receipt: dict[str, Any]) -> StructureConfig:
    if receipt.get("schema") != "doe-gems-structure-selection/v1":
        raise GemsError("unsupported selection receipt")
    if not receipt_integrity_valid(receipt):
        raise GemsError("selection receipt integrity check failed")
    if receipt.get("holdout_role") != "validation":
        raise GemsError("selection receipt is not validation-bound")
    if int(receipt.get("version", -1)) != V2_VERSION:
        raise GemsError("unsupported structure selection version")
    try:
        cfg = StructureConfig(**receipt["selected"]["config"])
    except (KeyError, TypeError) as exc:
        raise GemsError("invalid selected configuration") from exc
    cfg.validate()
    return cfg


def _validate_probability_raster(src: rasterio.io.DatasetReader) -> None:
    if src.count != 1 or src.dtypes[0] != "float32":
        raise GemsError("probability raster must be one float32 band")
    if src.crs is None or src.crs.to_string() != CRS:
        raise GemsError(f"probability raster CRS must be {CRS}")
    if abs(abs(float(src.res[0])) - RES_M) > 1e-6 or abs(
        abs(float(src.res[1])) - RES_M
    ) > 1e-6:
        raise GemsError("probability raster resolution must be 100m")


def apply_raster(
    probability_path: str | Path,
    output_path: str | Path,
    config: StructureConfig,
) -> dict[str, Any]:
    probability_path = Path(probability_path)
    output_path = Path(output_path)
    if probability_path.resolve() == output_path.resolve():
        raise GemsError("output path must differ from input probability path")
    if output_path.exists():
        raise GemsError("refusing to overwrite existing output")
    with rasterio.open(probability_path) as src:
        _validate_probability_raster(src)
        base = src.read(1)
        decoded = apply_structure(base, config)
        profile = src.profile.copy()
        profile.update(
            driver="GTiff",
            count=1,
            dtype="float32",
            nodata=np.nan,
            compress="deflate",
            predictor=3,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(output_path, "w", **profile) as dst:
            dst.write(decoded.astype(np.float32), 1)
        finite = np.isfinite(decoded)
        return {
            "schema": "doe-gems-structure-output/v1",
            "version": V2_VERSION,
            "input_probability_sha256": _file_sha256(probability_path),
            "output_sha256": _file_sha256(output_path),
            "width": int(src.width),
            "height": int(src.height),
            "crs": src.crs.to_string(),
            "resolution_m": RES_M,
            "finite_pixels": int(finite.sum()),
            "null_pixels": int((~finite).sum()),
            "config": asdict(config),
            "authority": {
                "official_data": False,
                "leaderboard": False,
                "submission": False,
                "prize": False,
            },
        }


def _reject_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise GemsError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise GemsError(f"non-finite JSON constant is not allowed: {value}")


def _read_json(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(
            Path(path).read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_object,
            parse_constant=_reject_constant,
        )
    except json.JSONDecodeError as exc:
        raise GemsError("invalid JSON document") from exc
    if not isinstance(value, dict):
        raise GemsError("JSON document must be an object")
    return value


def _write_exclusive_json(path: str | Path, value: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(value) + b"\n"
    try:
        with target.open("xb") as handle:
            handle.write(payload)
    except FileExistsError as exc:
        raise GemsError("refusing to overwrite existing selection receipt") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="DOE GEMS V2 structure-aware fault continuity ensemble"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    select_cmd = sub.add_parser("select")
    select_cmd.add_argument("--probability-npy", required=True)
    select_cmd.add_argument("--truth-npy", required=True)
    select_cmd.add_argument("--selection", required=True)

    apply_cmd = sub.add_parser("apply")
    apply_cmd.add_argument("--probability", required=True)
    apply_cmd.add_argument("--selection", required=True)
    apply_cmd.add_argument("--output", required=True)
    apply_cmd.add_argument("--receipt")

    verify_cmd = sub.add_parser("verify-selection")
    verify_cmd.add_argument("--probability-npy", required=True)
    verify_cmd.add_argument("--truth-npy", required=True)
    verify_cmd.add_argument("--selection", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "select":
            probability = np.load(args.probability_npy, allow_pickle=False)
            truth = np.load(args.truth_npy, allow_pickle=False)
            receipt = select_config(probability, truth)
            _write_exclusive_json(args.selection, receipt)
            print(receipt["receipt_sha256"])
            return 0
        if args.command == "apply":
            receipt = _read_json(args.selection)
            config = selected_config(receipt)
            result = apply_raster(args.probability, args.output, config)
            if args.receipt:
                _write_exclusive_json(args.receipt, result)
            print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            return 0
        if args.command == "verify-selection":
            receipt = _read_json(args.selection)
            probability = np.load(args.probability_npy, allow_pickle=False)
            truth = np.load(args.truth_npy, allow_pickle=False)
            valid = verify_selection(probability, truth, receipt)
            print("VALID" if valid else "INVALID")
            return 0 if valid else 1
        raise AssertionError(args.command)
    except (GemsError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
