#!/usr/bin/env python3
"""Secret-free idempotent inbound-reply triage.

A mailbox operator supplies only an opaque event ref, received_at, prospect
key, payload hash, and one manual classification. This tool writes one
public-safe durable receipt and the next action. It never reads a mailbox,
never reconstructs a body, and never records commercial state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import errno
import hashlib
import json
import os
import re
import secrets
import sys
from pathlib import Path
from typing import Any


SCHEMA_PATH = Path(__file__).with_name("reply.schema.json")
SCHEMA_VERSION = "production-survival-reply-intake/v1"
KIND = "PRODUCTION_SURVIVAL_REPLY_INTAKE_RECEIPT"
STATUS = "RECORDED"
LIMITS = [
    "mailbox-operator classification of an opaque payload hash only",
    "no mailbox send",
    "no commercial state change",
]
CLASS_TO_NEXT_ACTION = {
    "OPT_OUT": "DNC/CLOSE",
    "AUTO_RESPONSE": "WAIT_FOR_HUMAN_REPLY",
    "NEGATIVE": "CLOSE",
    "QUESTION": "DRAFT_REPLY",
    "POSITIVE_SCOPE": "NEEDS_ACCEPTANCE",
    "NEEDS_HUMAN": "ESCALATE_ONLY_IF_BUYER_REQUESTS_BRYCE",
}
ENVELOPE_FIELDS = (
    "event_ref",
    "received_at",
    "prospect_key",
    "payload_sha256",
    "classification",
)
FORBIDDEN_CLAIM_RE = re.compile(
    r"\b(replied|accepted|invoiced|authorized|settled|delivered|paid)\b",
    re.IGNORECASE,
)
EXIT_OK = 0
EXIT_SCHEMA = 1
EXIT_COLLISION = 2


class IntakeError(ValueError):
    """Envelope or receipt failed closed."""


class SchemaError(IntakeError):
    """Instance does not match reply.schema.json."""


class CollisionError(IntakeError):
    """Same event_ref already recorded with a different payload hash."""


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SchemaError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def load_schema() -> dict[str, Any]:
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        schema = json.load(handle, object_pairs_hook=_pairs_no_duplicates)
    if not isinstance(schema, dict):
        raise SchemaError("reply.schema.json must be an object")
    return schema


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle, object_pairs_hook=_pairs_no_duplicates)
    if not isinstance(value, dict):
        raise SchemaError(f"{path} must contain a JSON object")
    return value


def _resolve_ref(ref: str, root: dict[str, Any]) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise SchemaError(f"unsupported $ref: {ref}")
    node: Any = root
    for part in ref[2:].split("/"):
        if not isinstance(node, dict) or part not in node:
            raise SchemaError(f"unresolved $ref: {ref}")
        node = node[part]
    if not isinstance(node, dict):
        raise SchemaError(f"$ref did not resolve to an object: {ref}")
    return node


def _is_datetime(value: str) -> bool:
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def validate_schema(
    instance: Any,
    schema: dict[str, Any],
    root: dict[str, Any] | None = None,
) -> None:
    """Validate instance against a Draft 2020-12 subset used by reply.schema.json."""
    root = root if root is not None else schema
    if "$ref" in schema:
        validate_schema(instance, _resolve_ref(schema["$ref"], root), root)
        remaining = {key: schema[key] for key in schema if key != "$ref"}
        if remaining:
            validate_schema(instance, remaining, root)
        return
    if "allOf" in schema:
        for subschema in schema["allOf"]:
            validate_schema(instance, subschema, root)
    if "anyOf" in schema:
        errors: list[str] = []
        matched = False
        for subschema in schema["anyOf"]:
            try:
                validate_schema(instance, subschema, root)
            except SchemaError as error:
                errors.append(str(error))
            else:
                matched = True
                break
        if not matched:
            raise SchemaError("anyOf failed: " + "; ".join(errors))
    if "not" in schema:
        try:
            validate_schema(instance, schema["not"], root)
        except SchemaError:
            pass
        else:
            raise SchemaError("instance matches a forbidden schema")
    if "if" in schema:
        try:
            validate_schema(instance, schema["if"], root)
        except SchemaError:
            if "else" in schema:
                validate_schema(instance, schema["else"], root)
        else:
            if "then" in schema:
                validate_schema(instance, schema["then"], root)
    if "const" in schema and instance != schema["const"]:
        raise SchemaError(f"expected const {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise SchemaError(f"expected one of {schema['enum']!r}")
    expected_type = schema.get("type")
    if expected_type == "object" and not isinstance(instance, dict):
        raise SchemaError("expected object")
    if expected_type == "string" and not isinstance(instance, str):
        raise SchemaError("expected string")
    if expected_type == "array" and not isinstance(instance, list):
        raise SchemaError("expected array")
    if expected_type not in (None, "object", "string", "array"):
        raise SchemaError(f"unsupported schema type: {expected_type}")
    if isinstance(instance, dict):
        if "propertyNames" in schema:
            for key in instance:
                validate_schema(key, schema["propertyNames"], root)
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(instance) - set(properties))
            if extra:
                raise SchemaError(f"additional properties not allowed: {extra}")
        if schema.get("unevaluatedProperties") is False:
            extra = sorted(set(instance) - set(properties))
            if extra:
                raise SchemaError(f"unevaluated properties not allowed: {extra}")
        for key, subschema in properties.items():
            if key in instance:
                validate_schema(instance[key], subschema, root)
        missing = [key for key in schema.get("required", []) if key not in instance]
        if missing:
            raise SchemaError(f"missing required properties: {missing}")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            raise SchemaError("string shorter than minLength")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            raise SchemaError("string longer than maxLength")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            raise SchemaError(f"string failed pattern {schema['pattern']}")
        if schema.get("format") == "date-time" and not _is_datetime(instance):
            raise SchemaError("string failed date-time format")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise SchemaError("array shorter than minItems")
        if "items" in schema and isinstance(schema["items"], dict):
            for item in instance:
                validate_schema(item, schema["items"], root)


def envelope_schema(root: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = root if root is not None else load_schema()
    return schema["$defs"]["envelope"]


def receipt_schema(root: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = root if root is not None else load_schema()
    return schema["$defs"]["receipt"]


def validate_envelope(envelope: dict[str, Any], root: dict[str, Any] | None = None) -> None:
    schema = root if root is not None else load_schema()
    validate_schema(envelope, envelope_schema(schema), schema)


def validate_receipt(receipt: dict[str, Any], root: dict[str, Any] | None = None) -> None:
    schema = root if root is not None else load_schema()
    validate_schema(receipt, receipt_schema(schema), schema)
    validate_schema(receipt, schema, schema)


def receipt_id_for(event_ref: str) -> str:
    digest = hashlib.sha256(event_ref.encode("utf-8")).hexdigest()
    return f"reply-{digest[:24]}"


def build_receipt(envelope: dict[str, Any]) -> dict[str, Any]:
    classification = envelope["classification"]
    next_action = CLASS_TO_NEXT_ACTION[classification]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "receipt_id": receipt_id_for(envelope["event_ref"]),
        "status": STATUS,
        "event_ref": envelope["event_ref"],
        "received_at": envelope["received_at"],
        "prospect_key": envelope["prospect_key"],
        "payload_sha256": envelope["payload_sha256"],
        "classification": classification,
        "next_action": next_action,
        "limits": list(LIMITS),
    }


def _assert_no_forbidden_claims(receipt: dict[str, Any]) -> None:
    blob = canonical_bytes(receipt).decode("utf-8")
    match = FORBIDDEN_CLAIM_RE.search(blob)
    if match:
        raise SchemaError(f"receipt emitted forbidden claim {match.group(0)!r}")
    if (
        receipt["classification"] == "POSITIVE_SCOPE"
        and receipt["next_action"] != "NEEDS_ACCEPTANCE"
    ):
        raise SchemaError("POSITIVE_SCOPE can only stop at NEEDS_ACCEPTANCE")


def store_path_for(store: Path, event_ref: str) -> Path:
    return store / f"{receipt_id_for(event_ref)}.json"


def _before_exclusive_claim() -> None:
    """Test hook so concurrent callers can meet at the no-replace publish."""


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _validate_existing_receipt(
    path: Path,
    envelope: dict[str, Any],
    blob: bytes,
) -> bytes:
    try:
        existing = path.read_bytes()
    except FileNotFoundError as error:
        raise CollisionError(f"{path} vanished after exclusive claim") from error
    try:
        existing_obj = json.loads(existing, object_pairs_hook=_pairs_no_duplicates)
    except json.JSONDecodeError as error:
        raise CollisionError(f"{path} is not a complete receipt") from error
    if not isinstance(existing_obj, dict):
        raise CollisionError(f"{path} is not a receipt object")
    if existing_obj.get("event_ref") != envelope["event_ref"]:
        raise CollisionError("store path maps to a different event_ref")
    if existing_obj.get("payload_sha256") != envelope["payload_sha256"]:
        raise CollisionError("same event_ref with a different payload_sha256")
    if existing != blob:
        raise IntakeError("durable receipt bytes diverged from canonical form")
    return existing


def _write_complete_temp(directory: Path, target: Path, blob: bytes) -> Path:
    token = secrets.token_hex(8)
    temp = directory / f".{target.name}.{os.getpid()}.{token}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(temp, flags, 0o644)
    try:
        try:
            view = memoryview(blob)
            offset = 0
            while offset < len(view):
                offset += os.write(fd, view[offset:])
            os.fsync(fd)
        finally:
            os.close(fd)
    except Exception:
        _unlink_quietly(temp)
        raise
    return temp


def _link_no_replace(temp: Path, target: Path) -> bool:
    try:
        os.link(temp, target)
    except FileExistsError:
        return False
    except OSError as error:
        if error.errno != errno.EEXIST:
            raise
        return False
    return True


def record_envelope(envelope: dict[str, Any], store: Path) -> bytes:
    schema = load_schema()
    validate_envelope(envelope, schema)
    extra = sorted(set(envelope) - set(ENVELOPE_FIELDS))
    if extra:
        raise SchemaError(f"envelope has extra fields: {extra}")
    receipt = build_receipt(envelope)
    validate_receipt(receipt, schema)
    _assert_no_forbidden_claims(receipt)
    blob = canonical_bytes(receipt)
    store.mkdir(parents=True, exist_ok=True)
    path = store_path_for(store, envelope["event_ref"])
    temp: Path | None = None
    try:
        temp = _write_complete_temp(store, path, blob)
        _before_exclusive_claim()
        _link_no_replace(temp, path)
        return _validate_existing_receipt(path, envelope, blob)
    finally:
        if temp is not None:
            _unlink_quietly(temp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--envelope", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        envelope = read_json(args.envelope)
        blob = record_envelope(envelope, args.store)
    except CollisionError as error:
        print(str(error), file=sys.stderr)
        return EXIT_COLLISION
    except IntakeError as error:
        print(str(error), file=sys.stderr)
        return EXIT_SCHEMA
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(blob)
    sys.stdout.buffer.write(blob)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
