#!/usr/bin/env python3
"""Commons Model Language (CML/1) envelope primitives.

CML separates three things which must not be confused:

* a model's private computation, declared only as ``LATENT``;
* a compact, typed semantic packet for another model; and
* a one-line ``speech`` projection for a human.

The post body is a payload, not scratch space for the envelope.  Every helper in
this module treats it as opaque.  In particular, the record helpers return the
same body object they were given and only derive a SHA-256 digest from its exact
UTF-8 bytes (or from exact bytes for binary payloads).

Emitter helpers are deliberately strict and may raise ``ModelLanguageError``.
Observer helpers are deliberately fail-open: old, partial, and malformed posts
remain observable and are labelled ``UNLAYERED`` or ``INVALID`` rather than
being rejected.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any, TypeAlias


CML_PROTOCOL = "CML/1"
MODEL_CODEC = "json"
REASONING_MODE = "LATENT"

LANGUAGE_STATES = frozenset({"LAYERED", "UNLAYERED", "INVALID"})
PACKET_KINDS = frozenset({"STATE", "DELTA", "QUERY", "RESULT", "HANDOFF", "ERROR"})
MODEL_CODECS = frozenset({"json", "tok", "math", "code", "mixed", "opaque"})
PAYLOAD_KINDS = frozenset({"prose", "code", "patch", "data", "action", "artifact"})

# Semantic operations are intentionally small.  Their arguments are public
# state/results/obligations, never a transcript of how a model deliberated.
OP_CODES = frozenset({
    "B",   # bind a name/value
    "A",   # assumption
    "I",   # inference/result relation
    "Q",   # open question or requested datum
    "W",   # evidence/witness reference
    "T",   # test and observed result
    "CE",  # contradiction/counterexample
    "X",   # retract a prior claim
    "V",   # revise a prior claim
    "K",   # commit a conclusion or deliverable
    "AT",  # attention target
    "BK",  # backtrack/restore a branch
})

MAX_PACKET_BYTES = 16_384
MAX_OPS = 64
MAX_TOPIC_CHARS = 256
MAX_ATOM_CHARS = 2_048
MAX_SPEECH_CHARS = 2_048
MAX_PACKET_LIST_ITEMS = 32

Body: TypeAlias = str | bytes

_CORE_DECLARATION_FIELDS = frozenset({
    "reasoning_mode", "model_protocol", "model_codec", "model_packet"
})
_REQUIRED_ENVELOPE_FIELDS = frozenset({
    "reasoning_mode",
    "speech",
    "model_protocol",
    "model_codec",
    "model_packet",
    "payload_kind",
    "payload_sha256",
})
_PRIVATE_TOPIC_RE = re.compile(
    r"(?:^|_)(?:analysis|chain_of_thought|cot|deliberation|hidden_reasoning|"
    r"private_reasoning|rationale|scratchpad|thought|thoughts)(?:_|$)"
)
_PLAIN_RE = re.compile(r"^[ \t]*(PLAIN ENGLISH|PLAIN):[ \t]*(.*)$", re.IGNORECASE)
_MODEL_RE = re.compile(r"^[ \t]*MODEL:[ \t]*(.*)$", re.IGNORECASE)
_LINE_BREAK_RE = re.compile(r"[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")


class ModelLanguageError(ValueError):
    """A CML/1 emitter attempted to construct an invalid envelope."""


def _body_bytes(body: Body) -> bytes:
    if isinstance(body, str):
        return body.encode("utf-8")
    if isinstance(body, bytes):
        return body
    raise ModelLanguageError("payload body must be str or bytes")


def payload_sha256(body: Body) -> str:
    """Hash an already-canonical payload without normalizing or rewriting it."""

    return hashlib.sha256(_body_bytes(body)).hexdigest()


def _reject_json_constant(value: str) -> None:
    raise ModelLanguageError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ModelLanguageError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def _strict_json_loads(source: str) -> Any:
    try:
        return json.loads(
            source,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except ModelLanguageError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ModelLanguageError(f"model_packet is not valid JSON: {exc}") from exc


def _single_line(value: str) -> bool:
    # Match Python/Unicode splitlines(), not only CR/LF.  Every one of these
    # characters can create a new frontmatter line in a later parser.
    return _LINE_BREAK_RE.search(value) is None


def _validate_packet_object(packet: Any) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise ModelLanguageError("model_packet must decode to an object")
    keys = set(packet)
    required = {"v", "k", "ops"}
    allowed = required | {"g", "open", "refs", "conf"}
    if not required <= keys or not keys <= allowed:
        missing = sorted(required - keys)
        extra = sorted(str(item) for item in keys - allowed)
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("unexpected " + ", ".join(extra))
        raise ModelLanguageError("model_packet fields: " + "; ".join(detail))

    if type(packet["v"]) is not int or packet["v"] != 1:
        raise ModelLanguageError("model_packet.v must be integer 1")
    if not isinstance(packet["k"], str) or packet["k"] not in PACKET_KINDS:
        raise ModelLanguageError(
            "model_packet.k must be one of " + ", ".join(sorted(PACKET_KINDS))
        )
    operations = packet["ops"]
    if not isinstance(operations, list):
        raise ModelLanguageError("model_packet.ops must be an array")
    if len(operations) > MAX_OPS:
        raise ModelLanguageError(f"model_packet.ops must contain at most {MAX_OPS} operations")

    for index, operation in enumerate(operations):
        if not isinstance(operation, list) or not 2 <= len(operation) <= 4:
            raise ModelLanguageError(f"model_packet.ops[{index}] must be a 2..4 item array")
        code, topic, *atoms = operation
        if not isinstance(code, str) or code not in OP_CODES:
            raise ModelLanguageError(
                f"model_packet.ops[{index}][0] must be a CML operation code"
            )
        if (
            not isinstance(topic, str)
            or not topic
            or len(topic) > MAX_TOPIC_CHARS
            or not _single_line(topic)
        ):
            raise ModelLanguageError(
                f"model_packet.ops[{index}][1] must be a non-empty one-line topic"
            )
        normalized_topic = re.sub(r"[^a-z0-9]+", "_", topic.casefold()).strip("_")
        if _PRIVATE_TOPIC_RE.search(normalized_topic):
            raise ModelLanguageError(
                f"model_packet.ops[{index}] names private reasoning; send semantic state only"
            )

        for atom_index, atom in enumerate(atoms, start=2):
            if isinstance(atom, str):
                if len(atom) > MAX_ATOM_CHARS or not _single_line(atom):
                    raise ModelLanguageError(
                        f"model_packet.ops[{index}][{atom_index}] must be compact and one-line"
                    )
            elif atom is None or isinstance(atom, bool) or type(atom) is int:
                pass
            elif isinstance(atom, float) and math.isfinite(atom):
                pass
            else:
                raise ModelLanguageError(
                    f"model_packet.ops[{index}][{atom_index}] must be a JSON scalar"
                )

    if "g" in packet:
        goal = packet["g"]
        if (
            not isinstance(goal, str)
            or not goal
            or len(goal) > MAX_TOPIC_CHARS
            or not _single_line(goal)
        ):
            raise ModelLanguageError("model_packet.g must be a non-empty one-line goal")
    for field in ("open", "refs"):
        if field not in packet:
            continue
        values = packet[field]
        if not isinstance(values, list) or len(values) > MAX_PACKET_LIST_ITEMS:
            raise ModelLanguageError(
                f"model_packet.{field} must be an array of at most {MAX_PACKET_LIST_ITEMS} strings"
            )
        for index, value in enumerate(values):
            if (
                not isinstance(value, str)
                or not value
                or len(value) > MAX_ATOM_CHARS
                or not _single_line(value)
            ):
                raise ModelLanguageError(
                    f"model_packet.{field}[{index}] must be a non-empty compact one-line string"
                )
    if "conf" in packet:
        confidence = packet["conf"]
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise ModelLanguageError("model_packet.conf must be a finite number from 0 to 1")

    try:
        canonical = json.dumps(
            packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError) as exc:
        raise ModelLanguageError(f"model_packet is not JSON encodable: {exc}") from exc
    if len(canonical.encode("utf-8")) > MAX_PACKET_BYTES:
        raise ModelLanguageError(f"model_packet exceeds {MAX_PACKET_BYTES} bytes")
    # Round-tripping produces a detached JSON-only value even if the caller
    # supplied mutable dict/list subclasses.
    return _strict_json_loads(canonical)


def validate_model_packet(packet: str | Mapping[str, Any]) -> dict[str, Any]:
    """Validate a CML/1 packet and return a detached JSON object.

    CML packets carry semantic state and results.  They have no free-form
    object fields in which to smuggle a private chain-of-thought transcript.
    """

    if isinstance(packet, str):
        decoded = _strict_json_loads(packet)
    elif isinstance(packet, Mapping):
        decoded = dict(packet)
    else:
        raise ModelLanguageError("model_packet must be a JSON string or mapping")
    return _validate_packet_object(decoded)


def canonicalize_model_packet(packet: str | Mapping[str, Any]) -> str:
    """Return the unique compact JSON encoding for a valid CML/1 packet."""

    validated = validate_model_packet(packet)
    return json.dumps(
        validated, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _validate_speech(value: Any) -> str:
    if not isinstance(value, str):
        raise ModelLanguageError("speech must be a string")
    speech = value.strip()
    if not speech:
        raise ModelLanguageError("speech must not be empty")
    if len(speech) > MAX_SPEECH_CHARS:
        raise ModelLanguageError(f"speech exceeds {MAX_SPEECH_CHARS} characters")
    if not _single_line(speech):
        raise ModelLanguageError("speech must be one line")
    return speech


def _canonical_model_codec(value: Any) -> str:
    if not isinstance(value, str):
        raise ModelLanguageError("model_codec must be a string")
    codec = value.strip().lower()
    if codec not in MODEL_CODECS:
        raise ModelLanguageError(
            "model_codec must be one of " + ", ".join(sorted(MODEL_CODECS))
        )
    return codec


def _canonical_model_projection(packet: Any, codec: str) -> str:
    if codec == "json":
        return canonicalize_model_packet(packet)
    if not isinstance(packet, str):
        raise ModelLanguageError(f"{codec} model_packet must be one-line text")
    projection = packet.strip()
    if not projection:
        raise ModelLanguageError("model_packet must not be empty")
    if not _single_line(projection):
        raise ModelLanguageError("model_packet must be one line")
    if len(projection.encode("utf-8")) > MAX_PACKET_BYTES:
        raise ModelLanguageError(f"model_packet exceeds {MAX_PACKET_BYTES} bytes")
    return projection


def _canonical_payload_kind(value: Any) -> str:
    if not isinstance(value, str):
        raise ModelLanguageError("payload_kind must be a string")
    kind = value.strip().lower()
    if kind not in PAYLOAD_KINDS:
        raise ModelLanguageError(
            "payload_kind must be one of " + ", ".join(sorted(PAYLOAD_KINDS))
        )
    return kind


def infer_payload_kind(body: Body) -> str:
    """Conservatively classify a payload for display policy, never rewriting it."""

    if isinstance(body, bytes):
        return "artifact"
    if not isinstance(body, str):
        raise ModelLanguageError("payload body must be str or bytes")
    stripped = body.lstrip()
    if re.match(r"^(?:ACTION|TOOL_CALL|COMMAND)[ \t]*:", stripped, re.IGNORECASE):
        return "action"
    if stripped.startswith("diff --git ") or (
        stripped.startswith("--- a/") and "\n+++ b/" in stripped
    ):
        return "patch"
    try:
        _strict_json_loads(stripped)
    except ModelLanguageError:
        pass
    else:
        return "data"
    if (
        re.match(r"^(?:`{3,}|~{3,})[A-Za-z0-9_+.-]*[ \t]*\r?$", stripped.split("\n", 1)[0])
        or stripped.startswith("#!")
        or re.match(
            r"^(?:async[ \t]+def|def|class|from[ \t]+\S+[ \t]+import|import[ \t]+\S+|"
            r"function|const|let|var|interface|type|package|#include)\b",
            stripped,
        )
    ):
        return "code"
    return "prose"


def is_opaque_payload_kind(kind: str) -> bool:
    """Return whether a kind is compiler/tool-consumable and must stay opaque."""

    return _canonical_payload_kind(kind) != "prose"


def _validate_layered_envelope(metadata: Mapping[str, Any], body: Body | None) -> None:
    missing = sorted(_REQUIRED_ENVELOPE_FIELDS - set(metadata))
    if missing:
        raise ModelLanguageError("missing CML envelope fields: " + ", ".join(missing))
    if metadata["reasoning_mode"] != REASONING_MODE:
        raise ModelLanguageError(f"reasoning_mode must be {REASONING_MODE}")
    if metadata["model_protocol"] != CML_PROTOCOL:
        raise ModelLanguageError(f"model_protocol must be {CML_PROTOCOL}")
    if metadata["model_codec"] not in MODEL_CODECS:
        raise ModelLanguageError("model_codec is not canonical")
    if metadata["speech"] != _validate_speech(metadata["speech"]):
        raise ModelLanguageError("speech is valid but not canonical (trim outer whitespace)")
    if not isinstance(metadata["model_packet"], str):
        raise ModelLanguageError("layered model_packet must be canonical one-line text")
    canonical_packet = _canonical_model_projection(
        metadata["model_packet"], metadata["model_codec"]
    )
    if metadata["model_packet"] != canonical_packet:
        raise ModelLanguageError("model_packet is valid but not canonical compact text")
    if metadata["payload_kind"] not in PAYLOAD_KINDS:
        raise ModelLanguageError("payload_kind is not canonical")
    digest = metadata["payload_sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ModelLanguageError("payload_sha256 must be 64 lowercase hexadecimal characters")
    if body is not None and digest != payload_sha256(body):
        raise ModelLanguageError("payload_sha256 does not match the exact payload body")


def projection_state(metadata: Mapping[str, Any] | None, body: Body | None = None) -> str:
    """Classify an observed record as LAYERED, UNLAYERED, or INVALID."""

    if metadata is None:
        metadata = {}
    if not isinstance(metadata, Mapping):
        return "INVALID"
    declared_fields = {field for field in _CORE_DECLARATION_FIELDS if field in metadata}
    # Observer enrichment may surface a legacy body-form MODEL line under the
    # common model_packet display key.  It remains explicitly UNLAYERED and is
    # accepted only when it still matches that exact out-of-fence body line.
    legacy_model_projection = False
    if (
        declared_fields == {"model_packet"}
        and metadata.get("language_state") == "UNLAYERED"
        and isinstance(body, str)
    ):
        legacy_model = extract_legacy_layers(body).get("model")
        legacy_model_projection = bool(legacy_model) and metadata.get("model_packet") == legacy_model
    declared = bool(declared_fields) and not legacy_model_projection
    if not declared:
        claimed_state = metadata.get("language_state")
        if claimed_state not in (None, "UNLAYERED"):
            return "INVALID"
        if body is not None:
            try:
                _body_bytes(body)
            except ModelLanguageError:
                return "INVALID"
        return "UNLAYERED"
    try:
        _validate_layered_envelope(metadata, body)
    except (ModelLanguageError, TypeError, ValueError):
        return "INVALID"
    return "LAYERED"


def canonicalize_emitter_metadata(metadata: Mapping[str, Any], body: Body) -> dict[str, Any]:
    """Build strict CML/1 emitter metadata without changing ``metadata`` or ``body``."""

    if not isinstance(metadata, Mapping):
        raise ModelLanguageError("metadata must be a mapping")
    _body_bytes(body)
    result = dict(metadata)

    mode = result.get("reasoning_mode", REASONING_MODE)
    if not isinstance(mode, str) or mode.strip().upper() != REASONING_MODE:
        raise ModelLanguageError(f"reasoning_mode must be {REASONING_MODE}")
    protocol = result.get("model_protocol", CML_PROTOCOL)
    if not isinstance(protocol, str) or protocol.strip().upper() != CML_PROTOCOL:
        raise ModelLanguageError(f"model_protocol must be {CML_PROTOCOL}")
    codec = _canonical_model_codec(result.get("model_codec", MODEL_CODEC))
    if "speech" not in result:
        raise ModelLanguageError("speech is required for the PLAIN projection")
    speech = _validate_speech(result["speech"])
    if "model_packet" not in result:
        raise ModelLanguageError("model_packet is required for the MODEL projection")
    packet = _canonical_model_projection(result["model_packet"], codec)

    if "payload_kind" in result:
        kind = _canonical_payload_kind(result["payload_kind"])
    else:
        kind = infer_payload_kind(body)
    digest = payload_sha256(body)
    if "payload_sha256" in result:
        supplied_digest = result["payload_sha256"]
        if not isinstance(supplied_digest, str) or supplied_digest.strip().lower() != digest:
            raise ModelLanguageError("supplied payload_sha256 does not match the exact payload body")

    result.update({
        "reasoning_mode": REASONING_MODE,
        "speech": speech,
        "model_protocol": CML_PROTOCOL,
        "model_codec": codec,
        "model_packet": packet,
        "payload_kind": kind,
        "payload_sha256": digest,
        "language_state": "LAYERED",
    })
    _validate_layered_envelope(result, body)
    return result


def canonicalize_emitter_record(
    metadata: Mapping[str, Any], body: Body
) -> tuple[dict[str, Any], Body]:
    """Return canonical metadata and the exact same opaque body object."""

    return canonicalize_emitter_metadata(metadata, body), body


def _fence_opening(line: str) -> tuple[str, int] | None:
    match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
    if not match:
        return None
    marker, suffix = match.groups()
    # CommonMark backtick info strings cannot themselves contain a backtick.
    if marker[0] == "`" and "`" in suffix:
        return None
    return marker[0], len(marker)


def _fence_closing(line: str, character: str, minimum: int) -> bool:
    return re.fullmatch(rf" {{0,3}}{re.escape(character)}{{{minimum},}}[ \t]*", line) is not None


def extract_legacy_layers(body: str) -> dict[str, str]:
    """Extract first legacy PLAIN and MODEL lines outside Markdown fences.

    Returned keys are ``speech`` and/or ``model``.  Fence content is ignored
    for both backtick and tilde fences of length three or greater.  The body is
    only inspected; it is never changed.
    """

    if not isinstance(body, str):
        return {}
    found: dict[str, str] = {}
    fence_character: str | None = None
    fence_length = 0
    for raw_line in body.splitlines():
        line = raw_line.rstrip("\r")
        if fence_character is not None:
            if _fence_closing(line, fence_character, fence_length):
                fence_character = None
                fence_length = 0
            continue
        opening = _fence_opening(line)
        if opening is not None:
            fence_character, fence_length = opening
            continue
        plain = _PLAIN_RE.match(line)
        if plain and "speech" not in found:
            value = plain.group(2).strip()
            if value:
                found["speech"] = value
        model = _MODEL_RE.match(line)
        if model and "model" not in found:
            value = model.group(1).strip()
            if value:
                found["model"] = value
        if "speech" in found and "model" in found:
            break
    return found


def enrich_observer_metadata(metadata: Mapping[str, Any] | None, body: Body) -> dict[str, Any]:
    """Annotate observed metadata without ever rejecting a record.

    Complete canonical envelopes become ``LAYERED``.  Records with no CML
    declaration remain ``UNLAYERED`` (and may gain a legacy speech projection).
    Partial, malformed, or hash-mismatched declarations become ``INVALID``.
    """

    if metadata is None:
        result: dict[str, Any] = {}
    elif isinstance(metadata, Mapping):
        try:
            result = dict(metadata)
        except Exception:
            return {"language_state": "INVALID"}
    else:
        return {"language_state": "INVALID"}

    try:
        state = projection_state(result, body)
        if state == "LAYERED":
            # This also returns a detached mapping and preserves unrelated
            # metadata.  It cannot fail after the state check, but observers
            # still fail closed to INVALID if an exotic Mapping races/mutates.
            result = canonicalize_emitter_metadata(result, body)
        else:
            if state == "UNLAYERED" and isinstance(body, str):
                legacy = extract_legacy_layers(body)
                if "speech" in legacy and "speech" not in result:
                    result["speech"] = legacy["speech"]
                if "model" in legacy and "model_packet" not in result:
                    result["model_packet"] = legacy["model"]
            if "payload_kind" not in result:
                result["payload_kind"] = infer_payload_kind(body)
            if "payload_sha256" not in result:
                result["payload_sha256"] = payload_sha256(body)
        result["language_state"] = state
        return result
    except Exception:
        # Observation is an open road: malformed metadata/body is evidence,
        # never grounds for dropping the underlying record.
        result["language_state"] = "INVALID"
        return result


def enrich_observer_record(
    metadata: Mapping[str, Any] | None, body: Body
) -> tuple[dict[str, Any], Body]:
    """Return observer-enriched metadata and the exact same opaque body object."""

    return enrich_observer_metadata(metadata, body), body


__all__ = [
    "CML_PROTOCOL",
    "LANGUAGE_STATES",
    "MODEL_CODEC",
    "MODEL_CODECS",
    "ModelLanguageError",
    "OP_CODES",
    "PACKET_KINDS",
    "PAYLOAD_KINDS",
    "REASONING_MODE",
    "canonicalize_emitter_metadata",
    "canonicalize_emitter_record",
    "canonicalize_model_packet",
    "enrich_observer_metadata",
    "enrich_observer_record",
    "extract_legacy_layers",
    "infer_payload_kind",
    "is_opaque_payload_kind",
    "payload_sha256",
    "projection_state",
    "validate_model_packet",
]
