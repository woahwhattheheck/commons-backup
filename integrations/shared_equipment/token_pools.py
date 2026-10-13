"""Read GrokBot, standalone Cursor and Claude quota using existing custody.

Uses the installed clients' read-only status interfaces and returns normalized
commons.token_pool_status.v1 records. Makes no writes, redeems nothing, starts
no model work and performs no retries.
"""

import json
import math
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

__all__ = ["poll_token_pools", "poll_cursor_pool", "poll_claude_pool"]

_USAGE_URL = "https://api2.cursor.sh/aiserver.v1.DashboardService/GetSandUsageStatus"
_ACCESS_URL = "https://api2.cursor.sh/aiserver.v1.DashboardService/GetSandAccessStatus"
_DEFAULT_CREDENTIAL_REFERENCE = "vault/grokbot/account-0/cursor-access-token"
_REQUEST_TIMEOUT_SECONDS = 15
_MAX_RESPONSE_BYTES = 1024 * 1024
_USER_AGENT = "Grok Bot/0.43.0"


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Returning None makes the base handler raise HTTPError instead of
        # following the redirect, so the bearer token is never replayed
        # against a different host.
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirectHandler())


def _default_opener(request, timeout):
    return _NO_REDIRECT_OPENER.open(request, timeout=timeout)


def _error(exc, http_status=None):
    return {"class": type(exc).__name__, "http_status": http_status}


def _close_quietly(response):
    try:
        response.close()
    except Exception:
        pass


def _response_status(response):
    status = getattr(response, "status", None)
    if status is not None:
        return status
    getcode = getattr(response, "getcode", None)
    if getcode is not None:
        try:
            return getcode()
        except Exception:
            return None
    return None


def _call_method(opener, url, credential, *, http_method="POST", extra_headers=None):
    request = urllib.request.Request(
        url,
        data=b"{}" if http_method == "POST" else None,
        method=http_method,
        headers={
            "Content-Type": "application/json",
            "Connect-Protocol-Version": "1",
            "User-Agent": _USER_AGENT,
            "Authorization": "Bearer " + credential,
            **(extra_headers or {}),
        },
    )

    try:
        response = opener(request, _REQUEST_TIMEOUT_SECONDS)
    except urllib.error.HTTPError as exc:
        err = _error(exc, exc.code)
        _close_quietly(exc)
        return None, err
    except Exception as exc:
        return None, _error(exc)

    try:
        status = _response_status(response)
        raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except Exception as exc:
        return None, _error(exc, _response_status(response))
    finally:
        _close_quietly(response)

    if status is not None and not 200 <= status < 300:
        return None, {"class": "HTTPStatusError", "http_status": status}
    if len(raw) > _MAX_RESPONSE_BYTES:
        return None, {"class": "ResponseTooLarge", "http_status": status}

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        return None, _error(exc, status)

    if not isinstance(payload, dict):
        return None, {"class": "UnexpectedPayloadType", "http_status": status}

    return payload, None


def _norm_bool(value):
    return value if isinstance(value, bool) else None


def _norm_nonneg_finite_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except (ValueError, OverflowError):
            return None
        if math.isfinite(number) and number >= 0:
            return number
    return None


def _norm_iso_string(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError):
        return None


def _norm_int_like(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 2**63 - 1 else None
    if isinstance(value, str):
        stripped = value.strip()
        if re.fullmatch(r"[0-9]{1,19}", stripped):
            try:
                count = int(stripped)
                return count if count <= 2**63 - 1 else None
            except ValueError:
                return None
    return None


def _norm_enum(value, expected_prefix):
    if isinstance(value, str) and re.fullmatch(re.escape(expected_prefix) + r"[A-Z0-9_]{1,80}", value):
        return value
    return None


def _norm_on_demand_settings(value):
    if not isinstance(value, dict):
        return None
    return {
        "visible": _norm_bool(value.get("visible")),
        "eligible": _norm_bool(value.get("eligible")),
        "enabled": _norm_bool(value.get("enabled")),
    }


def _null_usage_fields():
    return {
        "usage_percent": None,
        "remaining_percent": None,
        "next_reset_at": None,
        "current_period_start": None,
        "has_available_usage": None,
        "has_non_zero_included_limit": None,
        "included_limit_zero": None,
        "uses_pooled_enterprise_allowance": None,
        "banked_resets_available": None,
        "on_demand": None,
    }


def _build_usage_fields(payload):
    usage_percent = _norm_nonneg_finite_number(payload.get("usagePercent"))
    remaining_percent = None
    if usage_percent is not None:
        remaining_percent = max(0.0, min(100.0, 100.0 - usage_percent))
    return {
        "usage_percent": usage_percent,
        "remaining_percent": remaining_percent,
        "next_reset_at": _norm_iso_string(payload.get("nextResetTimestampUtc")),
        "current_period_start": _norm_iso_string(payload.get("currentPeriodStart")),
        "has_available_usage": _norm_bool(payload.get("hasAvailableUsage")),
        "has_non_zero_included_limit": _norm_bool(payload.get("hasNonZeroIncludedLimit")),
        "included_limit_zero": _norm_bool(payload.get("includedLimitZero")),
        "uses_pooled_enterprise_allowance": _norm_bool(payload.get("usesPooledEnterpriseAllowance")),
        "banked_resets_available": _norm_int_like(payload.get("availableBankedResetCount")),
        "on_demand": _norm_on_demand_settings(payload.get("onDemandSettings")),
    }


def _null_access_fields():
    return {"state": None, "block_reason": None}


def _build_access_fields(payload):
    return {
        "state": _norm_enum(payload.get("state"), "SAND_ACCESS_STATE_"),
        "block_reason": _norm_enum(payload.get("blockReason"), "SAND_ACCESS_BLOCK_REASON_"),
    }


def _resolve_credential(credential_reader, reference=_DEFAULT_CREDENTIAL_REFERENCE):
    try:
        raw = credential_reader(reference)
    except Exception as exc:
        return None, _error(exc)

    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except Exception as exc:
            return None, _error(exc)

    if isinstance(raw, str):
        raw = raw.strip()
        if raw:
            return raw, None

    return None, None


def poll_token_pools(*, credential_reader, opener=None):
    observed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    request_opener = opener if opener is not None else _default_opener

    credential, credential_error = _resolve_credential(credential_reader)

    if credential is None:
        usage_result = {"status": "unavailable", "source": "GetSandUsageStatus", "error": credential_error}
        usage_result.update(_null_usage_fields())
        access_result = {"status": "unavailable", "source": "GetSandAccessStatus", "error": credential_error}
        access_result.update(_null_access_fields())
        return {
            "schema": "commons.token_pool_status.v1",
            "observed_at": observed_at,
            "provider": "grokbot",
            "pool_id": "grokbot_included",
            "ok": False,
            "usage": usage_result,
            "access": access_result,
        }

    usage_payload, usage_error = _call_method(request_opener, _USAGE_URL, credential)
    access_payload, access_error = _call_method(request_opener, _ACCESS_URL, credential)

    usage_result = {
        "status": "ok" if usage_error is None else "error",
        "source": "GetSandUsageStatus",
        "error": usage_error,
    }
    usage_result.update(_build_usage_fields(usage_payload) if usage_error is None else _null_usage_fields())

    access_result = {
        "status": "ok" if access_error is None else "error",
        "source": "GetSandAccessStatus",
        "error": access_error,
    }
    access_result.update(_build_access_fields(access_payload) if access_error is None else _null_access_fields())

    return {
        "schema": "commons.token_pool_status.v1",
        "observed_at": observed_at,
        "provider": "grokbot",
        "pool_id": "grokbot_included",
        "ok": usage_error is None and access_error is None,
        "usage": usage_result,
        "access": access_result,
    }


def _window(pool_id, usage, reset_at):
    used = _norm_nonneg_finite_number(usage)
    return {"pool_id": pool_id, "usage_percent": used,
            "remaining_percent": max(0.0, min(100.0, 100.0 - used)) if used is not None else None,
            "resets_at": reset_at}


def _epoch_millis(value):
    count = _norm_int_like(value)
    if count is None or count == 0:
        return None
    try:
        return datetime.fromtimestamp(count / 1000.0, timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError, OSError):
        return None


def _read_pool(provider, source, reference, url, credential_reader, opener,
               *, http_method="POST", extra_headers=None):
    result = {"schema": "commons.token_pool_status.v1", "provider": provider,
              "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "source": source, "ok": False, "status": "unavailable", "pools": [], "error": None}
    credential, error = _resolve_credential(credential_reader, reference)
    if credential is None:
        result["error"] = error
        return result, None
    payload, error = _call_method(opener or _default_opener, url, credential,
                                  http_method=http_method, extra_headers=extra_headers)
    result.update(ok=error is None, status="ok" if error is None else "error", error=error)
    return result, payload


def poll_cursor_pool(*, credential_reader, opener=None):
    """Read the standalone Cursor account's plan windows using its own grant."""
    result, payload = _read_pool(
        "cursor", "GetCurrentPeriodUsage", "vault/cursor/account/access",
        "https://api2.cursor.sh/aiserver.v1.DashboardService/GetCurrentPeriodUsage",
        credential_reader, opener, extra_headers={"User-Agent": "CommonsTokenPools/1"})
    if payload is None:
        return result
    usage = payload.get("planUsage")
    if not isinstance(usage, dict):
        usage = {}
    reset_at = _epoch_millis(payload.get("billingCycleEnd"))
    result["pools"] = [_window(name, usage.get(field), reset_at)
                       for name, field in (("cursor_plan", "totalPercentUsed"),
                                           ("cursor_auto", "autoPercentUsed"),
                                           ("cursor_api", "apiPercentUsed"))]
    return result


def poll_claude_pool(*, credential_reader, opener=None):
    """Read native Claude OAuth usage; this never starts a model turn."""
    result, payload = _read_pool(
        "claude", "/api/oauth/usage", "vault/claude/account/access",
        "https://api.anthropic.com/api/oauth/usage", credential_reader, opener,
        http_method="GET", extra_headers={"anthropic-beta": "oauth-2025-04-20",
                                          "User-Agent": "CommonsTokenPools/1"})
    if payload is None:
        return result
    # Only the provider's utilization/reset windows enter the shared result.
    for name, window in payload.items():
        if (isinstance(name, str) and re.fullmatch(r"(?:five_hour|seven_day)(?:_[a-z0-9_]{1,48})?", name)
                and (window is None or isinstance(window, dict))):
            window = window or {}
            result["pools"].append(_window(name, window.get("utilization"),
                                          _norm_iso_string(window.get("resets_at"))))
    return result
