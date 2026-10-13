"""Read existing Gemini Code Assist OAuth quota through shared custody.

The allowance is separate from API-key Gemini and Antigravity. Polling uses
existing-project discovery and quota reads, with no refresh or onboarding.
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

CREDENTIAL_REFERENCE = "vault/file/.gemini/oauth_creds.json/part-0"
_ENDPOINT = "https://cloudcode-pa.googleapis.com/v1internal"
_MAX_BYTES = 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return value if math.isfinite(value) else None
    except (OverflowError, ValueError):
        return None


def _iso(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError):
        return None


def _amount(value):
    # Keep the provider's numerical representation. No unit or token inference.
    number = _number(value)
    if number is not None and number >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,100}(?:\.[0-9]{1,100})?", value):
        return value
    return None


def normalize_bucket(bucket):
    model = bucket.get("modelId")
    fraction = _number(bucket.get("remainingFraction"))
    if fraction is not None and not 0 <= fraction <= 1:
        fraction = None
    return {
        "pool_id": model if isinstance(model, str) and len(model) <= 256 else None,
        "model_id": model if isinstance(model, str) and len(model) <= 256 else None,
        "remaining_fraction": fraction,
        "remaining_percent": 100 * fraction if fraction is not None else None,
        "usage_percent": 100 * (1 - fraction) if fraction is not None else None,
        "remaining_amount": _amount(bucket.get("remainingAmount")),
        "quota_unit": None,
        "resets_at": _iso(bucket.get("resetTime")),
        "window_duration_seconds": None,
    }


def configured_project_hint(environ=None):
    """CLI setup's existing env hint, not a discovered or created project."""
    env = os.environ if environ is None else environ
    return env.get("GOOGLE_CLOUD_PROJECT") or env.get("GOOGLE_CLOUD_PROJECT_ID")


def _valid_project(value):
    return isinstance(value, str) and 0 < len(value) <= 256 and not value.isdigit() and not any(ord(c) < 32 for c in value)


def _post(method, body, access_token, opener):
    # Fixed provider and method set; never replay the bearer on a redirect.
    if method not in ("loadCodeAssist", "retrieveUserQuota"):
        return None, {"code": "unsupported_method", "http_status": None}
    request = urllib.request.Request(
        _ENDPOINT + ":" + method,
        data=json.dumps(body, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": "Commons-Code-Assist-Quota/1",
                 "Authorization": "Bearer " + access_token},
    )
    response = None
    try:
        response = opener(request, 15)
        status = getattr(response, "status", None)
        if status is not None and not 200 <= status < 300:
            return None, {"code": "provider_http_error", "http_status": status}
        raw = response.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            return None, {"code": "response_too_large", "http_status": status}
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return None, {"code": "invalid_response_shape", "http_status": status}
        return payload, None
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        code = {401: "access_grant_unusable", 403: "access_denied",
                429: "quota_status_rate_limited"}.get(status, "provider_http_error")
        return None, {"code": code, "http_status": status}
    except Exception:
        return None, {"code": "quota_read_failed", "http_status": None}
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass


def poll_gemini_code_assist_pool(*, credential_reader, project_id_reader=None,
                                 opener=None, now=None):
    """Read only the existing Code Assist OAuth allowance.

    credential_reader is the existing CredentialSources.read road. It returns
    the selected vault file fragment as base64; parse it only in memory.
    project_id_reader supplies an existing project hint, without provider calls.
    If absent, only the two CLI project environment variables are considered.
    A loadCodeAssist response must demonstrate an existing current tier before
    quota retrieval. Never substitute API-key or Antigravity credentials.
    """
    instant = now or datetime.now(timezone.utc)
    result = {
        "schema": "commons.token_pool_status.v1",
        "provider": "gemini_code_assist",
        "source": "Gemini CLI 0.57.0 CodeAssistServer.retrieveUserQuota",
        "credential_reference": CREDENTIAL_REFERENCE,
        "observed_at": instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ok": False, "status": "unavailable", "pools": None, "error": None,
        "project_source": None,
    }

    def unavailable(code, stage, http_status=None):
        result["error"] = {"code": code, "stage": stage, "http_status": http_status}
        return result

    try:
        encoded = credential_reader(CREDENTIAL_REFERENCE)
        if not isinstance(encoded, (str, bytes)) or len(encoded) > 2 * _MAX_BYTES:
            return unavailable("credential_payload_unavailable", "credential")
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > _MAX_BYTES:
            return unavailable("credential_payload_invalid", "credential")
        cached = json.loads(raw.decode("utf-8-sig"))
        if not isinstance(cached, dict):
            return unavailable("credential_payload_invalid", "credential")
        access_token = cached.get("access_token")
        expiry = _number(cached.get("expiry_date"))
        # Never refresh a stale grant or treat unknown validity as fresh.
        if not isinstance(access_token, str) or not access_token or "\r" in access_token or "\n" in access_token:
            return unavailable("access_grant_missing", "credential")
        if expiry is None:
            return unavailable("access_grant_expiry_unknown", "credential")
        if expiry <= instant.timestamp() * 1000:
            return unavailable("access_grant_expired", "credential")
        # Discard references to the full parsed cache, including any refresh token.
        del cached, raw, encoded
    except Exception:
        return unavailable("credential_read_unavailable", "credential")

    try:
        hint = (project_id_reader or configured_project_hint)()
    except Exception:
        return unavailable("project_source_unavailable", "project")
    if hint is not None and not _valid_project(hint):
        return unavailable("project_id_invalid", "project")
    metadata = {"ideType": "IDE_UNSPECIFIED",
                "platform": "PLATFORM_UNSPECIFIED", "pluginType": "GEMINI"}
    discovery_body = {"metadata": metadata}
    if hint is not None:
        discovery_body["cloudaicompanionProject"] = hint
        metadata["duetProject"] = hint
    transport = opener
    if transport is None:
        guarded_opener = urllib.request.build_opener(_NoRedirect())
        transport = lambda request, timeout: guarded_opener.open(request, timeout=timeout)
    existing, error = _post("loadCodeAssist", discovery_body, access_token, transport)
    if error:
        return unavailable(error["code"], "existing_project", error["http_status"])
    if not isinstance(existing.get("currentTier"), dict):
        tiers = existing.get("ineligibleTiers")
        reason_codes = []
        if isinstance(tiers, list):
            for tier in tiers:
                code = tier.get("reasonCode") if isinstance(tier, dict) else None
                if isinstance(code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", code) and code not in reason_codes:
                    reason_codes.append(code)
        result["provider_reason_codes"] = reason_codes
        if "UNSUPPORTED_CLIENT" in reason_codes:
            return unavailable("provider_client_unsupported", "existing_project")
        if "VALIDATION_REQUIRED" in reason_codes:
            return unavailable("existing_access_validation_required", "existing_project")
        if isinstance(tiers, list) and tiers:
            return unavailable("existing_access_ineligible", "existing_project")
        return unavailable("existing_project_not_established_no_onboarding", "existing_project")
    project = existing.get("cloudaicompanionProject")
    if project is None:
        project = hint
        result["project_source"] = "existing_configured_hint" if hint else None
    else:
        result["project_source"] = "loadCodeAssist.cloudaicompanionProject"
    if not _valid_project(project):
        return unavailable("existing_project_id_missing_or_invalid", "existing_project")

    quota, error = _post("retrieveUserQuota", {"project": project}, access_token, transport)
    if error:
        return unavailable(error["code"], "quota", error["http_status"])
    buckets = quota.get("buckets")
    if buckets is None:
        return unavailable("quota_buckets_missing", "quota")
    if not isinstance(buckets, list) or any(not isinstance(bucket, dict) for bucket in buckets):
        return unavailable("quota_buckets_invalid", "quota")
    result.update(ok=True, status="ok", pools=[normalize_bucket(b) for b in buckets])
    return result
