#!/usr/bin/env python3
"""Offline verifier for Commons MCP Conformance receipts.

The verifier performs no network access. It validates strict JSON syntax, the
receipt's canonical SHA-256, public-safe endpoint labeling, discovery/page-ledger
shape, parity/status consistency, and optional explicit tool-result hashes. Its
own machine-readable verification receipt is hash-bound as well.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

RECEIPT_SCHEMA = "commons-mcp-conformance-receipt-v1"
VERIFICATION_SCHEMA = "commons-mcp-conformance-verification-v1"
DISCOVERY_METHODS = ("tools/list", "resources/list", "prompts/list")
TRANSPORT_FIELDS = (
    "http_status",
    "content_type",
    "request_sha256",
    "response_sha256",
    "response_bytes",
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class StrictJSONError(ValueError):
    """Raised when JSON is ambiguous or outside the interoperable JSON subset."""


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError("duplicate object key")
        result[key] = value
    return result


def _reject_constant(_raw: str) -> Any:
    raise StrictJSONError("non-finite JSON number")


def parse_json_strict(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise StrictJSONError("input is not valid UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_object_no_duplicates,
            parse_constant=_reject_constant,
        )
    except StrictJSONError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise StrictJSONError("input is not valid strict JSON") from exc


def _is_int(value: Any) -> bool:
    return type(value) is int


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _add_error(
    errors: list[dict[str, str]],
    category: str,
    code: str,
    path: str,
    message: str,
) -> None:
    errors.append(
        {
            "category": category,
            "code": code,
            "path": path,
            "message": message,
        }
    )


def _validate_hash(
    value: Any,
    *,
    path: str,
    errors: list[dict[str, str]],
    category: str = "STRUCTURE",
) -> bool:
    if _is_sha256(value):
        return True
    _add_error(errors, category, "INVALID_SHA256", path, "expected lowercase 64-character SHA-256")
    return False


def _validate_error_row(value: Any, *, path: str, errors: list[dict[str, str]]) -> bool:
    if not isinstance(value, dict):
        _add_error(errors, "STRUCTURE", "INVALID_ERROR_ROW", path, "expected error object")
        return False
    ok = True
    if not isinstance(value.get("code"), str) or not value.get("code"):
        _add_error(errors, "STRUCTURE", "INVALID_ERROR_CODE", path + ".code", "expected non-empty error code")
        ok = False
    if not isinstance(value.get("message"), str) or not value.get("message"):
        _add_error(errors, "STRUCTURE", "INVALID_ERROR_MESSAGE", path + ".message", "expected non-empty error message")
        ok = False
    return ok


def _validate_transport(value: Any, *, path: str, errors: list[dict[str, str]]) -> bool:
    if not isinstance(value, dict):
        _add_error(errors, "STRUCTURE", "INVALID_TRANSPORT", path, "expected transport object")
        return False
    ok = True
    status = value.get("http_status")
    if not _is_int(status) or not 100 <= status <= 599:
        _add_error(errors, "STRUCTURE", "INVALID_HTTP_STATUS", path + ".http_status", "expected HTTP status integer")
        ok = False
    if not isinstance(value.get("content_type"), str) or not value.get("content_type"):
        _add_error(errors, "STRUCTURE", "INVALID_CONTENT_TYPE", path + ".content_type", "expected non-empty content type")
        ok = False
    if not _validate_hash(value.get("request_sha256"), path=path + ".request_sha256", errors=errors):
        ok = False
    if not _validate_hash(value.get("response_sha256"), path=path + ".response_sha256", errors=errors):
        ok = False
    response_bytes = value.get("response_bytes")
    if not _is_int(response_bytes) or response_bytes < 0:
        _add_error(errors, "STRUCTURE", "INVALID_RESPONSE_BYTES", path + ".response_bytes", "expected non-negative byte count")
        ok = False
    return ok


def _validate_string_set(
    value: Any,
    *,
    path: str,
    errors: list[dict[str, str]],
) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        _add_error(errors, "STRUCTURE", "INVALID_NAME_SET", path, "expected list of non-empty strings")
        return None
    if value != sorted(set(value)):
        _add_error(errors, "SEMANTICS", "NONCANONICAL_NAME_SET", path, "expected sorted unique strings")
        return None
    return list(value)


def _validate_endpoint(value: Any, *, errors: list[dict[str, str]]) -> None:
    if not isinstance(value, str) or not value:
        _add_error(errors, "STRUCTURE", "INVALID_ENDPOINT", "endpoint", "expected non-empty endpoint string")
        return
    try:
        parsed = urllib.parse.urlsplit(value)
        _ = parsed.port
    except (TypeError, ValueError):
        _add_error(errors, "PRIVACY", "INVALID_PUBLIC_ENDPOINT", "endpoint", "endpoint label is not a valid public HTTP(S) URL")
        return
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        _add_error(errors, "PRIVACY", "INVALID_PUBLIC_ENDPOINT", "endpoint", "endpoint label must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        _add_error(errors, "PRIVACY", "ENDPOINT_USERINFO_PRESENT", "endpoint", "public endpoint label must omit URL userinfo")
    if parsed.query:
        _add_error(errors, "PRIVACY", "ENDPOINT_QUERY_PRESENT", "endpoint", "public endpoint label must omit URL query")
    if parsed.fragment:
        _add_error(errors, "PRIVACY", "ENDPOINT_FRAGMENT_PRESENT", "endpoint", "public endpoint label must omit URL fragment")


def _validate_discovery_current(
    discovery: dict[str, Any],
    *,
    errors: list[dict[str, str]],
) -> None:
    for method in DISCOVERY_METHODS:
        path = "discovery." + method
        row = discovery.get(method)
        if not isinstance(row, dict):
            _add_error(errors, "STRUCTURE", "INVALID_DISCOVERY_ROW", path, "expected discovery object")
            continue
        state = row.get("state")
        if state not in {"SUPPORTED", "UNSUPPORTED", "FAILED"}:
            _add_error(errors, "STRUCTURE", "INVALID_DISCOVERY_STATE", path + ".state", "unexpected discovery state")
            continue
        if "cursor" in row or "nextCursor" in row:
            _add_error(errors, "PRIVACY", "RAW_CURSOR_PRESENT", path, "durable discovery row must not include raw cursor material")

        complete = row.get("complete")
        page_count = row.get("page_count")
        pages = row.get("pages")
        if type(complete) is not bool:
            _add_error(errors, "STRUCTURE", "INVALID_DISCOVERY_COMPLETE", path + ".complete", "expected boolean")
        if not _is_int(page_count) or page_count < 0:
            _add_error(errors, "STRUCTURE", "INVALID_PAGE_COUNT", path + ".page_count", "expected non-negative integer")
        if not isinstance(pages, list):
            _add_error(errors, "STRUCTURE", "INVALID_PAGES", path + ".pages", "expected page list")
            pages = []
        if _is_int(page_count) and page_count >= 0 and page_count != len(pages):
            _add_error(errors, "SEMANTICS", "PAGE_COUNT_MISMATCH", path + ".page_count", "page_count must equal pages length")

        total_items = 0
        pages_valid = True
        for index, page in enumerate(pages, 1):
            page_path = f"{path}.pages[{index - 1}]"
            if not isinstance(page, dict):
                _add_error(errors, "STRUCTURE", "INVALID_PAGE", page_path, "expected page evidence object")
                pages_valid = False
                continue
            if "cursor" in page or "nextCursor" in page:
                _add_error(errors, "PRIVACY", "RAW_CURSOR_PRESENT", page_path, "page evidence must not include raw cursor material")
            if page.get("page") != index:
                _add_error(errors, "SEMANTICS", "NONSEQUENTIAL_PAGE", page_path + ".page", "pages must be numbered from 1 without gaps")
                pages_valid = False
            item_count = page.get("item_count")
            if not _is_int(item_count) or item_count < 0:
                _add_error(errors, "STRUCTURE", "INVALID_ITEM_COUNT", page_path + ".item_count", "expected non-negative item count")
                pages_valid = False
            else:
                total_items += item_count
            if not _validate_transport(page, path=page_path, errors=errors):
                pages_valid = False

        if state == "SUPPORTED":
            if complete is not True:
                _add_error(errors, "SEMANTICS", "SUPPORTED_NOT_COMPLETE", path + ".complete", "supported discovery must be complete")
            if not _is_int(page_count) or page_count < 1:
                _add_error(errors, "SEMANTICS", "SUPPORTED_WITHOUT_PAGE", path + ".page_count", "supported discovery must contain at least one page")
            item_count = row.get("item_count")
            if not _is_int(item_count) or item_count < 0:
                _add_error(errors, "STRUCTURE", "INVALID_ITEM_COUNT", path + ".item_count", "expected aggregate item count")
            elif pages_valid and item_count != total_items:
                _add_error(errors, "SEMANTICS", "ITEM_COUNT_MISMATCH", path + ".item_count", "aggregate item count must equal page item counts")
            if pages and isinstance(pages[0], dict):
                for field in TRANSPORT_FIELDS:
                    if row.get(field) != pages[0].get(field):
                        _add_error(errors, "SEMANTICS", "FIRST_PAGE_PROJECTION_MISMATCH", path + "." + field, "top-level discovery transport must project page 1")
        elif state == "UNSUPPORTED":
            if complete is not False:
                _add_error(errors, "SEMANTICS", "UNSUPPORTED_COMPLETE", path + ".complete", "unsupported discovery cannot be complete")
            if page_count != 0 or pages:
                _add_error(errors, "SEMANTICS", "UNSUPPORTED_WITH_PAGES", path, "unsupported discovery must fail before any successful page")
            _validate_error_row(row.get("error"), path=path + ".error", errors=errors)
        else:
            if complete is not False:
                _add_error(errors, "SEMANTICS", "FAILED_COMPLETE", path + ".complete", "failed discovery cannot be complete")
            _validate_error_row(row.get("error"), path=path + ".error", errors=errors)


def _validate_discovery_legacy(
    discovery: dict[str, Any],
    *,
    errors: list[dict[str, str]],
) -> None:
    for method in DISCOVERY_METHODS:
        path = "discovery." + method
        row = discovery.get(method)
        if not isinstance(row, dict):
            _add_error(errors, "STRUCTURE", "INVALID_DISCOVERY_ROW", path, "expected discovery object")
            continue
        state = row.get("state")
        if state == "SUPPORTED":
            _validate_transport(row, path=path, errors=errors)
        elif state in {"UNSUPPORTED", "FAILED"}:
            _validate_error_row(row.get("error"), path=path + ".error", errors=errors)
        else:
            _add_error(errors, "STRUCTURE", "INVALID_DISCOVERY_STATE", path + ".state", "unexpected discovery state")


def _validate_tool_call(value: Any, *, errors: list[dict[str, str]]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        _add_error(errors, "STRUCTURE", "INVALID_TOOL_CALL", "tool_call", "expected null or tool-call object")
        return None
    name = value.get("name")
    if not isinstance(name, str) or not name:
        _add_error(errors, "STRUCTURE", "INVALID_TOOL_NAME", "tool_call.name", "expected non-empty tool name")
    _validate_hash(value.get("request_sha256"), path="tool_call.request_sha256", errors=errors)
    state = value.get("state")
    if state == "RETURNED":
        _validate_transport(value.get("transport"), path="tool_call.transport", errors=errors)
        _validate_hash(value.get("result_sha256"), path="tool_call.result_sha256", errors=errors)
        result_bytes = value.get("result_bytes")
        if not _is_int(result_bytes) or result_bytes < 0:
            _add_error(errors, "STRUCTURE", "INVALID_RESULT_BYTES", "tool_call.result_bytes", "expected non-negative byte count")
        if "result" in value:
            try:
                rendered = canonical_json(value["result"])
            except (TypeError, ValueError):
                _add_error(errors, "STRUCTURE", "NONCANONICAL_RESULT", "tool_call.result", "included result is not canonical JSON data")
            else:
                if value.get("result_sha256") != sha256_text(rendered):
                    _add_error(errors, "INTEGRITY", "TOOL_RESULT_HASH_MISMATCH", "tool_call.result_sha256", "included result does not match result_sha256")
                if result_bytes != len(rendered.encode("utf-8")):
                    _add_error(errors, "INTEGRITY", "TOOL_RESULT_SIZE_MISMATCH", "tool_call.result_bytes", "included result does not match result_bytes")
    elif state == "FAILED":
        _validate_error_row(value.get("error"), path="tool_call.error", errors=errors)
    else:
        _add_error(errors, "STRUCTURE", "INVALID_TOOL_CALL_STATE", "tool_call.state", "expected RETURNED or FAILED")
    return state if isinstance(state, str) else None


def _finalize(result: dict[str, Any], *, file_sha256: str | None = None) -> dict[str, Any]:
    if file_sha256 is not None:
        result["subject_file_sha256"] = file_sha256
    result.pop("verification_sha256", None)
    result["verification_sha256"] = sha256_text(canonical_json(result))
    return result


def verify_receipt(receipt: Any) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    subject_canonical_sha256: str | None = None
    if isinstance(receipt, dict):
        try:
            subject_canonical_sha256 = sha256_text(canonical_json(receipt))
        except (TypeError, ValueError):
            _add_error(errors, "STRUCTURE", "NONCANONICAL_JSON_VALUE", "$", "receipt contains a value outside canonical JSON")
    else:
        _add_error(errors, "STRUCTURE", "INVALID_ROOT", "$", "receipt must be a JSON object")

    if not isinstance(receipt, dict):
        return _finalize({
            "schema": VERIFICATION_SCHEMA,
            "valid": False,
            "profile": "invalid",
            "subject_canonical_sha256": subject_canonical_sha256,
            "subject_receipt_sha256": None,
            "checks": {"integrity": False, "privacy": True, "structure": False, "semantics": True},
            "errors": errors,
        })

    if receipt.get("schema") != RECEIPT_SCHEMA:
        _add_error(errors, "STRUCTURE", "UNSUPPORTED_SCHEMA", "schema", "expected Commons MCP conformance receipt v1")

    claimed_hash = receipt.get("receipt_sha256")
    hash_shape_ok = _validate_hash(claimed_hash, path="receipt_sha256", errors=errors, category="INTEGRITY")
    if hash_shape_ok:
        unsigned = dict(receipt)
        unsigned.pop("receipt_sha256", None)
        try:
            expected_hash = sha256_text(canonical_json(unsigned))
        except (TypeError, ValueError):
            expected_hash = None
        if expected_hash is None or claimed_hash != expected_hash:
            _add_error(errors, "INTEGRITY", "RECEIPT_HASH_MISMATCH", "receipt_sha256", "receipt_sha256 does not match canonical unsigned JSON")

    _validate_endpoint(receipt.get("endpoint"), errors=errors)
    _validate_hash(receipt.get("input_sha256"), path="input_sha256", errors=errors)

    status = receipt.get("status")
    if status not in {"PASS", "PARTIAL", "FAIL"}:
        _add_error(errors, "STRUCTURE", "INVALID_STATUS", "status", "expected PASS, PARTIAL, or FAIL")

    required_tools = _validate_string_set(receipt.get("required_tools"), path="required_tools", errors=errors)
    for field in ("tool_names", "resource_names", "prompt_names"):
        if field in receipt:
            _validate_string_set(receipt.get(field), path=field, errors=errors)

    root_errors = receipt.get("errors")
    if not isinstance(root_errors, list):
        _add_error(errors, "STRUCTURE", "INVALID_ERRORS", "errors", "expected list")
        root_errors = []
    else:
        for index, row in enumerate(root_errors):
            _validate_error_row(row, path=f"errors[{index}]", errors=errors)

    transport = receipt.get("transport")
    if not isinstance(transport, dict):
        _add_error(errors, "STRUCTURE", "INVALID_TRANSPORT_LEDGER", "transport", "expected transport object")
    else:
        if "initialize" in transport:
            _validate_transport(transport.get("initialize"), path="transport.initialize", errors=errors)
        if "initialized" in transport:
            initialized = transport.get("initialized")
            if isinstance(initialized, dict) and initialized.get("state") == "FAILED":
                _validate_error_row(initialized.get("error"), path="transport.initialized.error", errors=errors)
            else:
                _validate_transport(initialized, path="transport.initialized", errors=errors)

    discovery = receipt.get("discovery")
    if not isinstance(discovery, dict):
        _add_error(errors, "STRUCTURE", "INVALID_DISCOVERY", "discovery", "expected discovery object")
        discovery = {}

    if discovery:
        missing_methods = [method for method in DISCOVERY_METHODS if method not in discovery]
        extra_methods = sorted(set(discovery) - set(DISCOVERY_METHODS))
        if missing_methods or extra_methods:
            _add_error(errors, "SEMANTICS", "DISCOVERY_METHOD_SET_MISMATCH", "discovery", "expected exactly tools/list, resources/list, and prompts/list")
        rows = [discovery.get(method) for method in DISCOVERY_METHODS]
        current_markers = [
            isinstance(row, dict) and all(key in row for key in ("complete", "page_count", "pages"))
            for row in rows
        ]
        if all(current_markers):
            profile = "paginated-v1"
            _validate_discovery_current(discovery, errors=errors)
        elif not any(current_markers):
            profile = "legacy-single-page-v1"
            _validate_discovery_legacy(discovery, errors=errors)
        else:
            profile = "mixed-invalid"
            _add_error(errors, "SEMANTICS", "MIXED_DISCOVERY_PROFILE", "discovery", "cannot mix legacy and paginated discovery rows")
    else:
        profile = "terminal-failure-v1"

    if profile == "paginated-v1":
        limits = receipt.get("discovery_limits")
        if not isinstance(limits, dict):
            _add_error(errors, "STRUCTURE", "INVALID_DISCOVERY_LIMITS", "discovery_limits", "expected discovery limits object")
        else:
            limit = limits.get("max_pages_per_method")
            if not _is_int(limit) or limit < 1:
                _add_error(errors, "STRUCTURE", "INVALID_DISCOVERY_LIMIT", "discovery_limits.max_pages_per_method", "expected positive integer")

    tool_call_state = _validate_tool_call(receipt.get("tool_call"), errors=errors)

    tool_names = receipt.get("tool_names") if isinstance(receipt.get("tool_names"), list) else []
    required = required_tools or []
    parity = receipt.get("tool_parity")
    missing: list[str] = []
    if discovery and not isinstance(parity, dict):
        _add_error(errors, "STRUCTURE", "INVALID_TOOL_PARITY", "tool_parity", "expected parity object")
    elif isinstance(parity, dict):
        present_value = _validate_string_set(parity.get("present"), path="tool_parity.present", errors=errors)
        missing_value = _validate_string_set(parity.get("missing"), path="tool_parity.missing", errors=errors)
        present = present_value or []
        missing = missing_value or []
        tools_row = discovery.get("tools/list") if isinstance(discovery.get("tools/list"), dict) else {}
        tools_supported_complete = (
            profile == "paginated-v1"
            and tools_row.get("state") == "SUPPORTED"
            and tools_row.get("complete") is True
        )
        if profile == "paginated-v1":
            authoritative = parity.get("authoritative")
            if type(authoritative) is not bool:
                _add_error(errors, "STRUCTURE", "INVALID_PARITY_AUTHORITY", "tool_parity.authoritative", "expected boolean")
            expected_authority = tools_supported_complete
            if authoritative is not expected_authority:
                _add_error(errors, "SEMANTICS", "PARITY_AUTHORITY_MISMATCH", "tool_parity.authoritative", "parity authority must match complete tools discovery")
            if tools_supported_complete:
                expected_present = sorted(set(required) & set(tool_names))
                expected_missing = sorted(set(required) - set(tool_names))
            else:
                expected_present = []
                expected_missing = []
            if present != expected_present or missing != expected_missing:
                _add_error(errors, "SEMANTICS", "PARITY_SET_MISMATCH", "tool_parity", "present/missing sets contradict required tools and discovered tool names")
            expected_complete = tools_supported_complete and not expected_missing
            if parity.get("complete") is not expected_complete:
                _add_error(errors, "SEMANTICS", "PARITY_COMPLETE_MISMATCH", "tool_parity.complete", "parity complete flag is inconsistent")
        elif profile == "legacy-single-page-v1":
            expected_present = sorted(set(required) & set(tool_names))
            expected_missing = sorted(set(required) - set(tool_names))
            if present != expected_present or missing != expected_missing:
                _add_error(errors, "SEMANTICS", "PARITY_SET_MISMATCH", "tool_parity", "legacy present/missing sets contradict required tools and discovered tool names")
            if parity.get("complete") is not (not expected_missing):
                _add_error(errors, "SEMANTICS", "PARITY_COMPLETE_MISMATCH", "tool_parity.complete", "legacy parity complete flag is inconsistent")

    if status in {"PASS", "PARTIAL", "FAIL"}:
        if root_errors:
            expected_status = "FAIL"
        elif discovery:
            discovery_states = [
                row.get("state") if isinstance(row, dict) else None
                for row in (discovery.get(method) for method in DISCOVERY_METHODS)
            ]
            if "FAILED" in discovery_states or tool_call_state == "FAILED":
                expected_status = "FAIL"
            elif missing or "UNSUPPORTED" in discovery_states:
                expected_status = "PARTIAL"
            else:
                expected_status = "PASS"
        else:
            expected_status = "FAIL"
        if status != expected_status:
            _add_error(errors, "SEMANTICS", "STATUS_MISMATCH", "status", "status contradicts receipt failure, discovery, parity, or tool-call state")

    categories = {error["category"] for error in errors}
    result = {
        "schema": VERIFICATION_SCHEMA,
        "valid": not errors,
        "profile": profile,
        "subject_canonical_sha256": subject_canonical_sha256,
        "subject_receipt_sha256": claimed_hash if _is_sha256(claimed_hash) else None,
        "checks": {
            "integrity": "INTEGRITY" not in categories,
            "privacy": "PRIVACY" not in categories,
            "structure": "STRUCTURE" not in categories,
            "semantics": "SEMANTICS" not in categories,
        },
        "errors": errors,
    }
    return _finalize(result)


def verify_bytes(raw: bytes) -> dict[str, Any]:
    file_sha = sha256_bytes(raw)
    try:
        value = parse_json_strict(raw)
    except StrictJSONError as exc:
        result = {
            "schema": VERIFICATION_SCHEMA,
            "valid": False,
            "profile": "invalid-json",
            "subject_canonical_sha256": None,
            "subject_receipt_sha256": None,
            "checks": {"integrity": False, "privacy": True, "structure": False, "semantics": True},
            "errors": [{"category": "STRUCTURE", "code": "INVALID_STRICT_JSON", "path": "$", "message": str(exc)}],
        }
        return _finalize(result, file_sha256=file_sha)
    result = verify_receipt(value)
    return _finalize(result, file_sha256=file_sha)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", help="path to an MCP Conformance JSON receipt")
    parser.add_argument("--output", help="write verification JSON to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        raw = Path(args.receipt).read_bytes()
    except OSError as exc:
        sys.stderr.write("receipt read failed: %s\n" % type(exc).__name__)
        return 2
    report = verify_bytes(raw)
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        try:
            Path(args.output).write_text(rendered, encoding="utf-8")
        except OSError as exc:
            sys.stderr.write("verification write failed: %s\n" % type(exc).__name__)
            return 2
    sys.stdout.write(rendered)
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
