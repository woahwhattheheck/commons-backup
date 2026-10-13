"""Provider-neutral, zero-network agent-event -> Slack transcript projector.

This module is intentionally offline.  It creates deterministic transcript *artifacts*;
it never calls Slack, Hyperagent, Gmail, or any other provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

SCHEMA = "tjlabs.hyperagent_slack_transcript/v1"
STATE_SCHEMA = "tjlabs.hyperagent_slack_transcript_state/v1"
MAX_JSON_NESTING_DEPTH = 128
ALLOWED_BACKENDS = frozenset({"stream", "trace", "envelope"})
ALLOWED_KINDS = frozenset({"TEXT", "MUTATING_ACTION"})
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class ValidationError(ValueError):
    """Input is malformed or outside the strict contract."""


class ConflictError(ValidationError):
    """An immutable source identity was replayed with changed semantics."""


class ApprovalError(ValidationError):
    """Approval evidence is malformed.  Missing/stale/foreign approvals hold silently."""


def _reject_constant(value: str) -> None:
    raise ValidationError(f"non-finite JSON number is forbidden: {value}")


def _pairs_no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValidationError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _check_json_depth(text: str) -> None:
    """Bound object/array nesting before decoding, ignoring quoted content."""
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_NESTING_DEPTH:
                raise ValidationError(
                    f"JSON nesting exceeds maximum depth {MAX_JSON_NESTING_DEPTH}"
                )
        elif character in "]}":
            # Syntax, including unmatched delimiters, remains the decoder's job.
            depth = max(0, depth - 1)


def load_strict_json(data: bytes | str) -> Any:
    """Parse strict UTF-8 JSON with at most 128 nested objects/arrays."""
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise ValidationError("input is not strict UTF-8") from exc
    elif type(data) is str:
        text = data
    else:
        raise ValidationError("JSON input must be bytes or str")
    _check_json_depth(text)
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_dupes,
            parse_constant=_reject_constant,
        )
    except ValidationError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError, RecursionError) as exc:
        raise ValidationError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (UnicodeEncodeError, TypeError, ValueError, RecursionError) as exc:
        raise ValidationError("value is not canonicalizable strict UTF-8 JSON") from exc


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _stable_id(prefix: str, *parts: str) -> str:
    material = "\x1f".join((prefix, *parts)).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(material).hexdigest()[:24]}"


def _plain_dict(value: Any, field: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValidationError(f"{field} must be an object")
    return value


def _exact_keys(obj: Mapping[str, Any], expected: set[str], field: str) -> None:
    got = set(obj)
    if got != expected:
        missing = sorted(expected - got)
        extra = sorted(got - expected)
        raise ValidationError(f"{field} keys mismatch missing={missing} extra={extra}")


def _text(value: Any, field: str, *, max_len: int = 4000) -> str:
    if type(value) is not str or not value or len(value) > max_len:
        raise ValidationError(f"{field} must be non-empty str <= {max_len}")
    try:
        value.encode("utf-8", "strict")
    except UnicodeEncodeError as exc:
        raise ValidationError(f"{field} contains non-scalar Unicode") from exc
    return value


def _opaque_id(value: Any, field: str) -> str:
    text = _text(value, field, max_len=128)
    if not ID_RE.fullmatch(text):
        raise ValidationError(f"{field} is not a safe opaque id")
    return text


def _int(value: Any, field: str, *, minimum: int = 0, maximum: int = 1_000_000) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValidationError(f"{field} must be int in [{minimum}, {maximum}]")
    return value


def _utc(value: Any, field: str) -> datetime:
    text = _text(value, field, max_len=32)
    if not text.endswith("Z") or "." in text:
        raise ValidationError(f"{field} must be whole-second UTC ending Z")
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValidationError(f"{field} must be canonical UTC") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise ValidationError(f"{field} is not canonical UTC")
    return parsed


def _sha256(value: Any, field: str) -> str:
    text = _text(value, field, max_len=64)
    if not SHA_RE.fullmatch(text):
        raise ValidationError(f"{field} must be lowercase sha256")
    return text


@dataclass(frozen=True)
class NormalizedEvent:
    backend: str
    source_event_id: str
    source_run_id: str
    sequence: int
    thread_ref: str
    kind: str
    text: str
    action_id: str | None = None
    generation: int | None = None

    @property
    def source_key(self) -> str:
        # Backend-local event IDs may repeat across runs. Bind immutable source
        # identity to backend + run + event with length-safe stable hashing.
        return _stable_id("source", self.backend, self.source_run_id, self.source_event_id)

    @property
    def run_id(self) -> str:
        return _stable_id("run", self.backend, self.source_run_id)

    @property
    def thread_id(self) -> str:
        return _stable_id("thread", self.run_id, self.thread_ref)

    @property
    def event_id(self) -> str:
        return _stable_id("event", self.source_key)

    def semantics(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "source_event_id": self.source_event_id,
            "source_run_id": self.source_run_id,
            "sequence": self.sequence,
            "thread_ref": self.thread_ref,
            "kind": self.kind,
            "text": self.text,
            "action_id": self.action_id,
            "generation": self.generation,
        }


def _normalize_common(
    backend: str,
    *,
    source_event_id: Any,
    source_run_id: Any,
    sequence: Any,
    thread_ref: Any,
    kind: Any,
    text: Any,
    action_id: Any,
    generation: Any,
) -> NormalizedEvent:
    if backend not in ALLOWED_BACKENDS:
        raise ValidationError("unsupported backend")
    event_kind = _text(kind, "kind", max_len=32)
    if event_kind not in ALLOWED_KINDS:
        raise ValidationError("unsupported event kind")
    action: str | None
    gen: int | None
    if event_kind == "TEXT":
        if action_id is not None or generation is not None:
            raise ValidationError("TEXT cannot carry action approval fields")
        action = None
        gen = None
    else:
        action = _opaque_id(action_id, "action_id")
        gen = _int(generation, "generation", minimum=1, maximum=1_000_000)
    return NormalizedEvent(
        backend=backend,
        source_event_id=_opaque_id(source_event_id, "source_event_id"),
        source_run_id=_opaque_id(source_run_id, "source_run_id"),
        sequence=_int(sequence, "sequence"),
        thread_ref=_opaque_id(thread_ref, "thread_ref"),
        kind=event_kind,
        text=_text(text, "text"),
        action_id=action,
        generation=gen,
    )


def normalize_event(raw: Any) -> NormalizedEvent:
    obj = _plain_dict(raw, "event")
    backend = _text(obj.get("backend"), "backend", max_len=16)
    if backend == "stream":
        _exact_keys(obj, {"backend", "run_id", "event_id", "seq", "kind", "payload"}, "stream event")
        payload = _plain_dict(obj["payload"], "payload")
        _exact_keys(payload, {"thread", "text", "action_id", "generation"}, "stream payload")
        return _normalize_common(
            backend,
            source_event_id=obj["event_id"],
            source_run_id=obj["run_id"],
            sequence=obj["seq"],
            thread_ref=payload["thread"],
            kind=obj["kind"],
            text=payload["text"],
            action_id=payload["action_id"],
            generation=payload["generation"],
        )
    if backend == "trace":
        _exact_keys(obj, {"backend", "trace", "id", "index", "type", "data"}, "trace event")
        data = _plain_dict(obj["data"], "data")
        _exact_keys(data, {"conversation", "message", "action", "generation"}, "trace data")
        return _normalize_common(
            backend,
            source_event_id=obj["id"],
            source_run_id=obj["trace"],
            sequence=obj["index"],
            thread_ref=data["conversation"],
            kind=obj["type"],
            text=data["message"],
            action_id=data["action"],
            generation=data["generation"],
        )
    if backend == "envelope":
        _exact_keys(obj, {"backend", "session", "uid", "ordinal", "event", "body"}, "envelope event")
        body = _plain_dict(obj["body"], "body")
        _exact_keys(body, {"thread_ref", "content", "action_ref", "action_generation"}, "envelope body")
        return _normalize_common(
            backend,
            source_event_id=obj["uid"],
            source_run_id=obj["session"],
            sequence=obj["ordinal"],
            thread_ref=body["thread_ref"],
            kind=obj["event"],
            text=body["content"],
            action_id=body["action_ref"],
            generation=body["action_generation"],
        )
    raise ValidationError(f"unsupported backend: {backend}")
