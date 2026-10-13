"""Deterministic offline proof for agent false-success handling.

The compiler consumes caller-supplied captured HTTP/MCP exchanges. It never
performs network I/O. Raw bodies stay in the input bundle; proof receipts retain
only digests and bounded semantic facts. Caller-provided source/client-event
SHA-256 values are commitments, not independently authenticated provenance.
"""
from __future__ import annotations

import base64
import binascii
import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

CAPTURE_SCHEMA = "agent-false-success-capture/v2"
PROOF_SCHEMA = "agent-false-success-proof/v2"
POLICY_VERSION = "false-success-policy/2"
MAX_CASES = 64
MAX_BODY_BYTES = 64 * 1024
MAX_INPUT_BYTES = 1024 * 1024
MAX_TEXT = 240
MAX_JSONRPC_ID = 2**53 - 1
REQUIRED_FAMILIES = (
    "HTTP_200_HTML",
    "HTTP_200_LOGIN_HTML",
    "HTTP_200_MISLABELED_HTML",
    "HTTP_NON_2XX",
    "JSON_RPC_ERROR",
    "MCP_TOOL_ERROR",
    "MCP_WRAPPED_HTML",
    "MALFORMED_JSON",
    "VALID_CONTROL",
)
_DISPOSITIONS = {"SUCCESS", "ERROR"}
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
_HTML_ROOT_MARKERS = ("<!doctype html", "<html")
_HTML_STRUCTURAL_MARKERS = ("<head", "<body", "<form", "<input", "<title", "<script", "<meta")
_LOGIN_MARKERS = (
    'type="password"', "type='password'", 'name="password"', "name='password'",
    "sign in", "log in", "login", "authentication required", "unauthorized",
)


class ProofError(ValueError):
    """Base proof/validation failure."""


class SchemaError(ProofError):
    """Input does not satisfy the strict proof schema."""


@dataclass(frozen=True)
class Classification:
    decision: str
    reasons: tuple[str, ...]
    tags: tuple[str, ...]
    body_sha256: str
    body_bytes: int
    media_type: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reasons": list(self.reasons),
            "tags": list(self.tags),
            "body_sha256": self.body_sha256,
            "body_bytes": self.body_bytes,
            "media_type": self.media_type,
        }


def _reject_constant(value: str) -> Any:
    raise SchemaError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise SchemaError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(raw: str | bytes) -> Any:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise SchemaError("JSON input is not strict UTF-8") from exc
    try:
        return json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except SchemaError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise SchemaError("invalid JSON") from exc


def _assert_unicode_scalars(value: Any, *, field: str) -> None:
    if type(value) is not str:
        raise SchemaError(f"{field} must be a string")
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in value):
        raise SchemaError(f"{field} contains a lone UTF-16 surrogate")


def canonical_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        return text.encode("utf-8", errors="strict")
    except (UnicodeEncodeError, ValueError, TypeError) as exc:
        raise SchemaError("value cannot be encoded as canonical UTF-8 JSON") from exc


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _exact_keys(value: Mapping[str, Any], required: Iterable[str], *, where: str) -> None:
    expected = set(required)
    actual = set(value)
    if actual != expected:
        raise SchemaError(
            f"{where} keys mismatch; missing={sorted(expected-actual)} extra={sorted(actual-expected)}"
        )


def _text(value: Any, *, field: str, max_len: int = MAX_TEXT, allow_empty: bool = False) -> str:
    _assert_unicode_scalars(value, field=field)
    assert isinstance(value, str)
    if len(value) > max_len or (not allow_empty and not value):
        raise SchemaError(f"{field} length is invalid")
    if any(ord(ch) < 0x20 and ch != "\t" for ch in value):
        raise SchemaError(f"{field} contains control characters")
    return value


def _free_text(value: Any, *, field: str, max_len: int = 65536) -> str:
    _assert_unicode_scalars(value, field=field)
    assert isinstance(value, str)
    if len(value) > max_len:
        raise SchemaError(f"{field} is too long")
    return value


def _safe_id(value: Any, *, field: str) -> str:
    text = _text(value, field=field, max_len=96)
    if not _SAFE_ID.fullmatch(text):
        raise SchemaError(f"{field} contains unsupported characters")
    return text


def _jsonrpc_id(value: Any, *, field: str) -> str | int:
    if type(value) is int:
        if not (0 <= value <= MAX_JSONRPC_ID):
            raise SchemaError(f"{field} integer is out of range")
        return value
    if type(value) is str:
        return _safe_id(value, field=field)
    raise SchemaError(f"{field} must be a non-negative integer or safe string")


def _hex64(value: Any, *, field: str) -> str:
    if type(value) is not str or not _HEX_64.fullmatch(value):
        raise SchemaError(f"{field} must be lowercase SHA-256 hex")
    return value


def _integer(value: Any, *, field: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not (minimum <= value <= maximum):
        raise SchemaError(f"{field} must be an integer in [{minimum}, {maximum}]")
    return value


def _utc_second(value: Any, *, field: str) -> str:
    text = _text(value, field=field, max_len=20)
    try:
        parsed = dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except ValueError as exc:
        raise SchemaError(f"{field} must be canonical whole-second UTC") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise SchemaError(f"{field} must be canonical whole-second UTC")
    return text


def _decode_body(value: Any) -> bytes:
    text = _text(value, field="body_base64", max_len=((MAX_BODY_BYTES + 2)//3)*4 + 8, allow_empty=True)
    try:
        body = base64.b64decode(text.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise SchemaError("body_base64 must be canonical base64") from exc
    if len(body) > MAX_BODY_BYTES:
        raise SchemaError(f"response body exceeds {MAX_BODY_BYTES} bytes")
    if base64.b64encode(body).decode("ascii") != text:
        raise SchemaError("body_base64 is not canonical")
    return body


def _media_type(value: Any) -> str:
    text = _text(value, field="content_type", max_len=160).strip()
    media = text.split(";", 1)[0].strip().casefold()
    if not media or "/" not in media or any(ch.isspace() for ch in media):
        raise SchemaError("content_type has an invalid media type")
    return media


def _looks_html_bytes(body: bytes) -> bool:
    if not body:
        return False
    sample = body[:8192].decode("utf-8", errors="ignore").lstrip("\ufeff\x00 \t\r\n").casefold()
    if any(sample.startswith(marker) for marker in _HTML_ROOT_MARKERS + _HTML_STRUCTURAL_MARKERS):
        return True
    if sample.startswith("<!--"):
        close = sample.find("-->")
        if close >= 0:
            after = sample[close+3:].lstrip()
            return any(after.startswith(marker) for marker in _HTML_ROOT_MARKERS + ("<body", "<head"))
    return False


def _looks_login_bytes(body: bytes) -> bool:
    if not _looks_html_bytes(body):
        return False
    sample = body[:8192].decode("utf-8", errors="ignore").casefold()
    return any(marker in sample for marker in _LOGIN_MARKERS)


def _looks_embedded_html_text(text: str) -> bool:
    _assert_unicode_scalars(text, field="MCP text content")
    sample = text[:8192].casefold()
    if any(marker in sample for marker in _HTML_ROOT_MARKERS):
        return True
    return any(marker in sample for marker in _HTML_STRUCTURAL_MARKERS) and any(
        marker in sample for marker in _LOGIN_MARKERS
    )


def _parse_json_bytes(body: bytes) -> Any:
    try:
        return loads_strict(body.decode("utf-8", errors="strict"))
    except UnicodeDecodeError as exc:
        raise SchemaError("response JSON is not strict UTF-8") from exc


def _parse_sse_events(body: bytes) -> list[Any]:
    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise SchemaError("SSE body is not strict UTF-8") from exc
    events: list[str] = []
    pending: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line == "":
            if pending:
                events.append("\n".join(pending)); pending = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("data:"):
            data = line[5:]
            if data.startswith(" "):
                data = data[1:]
            pending.append(data)
    if pending:
        events.append("\n".join(pending))
    if not events:
        raise SchemaError("SSE response contains no data event")
    return [loads_strict(event) for event in events]


def _correlate_payload(parsed: Any, expected_id: str | int, *, sse: bool) -> tuple[Any | None, list[str]]:
    reasons: list[str] = []
    if not sse:
        if not isinstance(parsed, dict):
            return parsed, reasons
        if "id" not in parsed:
            reasons.append("JSON_RPC_RESPONSE_ID_MISSING")
            return parsed, reasons
        try:
            response_id = _jsonrpc_id(parsed["id"], field="response.id")
        except SchemaError:
            reasons.append("JSON_RPC_RESPONSE_ID_INVALID")
            return parsed, reasons
        if response_id != expected_id:
            reasons.append("JSON_RPC_RESPONSE_ID_MISMATCH")
        return parsed, reasons

    assert isinstance(parsed, list)
    matching: list[Any] = []
    cross = False
    malformed_response_id = False
    for event in parsed:
        if not isinstance(event, dict):
            reasons.append("SSE_EVENT_NOT_OBJECT")
            continue
        if "id" not in event:
            continue
        try:
            event_id = _jsonrpc_id(event["id"], field="SSE response.id")
        except SchemaError:
            malformed_response_id = True
            continue
        if event_id == expected_id:
            matching.append(event)
        else:
            cross = True
    if malformed_response_id:
        reasons.append("JSON_RPC_RESPONSE_ID_INVALID")
    if cross:
        reasons.append("JSON_RPC_CROSS_ID_RESPONSE")
    if not matching:
        reasons.append("JSON_RPC_CORRELATED_RESPONSE_MISSING")
        return None, reasons
    if len(matching) != 1:
        reasons.append("JSON_RPC_CORRELATED_RESPONSE_DUPLICATE")
        return None, reasons
    return matching[0], reasons


def _validate_mcp_result(result: Any, reasons: list[str], tags: set[str]) -> None:
    if not isinstance(result, dict):
        reasons.append("MCP_RESULT_NOT_OBJECT")
        return
    allowed = {"isError", "content"}
    if set(result) != allowed:
        reasons.append("MCP_RESULT_KEYS_INVALID")
    if "isError" not in result:
        reasons.append("MCP_IS_ERROR_MISSING")
    elif type(result["isError"]) is not bool:
        reasons.append("MCP_IS_ERROR_NOT_BOOL")
    elif result["isError"]:
        reasons.append("MCP_TOOL_ERROR"); tags.add("MCP_TOOL_ERROR")
    content = result.get("content")
    if not isinstance(content, list):
        reasons.append("MCP_CONTENT_NOT_LIST")
        return
    if not content:
        reasons.append("MCP_CONTENT_EMPTY")
        return
    for item in content:
        if not isinstance(item, dict):
            reasons.append("MCP_CONTENT_ITEM_NOT_OBJECT"); continue
        if set(item) != {"type", "text"}:
            reasons.append("MCP_CONTENT_ITEM_KEYS_INVALID")
        block_type = item.get("type")
        if block_type != "text":
            reasons.append("MCP_CONTENT_TYPE_UNSUPPORTED")
            continue
        try:
            text = _free_text(item.get("text"), field="MCP text content")
        except SchemaError:
            reasons.append("MCP_TEXT_CONTENT_INVALID")
            continue
        if _looks_embedded_html_text(text):
            reasons.append("MCP_WRAPPED_HTML"); tags.add("MCP_WRAPPED_HTML")


def classify_exchange(status: int, content_type: str, body: bytes, expected_jsonrpc_id: str | int) -> Classification:
    status = _integer(status, field="status", minimum=100, maximum=599)
    expected_id = _jsonrpc_id(expected_jsonrpc_id, field="expected_jsonrpc_id")
    media = _media_type(content_type)
    reasons: list[str] = []
    tags: set[str] = set()
    body_sha = sha256_bytes(body)

    if not (200 <= status <= 299):
        reasons.append("HTTP_STATUS_NOT_SUCCESS"); tags.add("HTTP_NON_2XX")

    raw_html = _looks_html_bytes(body)
    if raw_html:
        reasons.append("HTML_BODY")
        if 200 <= status <= 299:
            tags.add("HTTP_200_HTML")
            if _looks_login_bytes(body): tags.add("HTTP_200_LOGIN_HTML")
            if media == "application/json" or media.endswith("+json"):
                tags.add("HTTP_200_MISLABELED_HTML")

    payload: Any = None
    json_media = media == "application/json" or media.endswith("+json")
    sse_media = media == "text/event-stream"
    if 200 <= status <= 299 and not raw_html:
        if not (json_media or sse_media):
            reasons.append("UNSUPPORTED_SUCCESS_MEDIA_TYPE")
        else:
            try:
                parsed = _parse_sse_events(body) if sse_media else _parse_json_bytes(body)
                payload, correlation_reasons = _correlate_payload(parsed, expected_id, sse=sse_media)
                reasons.extend(correlation_reasons)
            except SchemaError:
                reasons.append("MALFORMED_STRUCTURED_BODY")
                if json_media: tags.add("MALFORMED_JSON")

    if payload is not None:
        if not isinstance(payload, dict):
            reasons.append("JSON_RPC_ENVELOPE_NOT_OBJECT")
        else:
            if payload.get("jsonrpc") != "2.0": reasons.append("JSON_RPC_VERSION_INVALID")
            has_error = "error" in payload and payload.get("error") is not None
            has_result = "result" in payload
            if has_error and has_result:
                reasons.append("JSON_RPC_RESULT_AND_ERROR")
            elif has_error:
                if set(payload) != {"jsonrpc", "id", "error"}: reasons.append("JSON_RPC_ENVELOPE_KEYS_INVALID")
                reasons.append("JSON_RPC_ERROR"); tags.add("JSON_RPC_ERROR")
            elif not has_result:
                reasons.append("JSON_RPC_RESULT_MISSING")
            else:
                if set(payload) != {"jsonrpc", "id", "result"}: reasons.append("JSON_RPC_ENVELOPE_KEYS_INVALID")
                _validate_mcp_result(payload.get("result"), reasons, tags)

    decision = "REJECT" if reasons else "ACCEPT"
    if decision == "ACCEPT": tags.add("VALID_CONTROL")
    return Classification(
        decision=decision,
        reasons=tuple(sorted(set(reasons))),
        tags=tuple(sorted(tags)),
        body_sha256=body_sha,
        body_bytes=len(body),
        media_type=media,
    )


def _normalize_case(value: Any, *, index: int) -> tuple[dict[str, Any], Classification]:
    if not isinstance(value, dict): raise SchemaError(f"cases[{index}] must be an object")
    _exact_keys(value, (
        "id", "family", "status", "content_type", "body_base64", "expected_jsonrpc_id",
        "observed_client_disposition", "client_event_sha256", "source_sha256",
    ), where=f"cases[{index}]")
    case_id = _safe_id(value["id"], field=f"cases[{index}].id")
    family = _text(value["family"], field=f"cases[{index}].family", max_len=64)
    if family not in REQUIRED_FAMILIES: raise SchemaError(f"cases[{index}].family is unsupported")
    status = _integer(value["status"], field=f"cases[{index}].status", minimum=100, maximum=599)
    content_type = _text(value["content_type"], field=f"cases[{index}].content_type", max_len=160)
    body = _decode_body(value["body_base64"])
    expected_id = _jsonrpc_id(value["expected_jsonrpc_id"], field=f"cases[{index}].expected_jsonrpc_id")
    disposition = _text(value["observed_client_disposition"], field=f"cases[{index}].observed_client_disposition", max_len=16)
    if disposition not in _DISPOSITIONS: raise SchemaError(f"cases[{index}].observed_client_disposition is unsupported")
    normalized = {
        "id": case_id,
        "family": family,
        "status": status,
        "content_type": content_type.strip(),
        "body_base64": base64.b64encode(body).decode("ascii"),
        "expected_jsonrpc_id": expected_id,
        "observed_client_disposition": disposition,
        "client_event_sha256": _hex64(value["client_event_sha256"], field=f"cases[{index}].client_event_sha256"),
        "source_sha256": _hex64(value["source_sha256"], field=f"cases[{index}].source_sha256"),
    }
    classification = classify_exchange(status, normalized["content_type"], body, expected_id)
    if family not in classification.tags:
        raise SchemaError(
            f"cases[{index}] declared family {family} is not supported by captured exchange; observed tags={list(classification.tags)}"
        )
    return normalized, classification


def normalize_bundle(bundle: Any) -> tuple[dict[str, Any], list[tuple[dict[str, Any], Classification]]]:
    if not isinstance(bundle, dict): raise SchemaError("capture bundle must be an object")
    _exact_keys(bundle, ("schema", "client", "captured_at", "cases"), where="bundle")
    if bundle["schema"] != CAPTURE_SCHEMA: raise SchemaError("unsupported capture schema")
    client = bundle["client"]
    if not isinstance(client, dict): raise SchemaError("client must be an object")
    _exact_keys(client, ("name", "version"), where="client")
    client_norm = {
        "name": _text(client["name"], field="client.name", max_len=120),
        "version": _text(client["version"], field="client.version", max_len=120),
    }
    captured_at = _utc_second(bundle["captured_at"], field="captured_at")
    cases = bundle["cases"]
    if not isinstance(cases, list) or not (1 <= len(cases) <= MAX_CASES):
        raise SchemaError(f"cases must contain between 1 and {MAX_CASES} entries")
    seen_ids: set[str] = set()
    source_generations: dict[str, tuple[Any, ...]] = {}
    client_generations: dict[str, tuple[Any, ...]] = {}
    normalized_cases: list[dict[str, Any]] = []
    evidence: list[tuple[dict[str, Any], Classification]] = []
    for index, raw_case in enumerate(cases):
        case, classification = _normalize_case(raw_case, index=index)
        if case["id"] in seen_ids: raise SchemaError(f"duplicate case id: {case['id']}")
        seen_ids.add(case["id"])
        source_sem = (case["status"], _media_type(case["content_type"]), classification.body_sha256, case["expected_jsonrpc_id"])
        prior_source = source_generations.setdefault(case["source_sha256"], source_sem)
        if prior_source != source_sem:
            raise SchemaError("source_sha256 commitment reused across contradictory source generations")
        client_sem = (case["observed_client_disposition"], case["source_sha256"])
        prior_client = client_generations.setdefault(case["client_event_sha256"], client_sem)
        if prior_client != client_sem:
            raise SchemaError("client_event_sha256 commitment reused across contradictory client generations")
        normalized_cases.append(case); evidence.append((case, classification))
    normalized = {"schema": CAPTURE_SCHEMA, "client": client_norm, "captured_at": captured_at, "cases": normalized_cases}
    return normalized, evidence


def compile_proof(bundle: Any) -> dict[str, Any]:
    normalized, evidence = normalize_bundle(bundle)
    covered = sorted({case["family"] for case, _ in evidence})
    missing = sorted(set(REQUIRED_FAMILIES) - set(covered))
    findings: list[dict[str, Any]] = []
    false_success_ids: list[str] = []
    mismatch_ids: list[str] = []
    for case, classification in evidence:
        expected = "SUCCESS" if classification.decision == "ACCEPT" else "ERROR"
        observed = case["observed_client_disposition"]
        matched = observed == expected
        if not matched:
            mismatch_ids.append(case["id"])
            if classification.decision == "REJECT" and observed == "SUCCESS": false_success_ids.append(case["id"])
        findings.append({
            "id": case["id"], "family": case["family"], "status": case["status"],
            "media_type": classification.media_type, "body_sha256": classification.body_sha256,
            "body_bytes": classification.body_bytes, "source_commitment_sha256": case["source_sha256"],
            "client_event_commitment_sha256": case["client_event_sha256"],
            "commitment_authentication": "CALLER_PROVIDED_UNVERIFIED",
            "policy_decision": classification.decision, "observed_client_disposition": observed,
            "client_matches_policy": matched, "reasons": list(classification.reasons),
        })
    if missing: decision = "HOLD_INCOMPLETE_MATRIX"
    elif false_success_ids: decision = "FALSE_SUCCESS_DETECTED"
    elif mismatch_ids: decision = "CLIENT_MISMATCH"
    else: decision = "SURVIVED"
    proof = {
        "policy_version": POLICY_VERSION,
        "client": normalized["client"],
        "captured_at": normalized["captured_at"],
        "capture_bundle_sha256": sha256_bytes(canonical_bytes(normalized)),
        "commitment_authority": "CALLER_PROVIDED_UNVERIFIED",
        "required_families": list(REQUIRED_FAMILIES), "covered_families": covered,
        "missing_families": missing, "case_count": len(findings), "decision": decision,
        "false_success_case_ids": sorted(false_success_ids), "mismatch_case_ids": sorted(mismatch_ids),
        "external_send_authorized": False, "production_certified": False, "findings": findings,
    }
    return {"schema": PROOF_SCHEMA, "proof": proof, "proof_sha256": sha256_bytes(canonical_bytes(proof))}


def verify_proof(bundle: Any, candidate: Any) -> bool:
    if not isinstance(candidate, dict): return False
    try:
        _exact_keys(candidate, ("schema", "proof", "proof_sha256"), where="proof envelope")
        if candidate["schema"] != PROOF_SCHEMA or not isinstance(candidate["proof"], dict): return False
        if _hex64(candidate["proof_sha256"], field="proof_sha256") != sha256_bytes(canonical_bytes(candidate["proof"])):
            return False
        expected = compile_proof(bundle)
        return canonical_bytes(candidate) == canonical_bytes(expected)
    except ProofError:
        return False
