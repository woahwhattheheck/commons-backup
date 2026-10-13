"""Observe one asynchronous peer turn without replaying its submission."""
from __future__ import annotations

import base64
import binascii
import re
import time
import urllib.parse


class UpstreamTurnError(RuntimeError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


def wait_peer_turn(base_url, peer, message, *, post_json, get_json,
                   cancelled=None, on_submitted=None) -> str:
    """Submit once, retain the handle, and long-poll the existing status endpoint.

    Transport failure after POST is indeterminate and is never retried. Status
    reads tolerate two transient failures and stop on a third consecutive failure.
    Cancellation stops this observer; the remote turn may continue.
    """
    if cancelled is not None and cancelled():
        raise InterruptedError("cancelled before submit")

    parsed = urllib.parse.urlsplit(base_url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment):
        raise ValueError("upstream base URL must be HTTP(S) without embedded credentials")
    base_url = base_url.rstrip("/")
    handle = {"upstream_request_id": None, "upstream_status_url": None}

    def failure(message, *, status="unknown", terminal=False, error=None):
        details = {**handle, "upstream_status": status, "upstream_terminal": terminal}
        if error is not None:
            details["upstream_error"] = error
        return UpstreamTurnError(message, details)

    payload = {"peer": peer, "async": True,
               "message_utf8_base64": base64.b64encode(message.encode("utf-8")).decode("ascii")}
    try:
        submitted = post_json(base_url + "/v1/message", payload, timeout=30.0)
    except Exception as exc:
        raise failure("upstream submission response unavailable; submission was not replayed",
                      error=type(exc).__name__) from exc
    if not isinstance(submitted, dict):
        raise failure("invalid upstream submission response; submission was not replayed")

    request_id = submitted.get("request_id")
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
        raise failure("upstream submission returned no usable request handle; submission was not replayed")
    status_url = f"{base_url}/v1/requests/{urllib.parse.quote(request_id, safe='')}"
    handle.update(upstream_request_id=request_id, upstream_status_url=status_url)
    if on_submitted is not None:
        on_submitted(dict(handle))
    if submitted.get("ok") is not True:
        raise failure("upstream did not acknowledge submission; retain the handle before follow-up")

    consecutive_failures = 0
    while True:
        if cancelled is not None and cancelled():
            raise InterruptedError("observation stopped; remote work may continue")
        try:
            response = get_json(status_url + "?wait_ms=50000", timeout=60.0)
        except Exception as exc:
            consecutive_failures += 1
            if consecutive_failures >= 3:
                raise failure("upstream status reads failed; remote work may continue",
                              error=type(exc).__name__) from exc
            time.sleep(float(consecutive_failures))
            continue

        if not isinstance(response, dict) or response.get("request_id") != request_id:
            raise failure("upstream status response has no matching request handle")
        event = response.get("event")
        if not isinstance(event, dict) or event.get("request_id") != request_id:
            raise failure("upstream status event has no matching request handle")
        status = event.get("status")
        if not isinstance(status, str) or status not in {"queued", "running", "cancel_requested", "completed", "error", "cancelled", "interrupted"}:
            raise failure("upstream returned an unrecognized request state")
        if response.get("ok") is not True:
            raise failure("upstream status endpoint reported an error")
        consecutive_failures = 0
        if status in {"queued", "running", "cancel_requested"}:
            continue

        if status == "completed":
            if "reply_utf8_base64" in event:
                try:
                    encoded = event["reply_utf8_base64"]
                    if not isinstance(encoded, str):
                        raise TypeError("reply encoding must be text")
                    return base64.b64decode(encoded, validate=True).decode("utf-8")
                except (binascii.Error, UnicodeError, TypeError, ValueError) as exc:
                    raise failure("upstream completed with an invalid UTF-8 reply",
                                  status=status, terminal=True) from exc
            reply = event.get("reply")
            if isinstance(reply, str):
                return reply
            raise failure("upstream completed without reply text", status=status, terminal=True)

        # Keep the provider error class without copying arbitrary output into logs.
        error = event.get("error")
        if not isinstance(error, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,127}", error):
            error = "upstream_" + status
        raise failure(f"upstream work ended with status {status}: {error}",
                      status=status, terminal=True, error=error)
