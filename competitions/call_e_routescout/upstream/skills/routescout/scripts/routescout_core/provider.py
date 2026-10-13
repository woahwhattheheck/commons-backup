from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Mapping

from .contracts import RouteScoutError, OFFICIAL_API_ORIGIN, TERMINAL, approval_token, idempotency_key, validate_inquiry
from .planning import build_create_request
from .results import reconcile


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Fail closed before urllib can construct or issue a redirected request."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RouteScoutError(f"CALL-E API redirect refused ({code})")


class CalleApi:
    def __init__(self, api_key: str, timeout: int = 30):
        if not api_key:
            raise RouteScoutError("CALLE_API_KEY is not set")
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Mapping[str, Any] | None = None,
                 headers: Mapping[str, str] | None = None) -> dict[str, Any]:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
        req = urllib.request.Request(OFFICIAL_API_ORIGIN + path, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        opener = urllib.request.build_opener(_RejectRedirects())
        try:
            with opener.open(req, timeout=self.timeout) as response:
                parsed = json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise RouteScoutError(f"CALL-E HTTP {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise RouteScoutError(f"CALL-E API unreachable: {exc.reason}") from None
        if not isinstance(parsed, dict):
            raise RouteScoutError("CALL-E response must be JSON object")
        return parsed

    def create(self, inquiry: Mapping[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST", "/v1/calls", build_create_request(inquiry),
            {"Idempotency-Key": idempotency_key(inquiry)},
        )

    def get(self, call_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", call_id):
            raise RouteScoutError("call_id: invalid")
        return self._request("GET", f"/v1/calls/{call_id}")

    def wait(self, call_id: str, max_seconds: int = 1800, poll_seconds: float = 5.0) -> dict[str, Any]:
        deadline = time.time() + max_seconds
        while True:
            call = self.get(call_id)
            if call.get("status") in TERMINAL:
                return call
            if time.time() >= deadline:
                raise RouteScoutError(
                    f"call {call_id} is still non-terminal; resume by call id instead of creating another call"
                )
            time.sleep(poll_seconds)


def run_live(inquiry: Mapping[str, Any], confirm_call: str) -> tuple[str, dict[str, Any]]:
    i = validate_inquiry(inquiry)
    if confirm_call != approval_token(i):
        raise RouteScoutError("approval token does not match exact inquiry bytes; rerun preview")
    api = CalleApi(os.environ.get("CALLE_API_KEY", ""))
    created = api.create(i)  # exactly one POST; deterministic idempotency key
    call_id = created.get("id")
    if not isinstance(call_id, str) or not call_id:
        raise RouteScoutError(
            "CALL-E create response lacked call id; do not retry blindly—inspect provider state using the idempotency key"
        )
    terminal = api.wait(call_id)
    return call_id, reconcile(i, terminal, expected_call_id=call_id)
