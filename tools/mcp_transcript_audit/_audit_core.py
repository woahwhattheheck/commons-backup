from __future__ import annotations

import builtins as _builtins
from importlib import resources as _resources
from typing import Any

_OLD_TYPED_ID_KEY = '''def _typed_id_key(value: Any) -> tuple[str, Any]:
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, bool) or value is None:
        raise ValueError("request id must be a string or finite number, not bool/null")
    if isinstance(value, (int, float, Decimal)):
        return ("number", _number_identity(value))
    raise ValueError("request id must be a string or finite number, not bool/null")
'''

_INTEGER_TYPED_ID_KEY = '''def _typed_id_key(value: Any) -> tuple[str, Any]:
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, bool) or value is None:
        raise ValueError("request id must be a string or integer, not bool/null")
    if isinstance(value, (int, float, Decimal)):
        identity = _number_identity(value)
        if identity[2] < 0:
            raise ValueError("request id must be a string or integer")
        return ("number", identity)
    raise ValueError("request id must be a string or integer, not bool/null")
'''


def _build_api() -> tuple[Any, ...]:
    """Compile the reviewed donor into a reload-resistant private engine."""

    # Capture the interpreter primitives and resource resolver into private local
    # cells before any exported callable is created. Ordinary post-import module
    # rebinding (including ``_audit_core.exec``) cannot change these cells, and
    # reload re-imports the canonical builtins/resources modules before capture.
    execute = _builtins.exec
    compile_source = _builtins.compile
    resource_files = _resources.files

    package = __package__
    resource = resource_files(package).joinpath("_audit_engine_source.txt")
    donor_source = resource.read_text(encoding="utf-8")
    if donor_source.count(_OLD_TYPED_ID_KEY) != 1:
        raise ImportError("MCP transcript audit donor validator did not match exactly once")

    integrated_source = donor_source.replace(_OLD_TYPED_ID_KEY, _INTEGER_TYPED_ID_KEY)
    engine_code = compile_source(
        integrated_source, "<mcp-transcript-audit-engine>", "exec"
    )

    def new_engine() -> dict[str, Any]:
        # Every supported operation receives a fresh private globals dictionary.
        # Reloading/rebinding this module or the public facade therefore cannot
        # restore the donor's permissive validator inside an exported function.
        namespace: dict[str, Any] = {
            "__name__": f"{package}._audit_engine_runtime",
            "__package__": package,
            "__file__": "<mcp-transcript-audit-engine>",
        }
        execute(engine_code, namespace)
        return namespace

    bootstrap = new_engine()
    constants = tuple(
        bootstrap[name]
        for name in (
            "SCHEMA",
            "VERIFY_SCHEMA",
            "CAPTURE_SCHEMA",
            "REQUIRED_PROTOCOL_VERSION",
            "MAX_CAPTURE_BYTES",
            "MAX_LINE_BYTES",
            "MAX_PAYLOAD_BYTES",
            "MAX_EVENTS",
            "MAX_JSON_NESTING",
            "CLIENT",
            "SERVER",
            "DIRECTIONS",
            "LOGGING_LEVELS",
        )
    )
    required_protocol_version = bootstrap["REQUIRED_PROTOCOL_VERSION"]

    def audit_transcript(
        source: bytes,
        *,
        required_protocol_version: str = required_protocol_version,
    ) -> dict[str, Any]:
        return new_engine()["audit_transcript"](
            source,
            required_protocol_version=required_protocol_version,
        )

    def verify_receipt(
        source: bytes,
        receipt_bytes: bytes,
        *,
        required_protocol_version: str = required_protocol_version,
    ) -> dict[str, Any]:
        return new_engine()["verify_receipt"](
            source,
            receipt_bytes,
            required_protocol_version=required_protocol_version,
        )

    def canonical_json_bytes(value: Any) -> bytes:
        return new_engine()["canonical_json_bytes"](value)

    def encode_capture_event(direction: str, message: dict[str, Any]) -> bytes:
        return new_engine()["encode_capture_event"](direction, message)

    return constants + (
        audit_transcript,
        verify_receipt,
        canonical_json_bytes,
        encode_capture_event,
    )


(
    SCHEMA,
    VERIFY_SCHEMA,
    CAPTURE_SCHEMA,
    REQUIRED_PROTOCOL_VERSION,
    MAX_CAPTURE_BYTES,
    MAX_LINE_BYTES,
    MAX_PAYLOAD_BYTES,
    MAX_EVENTS,
    MAX_JSON_NESTING,
    CLIENT,
    SERVER,
    DIRECTIONS,
    LOGGING_LEVELS,
    audit_transcript,
    verify_receipt,
    canonical_json_bytes,
    encode_capture_event,
) = _build_api()

# Do not leave the donor source, transformation blocks, resource loader, or a
# mutable engine dictionary on the importable module surface.
del _build_api, _OLD_TYPED_ID_KEY, _INTEGER_TYPED_ID_KEY, _builtins, _resources

__all__ = [
    "REQUIRED_PROTOCOL_VERSION",
    "SCHEMA",
    "VERIFY_SCHEMA",
    "audit_transcript",
    "canonical_json_bytes",
    "encode_capture_event",
    "verify_receipt",
]
