"""Classify a saved GitHub provider outcome without network access or retries.

This is an advisory, single-observation classifier, not a token router or a
substitute for a fresh provider readback. Raw messages and headers are never
repeated in its output, to avoid echoing credentials or private payloads.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import sys
from collections.abc import Mapping
from typing import Any

SCHEMA = "commons-github-provider-outcome/v1"
_PERMISSION_MARKERS = (
    "resource not accessible by integration",
    "integration does not have permission",
)
_SECONDARY_MARKERS = (
    "secondary rate limit",
    "secondary rate-limit",
    "abuse detection mechanism",
)
_PRIMARY_MARKERS = (
    "api rate limit exceeded",
    "primary rate limit",
)
_SAFETY_MARKERS = (
    "blocked by openai's safety checks",
    "blocked by openai’s safety checks",
)
_HTTP_STATUS = re.compile(r"^[1-5][0-9]{2}$")


def _status(value: Any) -> int | None:
    if value is None:
        return None
    if type(value) is int and 100 <= value <= 599:
        return value
    if isinstance(value, str) and _HTTP_STATUS.fullmatch(value.strip()):
        return int(value.strip())
    raise ValueError("invalid HTTP status")


def _headers(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("headers must be an object")
    headers: dict[str, str] = {}
    for key, val in value.items():
        if not isinstance(key, str) or not isinstance(val, (str, int)):
            continue
        if len(key) <= 128 and len(str(val)) <= 256:
            headers[key.casefold()] = str(val).strip()
    return headers


def _seconds(value: str | None) -> int | None:
    if value is None or not re.fullmatch(r"[0-9]{1,8}", value):
        return None
    return int(value)


def _reset_utc(value: str | None) -> str | None:
    if value is None or not re.fullmatch(r"[0-9]{9,11}", value):
        return None
    try:
        return datetime.fromtimestamp(int(value), timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None


def classify(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Return an evidence-bound disposition for one saved provider observation.

    Input: operation_kind = read/write, http_status = int or numeric string,
    message = provider error text, headers = HTTP response headers, and optional
    provider_reached = explicit boolean. Ambiguous writes always require
    readback before a repeated mutation.
    """
    if not isinstance(observation, Mapping):
        raise ValueError("observation must be an object")
    operation_kind = observation.get("operation_kind", "read")
    if operation_kind not in ("read", "write"):
        raise ValueError("operation_kind must be read or write")
    reached = observation.get("provider_reached")
    if reached is not None and type(reached) is not bool:
        raise ValueError("provider_reached must be boolean when supplied")
    status = _status(observation.get("http_status"))
    headers = _headers(observation.get("headers"))
    message = observation.get("message", "")
    if not isinstance(message, str) or len(message) > 100_000:
        raise ValueError("message must be text of bounded length")

    text = message.casefold()
    remaining = _seconds(headers.get("x-ratelimit-remaining"))
    retry_after = _seconds(headers.get("retry-after"))
    reset = _reset_utc(headers.get("x-ratelimit-reset"))

    if reached is False or any(needle in text for needle in _SAFETY_MARKERS):
        kind, effect, decision = "pre_provider_block", "not_sent", "stop_and_review"
    elif status == 401:
        kind, effect, decision = "authentication_failure", "rejected", "repair_authentication"
    elif status in (403, 429) and any(needle in text for needle in _SECONDARY_MARKERS):
        kind, effect, decision = "secondary_rate_limit", "rejected", "wait_for_provider_cooldown"
    elif status == 403 and any(needle in text for needle in _PERMISSION_MARKERS):
        kind, effect, decision = "app_permission_denied", "rejected", "do_not_retry_same_integration"
    elif status in (403, 429) and (
        any(needle in text for needle in _PRIMARY_MARKERS) or remaining == 0
    ):
        kind, effect, decision = "primary_rate_limit", "rejected", "wait_for_provider_quota_reset"
    elif status == 429:
        kind, effect, decision = "rate_limited_unspecified", "rejected", "wait_and_recheck_limits"
    elif status == 403:
        kind, effect, decision = "forbidden_unclassified", "rejected", "inspect_provider_permissions_and_limits"
    elif status == 404:
        kind, effect, decision = "not_found", "rejected", "recheck_exact_resource_and_access"
    elif status in (409, 412, 422):
        kind, effect, decision = "state_conflict_or_validation", "rejected", "refresh_source_before_new_attempt"
    elif status is not None and 200 <= status <= 299:
        kind, effect, decision = "reported_success", "reported_success", "verify_provider_receipt"
    elif status is not None and 400 <= status <= 499:
        kind, effect, decision = "other_client_rejection", "rejected", "inspect_error_before_new_attempt"
    else:
        # Server failures, transport failures and incomplete observations may
        # hide a committed write. Elapsed time is not a reconciliation receipt.
        kind, effect, decision = "indeterminate", "uncertain", "reconcile_write_before_retry"

    if kind == "pre_provider_block" and reached is True:
        # Contradictory observation: do not turn a possibly-sent write into a
        # definitive not-sent result just because the text mentions a blocker.
        kind, effect, decision = "indeterminate", "uncertain", "reconcile_write_before_retry"

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "classification": kind,
        "http_status": status,
        "operation_kind": operation_kind,
        "effect_state": effect,
        "next_action": decision,
        "requires_provider_readback": operation_kind == "write"
        and effect in ("uncertain", "reported_success"),
        "automatic_retry": False,
    }
    if kind in ("primary_rate_limit", "secondary_rate_limit", "rate_limited_unspecified"):
        # Hints are observations, not permission to bypass a rate limit and
        # never authorization to switch identities.
        if retry_after is not None:
            result["retry_after_seconds_hint"] = retry_after
        if reset is not None:
            result["quota_reset_utc_hint"] = reset
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", metavar="JSON_FILE", help="saved observation; stdin by default")
    args = parser.parse_args(argv)
    try:
        if args.input:
            with open(args.input, "r", encoding="utf-8") as handle:
                source = json.load(handle)
        else:
            source = json.load(sys.stdin)
        if not isinstance(source, dict):
            raise ValueError("expected exactly one observation object")
        print(json.dumps(classify(source), sort_keys=True, indent=2))
        return 0
    except (OSError, ValueError, json.JSONDecodeError):
        print("Invalid observation; no classification issued.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
