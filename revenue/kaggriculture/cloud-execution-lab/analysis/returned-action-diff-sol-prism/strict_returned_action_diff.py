#!/usr/bin/env python3
"""Fail-closed consumer for one same-state/same-request returned-action pair.

This module is intentionally narrower than a trajectory analyzer. It validates
saved capture bundles from ``returned_action_diff.py`` bottom-up, then compares
ONE pair of deterministic actions. It does not infer temporal ordering,
state-transition edges, causality, or a first causal divergence across rows.

Evidence properties:
* duplicate JSON keys and non-finite JSON numbers are rejected;
* persisted state/request/action/sample claims are recomputed where the
  persisted bytes permit recomputation;
* both operands must prove the exact same canonical state and request bytes;
* unstable repeat captures produce HOLD rather than a sample-zero comparison;
* list order is semantic by default; unordered alignment requires an explicit
  reviewed JSON-path allowlist supplied by the caller; and
* inputs must be regular distinct files and outputs may not alias inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import returned_action_diff as parent

STRICT_REPORT_FORMAT = "titan-returned-action-diff-strict/v2"
SHA256_LEN = 64
_MISSING = object()


class EvidenceError(ValueError):
    """Evidence is malformed, self-inconsistent, aliased, or insufficient."""


@dataclass(frozen=True)
class StrictDifference:
    path: str
    kind: str
    left: Any
    right: Any
    absolute_delta: float | int | None = None
    relative_delta: float | None = None


@dataclass(frozen=True)
class ValidatedCapture:
    name: str
    endpoint: str
    source: str
    state: Any
    state_sha256: str
    request_sha256: str
    action: Any
    action_sha256: str
    sample_count: int
    unique_action_count: int
    deterministic: bool


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _reject_constant(token: str) -> Any:
    raise EvidenceError(f"non-finite JSON constant is forbidden: {token}")


def _finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise EvidenceError(f"non-finite JSON number is forbidden: {token}")
    return value


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def strict_loads(text: str) -> Any:
    try:
        return json.loads(
            text,
            object_pairs_hook=_object_no_duplicates,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"invalid JSON: {exc}") from exc


def _json_path_key(key: str) -> str:
    if key and (key[0].isalpha() or key[0] == "_") and all(
        ch.isalnum() or ch == "_" for ch in key
    ):
        return "." + key
    return "[" + json.dumps(key, ensure_ascii=False) + "]"


def _validate_json_domain(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise EvidenceError(f"{path}: non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_domain(item, f"{path}[{index}]")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise EvidenceError(f"{path}: non-string object key")
            _validate_json_domain(item, path + _json_path_key(key))
        return
    raise EvidenceError(f"{path}: unsupported JSON value type {type(value).__name__}")


def _require_exact_type(value: Any, expected: type, field: str) -> Any:
    if type(value) is not expected:
        raise EvidenceError(f"{field}: expected {expected.__name__}")
    return value


def _require_int(value: Any, field: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise EvidenceError(f"{field}: expected integer")
    if minimum is not None and value < minimum:
        raise EvidenceError(f"{field}: must be >= {minimum}")
    return value


def _require_sha(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != SHA256_LEN:
        raise EvidenceError(f"{field}: expected 64-char SHA-256")
    try:
        int(value, 16)
    except ValueError as exc:
        raise EvidenceError(f"{field}: invalid SHA-256 hex") from exc
    if value.lower() != value:
        raise EvidenceError(f"{field}: SHA-256 must use lowercase hex")
    return value


def _numbers_close(
    left: int | float,
    right: int | float,
    abs_tol: float,
    rel_tol: float,
) -> bool:
    if abs_tol == 0 and rel_tol == 0:
        if isinstance(left, int) and isinstance(right, int):
            return left == right
        if isinstance(left, int) and isinstance(right, float):
            return right.is_integer() and left == int(right)
        if isinstance(left, float) and isinstance(right, int):
            return left.is_integer() and int(left) == right
        return left == right
    try:
        return math.isclose(float(left), float(right), abs_tol=abs_tol, rel_tol=rel_tol)
    except OverflowError:
        return left == right


def _numeric_delta(
    left: int | float, right: int | float
) -> tuple[float | int, float | None]:
    absolute = abs(right - left)
    denominator = max(abs(left), abs(right))
    if not denominator:
        return absolute, 0.0
    try:
        relative = float(absolute / denominator)
    except (OverflowError, ZeroDivisionError):
        relative = None
    return absolute, relative


def _identity_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _identity_keyset(
    left: Sequence[Any], right: Sequence[Any]
) -> tuple[str, ...] | None:
    items = [*left, *right]
    if not items or not all(isinstance(item, Mapping) for item in items):
        return None
    for keys in parent.IDENTITY_CANDIDATES:
        if not all(
            all(key in item and _identity_scalar(item[key]) for key in keys)
            for item in items
        ):
            continue
        left_tokens = [
            canonical_json_bytes([item[key] for key in keys]).decode("utf-8")
            for item in left
        ]
        right_tokens = [
            canonical_json_bytes([item[key] for key in keys]).decode("utf-8")
            for item in right
        ]
        if len(left_tokens) == len(set(left_tokens)) and len(right_tokens) == len(
            set(right_tokens)
        ):
            return tuple(keys)
    return None


def _identity_token(item: Mapping[str, Any], keys: Sequence[str]) -> str:
    return canonical_json_bytes([item[key] for key in keys]).decode("utf-8")


def _identity_path(keys: Sequence[str], item: Mapping[str, Any]) -> str:
    pieces = [
        f"{key}={json.dumps(item[key], ensure_ascii=False, sort_keys=True)}"
        for key in keys
    ]
    return "[" + ",".join(pieces) + "]"


def strict_semantic_diff(
    left: Any,
    right: Any,
    *,
    abs_tol: float = 0.0,
    rel_tol: float = 0.0,
    unordered_paths: frozenset[str] = frozenset(),
    path: str = "$",
) -> list[StrictDifference]:
    """Diff JSON values; list positions are semantic unless explicitly allowed."""
    if abs_tol < 0 or rel_tol < 0 or not math.isfinite(abs_tol) or not math.isfinite(rel_tol):
        raise EvidenceError("numeric tolerances must be finite and non-negative")
    _validate_json_domain(left, "$left")
    _validate_json_domain(right, "$right")
    if any(not isinstance(item, str) or not item.startswith("$") for item in unordered_paths):
        raise EvidenceError("unordered paths must be explicit JSON paths beginning with '$'")

    differences: list[StrictDifference] = []

    def visit(left_value: Any, right_value: Any, current_path: str) -> None:
        if left_value is _MISSING:
            differences.append(StrictDifference(current_path, "left_missing", None, right_value))
            return
        if right_value is _MISSING:
            differences.append(StrictDifference(current_path, "right_missing", left_value, None))
            return

        left_number = type(left_value) in (int, float)
        right_number = type(right_value) in (int, float)
        if left_number and right_number:
            if not _numbers_close(left_value, right_value, abs_tol, rel_tol):
                absolute, relative = _numeric_delta(left_value, right_value)
                differences.append(
                    StrictDifference(
                        current_path,
                        "number",
                        left_value,
                        right_value,
                        absolute_delta=absolute,
                        relative_delta=relative,
                    )
                )
            return

        if type(left_value) is not type(right_value):
            differences.append(StrictDifference(current_path, "type", left_value, right_value))
            return

        if isinstance(left_value, Mapping):
            for key in sorted(set(left_value) | set(right_value)):
                visit(
                    left_value.get(key, _MISSING),
                    right_value.get(key, _MISSING),
                    current_path + _json_path_key(key),
                )
            return

        if isinstance(left_value, list):
            if current_path in unordered_paths:
                identity_keys = _identity_keyset(left_value, right_value)
                if not identity_keys:
                    raise EvidenceError(
                        f"{current_path}: unordered alignment requires a unique reviewed identity key"
                    )
                left_by_token = {
                    _identity_token(item, identity_keys): item for item in left_value
                }
                right_by_token = {
                    _identity_token(item, identity_keys): item for item in right_value
                }
                for token in sorted(set(left_by_token) | set(right_by_token)):
                    representative = left_by_token.get(token) or right_by_token[token]
                    visit(
                        left_by_token.get(token, _MISSING),
                        right_by_token.get(token, _MISSING),
                        current_path + _identity_path(identity_keys, representative),
                    )
            else:
                for index in range(max(len(left_value), len(right_value))):
                    visit(
                        left_value[index] if index < len(left_value) else _MISSING,
                        right_value[index] if index < len(right_value) else _MISSING,
                        f"{current_path}[{index}]",
                    )
            return

        if left_value != right_value:
            differences.append(StrictDifference(current_path, "value", left_value, right_value))

    visit(left, right, path)
    return differences


def _recomputed_internal_difference(first: Any, later: Any) -> dict[str, Any] | None:
    # This validates the parent's diagnostic field only. Attribution below uses
    # the stricter positional-by-default comparator.
    diffs = parent.semantic_diff(first, later)
    return asdict(diffs[0]) if diffs else None


def validate_capture_bundle(data: Any, *, source: str = "<memory>") -> ValidatedCapture:
    """Validate one parent capture bundle bottom-up and return trusted fields."""
    if not isinstance(data, Mapping):
        raise EvidenceError(f"{source}: capture must be an object")
    _validate_json_domain(data)
    if data.get("format") != parent.CAPTURE_FORMAT:
        raise EvidenceError(f"{source}: unsupported capture format")

    name = _require_exact_type(data.get("name"), str, f"{source}.name")
    endpoint = _require_exact_type(data.get("endpoint"), str, f"{source}.endpoint")
    if "state" not in data:
        raise EvidenceError(f"{source}.state: missing")
    state = data["state"]
    state_bytes = canonical_json_bytes(state)
    expected_state_sha = sha256_bytes(state_bytes)
    state_sha = _require_sha(data.get("state_sha256"), f"{source}.state_sha256")
    request_sha = _require_sha(data.get("request_sha256"), f"{source}.request_sha256")
    if state_sha != expected_state_sha:
        raise EvidenceError(f"{source}: state_sha256 does not match canonical state bytes")
    if request_sha != expected_state_sha:
        raise EvidenceError(f"{source}: request_sha256 does not match canonical request bytes")
    if _require_int(
        data.get("request_bytes_length"),
        f"{source}.request_bytes_length",
        minimum=0,
    ) != len(state_bytes):
        raise EvidenceError(f"{source}: request_bytes_length mismatch")

    samples = data.get("samples")
    if not isinstance(samples, list) or not samples:
        raise EvidenceError(f"{source}.samples: expected non-empty list")
    sample_count = _require_int(data.get("sample_count"), f"{source}.sample_count", minimum=1)
    if sample_count != len(samples):
        raise EvidenceError(f"{source}: sample_count mismatch")

    action_hashes: list[str] = []
    trusted_samples: list[tuple[Any, Any, tuple[str, ...], str]] = []
    for index, sample in enumerate(samples):
        prefix = f"{source}.samples[{index}]"
        if not isinstance(sample, Mapping):
            raise EvidenceError(f"{prefix}: expected object")
        if "raw_response" not in sample or "action" not in sample:
            raise EvidenceError(f"{prefix}: raw_response/action missing")
        raw_response = sample["raw_response"]
        action = sample["action"]
        claimed_path = sample.get("unwrap_path")
        if not isinstance(claimed_path, list) or not all(
            isinstance(item, str) for item in claimed_path
        ):
            raise EvidenceError(f"{prefix}.unwrap_path: expected string list")
        recomputed_action, recomputed_path = parent.unwrap_action(raw_response)
        if action != recomputed_action:
            raise EvidenceError(f"{prefix}: action is not the raw_response projection")
        if tuple(claimed_path) != tuple(recomputed_path):
            raise EvidenceError(f"{prefix}: unwrap_path mismatch")
        action_sha = _require_sha(sample.get("action_sha256"), f"{prefix}.action_sha256")
        if action_sha != sha256_json(action):
            raise EvidenceError(f"{prefix}: action_sha256 mismatch")
        http = sample.get("http")
        if not isinstance(http, Mapping):
            raise EvidenceError(f"{prefix}.http: expected object")
        _require_int(http.get("status"), f"{prefix}.http.status", minimum=100)
        # Parent hashes raw wire bytes before JSON parsing, but those bytes are
        # not persisted. Validate digest shape only; never relabel it as
        # recomputed evidence.
        _require_sha(http.get("body_sha256"), f"{prefix}.http.body_sha256")
        action_hashes.append(action_sha)
        trusted_samples.append((raw_response, action, tuple(recomputed_path), action_sha))

    unique_action_count = len(set(action_hashes))
    deterministic = unique_action_count == 1
    if _require_int(
        data.get("unique_action_count"),
        f"{source}.unique_action_count",
        minimum=1,
    ) != unique_action_count:
        raise EvidenceError(f"{source}: unique_action_count mismatch")
    if _require_exact_type(
        data.get("deterministic"), bool, f"{source}.deterministic"
    ) != deterministic:
        raise EvidenceError(f"{source}: deterministic flag mismatch")

    first_unstable = next(
        (i for i, value in enumerate(action_hashes[1:], 1) if value != action_hashes[0]),
        None,
    )
    claimed_first_unstable = data.get("first_unstable_sample")
    if claimed_first_unstable is not None:
        claimed_first_unstable = _require_int(
            claimed_first_unstable,
            f"{source}.first_unstable_sample",
            minimum=1,
        )
    if claimed_first_unstable != first_unstable:
        raise EvidenceError(f"{source}: first_unstable_sample mismatch")

    expected_internal = (
        _recomputed_internal_difference(
            trusted_samples[0][1], trusted_samples[first_unstable][1]
        )
        if first_unstable is not None
        else None
    )
    if data.get("first_internal_difference") != expected_internal:
        raise EvidenceError(f"{source}: first_internal_difference mismatch")

    baseline_raw, baseline_action, baseline_path, baseline_sha = trusted_samples[0]
    if data.get("raw_response") != baseline_raw:
        raise EvidenceError(f"{source}: top-level raw_response does not equal sample zero")
    if data.get("action") != baseline_action:
        raise EvidenceError(f"{source}: top-level action does not equal sample zero")
    claimed_top_path = data.get("unwrap_path")
    if not isinstance(claimed_top_path, list) or tuple(claimed_top_path) != baseline_path:
        raise EvidenceError(f"{source}: top-level unwrap_path mismatch")
    top_action_sha = _require_sha(data.get("action_sha256"), f"{source}.action_sha256")
    if top_action_sha != baseline_sha:
        raise EvidenceError(f"{source}: top-level action_sha256 mismatch")

    return ValidatedCapture(
        name=name,
        endpoint=endpoint,
        source=source,
        state=state,
        state_sha256=state_sha,
        request_sha256=request_sha,
        action=baseline_action,
        action_sha256=top_action_sha,
        sample_count=sample_count,
        unique_action_count=unique_action_count,
        deterministic=deterministic,
    )


def _pair_proof(left: ValidatedCapture, right: ValidatedCapture) -> dict[str, Any]:
    if left.state_sha256 != right.state_sha256:
        raise EvidenceError("state SHA-256 mismatch; same-state comparison forbidden")
    if left.request_sha256 != right.request_sha256:
        raise EvidenceError("request SHA-256 mismatch; same-request comparison forbidden")
    if left.state_sha256 != left.request_sha256 or right.state_sha256 != right.request_sha256:
        raise EvidenceError("capture state/request identity is internally inconsistent")
    return {
        "state_sha256": left.state_sha256,
        "request_sha256": left.request_sha256,
        "state_verified": True,
        "request_verified": True,
    }


def _seal(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("report_sha256", None)
    return sha256_json(body)


def compare_validated_captures(
    left_data: Any,
    right_data: Any,
    *,
    left_source: str = "<left>",
    right_source: str = "<right>",
    abs_tol: float = 0.0,
    rel_tol: float = 0.0,
    unordered_paths: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """Validate and compare one pair; this function makes no cross-row claim."""
    left = validate_capture_bundle(left_data, source=left_source)
    right = validate_capture_bundle(right_data, source=right_source)
    proof = _pair_proof(left, right)
    report: dict[str, Any] = {
        "format": STRICT_REPORT_FORMAT,
        "scope": "single_pair_only",
        "trajectory_claim": False,
        "causality_claim": False,
        "left": {
            "name": left.name,
            "endpoint": left.endpoint,
            "source": left.source,
            "action_sha256": left.action_sha256,
            "sample_count": left.sample_count,
            "unique_action_count": left.unique_action_count,
        },
        "right": {
            "name": right.name,
            "endpoint": right.endpoint,
            "source": right.source,
            "action_sha256": right.action_sha256,
            "sample_count": right.sample_count,
            "unique_action_count": right.unique_action_count,
        },
        "proof": proof,
        "unordered_paths": sorted(unordered_paths),
        "tolerances": {"absolute": abs_tol, "relative": rel_tol},
    }
    if not left.deterministic or not right.deterministic:
        report.update(
            {
                "verdict": "HOLD_UNSTABLE",
                "summary": {
                    "equal": None,
                    "difference_count": None,
                    "first_difference": None,
                    "reason": "repeat instability forbids pair attribution",
                },
            }
        )
    else:
        differences = strict_semantic_diff(
            left.action,
            right.action,
            abs_tol=abs_tol,
            rel_tol=rel_tol,
            unordered_paths=unordered_paths,
        )
        report.update(
            {
                "verdict": "EQUAL" if not differences else "DIFFERENT",
                "summary": {
                    "equal": not differences,
                    "difference_count": len(differences),
                    "first_difference": asdict(differences[0]) if differences else None,
                    "by_kind": dict(
                        sorted(Counter(item.kind for item in differences).items())
                    ),
                },
                "differences": [asdict(item) for item in differences],
            }
        )
    report["report_sha256"] = _seal(report)
    return report


def _assert_regular_file(path: Path, label: str) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise EvidenceError(f"{label}: cannot stat {path}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise EvidenceError(f"{label}: input must be a regular non-symlink file")


def _same_existing_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except (FileNotFoundError, OSError):
        return False


def _resolved(path: Path) -> Path:
    return path.resolve(strict=False)


def validate_path_separation(inputs: Sequence[Path], outputs: Sequence[Path]) -> None:
    if len({_resolved(path) for path in inputs}) != len(inputs):
        raise EvidenceError("input paths alias each other")
    for path in inputs:
        _assert_regular_file(path, "input")
    for i, left in enumerate(inputs):
        for right in inputs[i + 1 :]:
            if _same_existing_file(left, right):
                raise EvidenceError("input files alias the same inode")

    all_outputs = [path for path in outputs if path is not None]
    if len({_resolved(path) for path in all_outputs}) != len(all_outputs):
        raise EvidenceError("output paths alias each other")
    for output in all_outputs:
        try:
            info = output.lstat()
        except FileNotFoundError:
            info = None
        except OSError as exc:
            raise EvidenceError(f"output: cannot stat {output}: {exc}") from exc
        if info is not None and stat.S_ISLNK(info.st_mode):
            raise EvidenceError("output path may not be a symlink")
        if info is not None and not stat.S_ISREG(info.st_mode):
            raise EvidenceError("existing output must be a regular file")
        for input_path in inputs:
            if _resolved(output) == _resolved(input_path) or _same_existing_file(
                output, input_path
            ):
                raise EvidenceError("output path aliases immutable input evidence")


def strict_load_file(path: Path) -> Any:
    _assert_regular_file(path, "input")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise EvidenceError(f"cannot read {path}: {exc}") from exc
    return strict_loads(text)


def atomic_write_json(path: Path, value: Any) -> None:
    payload = json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and compare exactly one parent returned-action capture pair."
    )
    parser.add_argument("--left", type=Path, required=True, help="left parent capture bundle")
    parser.add_argument("--right", type=Path, required=True, help="right parent capture bundle")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--abs-tol", type=float, default=0.0)
    parser.add_argument("--rel-tol", type=float, default=0.0)
    parser.add_argument(
        "--unordered-path",
        action="append",
        default=[],
        help="exact reviewed JSON path where order is semantically irrelevant; repeatable",
    )
    parser.add_argument("--fail-on-diff", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    unordered_paths = frozenset(args.unordered_path)
    output_paths = [args.json_out] if args.json_out else []
    try:
        validate_path_separation([args.left, args.right], output_paths)
        report = compare_validated_captures(
            strict_load_file(args.left),
            strict_load_file(args.right),
            left_source=str(args.left),
            right_source=str(args.right),
            abs_tol=args.abs_tol,
            rel_tol=args.rel_tol,
            unordered_paths=unordered_paths,
        )
        if args.json_out:
            atomic_write_json(args.json_out, report)
        else:
            print(
                json.dumps(
                    report,
                    indent=2,
                    sort_keys=True,
                    ensure_ascii=False,
                    allow_nan=False,
                )
            )
        if report["verdict"] == "HOLD_UNSTABLE":
            return 3
        if args.fail_on_diff and report["verdict"] == "DIFFERENT":
            return 1
        return 0
    except (EvidenceError, OSError, OverflowError, TypeError, ValueError) as exc:
        print(f"error: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
