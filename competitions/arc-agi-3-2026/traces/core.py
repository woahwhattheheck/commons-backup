"""Deterministic custody and replay primitives for ARC-AGI-3 style traces.

The module is dependency-free and deliberately does not call ARC/Kaggle providers.
It records exact normalized frame bytes, action chronology, and evidence provenance.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA = "arc3-full-frame-trace/v1"
FRAME_ENCODING = "arc3-grid-u8/v1"
EVIDENCE_CLASSES = frozenset({"SYNTHETIC", "PUBLIC_SOURCE", "PROVIDER_DERIVED_UNVERIFIED"})
TERMINAL_STATES = frozenset({"WIN", "GAME_OVER"})
MAX_EVENTS = 20_001
MAX_ACTIONS = 10_000
MAX_TEXT = 16_384
MAX_SOURCE_REF = 512
MAX_JSON_DEPTH = 128
MAX_JSON_NODES = 1_000_000
ZERO_SHA256 = "0" * 64
_SECRET_PATTERNS = (
    re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+"),
    re.compile(r"(?i)(?:api[_-]?key|access[_-]?token|secret)\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp_|github_pat_|sk-)[A-Za-z0-9_\-]{12,}\b"),
)


class TraceError(ValueError):
    """Raised when trace material violates the replay contract."""


def _exact_int(value: Any, name: str, *, minimum: int = 0, maximum: int | None = None) -> int:
    if type(value) is not int:
        raise TraceError(f"{name} must be an exact int")
    if value < minimum or (maximum is not None and value > maximum):
        raise TraceError(f"{name} outside bounds")
    return value


def _text(value: Any, name: str, *, maximum: int = MAX_TEXT) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        raise TraceError(f"{name} must be a non-empty bounded string")
    if "\x00" in value:
        raise TraceError(f"{name} contains NUL")
    return value


def _sha(value: Any, name: str) -> str:
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise TraceError(f"{name} must be lowercase sha256 hex")
    return value


def _canonical_value(value: Any, path: str = "$", *, max_depth: int = MAX_JSON_DEPTH) -> None:
    """Reject alias-prone, cyclic, or excessively nested values iteratively."""
    stack: list[tuple[Any, str, int, bool]] = [(value, path, 0, False)]
    active_containers: set[int] = set()
    nodes = 0
    while stack:
        current, current_path, depth, exiting = stack.pop()
        if exiting:
            active_containers.discard(id(current))
            continue
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise TraceError("canonical JSON node bound exceeded")
        if depth > max_depth:
            raise TraceError("canonical JSON depth bound exceeded")
        if current is None or type(current) in (str, bool):
            continue
        if type(current) is int:
            if abs(current) > 9_007_199_254_740_991:
                raise TraceError(f"{current_path} integer outside interoperable bound")
            continue
        if type(current) is list:
            container_id = id(current)
            if container_id in active_containers:
                raise TraceError(f"{current_path} contains a cyclic list")
            active_containers.add(container_id)
            stack.append((current, current_path, depth, True))
            for idx in range(len(current) - 1, -1, -1):
                stack.append((current[idx], f"{current_path}[{idx}]", depth + 1, False))
            continue
        if type(current) is dict:
            container_id = id(current)
            if container_id in active_containers:
                raise TraceError(f"{current_path} contains a cyclic object")
            active_containers.add(container_id)
            stack.append((current, current_path, depth, True))
            items = list(current.items())
            for key, item in reversed(items):
                if type(key) is not str:
                    raise TraceError(f"{current_path} has non-string key")
                stack.append((item, f"{current_path}.{key}", depth + 1, False))
            continue
        raise TraceError(f"{current_path} contains unsupported value type {type(current).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    _canonical_value(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError) as exc:
        raise TraceError("value is not canonical-json serializable") from exc


def _parse_int(raw: str) -> int:
    digits = raw[1:] if raw.startswith("-") else raw
    if len(digits) > 16:
        raise TraceError("JSON integer outside interoperable bound")
    try:
        return int(raw)
    except ValueError as exc:
        raise TraceError("invalid JSON integer") from exc


def _no_float(_: str) -> Any:
    raise TraceError("JSON floats are forbidden")


def _no_constant(_: str) -> Any:
    raise TraceError("non-finite JSON constants are forbidden")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise TraceError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def strict_json_loads(data: bytes | str, *, require_canonical: bool = False) -> Any:
    if isinstance(data, bytes):
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise TraceError("manifest is not strict UTF-8") from exc
        original = data
    elif type(data) is str:
        text = data
        try:
            original = data.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise TraceError("manifest string is not strict UTF-8") from exc
    else:
        raise TraceError("JSON input must be bytes or str")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_int=_parse_int,
            parse_float=_no_float,
            parse_constant=_no_constant,
        )
    except TraceError:
        raise
    except (json.JSONDecodeError, UnicodeEncodeError, ValueError, RecursionError) as exc:
        raise TraceError("invalid JSON") from exc
    _canonical_value(value)
    if require_canonical and canonical_json_bytes(value) != original:
        raise TraceError("manifest bytes are not canonical JSON")
    return value


def scan_secret_text(value: str) -> None:
    if len(value) > MAX_TEXT:
        raise TraceError("text exceeds secret-scan bound")
    for pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            raise TraceError("secret-like material rejected")


def scan_secret_tree(value: Any) -> None:
    if type(value) is str:
        scan_secret_text(value)
    elif type(value) is list:
        for item in value:
            scan_secret_tree(item)
    elif type(value) is dict:
        for key, item in value.items():
            scan_secret_text(key)
            scan_secret_tree(item)


def validate_grid(grid: Any) -> tuple[tuple[int, ...], ...]:
    if not isinstance(grid, Sequence) or isinstance(grid, (str, bytes, bytearray)) or not grid:
        raise TraceError("grid must be a non-empty row sequence")
    if len(grid) > 64:
        raise TraceError("grid height exceeds 64")
    out: list[tuple[int, ...]] = []
    width: int | None = None
    for row in grid:
        if not isinstance(row, Sequence) or isinstance(row, (str, bytes, bytearray)) or not row:
            raise TraceError("grid row must be a non-empty sequence")
        if len(row) > 64:
            raise TraceError("grid width exceeds 64")
        vals: list[int] = []
        for value in row:
            if type(value) is not int or not 0 <= value <= 15:
                raise TraceError("grid cells must be exact ints in [0,15]")
            vals.append(value)
        if width is None:
            width = len(vals)
        elif len(vals) != width:
            raise TraceError("grid must be rectangular")
        out.append(tuple(vals))
    return tuple(out)


def encode_frame(grid: Any) -> bytes:
    checked = validate_grid(grid)
    height, width = len(checked), len(checked[0])
    return b"ARC3GRID\x00\x01" + bytes((height, width)) + bytes(v for row in checked for v in row)


def decode_frame(data: bytes) -> tuple[tuple[int, ...], ...]:
    if not isinstance(data, bytes) or len(data) < 12 or not data.startswith(b"ARC3GRID\x00\x01"):
        raise TraceError("invalid frame encoding")
    height, width = data[10], data[11]
    if not 1 <= height <= 64 or not 1 <= width <= 64:
        raise TraceError("encoded frame dimensions outside bounds")
    body = data[12:]
    if len(body) != height * width or any(v > 15 for v in body):
        raise TraceError("encoded frame payload is invalid")
    return tuple(tuple(body[y * width : (y + 1) * width]) for y in range(height))


def frame_record(grid: Any) -> dict[str, Any]:
    raw = encode_frame(grid)
    checked = decode_frame(raw)
    return {
        "encoding": FRAME_ENCODING,
        "height": len(checked),
        "width": len(checked[0]),
        "payload_b64": base64.b64encode(raw).decode("ascii"),
        "sha256": sha256(raw).hexdigest(),
    }


def decode_frame_record(record: Mapping[str, Any]) -> tuple[tuple[int, ...], ...]:
    if type(record) is not dict or set(record) != {"encoding", "height", "width", "payload_b64", "sha256"}:
        raise TraceError("frame record keys mismatch")
    if record["encoding"] != FRAME_ENCODING:
        raise TraceError("unsupported frame encoding")
    height = _exact_int(record["height"], "frame height", minimum=1, maximum=64)
    width = _exact_int(record["width"], "frame width", minimum=1, maximum=64)
    payload = _text(record["payload_b64"], "frame payload", maximum=8_192)
    digest = _sha(record["sha256"], "frame sha256")
    try:
        raw = base64.b64decode(payload, validate=True)
    except Exception as exc:
        raise TraceError("frame payload is not strict base64") from exc
    if sha256(raw).hexdigest() != digest:
        raise TraceError("frame sha256 mismatch")
    grid = decode_frame(raw)
    if len(grid) != height or len(grid[0]) != width:
        raise TraceError("frame dimension metadata mismatch")
    return grid


def _action_record(name: Any, x: Any = None, y: Any = None) -> dict[str, Any]:
    name = _text(name, "action name", maximum=64)
    if not name.startswith("ACTION"):
        raise TraceError("action name must use ACTION* form")
    if (x is None) != (y is None):
        raise TraceError("x and y must be supplied together")
    if x is not None:
        x = _exact_int(x, "action x", maximum=63)
        y = _exact_int(y, "action y", maximum=63)
    return {"name": name, "x": x, "y": y}


def _observation_payload(
    frames: Any,
    available_actions: Any,
    *,
    state: Any,
    levels_completed: Any,
    win_levels: Any,
    evidence_class: Any,
    source_ref: Any,
) -> dict[str, Any]:
    if not isinstance(frames, Sequence) or isinstance(frames, (str, bytes, bytearray)) or not frames:
        raise TraceError("observation frames must be non-empty")
    if len(frames) > 256:
        raise TraceError("too many animation frames")
    encoded = [frame_record(frame) for frame in frames]
    if not isinstance(available_actions, Sequence) or isinstance(available_actions, (str, bytes)):
        raise TraceError("available actions must be a sequence")
    actions = [_action_record(name)["name"] for name in available_actions]
    if len(actions) != len(set(actions)):
        raise TraceError("available actions must be unique")
    evidence_class = _text(evidence_class, "evidence class", maximum=64)
    if evidence_class not in EVIDENCE_CLASSES:
        raise TraceError("unknown evidence class")
    source_ref = _text(source_ref, "source ref", maximum=MAX_SOURCE_REF)
    scan_secret_text(source_ref)
    state = _text(state, "state", maximum=64)
    return {
        "frames": encoded,
        "available_actions": actions,
        "state": state,
        "levels_completed": _exact_int(levels_completed, "levels completed"),
        "win_levels": _exact_int(win_levels, "win levels"),
        "evidence_class": evidence_class,
        "source_ref": source_ref,
    }


def _event(seq: int, kind: str, payload: dict[str, Any], prev_sha256: str) -> dict[str, Any]:
    core = {
        "seq": _exact_int(seq, "event seq", maximum=MAX_EVENTS - 1),
        "kind": kind,
        "payload": payload,
        "prev_event_sha256": _sha(prev_sha256, "previous event sha256"),
    }
    digest = sha256(canonical_json_bytes(core)).hexdigest()
    return {**core, "event_sha256": digest}


@dataclass
class EpisodeRecorder:
    episode_id: str
    max_actions: int
    events: list[dict[str, Any]]
    _actions: int = 0

    def __init__(self, episode_id: str, *, max_actions: int = 80) -> None:
        self.episode_id = _text(episode_id, "episode id", maximum=128)
        scan_secret_text(self.episode_id)
        self.max_actions = _exact_int(max_actions, "max actions", minimum=1, maximum=MAX_ACTIONS)
        self.events = []
        self._actions = 0

    def _append(self, kind: str, payload: dict[str, Any]) -> None:
        if len(self.events) >= MAX_EVENTS:
            raise TraceError("episode exceeds event bound")
        prev = self.events[-1]["event_sha256"] if self.events else ZERO_SHA256
        self.events.append(_event(len(self.events), kind, payload, prev))

    def append_observation(
        self,
        frames: Any,
        available_actions: Any,
        *,
        state: str = "NOT_FINISHED",
        levels_completed: int = 0,
        win_levels: int = 0,
        evidence_class: str = "SYNTHETIC",
        source_ref: str = "synthetic:unspecified",
    ) -> None:
        if self.events and self.events[-1]["kind"] != "ACTION":
            raise TraceError("observations must alternate with actions")
        payload = _observation_payload(
            frames,
            available_actions,
            state=state,
            levels_completed=levels_completed,
            win_levels=win_levels,
            evidence_class=evidence_class,
            source_ref=source_ref,
        )
        if self.events:
            prior_obs = self.events[-2]["payload"]
            if payload["levels_completed"] < prior_obs["levels_completed"]:
                raise TraceError("levels_completed cannot decrease")
            if payload["win_levels"] < prior_obs["win_levels"]:
                raise TraceError("win_levels cannot decrease")
        self._append("OBSERVATION", payload)

    def append_action(self, name: str, *, x: int | None = None, y: int | None = None, actions_left_before: int | None = None) -> None:
        if not self.events or self.events[-1]["kind"] != "OBSERVATION":
            raise TraceError("action requires a preceding observation")
        if self.events[-1]["payload"]["state"] in TERMINAL_STATES:
            raise TraceError("cannot act after terminal observation")
        if self._actions >= self.max_actions:
            raise TraceError("action budget exhausted")
        action = _action_record(name, x, y)
        available = self.events[-1]["payload"]["available_actions"]
        if action["name"] not in available:
            raise TraceError("action was not available in preceding observation")
        expected_left = self.max_actions - self._actions
        if actions_left_before is None:
            actions_left_before = expected_left
        actions_left_before = _exact_int(actions_left_before, "actions left before", minimum=1, maximum=self.max_actions)
        if actions_left_before != expected_left:
            raise TraceError("action budget accounting drift")
        self._append(
            "ACTION",
            {
                "action": action,
                "actions_left_before": actions_left_before,
                "action_index": self._actions,
            },
        )
        self._actions += 1

    def compile(self) -> dict[str, Any]:
        if not self.events or self.events[0]["kind"] != "OBSERVATION":
            raise TraceError("episode must start with an observation")
        if self.events[-1]["kind"] != "OBSERVATION":
            raise TraceError("episode must end with an observation")
        evidence = sorted({event["payload"]["evidence_class"] for event in self.events if event["kind"] == "OBSERVATION"})
        manifest_core = {
            "schema": SCHEMA,
            "episode_id": self.episode_id,
            "max_actions": self.max_actions,
            "action_count": self._actions,
            "event_count": len(self.events),
            "event_chain_sha256": self.events[-1]["event_sha256"],
            "evidence_classes": evidence,
            "events": self.events,
            "authority": {
                "official_trace_claimed": False,
                "provider_capture_verified": False,
                "submission_authorized": False,
                "score_or_prize_claimed": False,
            },
        }
        scan_secret_tree(manifest_core)
        manifest_sha = sha256(canonical_json_bytes(manifest_core)).hexdigest()
        return {**manifest_core, "manifest_sha256": manifest_sha}


def _validate_event(event: Any, index: int, previous: str, *, max_actions: int, action_count: int) -> tuple[str, int]:
    if type(event) is not dict or set(event) != {"seq", "kind", "payload", "prev_event_sha256", "event_sha256"}:
        raise TraceError("event keys mismatch")
    if _exact_int(event["seq"], "event seq") != index:
        raise TraceError("event sequence drift")
    if event["prev_event_sha256"] != previous:
        raise TraceError("event chain predecessor mismatch")
    kind = event["kind"]
    if kind not in {"OBSERVATION", "ACTION"}:
        raise TraceError("unknown event kind")
    if (index % 2 == 0) != (kind == "OBSERVATION"):
        raise TraceError("event kinds must alternate OBSERVATION/ACTION")
    payload = event["payload"]
    if type(payload) is not dict:
        raise TraceError("event payload must be object")
    if kind == "OBSERVATION":
        required = {"frames", "available_actions", "state", "levels_completed", "win_levels", "evidence_class", "source_ref"}
        if set(payload) != required:
            raise TraceError("observation payload keys mismatch")
        rebuilt = _observation_payload(
            [decode_frame_record(fr) for fr in payload["frames"]],
            payload["available_actions"],
            state=payload["state"],
            levels_completed=payload["levels_completed"],
            win_levels=payload["win_levels"],
            evidence_class=payload["evidence_class"],
            source_ref=payload["source_ref"],
        )
        if canonical_json_bytes(rebuilt) != canonical_json_bytes(payload):
            raise TraceError("observation payload failed semantic recompile")
    else:
        if set(payload) != {"action", "actions_left_before", "action_index"}:
            raise TraceError("action payload keys mismatch")
        action = payload["action"]
        rebuilt_action = _action_record(action.get("name") if type(action) is dict else None, action.get("x") if type(action) is dict else None, action.get("y") if type(action) is dict else None)
        if canonical_json_bytes(rebuilt_action) != canonical_json_bytes(action):
            raise TraceError("action payload failed semantic recompile")
        idx = _exact_int(payload["action_index"], "action index", maximum=MAX_ACTIONS - 1)
        if idx != action_count:
            raise TraceError("action index drift")
        expected_left = max_actions - idx
        if _exact_int(payload["actions_left_before"], "actions left before", minimum=1, maximum=max_actions) != expected_left:
            raise TraceError("action budget accounting drift")
        action_count += 1
    core = {k: event[k] for k in ("seq", "kind", "payload", "prev_event_sha256")}
    expected_sha = sha256(canonical_json_bytes(core)).hexdigest()
    if _sha(event["event_sha256"], "event sha256") != expected_sha:
        raise TraceError("event sha256 mismatch")
    return expected_sha, action_count


def verify_manifest(manifest: Any) -> dict[str, Any]:
    if type(manifest) is not dict:
        raise TraceError("manifest must be an object")
    required = {
        "schema", "episode_id", "max_actions", "action_count", "event_count",
        "event_chain_sha256", "evidence_classes", "events", "authority", "manifest_sha256",
    }
    if set(manifest) != required:
        raise TraceError("manifest keys mismatch")
    if manifest["schema"] != SCHEMA:
        raise TraceError("unsupported trace schema")
    episode_id = _text(manifest["episode_id"], "episode id", maximum=128)
    scan_secret_text(episode_id)
    max_actions = _exact_int(manifest["max_actions"], "max actions", minimum=1, maximum=MAX_ACTIONS)
    action_count_claim = _exact_int(manifest["action_count"], "action count", maximum=max_actions)
    event_count = _exact_int(manifest["event_count"], "event count", minimum=1, maximum=MAX_EVENTS)
    events = manifest["events"]
    if type(events) is not list or len(events) != event_count or event_count % 2 != 1:
        raise TraceError("event count mismatch")
    previous = ZERO_SHA256
    action_count = 0
    for index, event in enumerate(events):
        previous, action_count = _validate_event(event, index, previous, max_actions=max_actions, action_count=action_count)
        if index >= 2 and event["kind"] == "OBSERVATION":
            prior_obs = events[index - 2]["payload"]
            if event["payload"]["levels_completed"] < prior_obs["levels_completed"] or event["payload"]["win_levels"] < prior_obs["win_levels"]:
                raise TraceError("progress counters cannot decrease")
        if event["kind"] == "ACTION":
            prior_obs = events[index - 1]["payload"]
            action = event["payload"]["action"]
            if prior_obs["state"] in TERMINAL_STATES:
                raise TraceError("action follows terminal observation")
            if action["name"] not in prior_obs["available_actions"]:
                raise TraceError("action unavailable in preceding observation")
    if events[0]["kind"] != "OBSERVATION" or events[-1]["kind"] != "OBSERVATION":
        raise TraceError("manifest boundaries must be observations")
    if action_count != action_count_claim:
        raise TraceError("action count mismatch")
    if _sha(manifest["event_chain_sha256"], "event chain sha256") != previous:
        raise TraceError("event chain terminal mismatch")
    evidence = sorted({event["payload"]["evidence_class"] for event in events if event["kind"] == "OBSERVATION"})
    if type(manifest["evidence_classes"]) is not list or manifest["evidence_classes"] != evidence:
        raise TraceError("evidence class summary mismatch")
    authority = manifest["authority"]
    expected_authority = {
        "official_trace_claimed": False,
        "provider_capture_verified": False,
        "submission_authorized": False,
        "score_or_prize_claimed": False,
    }
    if type(authority) is not dict or authority != expected_authority or canonical_json_bytes(authority) != canonical_json_bytes(expected_authority):
        raise TraceError("authority ceiling mismatch")
    core = {k: manifest[k] for k in required if k != "manifest_sha256"}
    expected_manifest_sha = sha256(canonical_json_bytes(core)).hexdigest()
    if _sha(manifest["manifest_sha256"], "manifest sha256") != expected_manifest_sha:
        raise TraceError("manifest sha256 mismatch")
    scan_secret_tree(core)
    return {
        "status": "VERIFIED_OFFLINE_TRACE",
        "episode_id": episode_id,
        "event_count": event_count,
        "action_count": action_count,
        "manifest_sha256": expected_manifest_sha,
        "provider_capture_verified": False,
        "submission_authorized": False,
    }


def verify_manifest_bytes(data: bytes | str) -> dict[str, Any]:
    manifest = strict_json_loads(data, require_canonical=True)
    return verify_manifest(manifest)


def load_manifest(path: str | Path) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    value = strict_json_loads(raw, require_canonical=True)
    verify_manifest(value)
    return value


def write_manifest(path: str | Path, manifest: Mapping[str, Any]) -> None:
    verify_manifest(dict(manifest))
    target = Path(path)
    target.write_bytes(canonical_json_bytes(dict(manifest)))
