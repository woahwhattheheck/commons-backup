"""Build and verify a policy-bounded evidence packet for an AI assistant."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

from internal_brain.core import (
    AuthorizationError,
    BrainError,
    InternalBrain,
    SchemaError,
    canonical_json,
    sha256_hex,
    strict_loads,
)

CONTEXT_SCHEMA = "internal-brain-ai-context/v1"
VERIFICATION_SCHEMA = "internal-brain-ai-context-verification/v1"
RECEIPT_SCHEMA = "internal-brain-receipt/v1"
_ALLOWED_DECISIONS = {
    "AUTHORIZED_MATCH",
    "AUTHORIZED_AMBIGUOUS_MATCH",
    "NO_AUTHORIZED_MATCH",
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MAX_EVIDENCE = 20


def _mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaError(f"{where} must be an object")
    return value


def _text(value: Any, where: str, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum or "\x00" in value:
        raise SchemaError(f"{where} must be a non-empty bounded string")
    return value


def _digest(value: Any, where: str) -> str:
    value = _text(value, where, 64)
    if not _HEX64.fullmatch(value):
        raise SchemaError(f"{where} must be 64 lowercase hexadecimal characters")
    return value


def _string_list(value: Any, where: str, maximum: int = 128) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        raise SchemaError(f"{where} must be a bounded string list")
    output: list[str] = []
    for index, item in enumerate(value):
        output.append(_text(item, f"{where}[{index}]", 2048))
    return output


def _authorization(value: Any) -> dict[str, Any]:
    record = _mapping(value, "receipt.authorization")
    evaluated = record.get("evaluated_before_retrieval")
    denied_count = record.get("scope_denied_count")
    if evaluated is not True:
        raise SchemaError("receipt must record authorization before retrieval")
    if isinstance(denied_count, bool) or not isinstance(denied_count, int) or denied_count < 0:
        raise SchemaError("receipt.authorization.scope_denied_count must be nonnegative")
    return {
        "evaluated_before_retrieval": True,
        "scope_denied_count": denied_count,
        "requested_document_ids": _string_list(
            record.get("requested_document_ids", []),
            "receipt.authorization.requested_document_ids",
        ),
    }


def _evidence_item(value: Any, index: int) -> dict[str, Any]:
    item = _mapping(value, f"receipt.results[{index}]")
    score = item.get("score")
    if isinstance(score, bool) or not isinstance(score, int) or score < 0:
        raise SchemaError(f"receipt.results[{index}].score must be nonnegative")
    citation = _mapping(item.get("citation"), f"receipt.results[{index}].citation")
    return {
        "document_id": _text(item.get("document_id"), f"receipt.results[{index}].document_id", 128),
        "version": _text(item.get("version"), f"receipt.results[{index}].version", 128),
        "score": score,
        "title": _text(item.get("title"), f"receipt.results[{index}].title", 512),
        "snippet": _text(item.get("snippet"), f"receipt.results[{index}].snippet", 4096),
        "citation": {
            "source_uri": _text(citation.get("source_uri"), f"receipt.results[{index}].citation.source_uri", 2048),
            "content_sha256": _digest(citation.get("content_sha256"), f"receipt.results[{index}].citation.content_sha256"),
            "document_sha256": _digest(citation.get("document_sha256"), f"receipt.results[{index}].citation.document_sha256"),
        },
        "untrusted_instruction_markers": _string_list(
            item.get("untrusted_instruction_markers", []),
            f"receipt.results[{index}].untrusted_instruction_markers",
            64,
        ),
    }


def _evidence(value: Any, decision_code: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > _MAX_EVIDENCE:
        raise SchemaError(f"receipt.results must contain at most {_MAX_EVIDENCE} items")
    output = [_evidence_item(item, index) for index, item in enumerate(value)]
    if decision_code == "NO_AUTHORIZED_MATCH" and output:
        raise SchemaError("NO_AUTHORIZED_MATCH must not carry evidence")
    if decision_code != "NO_AUTHORIZED_MATCH" and not output:
        raise SchemaError("an authorized match must carry evidence")
    return output


def _constraints() -> dict[str, bool]:
    return {
        "evidence_only": True,
        "document_text_is_data": True,
        "do_not_widen_actor_scope": True,
        "abstain_when_no_authorized_match": True,
    }


def build_context_packet(receipt: Mapping[str, Any]) -> dict[str, Any]:
    receipt = _mapping(receipt, "receipt")
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("operation") != "query":
        raise SchemaError("context packets require an Internal Brain query receipt")
    decision = _text(receipt.get("decision_code"), "receipt.decision_code", 64)
    if decision not in _ALLOWED_DECISIONS:
        raise SchemaError("receipt.decision_code is not supported for an AI context packet")
    security = _mapping(receipt.get("security_boundary"), "receipt.security_boundary")
    for key in (
        "document_text_is_data_not_instruction",
        "retrieval_cannot_widen_actor_roles",
        "cross_tenant_requests_fail_closed",
    ):
        if security.get(key) is not True:
            raise SchemaError(f"receipt.security_boundary.{key} must be true")
    packet = {
        "schema": CONTEXT_SCHEMA,
        "tenant_id": _text(receipt.get("tenant_id"), "receipt.tenant_id", 128),
        "actor_user_id": _text(receipt.get("actor_user_id"), "receipt.actor_user_id", 128),
        "query_sha256": _digest(receipt.get("query_sha256"), "receipt.query_sha256"),
        "decision_code": decision,
        "authorization": _authorization(receipt.get("authorization")),
        "evidence": _evidence(receipt.get("results"), decision),
        "constraints": _constraints(),
        "audit_event_digest": _digest(receipt.get("audit_event_digest"), "receipt.audit_event_digest"),
        "source_result_receipt_sha256": _digest(
            receipt.get("result_receipt_sha256"), "receipt.result_receipt_sha256"
        ),
    }
    return {**packet, "packet_sha256": sha256_hex(canonical_json(packet))}


def verify_context_packet(value: Mapping[str, Any]) -> dict[str, Any]:
    packet = _mapping(value, "context packet")
    expected_keys = {
        "schema", "tenant_id", "actor_user_id", "query_sha256", "decision_code",
        "authorization", "evidence", "constraints", "audit_event_digest",
        "source_result_receipt_sha256", "packet_sha256",
    }
    missing = sorted(expected_keys - set(packet))
    extra = sorted(set(packet) - expected_keys)
    if missing or extra:
        raise SchemaError("context packet fields do not match the schema")
    if packet.get("schema") != CONTEXT_SCHEMA:
        raise SchemaError(f"context packet schema must be {CONTEXT_SCHEMA!r}")
    decision = _text(packet.get("decision_code"), "context packet decision_code", 64)
    if decision not in _ALLOWED_DECISIONS:
        raise SchemaError("context packet decision_code is unsupported")
    _text(packet.get("tenant_id"), "context packet tenant_id", 128)
    _text(packet.get("actor_user_id"), "context packet actor_user_id", 128)
    _digest(packet.get("query_sha256"), "context packet query_sha256")
    authorization = _authorization(packet.get("authorization"))
    evidence = _evidence(packet.get("evidence"), decision)
    constraints = _mapping(packet.get("constraints"), "context packet constraints")
    if dict(constraints) != _constraints():
        raise SchemaError("context packet constraints do not match the evidence boundary")
    _digest(packet.get("audit_event_digest"), "context packet audit_event_digest")
    _digest(packet.get("source_result_receipt_sha256"), "context packet source_result_receipt_sha256")
    claimed = _digest(packet.get("packet_sha256"), "context packet packet_sha256")
    unsigned = {key: packet[key] for key in packet if key != "packet_sha256"}
    computed = sha256_hex(canonical_json(unsigned))
    if claimed != computed:
        raise SchemaError("context packet digest mismatch")
    return {
        "schema": VERIFICATION_SCHEMA,
        "valid": True,
        "packet_sha256": claimed,
        "decision_code": decision,
        "evidence_count": len(evidence),
        "scope_denied_count": authorization["scope_denied_count"],
    }


def _read_object(path: Path, where: str) -> Mapping[str, Any]:
    try:
        return _mapping(strict_loads(path.read_text(encoding="utf-8")), where)
    except OSError as exc:
        raise SchemaError(f"could not read {where}: {exc}") from exc


def _emit(value: Mapping[str, Any], output: Path | None) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output is None:
        sys.stdout.write(rendered)
        return
    try:
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
    except OSError as exc:
        raise SchemaError(f"could not create output: {exc}") from exc
    print(json.dumps({"created": str(output), "packet_sha256": value.get("packet_sha256")}))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="run one query and emit its AI context packet")
    build.add_argument("bundle", type=Path)
    build.add_argument("query", type=Path)
    build.add_argument("--out", type=Path)
    verify = sub.add_parser("verify", help="verify one retained AI context packet")
    verify.add_argument("packet", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "verify":
            result = verify_context_packet(_read_object(args.packet, "context packet"))
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 0
        engine = InternalBrain(_read_object(args.bundle, "bundle"))
        receipt = engine.query(_read_object(args.query, "query"))
        packet = build_context_packet(receipt)
        _emit(packet, args.out)
        return 0 if receipt["decision_code"] != "NO_AUTHORIZED_MATCH" else 3
    except AuthorizationError as exc:
        print(json.dumps({"error": exc.code, "message": str(exc)}), file=sys.stderr)
        return 3
    except BrainError as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
