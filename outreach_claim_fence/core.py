"""Core types and validation for the v2 outreach claim fence."""
from __future__ import annotations

import dataclasses
import datetime as dt
import email.utils
import hashlib
import hmac
import json
import os
import re
import stat
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Mapping, MutableMapping, Optional

SCHEMA = "outreach-claim-fence/v2"
CANONICAL_API_URL = "https://api.github.com"
CANONICAL_REPOSITORY = "woahwhattheheck/commons"
DEFAULT_BRANCH = "coordination/outreach-claims-v2"
DEFAULT_ROOT = ".coordination/outreach-claims/v2"
AUTHORITY_GENERATION = "outreach-claims-v2/2026-09-14"
API_VERSION = "2022-11-28"
MIN_LEASE_SECONDS = 60
MAX_LEASE_SECONDS = 7 * 24 * 60 * 60
MIN_COOLDOWN_SECONDS = 5 * 60
MAX_COOLDOWN_SECONDS = 30 * 24 * 60 * 60
MAX_RETRIES = 4
MAX_MESSAGE_BYTES = 2 * 1024 * 1024
_STATES = {"ACTIVE", "ARMED", "OUTCOME_UNKNOWN", "CONTACTED", "RELEASED"}
_TARGET_KINDS = {"email", "domain", "github", "slack", "custom"}
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_WEAK_COMPENSATION_PATHS = {
    "none", "n/a", "na", "free", "unknown", "tbd", "no payment", "unpaid",
}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


AUTHORITY_POLICY = {
    "schema": SCHEMA,
    "generation": AUTHORITY_GENERATION,
    "repository": CANONICAL_REPOSITORY,
    "branch": DEFAULT_BRANCH,
    "root": DEFAULT_ROOT,
    "api_origin": CANONICAL_API_URL,
}
AUTHORITY_DIGEST = _sha256_hex(_canonical_json_bytes(AUTHORITY_POLICY))


class ClaimFenceError(Exception):
    exit_code = 6
    def __init__(self, message: str, *, details: Optional[Mapping[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = dict(details or {})
    def safe_payload(self) -> dict[str, Any]:
        return {"ok": False, "error": self.__class__.__name__, "message": self.message, "details": self.details}


class ValidationError(ClaimFenceError): exit_code = 2
class ClaimConflict(ClaimFenceError): exit_code = 3
class ClaimNotFound(ClaimFenceError): exit_code = 4
class OwnershipError(ClaimFenceError): exit_code = 5
class RemoteError(ClaimFenceError): exit_code = 6
class ProtocolError(ClaimFenceError): exit_code = 7
class _CasConflict(Exception): pass


@dataclasses.dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


class UrllibTransport:
    """Canonical GitHub HTTPS transport that never forwards auth across redirects."""
    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(_NoRedirect())

    @staticmethod
    def _validate_url(url: str) -> None:
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com":
            raise ValidationError("token-bearing GitHub URL must use canonical https://api.github.com origin")
        if parsed.username or parsed.password or parsed.fragment:
            raise ValidationError("token-bearing GitHub URL contains forbidden authority components")

    def request(self, method: str, url: str, headers: Mapping[str, str], body: Optional[bytes] = None) -> HttpResponse:
        self._validate_url(url)
        request = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
        try:
            with self._opener.open(request, timeout=30) as response:
                return HttpResponse(int(response.status), {str(k): str(v) for k, v in response.headers.items()}, response.read())
        except urllib.error.HTTPError as exc:
            # Redirects surface here because the opener refuses to follow them.
            return HttpResponse(int(exc.code), {str(k): str(v) for k, v in exc.headers.items()}, exc.read())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RemoteError("GitHub request failed before a response was received") from exc


@dataclasses.dataclass(frozen=True)
class TargetIdentity:
    kind: str
    normalized: str
    claim_key: str
    hint: str


@dataclasses.dataclass(frozen=True)
class StoredClaim:
    record: Mapping[str, Any]
    blob_sha: str
    server_now: dt.datetime


@dataclasses.dataclass(frozen=True)
class ClaimReceipt:
    action: str
    claim_key: str
    state: str
    revision: int
    agent_id: str
    operation_id: str
    ownership_expires_at: str
    contact_not_before: Optional[str]
    record_digest: str
    path: str
    authority_generation: str = AUTHORITY_GENERATION
    authority_digest: str = AUTHORITY_DIGEST
    repository: str = CANONICAL_REPOSITORY
    branch: str = DEFAULT_BRANCH
    root: str = DEFAULT_ROOT
    api_origin: str = CANONICAL_API_URL
    blob_sha: Optional[str] = None
    commit_sha: Optional[str] = None
    dispatch_token: Optional[str] = None
    def as_dict(self) -> dict[str, Any]:
        return {"ok": True, **dataclasses.asdict(self)}


def _clean_text(value: str, *, field: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be a string")
    cleaned = " ".join(unicodedata.normalize("NFKC", value).split())
    if not cleaned:
        raise ValidationError(f"{field} must not be empty")
    if len(cleaned) > max_length:
        raise ValidationError(f"{field} exceeds {max_length} characters")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in cleaned):
        raise ValidationError(f"{field} contains a control character")
    return cleaned


def _normalize_domain(value: str) -> str:
    domain = value.strip().rstrip(".").casefold()
    if not domain or "." not in domain:
        raise ValidationError("domain must contain at least one dot")
    try:
        ascii_domain = domain.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValidationError("domain is not valid IDNA") from exc
    labels = ascii_domain.split(".")
    label_re = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
    if any(not label or len(label) > 63 or not label_re.fullmatch(label) for label in labels) or len(ascii_domain) > 253:
        raise ValidationError("domain contains invalid characters or label lengths")
    return ascii_domain


def _masked_domain_hint(domain: str) -> str:
    return ".".join(f"{label[:1]}***" for label in domain.split("."))


def normalize_target(kind: str, value: str) -> TargetIdentity:
    kind = _clean_text(kind, field="target kind", max_length=24).casefold()
    if kind not in _TARGET_KINDS:
        raise ValidationError("unsupported target kind", details={"allowed": sorted(_TARGET_KINDS)})
    raw = _clean_text(value, field="contact target", max_length=512)
    if kind == "email":
        if raw.count("@") != 1:
            raise ValidationError("email target must contain exactly one @")
        local, domain = raw.rsplit("@", 1)
        local = unicodedata.normalize("NFKC", local).casefold()
        if not local or len(local) > 64 or any(ch.isspace() for ch in local):
            raise ValidationError("email local part is invalid")
        domain = _normalize_domain(domain)
        normalized = f"{local}@{domain}"
        hint = f"{local[:1]}***@{_masked_domain_hint(domain)}"
    elif kind == "domain":
        normalized = _normalize_domain(raw); hint = _masked_domain_hint(normalized)
    elif kind == "github":
        normalized = raw.lstrip("@").casefold()
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?", normalized):
            raise ValidationError("GitHub handle is invalid")
        hint = f"@{normalized[:2]}***" if len(normalized) > 2 else f"@{normalized[:1]}*"
    elif kind == "slack":
        normalized = raw.lstrip("@").casefold()
        if not re.fullmatch(r"[a-z0-9._-]{1,80}", normalized):
            raise ValidationError("Slack handle is invalid")
        hint = f"@{normalized[:2]}***" if len(normalized) > 2 else f"@{normalized[:1]}*"
    else:
        normalized = raw.casefold(); hint = f"{normalized[:2]}***" if len(normalized) > 2 else "***"
    claim_key = _sha256_hex(_canonical_json_bytes({"schema": SCHEMA, "target_kind": kind, "target": normalized}))
    return TargetIdentity(kind, normalized, claim_key, hint)


def _format_timestamp(value: dt.datetime) -> str:
    if value.tzinfo is None:
        raise ValidationError("timestamp must be timezone-aware")
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any, *, field: str) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProtocolError(f"stored {field} is not a canonical UTC timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ProtocolError(f"stored {field} is invalid") from exc
    if parsed.tzinfo is None:
        raise ProtocolError(f"stored {field} has no timezone")
    return parsed.astimezone(dt.timezone.utc)


def _server_time(headers: Mapping[str, str]) -> dt.datetime:
    raw = next((v for k, v in headers.items() if k.casefold() == "date"), None)
    if not raw:
        raise ProtocolError("GitHub response omitted the Date header; refusing local-clock fallback")
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("GitHub Date header is invalid") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0)


def _record_digest(record: Mapping[str, Any]) -> str:
    payload = dict(record); payload.pop("record_digest", None)
    return _sha256_hex(_canonical_json_bytes(payload))


def _seal_record(record: MutableMapping[str, Any]) -> dict[str, Any]:
    out = dict(record); out.pop("record_digest", None); out["record_digest"] = _record_digest(out); return out


def _validate_duration(value: int, *, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValidationError(f"{field} must be an integer between {minimum} and {maximum} seconds")
    return value


def _safe_owner(value: str, *, field: str) -> str:
    cleaned = _clean_text(value, field=field, max_length=128)
    if not re.fullmatch(r"[A-Za-z0-9._:/-]+", cleaned):
        raise ValidationError(f"{field} contains unsupported characters")
    return cleaned


def _safe_label(value: str, *, field: str, max_length: int = 200) -> str:
    return _clean_text(value, field=field, max_length=max_length)


def _safe_hex(value: str, *, field: str) -> str:
    if not isinstance(value, str) or not _HEX_64.fullmatch(value.strip().casefold()):
        raise ValidationError(f"{field} must be 64 lowercase hexadecimal characters")
    return value.strip().casefold()


def _has_concrete_compensation_signal(value: str) -> bool:
    folded = value.casefold()
    if folded in _WEAK_COMPENSATION_PATHS:
        return False
    if re.search(r"(?:[$€£¥]|\b(?:usd|eur|gbp|cad|aud)\b)\s*\d", folded):
        return True
    return any(term in folded for term in ("bounty", "paid", "payment", "proposal", "contract", "invoice", "retainer", "commission", "fee", "purchase order", "revenue share", "fixed-scope", "fixed scope", "discovery", "quote", "bid", "award"))


def digest_message_bytes(message: bytes) -> str:
    if not isinstance(message, (bytes, bytearray)):
        raise ValidationError("message must be bytes")
    if len(message) > MAX_MESSAGE_BYTES:
        raise ValidationError("message exceeds bounded digest input size")
    return _sha256_hex(bytes(message))


def digest_message_file(path: str) -> str:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise ValidationError("message file could not be opened safely") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_MESSAGE_BYTES:
            raise ValidationError("message file must be a bounded regular file")
        chunks: list[bytes] = []
        remaining = MAX_MESSAGE_BYTES + 1
        while remaining:
            part = os.read(fd, min(65536, remaining))
            if not part: break
            chunks.append(part); remaining -= len(part)
        data = b"".join(chunks)
        after = os.fstat(fd)
        identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if identity != after_identity or len(data) != before.st_size:
            raise ValidationError("message file changed during digest read")
        return digest_message_bytes(data)
    finally:
        os.close(fd)


def _reconciliation_payload(*, claim_key: str, record_digest: str, provider_history_digest: str) -> bytes:
    return _canonical_json_bytes({
        "schema": SCHEMA,
        "authority_digest": AUTHORITY_DIGEST,
        "decision": "UNSENT",
        "claim_key": claim_key,
        "record_digest": record_digest,
        "provider_history_digest": provider_history_digest,
    })


def sign_unsent_reconciliation(*, key: bytes, claim_key: str, record_digest: str, provider_history_digest: str) -> str:
    if not isinstance(key, (bytes, bytearray)) or len(key) < 32:
        raise ValidationError("reconciliation key must be at least 32 bytes")
    provider_history_digest = _safe_hex(provider_history_digest, field="provider history digest")
    return hmac.new(bytes(key), _reconciliation_payload(claim_key=claim_key, record_digest=record_digest, provider_history_digest=provider_history_digest), hashlib.sha256).hexdigest()


def verify_unsent_reconciliation(*, key: bytes, claim_key: str, record_digest: str, provider_history_digest: str, signature: str) -> bool:
    expected = sign_unsent_reconciliation(key=key, claim_key=claim_key, record_digest=record_digest, provider_history_digest=provider_history_digest)
    try:
        supplied = _safe_hex(signature, field="reconciliation signature")
    except ValidationError:
        return False
    return hmac.compare_digest(expected, supplied)
