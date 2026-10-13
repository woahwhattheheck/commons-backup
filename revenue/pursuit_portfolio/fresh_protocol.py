"""Bounded canonical protocol for the isolated current-authority worker."""
from __future__ import annotations

import base64
import json
from typing import Any, Mapping

from .core import CompiledPortfolio, PortfolioError
from .current import AuthorizedPortfolio
from .host_kernel import HostAuthorizedPortfolio
from .fresh_exec import WORKER_LIMIT


ARTIFACT_KEYS = frozenset(
    {"authority", "current_receipt", "host_seal", "markdown", "receipt", "result"}
)
VALUE_KEYS = frozenset(
    {"authority", "current_receipt", "host_seal", "receipt", "result"}
)


def canonical_json(value: Any, *, _dumps=json.dumps, _error=PortfolioError) -> bytes:
    try:
        return (
            _dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise _error("fresh worker request is not canonical JSON") from exc


def decode_response(
    raw: bytes,
    *,
    _loads=json.loads,
    _json_error=json.JSONDecodeError,
    _error=PortfolioError,
    _limit=WORKER_LIMIT,
) -> dict[str, Any]:
    if type(raw) is not bytes or len(raw) > _limit:
        raise _error("fresh worker response exceeds byte bound")
    try:
        value = _loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, _json_error) as exc:
        raise _error("fresh worker returned invalid JSON") from exc
    if type(value) is not dict or type(value.get("ok")) is not bool:
        raise _error("fresh worker returned malformed response")
    if not value["ok"]:
        message = value.get("error")
        if type(message) is not str or not message:
            message = "operation rejected"
        raise _error(f"fresh current authority: {message[:2000]}")
    return value


def strict_b64decode(
    value: Any,
    where: str,
    *,
    _decode=base64.b64decode,
    _error=PortfolioError,
    _limit=WORKER_LIMIT,
) -> bytes:
    if type(value) is not str:
        raise _error(f"fresh worker {where}: base64 text required")
    try:
        raw = _decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise _error(f"fresh worker {where}: invalid base64") from exc
    if len(raw) > _limit:
        raise _error(f"fresh worker {where}: artifact exceeds byte bound")
    return raw


def rebuild_compile(
    value: Mapping[str, Any],
    *,
    _decode=strict_b64decode,
    _Compiled=CompiledPortfolio,
    _Authorized=AuthorizedPortfolio,
    _Host=HostAuthorizedPortfolio,
    _error=PortfolioError,
    _artifact_keys=ARTIFACT_KEYS,
    _value_keys=VALUE_KEYS,
) -> HostAuthorizedPortfolio:
    if set(value) != {"ok", "artifacts", "values"}:
        raise _error("fresh worker compile response has wrong key set")
    artifacts = value["artifacts"]
    values = value["values"]
    if type(artifacts) is not dict or set(artifacts) != set(_artifact_keys):
        raise _error("fresh worker compile artifacts have wrong key set")
    if type(values) is not dict or set(values) != set(_value_keys):
        raise _error("fresh worker compile values have wrong key set")
    decoded = {name: _decode(artifacts[name], name) for name in _artifact_keys}
    for name in _value_keys:
        if type(values[name]) is not dict:
            raise _error(f"fresh worker compile value {name} must be an object")
    compiled = _Compiled(
        result=dict(values["result"]),
        result_bytes=decoded["result"],
        markdown_bytes=decoded["markdown"],
        receipt=dict(values["receipt"]),
        receipt_bytes=decoded["receipt"],
    )
    authorized = _Authorized(
        compiled=compiled,
        authority=dict(values["authority"]),
        authority_bytes=decoded["authority"],
        current_receipt=dict(values["current_receipt"]),
        current_receipt_bytes=decoded["current_receipt"],
    )
    return _Host(
        authorized=authorized,
        host_seal=dict(values["host_seal"]),
        host_seal_bytes=decoded["host_seal"],
    )
