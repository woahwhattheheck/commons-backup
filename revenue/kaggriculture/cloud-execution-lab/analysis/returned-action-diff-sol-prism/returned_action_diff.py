#!/usr/bin/env python3
"""Capture and semantically diff TITAN actions produced from an identical state.

The harness deliberately uses only the Python standard library so it can run in
minimal Kaggle/CI environments. Endpoint mode serializes a state exactly once
and reuses those bytes for every request, making state drift detectable rather
than an unexamined source of regression noise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

CAPTURE_FORMAT = "titan-returned-action-capture/v1"
REPORT_FORMAT = "titan-returned-action-diff/v1"
WRAPPER_KEYS = ("body", "result", "response", "payload", "data")
ENVELOPE_METADATA_KEYS = {
    "status",
    "statusCode",
    "status_code",
    "headers",
    "cookies",
    "isBase64Encoded",
    "ok",
    "message",
    "request_id",
    "requestId",
}
IDENTITY_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("market_id", "product_id", "delivery_time", "agent_id"),
    ("market", "product", "delivery", "agent"),
    ("market_id", "product_id", "delivery_time"),
    ("market", "product", "delivery"),
    ("market_id", "product_id"),
    ("market", "product"),
    ("agent_id", "market_id"),
    ("agent", "market"),
    ("order_id",),
    ("offer_id",),
    ("action_id",),
    ("id",),
    ("market_id",),
    ("market",),
    ("product_id",),
    ("product",),
    ("delivery_time",),
    ("delivery",),
    ("agent_id",),
    ("agent",),
    ("name",),
)
_MISSING = object()


class StateMismatchError(ValueError):
    """Raised when capture bundles prove they came from different states."""


class EndpointError(RuntimeError):
    """Raised when an endpoint cannot be queried successfully."""


@dataclass(frozen=True)
class Difference:
    path: str
    kind: str
    left: Any
    right: Any
    absolute_delta: float | int | None = None
    relative_delta: float | None = None


@dataclass(frozen=True)
class Operand:
    name: str
    action: Any
    source: str
    state_sha256: str | None = None
    request_sha256: str | None = None
    action_sha256: str | None = None
    unwrap_path: tuple[str, ...] = ()
    deterministic: bool | None = None
    unique_action_count: int | None = None
    sample_count: int | None = None


def canonical_json_bytes(value: Any) -> bytes:
    """Return a stable, UTF-8 JSON representation suitable for hashing/POSTing."""

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


def _decode_jsonish(value: Any, max_depth: int = 6) -> Any:
    """Decode nested JSON strings commonly returned by API Gateway wrappers."""

    current = value
    for _ in range(max_depth):
        if isinstance(current, (bytes, bytearray)):
            current = bytes(current).decode("utf-8-sig")
            continue
        if not isinstance(current, str):
            break
        stripped = current.strip()
        if not stripped or stripped[0] not in "{[\"":
            break
        try:
            decoded = json.loads(stripped)
        except json.JSONDecodeError:
            break
        if decoded == current:
            break
        current = decoded
    return current


def _looks_like_envelope(mapping: Mapping[str, Any], key: str, candidate: Any) -> bool:
    if len(mapping) == 1:
        return True
    if key == "body" and (set(mapping) & ENVELOPE_METADATA_KEYS):
        return True
    if set(mapping) - {key} <= ENVELOPE_METADATA_KEYS:
        return True
    if isinstance(candidate, Mapping):
        return "action" in candidate or any(wrapper in candidate for wrapper in WRAPPER_KEYS)
    return False


def unwrap_action(raw_response: Any, max_depth: int = 12) -> tuple[Any, tuple[str, ...]]:
    """Unwrap common response envelopes without assuming one action schema.

    The function only unwraps ``action`` when it contains a structured payload;
    this avoids mistaking a legitimate scalar field such as ``{"action":"SELL"}``
    for an endpoint envelope.
    """

    current = _decode_jsonish(raw_response)
    path: list[str] = []

    for _ in range(max_depth):
        if not isinstance(current, Mapping):
            break

        if "action" in current:
            candidate = _decode_jsonish(current["action"])
            if isinstance(candidate, (Mapping, list)) and (
                len(current) == 1
                or bool(set(current) & ENVELOPE_METADATA_KEYS)
                or any(key in current for key in WRAPPER_KEYS)
            ):
                current = candidate
                path.append("action")
                continue

        selected_key: str | None = None
        selected_value: Any = None
        for key in WRAPPER_KEYS:
            if key not in current:
                continue
            candidate = _decode_jsonish(current[key])
            if _looks_like_envelope(current, key, candidate):
                selected_key = key
                selected_value = candidate
                break

        if selected_key is None:
            break
        current = selected_value
        path.append(selected_key)

    return current, tuple(path)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _json_path_key(key: Any) -> str:
    text = str(key)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text):
        return f".{text}"
    return f"[{json.dumps(text, ensure_ascii=False)}]"


def _identity_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _identity_token(item: Mapping[str, Any], keys: Sequence[str]) -> str:
    return canonical_json_bytes([item[key] for key in keys]).decode("utf-8")


def _identity_keyset(left: Sequence[Any], right: Sequence[Any]) -> tuple[str, ...] | None:
    items = [*left, *right]
    if not items or not all(isinstance(item, Mapping) for item in items):
        return None

    for keys in IDENTITY_CANDIDATES:
        if not all(all(key in item and _identity_scalar(item[key]) for key in keys) for item in items):
            continue
        left_tokens = [_identity_token(item, keys) for item in left]
        right_tokens = [_identity_token(item, keys) for item in right]
        if len(set(left_tokens)) == len(left_tokens) and len(set(right_tokens)) == len(right_tokens):
            return keys
    return None


def _identity_path(keys: Sequence[str], item: Mapping[str, Any]) -> str:
    pieces = [f"{key}={json.dumps(item[key], ensure_ascii=False, sort_keys=True)}" for key in keys]
    return "[" + ",".join(pieces) + "]"


def _numeric_delta(left: int | float, right: int | float) -> tuple[float | int, float | None]:
    absolute = abs(right - left)
    denominator = max(abs(left), abs(right))
    relative = float(absolute / denominator) if denominator else 0.0
    return absolute, relative


def _numbers_close(left: int | float, right: int | float, abs_tol: float, rel_tol: float) -> bool:
    try:
        left_f = float(left)
        right_f = float(right)
    except (OverflowError, ValueError):
        return left == right
    if not (math.isfinite(left_f) and math.isfinite(right_f)):
        return left == right
    return math.isclose(left_f, right_f, abs_tol=abs_tol, rel_tol=rel_tol)


def semantic_diff(
    left: Any,
    right: Any,
    *,
    abs_tol: float = 0.0,
    rel_tol: float = 0.0,
    path: str = "$",
) -> list[Difference]:
    """Deep-diff two JSON values, aligning action lists by stable identities."""

    differences: list[Difference] = []

    def visit(left_value: Any, right_value: Any, current_path: str) -> None:
        if left_value is _MISSING:
            differences.append(Difference(current_path, "left_missing", None, right_value))
            return
        if right_value is _MISSING:
            differences.append(Difference(current_path, "right_missing", left_value, None))
            return

        if _is_number(left_value) and _is_number(right_value):
            if not _numbers_close(left_value, right_value, abs_tol, rel_tol):
                absolute, relative = _numeric_delta(left_value, right_value)
                differences.append(
                    Difference(
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
            differences.append(Difference(current_path, "type", left_value, right_value))
            return

        if isinstance(left_value, Mapping):
            left_keys = set(left_value)
            right_keys = set(right_value)
            for key in sorted(left_keys | right_keys, key=lambda item: str(item)):
                visit(
                    left_value.get(key, _MISSING),
                    right_value.get(key, _MISSING),
                    current_path + _json_path_key(key),
                )
            return

        if isinstance(left_value, list):
            identity_keys = _identity_keyset(left_value, right_value)
            if identity_keys:
                left_by_token = {_identity_token(item, identity_keys): item for item in left_value}
                right_by_token = {_identity_token(item, identity_keys): item for item in right_value}
                for token in sorted(set(left_by_token) | set(right_by_token)):
                    representative = left_by_token.get(token) or right_by_token[token]
                    item_path = current_path + _identity_path(identity_keys, representative)
                    visit(
                        left_by_token.get(token, _MISSING),
                        right_by_token.get(token, _MISSING),
                        item_path,
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
            differences.append(Difference(current_path, "value", left_value, right_value))

    visit(left, right, path)
    return differences


def _parse_headers(header_values: Iterable[str]) -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    for value in header_values:
        if ":" not in value:
            raise ValueError(f"header must use 'Name: value' syntax: {value!r}")
        name, header_value = value.split(":", 1)
        name = name.strip()
        if not name:
            raise ValueError(f"header name is empty: {value!r}")
        headers[name] = header_value.strip()
    return headers


def _validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"endpoint must be an absolute HTTP(S) URL: {url!r}")


def _redact_url(url: str) -> str:
    parsed = urlsplit(url)
    hostname = parsed.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"
    path = parsed.path or "/"
    redacted_query = "REDACTED" if parsed.query else ""
    return urlunsplit((parsed.scheme, hostname, path, redacted_query, ""))


def _parse_response_body(payload: bytes) -> Any:
    if not payload:
        return None
    text = payload.decode("utf-8-sig", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def post_exact_json(url: str, request_bytes: bytes, headers: Mapping[str, str], timeout: float) -> dict[str, Any]:
    """POST pre-serialized bytes and return a JSON-safe response record."""

    _validate_url(url)
    request = Request(url, data=request_bytes, headers=dict(headers), method="POST")
    started = time.monotonic()
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec B310: URL scheme is validated above.
            response_bytes = response.read()
            status = getattr(response, "status", response.getcode())
            content_type = response.headers.get("Content-Type")
    except HTTPError as exc:
        response_bytes = exc.read()
        excerpt = response_bytes.decode("utf-8", errors="replace")[:500]
        raise EndpointError(f"{_redact_url(url)} returned HTTP {exc.code}: {excerpt}") from exc
    except URLError as exc:
        raise EndpointError(f"request to {_redact_url(url)} failed: {exc.reason}") from exc

    elapsed_ms = round((time.monotonic() - started) * 1000.0, 3)
    return {
        "status": int(status),
        "content_type": content_type,
        "elapsed_ms": elapsed_ms,
        "body_sha256": sha256_bytes(response_bytes),
        "body": _parse_response_body(response_bytes),
    }


def _capture_sample(url: str, request_bytes: bytes, headers: Mapping[str, str], timeout: float) -> dict[str, Any]:
    response = post_exact_json(url, request_bytes, headers, timeout)
    action, unwrap_path = unwrap_action(response["body"])
    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "http": {
            "status": response["status"],
            "content_type": response["content_type"],
            "elapsed_ms": response["elapsed_ms"],
            "body_sha256": response["body_sha256"],
        },
        "raw_response": response["body"],
        "unwrap_path": list(unwrap_path),
        "action": action,
        "action_sha256": sha256_json(action),
    }


def _build_capture_bundle(
    *,
    name: str,
    url: str,
    state: Any,
    request_bytes: bytes,
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    fingerprints = [sample["action_sha256"] for sample in samples]
    baseline = samples[0]
    first_unstable_sample: int | None = None
    first_internal_difference: dict[str, Any] | None = None
    for index, sample in enumerate(samples[1:], start=1):
        if sample["action_sha256"] != baseline["action_sha256"]:
            first_unstable_sample = index
            internal = semantic_diff(baseline["action"], sample["action"])
            first_internal_difference = asdict(internal[0]) if internal else None
            break

    return {
        "format": CAPTURE_FORMAT,
        "name": name,
        "endpoint": _redact_url(url),
        "captured_at": baseline["captured_at"],
        "state_sha256": sha256_bytes(request_bytes),
        "request_sha256": sha256_bytes(request_bytes),
        "request_bytes_length": len(request_bytes),
        "state": state,
        "sample_count": len(samples),
        "unique_action_count": len(set(fingerprints)),
        "deterministic": len(set(fingerprints)) == 1,
        "first_unstable_sample": first_unstable_sample,
        "first_internal_difference": first_internal_difference,
        "samples": samples,
        "raw_response": baseline["raw_response"],
        "unwrap_path": baseline["unwrap_path"],
        "action": baseline["action"],
        "action_sha256": baseline["action_sha256"],
    }


def capture_pair(
    *,
    state: Any,
    left_url: str,
    right_url: str,
    left_name: str = "left",
    right_name: str = "right",
    headers: Mapping[str, str] | None = None,
    timeout: float = 30.0,
    repeat: int = 1,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Capture two endpoints using the exact same canonical request bytes.

    For repeat counts above one, request order alternates each round to reduce
    systematic left-first timing bias while preserving per-endpoint sample order.
    """

    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    _validate_url(left_url)
    _validate_url(right_url)

    request_bytes = canonical_json_bytes(state)
    common_headers = dict(headers or {"Accept": "application/json", "Content-Type": "application/json"})
    left_samples: list[dict[str, Any]] = []
    right_samples: list[dict[str, Any]] = []

    for round_index in range(repeat):
        order = (
            ((left_url, left_samples), (right_url, right_samples))
            if round_index % 2 == 0
            else ((right_url, right_samples), (left_url, left_samples))
        )
        for url, destination in order:
            destination.append(_capture_sample(url, request_bytes, common_headers, timeout))

    return (
        _build_capture_bundle(
            name=left_name,
            url=left_url,
            state=state,
            request_bytes=request_bytes,
            samples=left_samples,
        ),
        _build_capture_bundle(
            name=right_name,
            url=right_url,
            state=state,
            request_bytes=request_bytes,
            samples=right_samples,
        ),
    )


def _safe_optional_hash(value: Any) -> str | None:
    try:
        return sha256_json(value)
    except (TypeError, ValueError, OverflowError):
        return None


def operand_from_data(data: Any, *, name: str, source: str) -> Operand:
    if isinstance(data, Mapping) and data.get("format") == CAPTURE_FORMAT:
        samples = data.get("samples")
        action = data.get("action")
        unwrap_path = tuple(data.get("unwrap_path") or ())
        action_sha = data.get("action_sha256")
        if action is None and isinstance(samples, list) and samples:
            action = samples[0].get("action")
            unwrap_path = tuple(samples[0].get("unwrap_path") or ())
            action_sha = samples[0].get("action_sha256")
        return Operand(
            name=name,
            action=action,
            source=source,
            state_sha256=data.get("state_sha256"),
            request_sha256=data.get("request_sha256"),
            action_sha256=action_sha or _safe_optional_hash(action),
            unwrap_path=unwrap_path,
            deterministic=data.get("deterministic"),
            unique_action_count=data.get("unique_action_count"),
            sample_count=data.get("sample_count"),
        )

    action, unwrap_path = unwrap_action(data)
    state_hash = data.get("state_sha256") if isinstance(data, Mapping) else None
    request_hash = data.get("request_sha256") if isinstance(data, Mapping) else None
    return Operand(
        name=name,
        action=action,
        source=source,
        state_sha256=state_hash if isinstance(state_hash, str) else None,
        request_sha256=request_hash if isinstance(request_hash, str) else None,
        action_sha256=_safe_optional_hash(action),
        unwrap_path=unwrap_path,
    )


def load_operand(path: Path, *, name: str) -> Operand:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    return operand_from_data(data, name=name, source=str(path))


def validate_state_hashes(
    left: Operand,
    right: Operand,
    *,
    allow_state_mismatch: bool = False,
) -> dict[str, Any]:
    both_present = bool(left.state_sha256 and right.state_sha256)
    match = left.state_sha256 == right.state_sha256 if both_present else None
    result = {
        "left_state_sha256": left.state_sha256,
        "right_state_sha256": right.state_sha256,
        "both_present": both_present,
        "match": match,
        "proof": "verified" if match else ("mismatch" if match is False else "unavailable"),
    }
    if match is False and not allow_state_mismatch:
        raise StateMismatchError(
            "capture state hashes differ; refusing to attribute action differences to policy "
            f"({left.state_sha256} != {right.state_sha256})"
        )
    return result


def _top_path(path: str) -> str:
    if path == "$":
        return "$"
    match = re.match(r"^\$\.([A-Za-z_][A-Za-z0-9_]*)", path)
    if match:
        return f"$.{match.group(1)}"
    match = re.match(r'^\$\["((?:[^"\\]|\\.)*)"\]', path)
    if match:
        return '$["' + match.group(1) + '"]'
    match = re.match(r"^(\$\[[^\]]+\])", path)
    return match.group(1) if match else path


def build_report(
    left: Operand,
    right: Operand,
    *,
    abs_tol: float = 0.0,
    rel_tol: float = 0.0,
    allow_state_mismatch: bool = False,
) -> dict[str, Any]:
    state_validation = validate_state_hashes(left, right, allow_state_mismatch=allow_state_mismatch)
    differences = semantic_diff(left.action, right.action, abs_tol=abs_tol, rel_tol=rel_tol)
    by_kind = Counter(difference.kind for difference in differences)
    by_top_path = Counter(_top_path(difference.path) for difference in differences)

    return {
        "format": REPORT_FORMAT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "left": {
            "name": left.name,
            "source": left.source,
            "state_sha256": left.state_sha256,
            "request_sha256": left.request_sha256,
            "action_sha256": left.action_sha256,
            "unwrap_path": list(left.unwrap_path),
            "deterministic": left.deterministic,
            "unique_action_count": left.unique_action_count,
            "sample_count": left.sample_count,
        },
        "right": {
            "name": right.name,
            "source": right.source,
            "state_sha256": right.state_sha256,
            "request_sha256": right.request_sha256,
            "action_sha256": right.action_sha256,
            "unwrap_path": list(right.unwrap_path),
            "deterministic": right.deterministic,
            "unique_action_count": right.unique_action_count,
            "sample_count": right.sample_count,
        },
        "state_validation": state_validation,
        "tolerances": {"absolute": abs_tol, "relative": rel_tol},
        "summary": {
            "equal": not differences,
            "difference_count": len(differences),
            "first_difference": asdict(differences[0]) if differences else None,
            "by_kind": dict(sorted(by_kind.items())),
            "by_top_path": dict(sorted(by_top_path.items(), key=lambda item: (-item[1], item[0]))),
        },
        "differences": [asdict(difference) for difference in differences],
    }


def _short_json(value: Any, limit: int = 120) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(rendered) > limit:
        rendered = rendered[: limit - 1] + "…"
    return rendered.replace("|", "\\|").replace("\n", "\\n")


def render_markdown(report: Mapping[str, Any], *, max_differences: int = 100) -> str:
    left = report["left"]
    right = report["right"]
    state = report["state_validation"]
    summary = report["summary"]
    lines = [
        f"# Returned-action differential: {left['name']} vs {right['name']}",
        "",
        f"- State proof: **{state['proof']}**",
        f"- Left action SHA-256: `{left.get('action_sha256') or 'unavailable'}`",
        f"- Right action SHA-256: `{right.get('action_sha256') or 'unavailable'}`",
        f"- Semantic differences: **{summary['difference_count']}**",
    ]

    if left.get("request_sha256") and right.get("request_sha256"):
        request_match = left["request_sha256"] == right["request_sha256"]
        lines.append(f"- Exact request-byte proof: **{'verified' if request_match else 'mismatch'}**")
        lines.append(f"- Request SHA-256: `{left['request_sha256']}`")

    for label, side in (("Left", left), ("Right", right)):
        if side.get("sample_count") is not None:
            lines.append(
                f"- {label} repeat stability: **{'stable' if side.get('deterministic') else 'unstable'}** "
                f"({side.get('unique_action_count')} unique action(s) / {side.get('sample_count')} sample(s))"
            )

    lines.extend(["", "## First divergent field", ""])
    first = summary.get("first_difference")
    if first:
        lines.extend(
            [
                f"- Path: `{first['path']}`",
                f"- Kind: `{first['kind']}`",
                f"- Left: `{_short_json(first['left'])}`",
                f"- Right: `{_short_json(first['right'])}`",
            ]
        )
        if first.get("absolute_delta") is not None:
            lines.append(f"- Absolute delta: `{first['absolute_delta']}`")
            lines.append(f"- Relative delta: `{first['relative_delta']}`")
    else:
        lines.append("No semantic action difference was found at the configured tolerances.")

    if summary.get("by_top_path"):
        lines.extend(["", "## Difference concentration", "", "| Action path | Count |", "|---|---:|"])
        for path, count in summary["by_top_path"].items():
            lines.append(f"| `{path}` | {count} |")

    differences = report.get("differences", [])
    if differences:
        lines.extend(
            [
                "",
                "## Semantic differences",
                "",
                "| # | Path | Kind | Left | Right | Δ |",
                "|---:|---|---|---|---|---:|",
            ]
        )
        for index, difference in enumerate(differences[:max_differences], start=1):
            delta = difference.get("absolute_delta")
            lines.append(
                f"| {index} | `{difference['path']}` | `{difference['kind']}` | "
                f"`{_short_json(difference['left'])}` | `{_short_json(difference['right'])}` | "
                f"{'' if delta is None else f'`{delta}`'} |"
            )
        omitted = len(differences) - max_differences
        if omitted > 0:
            lines.extend(["", f"_Markdown truncated {omitted} additional difference(s); JSON output retains all._"])

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "A verified state/request hash removes input drift as an explanation. The first divergent "
            "path is therefore the earliest observable returned-action seam to trace through candidate "
            "construction, selector scoring, or response serialization. An unstable repeat result means "
            "endpoint nondeterminism must be resolved before cross-version attribution is trusted.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")
    return cleaned or "capture"


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture and semantically diff TITAN returned actions from an identical state."
    )
    parser.add_argument("--state", type=Path, help="JSON state to POST in endpoint mode")
    parser.add_argument("--left-url", help="left endpoint URL")
    parser.add_argument("--right-url", help="right endpoint URL")
    parser.add_argument("--left", type=Path, help="left raw response or capture bundle")
    parser.add_argument("--right", type=Path, help="right raw response or capture bundle")
    parser.add_argument("--left-name", default="left")
    parser.add_argument("--right-name", default="right")
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="NAME:VALUE",
        help="HTTP header shared by both endpoint requests; repeatable",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--repeat",
        type=_positive_int,
        default=1,
        help="same-state samples per endpoint; detects endpoint nondeterminism",
    )
    parser.add_argument("--capture-dir", type=Path, help="directory for endpoint capture bundles")
    parser.add_argument("--json-out", type=Path, help="write full machine-readable report")
    parser.add_argument("--md-out", type=Path, help="write Markdown report")
    parser.add_argument("--abs-tol", type=float, default=0.0)
    parser.add_argument("--rel-tol", type=float, default=0.0)
    parser.add_argument("--max-differences", type=_positive_int, default=100)
    parser.add_argument(
        "--allow-state-mismatch",
        action="store_true",
        help="compare mismatched capture states (report remains marked mismatch)",
    )
    parser.add_argument(
        "--fail-on-diff",
        action="store_true",
        help="return exit status 1 when semantic differences are present",
    )
    return parser


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _resolve_operands(args: argparse.Namespace, parser: argparse.ArgumentParser) -> tuple[Operand, Operand]:
    endpoint_mode = any((args.state, args.left_url, args.right_url))
    file_mode = any((args.left, args.right))
    if endpoint_mode and file_mode:
        parser.error("endpoint mode (--state/--left-url/--right-url) cannot be mixed with --left/--right")

    if endpoint_mode:
        if not (args.state and args.left_url and args.right_url):
            parser.error("endpoint mode requires --state, --left-url, and --right-url")
        state = _load_json(args.state)
        headers = _parse_headers(args.header)
        left_capture, right_capture = capture_pair(
            state=state,
            left_url=args.left_url,
            right_url=args.right_url,
            left_name=args.left_name,
            right_name=args.right_name,
            headers=headers,
            timeout=args.timeout,
            repeat=args.repeat,
        )
        if args.capture_dir:
            _write_json(args.capture_dir / f"{_safe_filename(args.left_name)}.capture.json", left_capture)
            _write_json(args.capture_dir / f"{_safe_filename(args.right_name)}.capture.json", right_capture)
        return (
            operand_from_data(left_capture, name=args.left_name, source=left_capture["endpoint"]),
            operand_from_data(right_capture, name=args.right_name, source=right_capture["endpoint"]),
        )

    if not (args.left and args.right):
        parser.error("file mode requires --left and --right, or use endpoint mode")
    if args.repeat != 1:
        parser.error("--repeat is only valid in endpoint mode")
    if args.header:
        parser.error("--header is only valid in endpoint mode")
    return (
        load_operand(args.left, name=args.left_name),
        load_operand(args.right, name=args.right_name),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.abs_tol < 0 or args.rel_tol < 0:
        parser.error("numeric tolerances must be non-negative")

    try:
        left, right = _resolve_operands(args, parser)
        report = build_report(
            left,
            right,
            abs_tol=args.abs_tol,
            rel_tol=args.rel_tol,
            allow_state_mismatch=args.allow_state_mismatch,
        )
    except (OSError, json.JSONDecodeError, ValueError, EndpointError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    markdown = render_markdown(report, max_differences=args.max_differences)
    if args.json_out:
        _write_json(args.json_out, report)
    if args.md_out:
        _write_text(args.md_out, markdown)
    if not args.md_out:
        print(markdown)
    return 1 if args.fail_on_diff and not report["summary"]["equal"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
