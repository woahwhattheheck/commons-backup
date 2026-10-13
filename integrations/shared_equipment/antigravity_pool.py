"""Read existing Antigravity model quota, independently of Code Assist CLI.

Uses the existing Antigravity profile and relay connection settings. No model
request, OAuth refresh, onboarding, identity changes, retries, or writes.
"""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from datetime import datetime, timezone

CREDENTIAL_REFERENCE = "gemini/profile"
STATUS_URL = "https://daily-cloudcode-pa.googleapis.com/v1internal:fetchAvailableModels"
PROJECT = "default-cli-project"
USER_AGENT = "antigravity/1.1.20"
_MAX_BYTES = 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _utc(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo is not None else None
    except (ValueError, OverflowError):
        return None


def _fraction(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) and 0 <= value <= 1 else None
    except (OverflowError, ValueError):
        return None


def _pool(model_id, details):
    quota = details.get("quotaInfo")
    quota = quota if isinstance(quota, dict) else {}
    remaining = _fraction(quota.get("remainingFraction"))
    reset = _utc(quota.get("resetTime"))
    display_name = details.get("displayName")
    return {
        "pool_id": model_id,
        "model_id": model_id,
        "display_name": display_name if isinstance(display_name, str) and len(display_name) <= 256 else None,
        "disabled": details.get("disabled") if isinstance(details.get("disabled"), bool) else None,
        "remaining_fraction": remaining,
        "remaining_percent": remaining * 100 if remaining is not None else None,
        "usage_percent": (1 - remaining) * 100 if remaining is not None else None,
        "resets_at": reset.isoformat().replace("+00:00", "Z") if reset else None,
        "remaining_amount": None,
        "quota_unit": None,
        "window_duration_seconds": None,
    }


def poll_antigravity_pool(*, credential_reader, opener=None, now=None):
    """Read one existing Antigravity model-metadata response.

    Bind credential_reader to existing CredentialSources.read. Read the profile
    once so access and expiry come from the same custody snapshot. The profile
    and bearer stay in memory and never enter returned results.
    """
    instant = now or datetime.now(timezone.utc)
    result = {
        "schema": "commons.token_pool_status.v1", "provider": "antigravity",
        "source": "Antigravity fetchAvailableModels.models.quotaInfo",
        "credential_reference": CREDENTIAL_REFERENCE,
        "observed_at": instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ok": False, "status": "unavailable", "quota_reported": None,
        "pools": None, "error": None,
    }

    def unavailable(code, stage, http_status=None):
        result["error"] = {"code": code, "stage": stage, "http_status": http_status}
        return result

    try:
        profile = credential_reader(CREDENTIAL_REFERENCE)
        token = profile.get("token") if isinstance(profile, dict) else None
        if not isinstance(token, dict):
            return unavailable("credential_profile_invalid", "credential")
        access = token.get("access_token")
        if not isinstance(access, str) or not access or "\r" in access or "\n" in access:
            return unavailable("access_grant_missing", "credential")
        expiry = _utc(token.get("expiry"))
        if expiry is None:
            return unavailable("access_grant_expiry_unknown", "credential")
        if expiry <= instant:
            return unavailable("access_grant_expired", "credential")
        del profile, token
    except Exception:
        return unavailable("credential_read_unavailable", "credential")

    request = urllib.request.Request(
        STATUS_URL, data=json.dumps({"project": PROJECT}).encode("utf-8"),
        headers={"Authorization": "Bearer " + access,
                 "Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    transport = opener
    if transport is None:
        guarded = urllib.request.build_opener(_NoRedirect())
        transport = lambda req, timeout: guarded.open(req, timeout=timeout)
    response = None
    try:
        response = transport(request, 15)
        status = getattr(response, "status", None)
        if status is not None and not 200 <= status < 300:
            return unavailable("provider_http_error", "quota", status)
        raw = response.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            return unavailable("response_too_large", "quota", status)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return unavailable("invalid_response_shape", "quota", status)
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        code = {401: "access_grant_unusable", 403: "access_denied",
                429: "quota_status_rate_limited"}.get(status, "provider_http_error")
        return unavailable(code, "quota", status)
    except Exception:
        return unavailable("quota_read_failed", "quota")
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
    models = payload.get("models")
    if models is None:
        return unavailable("model_metadata_missing", "quota")
    if not isinstance(models, dict) or any(
        not isinstance(key, str) or len(key) > 256 or not isinstance(value, dict)
        for key, value in models.items()
    ):
        return unavailable("model_metadata_invalid", "quota")
    pools = [_pool(model_id, details) for model_id, details in models.items()]
    result.update(ok=True, status="ok", pools=pools,
                  quota_reported=any(p["remaining_fraction"] is not None for p in pools))
    return result
