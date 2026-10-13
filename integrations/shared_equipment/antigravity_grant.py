"""On-demand renewal of the existing Antigravity OAuth grant only.

No import-time credential/provider access. Existing primary and deposited
custody are updated in place; returned records contain no credential values.
"""
from __future__ import annotations

import base64
import ctypes
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

PRIMARY_TARGET = "gemini:antigravity"
COPY_REFERENCE = "vault/windows/gemini%3Aantigravity/part-0"
CLIENT_REFERENCE = "vault/google/antigravity/oauth-client/part-0"
MUTEX_NAME = r"Local\CommonsExistingGoogleGrantRefresh"
TOKEN_URL = "https://oauth2.googleapis.com/token"
_MAX_CREDENTIAL_BYTES = 2560
_MAX_RESPONSE_BYTES = 65536


class _Failure(Exception):
    def __init__(self, code, http_status=None):
        self.code = code
        self.http_status = http_status


class _FILETIME(ctypes.Structure):
    _fields_ = [("low", ctypes.c_uint32), ("high", ctypes.c_uint32)]


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [
        ("Flags", ctypes.c_uint32), ("Type", ctypes.c_uint32),
        ("TargetName", ctypes.c_wchar_p), ("Comment", ctypes.c_wchar_p),
        ("LastWritten", _FILETIME), ("CredentialBlobSize", ctypes.c_uint32),
        ("CredentialBlob", ctypes.c_void_p), ("Persist", ctypes.c_uint32),
        ("AttributeCount", ctypes.c_uint32), ("Attributes", ctypes.c_void_p),
        ("TargetAlias", ctypes.c_wchar_p), ("UserName", ctypes.c_wchar_p),
    ]


class _ExistingWindowsCustody:
    def __init__(self):
        self.api = ctypes.WinDLL("advapi32", use_last_error=True)
        self.api.CredReadW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p)]
        self.api.CredReadW.restype = ctypes.c_int
        self.api.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), ctypes.c_uint32]
        self.api.CredWriteW.restype = ctypes.c_int
        self.api.CredFree.argtypes = [ctypes.c_void_p]
        self.api.CredFree.restype = None

    def _open_existing(self, target):
        pointer = ctypes.c_void_p()
        if not self.api.CredReadW(target, 1, 0, ctypes.byref(pointer)):
            raise _Failure("existing_credential_unavailable")
        return pointer

    def read(self, target):
        pointer = self._open_existing(target)
        try:
            item = ctypes.cast(pointer, ctypes.POINTER(_CREDENTIAL)).contents
            return ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
        finally:
            self.api.CredFree(pointer)

    def replace_existing(self, target, expected, replacement):
        if len(replacement) > _MAX_CREDENTIAL_BYTES:
            raise _Failure("existing_record_size_exceeded")
        pointer = self._open_existing(target)
        buffer = ctypes.create_string_buffer(replacement)
        try:
            item = ctypes.cast(pointer, ctypes.POINTER(_CREDENTIAL)).contents
            current = ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize)
            if current != expected:
                raise _Failure("concurrent_custody_change")
            # Preserve all existing Windows credential metadata.
            item.CredentialBlobSize = len(replacement)
            item.CredentialBlob = ctypes.cast(buffer, ctypes.c_void_p)
            if not self.api.CredWriteW(ctypes.byref(item), 0):
                raise _Failure("existing_credential_write_failed")
        finally:
            self.api.CredFree(pointer)
        if self.read(target) != replacement:
            raise _Failure("existing_credential_readback_failed")


class _GrantMutex:
    def __enter__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        self.kernel.CreateMutexW.restype = ctypes.c_void_p
        self.kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.kernel.WaitForSingleObject.restype = ctypes.c_uint32
        self.kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
        self.kernel.ReleaseMutex.restype = ctypes.c_int
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel.CloseHandle.restype = ctypes.c_int
        self.handle = self.kernel.CreateMutexW(None, 0, MUTEX_NAME)
        if not self.handle:
            raise _Failure("refresh_coordination_unavailable")
        wait_status = self.kernel.WaitForSingleObject(self.handle, 15000)
        if wait_status not in (0, 0x80):
            self.kernel.CloseHandle(self.handle)
            self.handle = None
            raise _Failure("refresh_already_in_progress" if wait_status == 0x102
                           else "refresh_coordination_unavailable")
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self.handle:
            self.kernel.ReleaseMutex(self.handle)
            self.kernel.CloseHandle(self.handle)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _expiry(token):
    value = token.get("expiry")
    if not isinstance(value, str) or len(value) > 64:
        raise _Failure("stored_expiry_unknown")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError()
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise _Failure("stored_expiry_unknown") from None


def _refresh(token, client, opener):
    if not isinstance(client, dict) or client.get("token_uri") != TOKEN_URL:
        raise _Failure("existing_oauth_client_endpoint_mismatch")
    fields = {"client_id": client.get("client_id"),
              "client_secret": client.get("client_secret"),
              "refresh_token": token.get("refresh_token")}
    if any(not isinstance(value, str) or not value for value in fields.values()):
        raise _Failure("existing_refresh_material_unavailable")
    fields["grant_type"] = "refresh_token"
    request = urllib.request.Request(
        TOKEN_URL, data=urllib.parse.urlencode(fields).encode("ascii"),
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    response = None
    try:
        response = opener(request, 15)
        status = getattr(response, "status", None)
        if status is not None and not 200 <= status < 300:
            raise _Failure("oauth_http_error", status)
        raw = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise _Failure("oauth_response_too_large", status)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise _Failure("oauth_response_invalid", status)
        return payload
    except urllib.error.HTTPError as error:
        status = error.code
        safe_code = "oauth_http_error"
        try:
            raw = error.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) <= _MAX_RESPONSE_BYTES:
                payload = json.loads(raw.decode("utf-8"))
                code = payload.get("error") if isinstance(payload, dict) else None
                if code in {"invalid_grant", "invalid_client", "invalid_request",
                            "unauthorized_client", "invalid_scope", "temporarily_unavailable"}:
                    safe_code = "oauth_" + code
        except Exception:
            pass
        finally:
            error.close()
        raise _Failure(safe_code, status) from None
    except _Failure:
        raise
    except Exception:
        raise _Failure("oauth_refresh_failed") from None
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass


def _updated_profile(original, response):
    access = response.get("access_token")
    if not isinstance(access, str) or not access or "\r" in access or "\n" in access:
        raise _Failure("oauth_response_missing_access_token")
    lifetime = response.get("expires_in")
    if isinstance(lifetime, str) and lifetime.isascii() and lifetime.isdigit():
        lifetime = int(lifetime)
    if isinstance(lifetime, bool) or not isinstance(lifetime, (int, float)):
        raise _Failure("oauth_response_invalid_expiry")
    try:
        if not math.isfinite(lifetime) or lifetime <= 0 or int(lifetime) != lifetime:
            raise ValueError()
        stamp = datetime.now(timezone.utc) + timedelta(seconds=lifetime)
    except (ValueError, OverflowError):
        raise _Failure("oauth_response_invalid_expiry") from None
    token = dict(original["token"])
    for field in ("access_token", "refresh_token", "token_type", "scope", "id_token"):
        if response.get(field):
            if not isinstance(response[field], str):
                raise _Failure("oauth_response_invalid_token_field")
            token[field] = response[field]
    token["expiry"] = stamp.isoformat().replace("+00:00", "Z")
    revised = dict(original)
    revised["token"] = token
    return revised, stamp


def ensure_antigravity_grant(*, sources=None, opener=None):
    """Renew expired primary custody or synchronize an already-fresh grant.

    Uses the same named mutex as the owner's existing refresh helper. A waiter
    re-reads expiry after acquiring it and reuses the winner's refreshed grant.
    The caller subsequently reads gemini/profile through its ordinary road.
    """
    result = {
        "provider": "antigravity", "operation": "existing_grant_renewal",
        "ok": False, "status": "unavailable",
        "refreshed": False, "primary_custody_updated": False,
        "shared_custody_updated": False, "expires_at": None, "error": None,
    }
    try:
        if sources is None:
            from .credential_transfer import CredentialSources
            sources = CredentialSources()
        transport = opener
        if transport is None:
            guarded = urllib.request.build_opener(_NoRedirect())
            transport = lambda request, timeout: guarded.open(request, timeout=timeout)
        with _GrantMutex():
            custody = _ExistingWindowsCustody()
            descriptor = sources._configured().get(COPY_REFERENCE)
            if (not isinstance(descriptor, dict)
                    or descriptor.get("type") != "windows_credential"
                    or descriptor.get("encoding") != "base64"
                    or not isinstance(descriptor.get("target"), str)
                    or not descriptor["target"]
                    or descriptor["target"] == PRIMARY_TARGET):
                raise _Failure("existing_copy_descriptor_unavailable")
            copy_target = descriptor["target"]
            primary_before = custody.read(PRIMARY_TARGET)
            copy_before = custody.read(copy_target)
            try:
                original = json.loads(primary_before.decode("utf-8").rstrip("\x00"))
                if not isinstance(original, dict) or not isinstance(original.get("token"), dict):
                    raise ValueError()
            except Exception:
                raise _Failure("existing_primary_profile_invalid") from None
            expiry = _expiry(original["token"])
            result["expires_at"] = expiry.isoformat().replace("+00:00", "Z")
            raw = primary_before
            if expiry <= datetime.now(timezone.utc):
                try:
                    encoded = sources.read(CLIENT_REFERENCE)
                    client_raw = base64.b64decode(encoded, validate=True)
                    if len(client_raw) > _MAX_CREDENTIAL_BYTES:
                        raise ValueError()
                    client = json.loads(client_raw.decode("utf-8"))
                except Exception:
                    raise _Failure("existing_client_reference_unavailable") from None
                response = _refresh(original["token"], client, transport)
                revised, expiry = _updated_profile(original, response)
                raw = json.dumps(revised, separators=(",", ":")).encode("utf-8")
                if len(raw) > _MAX_CREDENTIAL_BYTES:
                    raise _Failure("existing_record_size_exceeded")
                # The primary is compared inside replace_existing; first check
                # that the shared destination has not changed during network I/O.
                if custody.read(copy_target) != copy_before:
                    raise _Failure("concurrent_custody_change")
                result["primary_custody_updated"] = None
                custody.replace_existing(PRIMARY_TARGET, primary_before, raw)
                result.update(refreshed=True, primary_custody_updated=True,
                              expires_at=expiry.isoformat().replace("+00:00", "Z"))
            else:
                access = original["token"].get("access_token")
                if not isinstance(access, str) or not access or "\r" in access or "\n" in access:
                    raise _Failure("stored_access_grant_missing_or_invalid")
            # A fresh primary can repair a stale shared copy without any OAuth call.
            if copy_before != raw:
                if custody.read(PRIMARY_TARGET) != raw:
                    raise _Failure("concurrent_custody_change")
                result["shared_custody_updated"] = None
                custody.replace_existing(copy_target, copy_before, raw)
                result["shared_custody_updated"] = True
            result.update(ok=True, status="ready")
    except _Failure as error:
        result["error"] = {"code": error.code, "http_status": error.http_status}
    except Exception:
        result["error"] = {"code": "existing_grant_recovery_failed", "http_status": None}
    return result
