"""Fail-closed prospect contact lock backed by GitHub Contents CAS.

This module is coordination-only.  It never sends provider traffic and no
receipt grants external-send, customer, proposal, payment, or revenue authority.

The canonical contact fingerprint is deliberately independent of campaign,
offer, price, subject, and opportunity wording.  Cooperating workers therefore
race one record for one normalized contact, rather than campaign-specific locks.
"""
from __future__ import annotations

import base64
import dataclasses
import email.utils
import hashlib
import json
import os
import re
import stat
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol

SCHEMA = "prospect-contact-lock-record/v1"
RECEIPT_SCHEMA = "prospect-contact-lock-receipt/v1"
AUTHORITY_GENERATION = "prospect-contact-lock/v1/2026-09-14"
CANONICAL_API_ORIGIN = "https://api.github.com"
CANONICAL_REPOSITORY = "woahwhattheheck/commons"
AUTHORITY_BRANCH = "coordination/prospect-contact-lock-v1"
AUTHORITY_ROOT = ".coordination/prospect-contact-lock/v1"
MAX_MESSAGE_BYTES = 2_000_000
ZERO_SHA256 = "0" * 64
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,159}$")
PHONE_RE = re.compile(r"^\+[1-9][0-9]{7,14}$")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
PAID_SIGNALS = (
    "paid", "bounty", "prize", "contract", "subcontract", "invoice", "fee",
    "commission", "award", "bid", "purchase order", "revenue", "payment",
    "retainer", "discovery", "pilot",
)

AUTHORITY_DOCUMENT = {
    "generation": AUTHORITY_GENERATION,
    "api_origin": CANONICAL_API_ORIGIN,
    "repository": CANONICAL_REPOSITORY,
    "branch": AUTHORITY_BRANCH,
    "root": AUTHORITY_ROOT,
}
AUTHORITY_DIGEST = hashlib.sha256(
    json.dumps(AUTHORITY_DOCUMENT, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()


class LockError(RuntimeError):
    """Base lock failure."""


class ValidationError(LockError):
    """Input or retained-record validation failure."""


class ConflictError(LockError):
    """Another generation owns or changed the prospect record."""


class RemoteError(LockError):
    """Canonical GitHub authority could not be read/written safely."""


@dataclasses.dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes


class Transport(Protocol):
    def request(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> Response:
        ...


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


class UrllibTransport:
    """Token-bearing HTTPS transport pinned to api.github.com and no redirects."""

    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(_RejectRedirects())

    def request(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None) -> Response:
        _assert_canonical_url(url)
        req = urllib.request.Request(url=url, method=method, headers=dict(headers), data=body)
        try:
            with self._opener.open(req, timeout=20) as resp:
                return Response(int(resp.status), dict(resp.headers.items()), resp.read())
        except urllib.error.HTTPError as exc:
            payload = exc.read() if getattr(exc, "fp", None) else b""
            return Response(int(exc.code), dict(exc.headers.items()) if exc.headers else {}, payload)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RemoteError(f"canonical GitHub request failed: {type(exc).__name__}") from exc


@dataclasses.dataclass(frozen=True)
class Target:
    kind: str
    fingerprint: str
    hint: str


@dataclasses.dataclass(frozen=True)
class Receipt:
    action: str
    outcome: str
    key_sha256: str
    state: str
    generation: int
    owner_agent_id: str | None
    owner_operation_id: str | None
    authority_digest: str
    record_sha256: str
    blob_sha: str | None
    commit_sha: str | None
    external_send_authorized: bool = False
    provider_send_completed: bool = False
    payment_or_revenue_inferred: bool = False

    def document(self) -> dict[str, Any]:
        doc = dataclasses.asdict(self)
        doc["schema"] = RECEIPT_SCHEMA
        seal = _sha256_json(doc)
        doc["receipt_sha256"] = seal
        return doc


def verify_receipt(raw: Mapping[str, Any]) -> bool:
    doc = dict(raw)
    seal = doc.pop("receipt_sha256", None)
    if doc.get("schema") != RECEIPT_SCHEMA:
        raise ValidationError("receipt schema mismatch")
    if not isinstance(seal, str) or not HEX64_RE.fullmatch(seal):
        raise ValidationError("receipt seal invalid")
    if _sha256_json(doc) != seal:
        raise ValidationError("receipt seal mismatch")
    if doc.get("authority_digest") != AUTHORITY_DIGEST:
        raise ValidationError("receipt authority mismatch")
    for flag in ("external_send_authorized", "provider_send_completed", "payment_or_revenue_inferred"):
        if doc.get(flag) is not False:
            raise ValidationError(f"receipt authority flag {flag} must remain false")
    return True


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValidationError("value is not canonical JSON") from exc
    return text.encode("utf-8")


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _parse_json_strict(raw: bytes) -> Any:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValidationError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda x: (_ for _ in ()).throw(ValidationError("non-finite JSON")))
    except UnicodeDecodeError as exc:
        raise ValidationError("non-UTF8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError("invalid JSON") from exc


def _token(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text")
    value = unicodedata.normalize("NFKC", value.strip())
    if not TOKEN_RE.fullmatch(value):
        raise ValidationError(f"{field} must be a bounded machine token")
    return value


def _normalize_domain(raw: str) -> str:
    value = unicodedata.normalize("NFKC", raw.strip()).rstrip(".").casefold()
    if not value or CONTROL_RE.search(value) or any(ch.isspace() for ch in value):
        raise ValidationError("invalid domain")
    try:
        ascii_domain = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValidationError("invalid domain") from exc
    if len(ascii_domain) > 253 or "." not in ascii_domain:
        raise ValidationError("domain must be a qualified DNS name")
    labels = ascii_domain.split(".")
    if any(not label or len(label) > 63 or label[0] == "-" or label[-1] == "-" or not re.fullmatch(r"[a-z0-9-]+", label) for label in labels):
        raise ValidationError("invalid domain labels")
    return ascii_domain


def normalize_target(kind: str, raw: str) -> Target:
    kind = _token(kind, "kind").casefold()
    if not isinstance(raw, str):
        raise ValidationError("target must be text")
    value = unicodedata.normalize("NFKC", raw.strip())
    if kind == "email":
        if CONTROL_RE.search(value) or any(ch.isspace() for ch in value) or value.count("@") != 1:
            raise ValidationError("invalid email")
        local, domain = value.rsplit("@", 1)
        local = local.casefold()
        if not local or len(local) > 64:
            raise ValidationError("invalid email local part")
        domain = _normalize_domain(domain)
        canonical = f"{local}@{domain}"
        hint = f"{local[:1]}…@{domain}"
    elif kind == "domain":
        canonical = _normalize_domain(value)
        hint = f"{canonical[:1]}…{canonical[-1:]}"
    elif kind == "phone":
        canonical = re.sub(r"[\s().-]", "", value)
        if not PHONE_RE.fullmatch(canonical):
            raise ValidationError("phone must be E.164")
        hint = canonical[:2] + "…" + canonical[-2:]
    else:
        raise ValidationError("kind must be email, domain, or phone")
    fingerprint = hashlib.sha256(
        b"prospect-contact-lock/v1\0" + kind.encode() + b"\0" + canonical.encode()
    ).hexdigest()
    return Target(kind=kind, fingerprint=fingerprint, hint=hint)


def _compensation_category(text: str) -> str:
    if not isinstance(text, str):
        raise ValidationError("compensation_path must be text")
    norm = unicodedata.normalize("NFKC", text.strip()).casefold()
    if not norm or len(norm) > 500 or CONTROL_RE.search(norm):
        raise ValidationError("compensation_path invalid")
    has_amount = bool(re.search(r"(?:[$€£]\s?\d)|(?:\b\d[\d,.]*\s?(?:usd|eur|gbp|rtc)\b)", norm))
    has_signal = any(word in norm for word in PAID_SIGNALS)
    if not (has_amount or has_signal):
        raise ValidationError("compensation_path must state a concrete paid/award path")
    if "bounty" in norm or "prize" in norm:
        return "bounty_or_prize"
    if "bid" in norm or "award" in norm or "contract" in norm or "subcontract" in norm:
        return "bid_or_contract"
    if "fee" in norm or "commission" in norm or "invoice" in norm or "retainer" in norm:
        return "fee_or_invoice"
    if "pilot" in norm or "discovery" in norm or has_amount:
        return "priced_service"
    return "paid_path"


def digest_message_bytes(data: bytes) -> str:
    if not isinstance(data, (bytes, bytearray)):
        raise ValidationError("message bytes required")
    if not data or len(data) > MAX_MESSAGE_BYTES:
        raise ValidationError("message must be non-empty and bounded")
    return hashlib.sha256(bytes(data)).hexdigest()


def digest_message_file(path: str | os.PathLike[str]) -> str:
    p = os.fspath(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(p, flags)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise ValidationError("message file must be regular")
        if before.st_size <= 0 or before.st_size > MAX_MESSAGE_BYTES:
            raise ValidationError("message file size invalid")
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                raise ValidationError("message file changed during read")
            chunks.append(chunk)
            remaining -= len(chunk)
        extra = os.read(fd, 1)
        after = os.fstat(fd)
        if extra or (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns
        ) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise ValidationError("message file changed during read")
        return hashlib.sha256(b"".join(chunks)).hexdigest()
    finally:
        os.close(fd)


def _assert_canonical_url(url: str) -> None:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "api.github.com":
        raise ValidationError("token-bearing URL is not canonical GitHub API")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValidationError("unsafe canonical API URL")
    if not parsed.path.startswith(f"/repos/{CANONICAL_REPOSITORY}/"):
        raise ValidationError("URL escaped canonical repository")


def _server_time(headers: Mapping[str, str]) -> str:
    date_value = next((v for k, v in headers.items() if k.casefold() == "date"), None)
    if not date_value:
        raise RemoteError("GitHub Date header missing; mutation fails closed")
    try:
        dt = email.utils.parsedate_to_datetime(date_value)
    except (TypeError, ValueError) as exc:
        raise RemoteError("GitHub Date header invalid") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _record_path(target: Target) -> str:
    return f"{AUTHORITY_ROOT}/{target.fingerprint[:2]}/{target.fingerprint}.json"


def _content_url(target: Target) -> str:
    path = urllib.parse.quote(_record_path(target), safe="/")
    url = f"{CANONICAL_API_ORIGIN}/repos/{CANONICAL_REPOSITORY}/contents/{path}?ref={urllib.parse.quote(AUTHORITY_BRANCH, safe='')}"
    _assert_canonical_url(url)
    return url


def _headers(token: str) -> dict[str, str]:
    if not isinstance(token, str) or len(token) < 8 or CONTROL_RE.search(token):
        raise ValidationError("GitHub token missing/invalid")
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "commons-prospect-contact-lock-v1",
    }


def _history_hash(previous: str, record_without_history: Mapping[str, Any]) -> str:
    if previous != ZERO_SHA256 and not HEX64_RE.fullmatch(previous):
        raise ValidationError("previous history hash invalid")
    return hashlib.sha256(bytes.fromhex(previous) + _canonical_json_bytes(record_without_history)).hexdigest()


def _base_record(
    target: Target,
    state: str,
    generation: int,
    owner_agent_id: str | None,
    owner_operation_id: str | None,
    server_time: str,
    previous_record_sha256: str,
    previous_history_sha256: str,
    **extra: Any,
) -> dict[str, Any]:
    core: dict[str, Any] = {
        "schema": SCHEMA,
        "authority": dict(AUTHORITY_DOCUMENT),
        "authority_digest": AUTHORITY_DIGEST,
        "key_sha256": target.fingerprint,
        "target_kind": target.kind,
        "target_hint": target.hint,
        "state": state,
        "generation": generation,
        "owner_agent_id": owner_agent_id,
        "owner_operation_id": owner_operation_id,
        "updated_at": server_time,
        "previous_record_sha256": previous_record_sha256,
        "previous_history_sha256": previous_history_sha256,
        "external_send_authorized": False,
        "provider_send_completed": False,
        "payment_or_revenue_inferred": False,
    }
    core.update(extra)
    core["history_sha256"] = _history_hash(previous_history_sha256, core)
    return core


def _bound_inputs(message_sha256: str, channel: str, compensation_path: str) -> tuple[str, str, str]:
    if not isinstance(message_sha256, str) or not HEX64_RE.fullmatch(message_sha256):
        raise ValidationError("message_sha256 must be lowercase SHA-256")
    channel = _token(channel, "channel").casefold()
    category = _compensation_category(compensation_path)
    compensation_sha = hashlib.sha256(
        unicodedata.normalize("NFKC", compensation_path.strip()).encode()
    ).hexdigest()
    return channel, category, compensation_sha


def _validate_bound_evidence(record: Mapping[str, Any], state: str) -> None:
    for key in ("message_sha256", "compensation_path_sha256"):
        if not isinstance(record.get(key), str) or not HEX64_RE.fullmatch(record[key]):
            raise ValidationError(f"{state} {key} invalid")
    if not isinstance(record.get("channel"), str) or not record["channel"]:
        raise ValidationError(f"{state} channel missing")
    if record.get("compensation_category") not in {
        "bounty_or_prize", "bid_or_contract", "fee_or_invoice",
        "priced_service", "paid_path",
    }:
        raise ValidationError(f"{state} compensation category invalid")


def _validate_record(raw: Mapping[str, Any], target: Target) -> dict[str, Any]:
    record = dict(raw)
    required_exact = {
        "schema": SCHEMA,
        "authority": AUTHORITY_DOCUMENT,
        "authority_digest": AUTHORITY_DIGEST,
        "key_sha256": target.fingerprint,
        "target_kind": target.kind,
        "target_hint": target.hint,
        "external_send_authorized": False,
        "provider_send_completed": False,
        "payment_or_revenue_inferred": False,
    }
    for k, v in required_exact.items():
        if record.get(k) != v:
            raise ValidationError(f"retained record {k} mismatch")
    if record.get("state") not in {"ACTIVE", "ARMED", "OUTCOME_UNKNOWN", "CONTACTED", "RELEASED"}:
        raise ValidationError("retained record state invalid")
    generation = record.get("generation")
    if type(generation) is not int or generation < 1:
        raise ValidationError("retained record generation invalid")
    contacted_count = record.get("contacted_count")
    if type(contacted_count) is not int or contacted_count < 0:
        raise ValidationError("retained contacted_count invalid")
    for key in ("previous_record_sha256", "previous_history_sha256", "history_sha256"):
        value = record.get(key)
        if not isinstance(value, str) or not HEX64_RE.fullmatch(value):
            raise ValidationError(f"retained record {key} invalid")
    history = record["history_sha256"]
    base = dict(record)
    base.pop("history_sha256")
    expected = _history_hash(record["previous_history_sha256"], base)
    if history != expected:
        raise ValidationError("retained history seal mismatch")

    state = record["state"]
    if state == "ACTIVE":
        _token(record.get("owner_agent_id"), "owner_agent_id")
        _token(record.get("owner_operation_id"), "owner_operation_id")
        for forbidden in (
            "armed_at", "dispatched_at", "contacted_at", "message_sha256",
            "provider_receipt_sha256", "compensation_path_sha256",
        ):
            if record.get(forbidden) is not None:
                raise ValidationError("ACTIVE record carries later-stage evidence")
    elif state in {"ARMED", "OUTCOME_UNKNOWN"}:
        _token(record.get("owner_agent_id"), "owner_agent_id")
        _token(record.get("owner_operation_id"), "owner_operation_id")
        _validate_bound_evidence(record, state)
        if not isinstance(record.get("armed_at"), str):
            raise ValidationError(f"{state} armed_at missing")
        if record.get("provider_receipt_sha256") is not None or record.get("contacted_at") is not None:
            raise ValidationError(f"{state} carries contacted evidence")
        if state == "ARMED":
            if record.get("dispatched_at") is not None:
                raise ValidationError("ARMED cannot carry dispatched_at")
        elif not isinstance(record.get("dispatched_at"), str):
            raise ValidationError("OUTCOME_UNKNOWN dispatched_at missing")
    elif state == "CONTACTED":
        _token(record.get("owner_agent_id"), "owner_agent_id")
        _token(record.get("owner_operation_id"), "owner_operation_id")
        _validate_bound_evidence(record, state)
        if not isinstance(record.get("armed_at"), str) or not isinstance(record.get("dispatched_at"), str):
            raise ValidationError("CONTACTED dispatch lineage missing")
        if not isinstance(record.get("contacted_at"), str):
            raise ValidationError("CONTACTED contacted_at missing")
        provider_sha = record.get("provider_receipt_sha256")
        if not isinstance(provider_sha, str) or not HEX64_RE.fullmatch(provider_sha):
            raise ValidationError("CONTACTED provider receipt digest invalid")
    else:
        if record.get("owner_agent_id") is not None or record.get("owner_operation_id") is not None:
            raise ValidationError("RELEASED must have no active owner")
        if record.get("released_from_state") not in {"ACTIVE", "ARMED"}:
            raise ValidationError("RELEASED origin invalid")
        if not isinstance(record.get("release_reason_sha256"), str) or not HEX64_RE.fullmatch(record["release_reason_sha256"]):
            raise ValidationError("RELEASED reason digest invalid")
        for forbidden in ("provider_receipt_sha256", "contacted_at", "dispatched_at"):
            if record.get(forbidden) is not None:
                raise ValidationError("RELEASED carries forbidden effect evidence")
    return record


class ProspectContactLock:
    """Canonical GitHub-backed contact lock.

    The namespace is not configurable. Tests may inject a transport, but all
    generated URLs and every retained record remain bound to AUTHORITY_DOCUMENT.
    No return value from this class is external-send authority.
    """

    def __init__(self, token: str, transport: Transport | None = None) -> None:
        self._token = token
        self._transport = transport or UrllibTransport()
        self._headers = _headers(token)

    def fingerprint(self, kind: str, target: str) -> Target:
        return normalize_target(kind, target)

    def _get(self, target: Target) -> tuple[dict[str, Any] | None, str | None, str]:
        url = _content_url(target)
        response = self._transport.request("GET", url, self._headers, None)
        server_time = _server_time(response.headers)
        if response.status == 404:
            return None, None, server_time
        if response.status != 200:
            raise RemoteError(f"canonical record read failed with HTTP {response.status}")
        envelope = _parse_json_strict(response.body)
        if not isinstance(envelope, Mapping):
            raise ValidationError("GitHub content envelope invalid")
        blob_sha = envelope.get("sha")
        if not isinstance(blob_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", blob_sha):
            raise ValidationError("GitHub content blob SHA invalid")
        if envelope.get("encoding") != "base64" or not isinstance(envelope.get("content"), str):
            raise ValidationError("GitHub content encoding invalid")
        try:
            record_bytes = base64.b64decode(envelope["content"], validate=False)
        except Exception as exc:
            raise ValidationError("GitHub content base64 invalid") from exc
        parsed = _parse_json_strict(record_bytes)
        if not isinstance(parsed, Mapping):
            raise ValidationError("retained record must be object")
        return _validate_record(parsed, target), blob_sha, server_time

    def _put(
        self,
        target: Target,
        record: Mapping[str, Any],
        current_blob_sha: str | None,
        message: str,
    ) -> tuple[str, str | None]:
        body: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(_canonical_json_bytes(record) + b"\n").decode("ascii"),
            "branch": AUTHORITY_BRANCH,
        }
        if current_blob_sha is not None:
            body["sha"] = current_blob_sha
        response = self._transport.request(
            "PUT", _content_url(target), self._headers, _canonical_json_bytes(body)
        )
        _server_time(response.headers)
        if response.status in {409, 412, 422}:
            raise ConflictError("canonical CAS lost; refresh before any external action")
        if response.status not in {200, 201}:
            raise RemoteError(f"canonical record write failed with HTTP {response.status}")
        envelope = _parse_json_strict(response.body)
        if not isinstance(envelope, Mapping):
            raise ValidationError("GitHub write envelope invalid")
        content = envelope.get("content")
        commit = envelope.get("commit")
        if not isinstance(content, Mapping) or not isinstance(commit, Mapping):
            raise ValidationError("GitHub write receipt incomplete")
        blob_sha = content.get("sha")
        commit_sha = commit.get("sha")
        if not isinstance(blob_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", blob_sha):
            raise ValidationError("GitHub write blob SHA invalid")
        if not isinstance(commit_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", commit_sha):
            raise ValidationError("GitHub write commit SHA invalid")
        return blob_sha, commit_sha

    @staticmethod
    def _receipt(
        action: str,
        outcome: str,
        target: Target,
        record: Mapping[str, Any],
        blob_sha: str | None,
        commit_sha: str | None,
    ) -> dict[str, Any]:
        receipt = Receipt(
            action=action,
            outcome=outcome,
            key_sha256=target.fingerprint,
            state=record["state"],
            generation=record["generation"],
            owner_agent_id=record.get("owner_agent_id"),
            owner_operation_id=record.get("owner_operation_id"),
            authority_digest=AUTHORITY_DIGEST,
            record_sha256=_sha256_json(record),
            blob_sha=blob_sha,
            commit_sha=commit_sha,
        ).document()
        verify_receipt(receipt)
        return receipt

    def status(self, kind: str, raw_target: str) -> dict[str, Any]:
        target = normalize_target(kind, raw_target)
        record, blob_sha, _ = self._get(target)
        if record is None:
            return {
                "schema": "prospect-contact-lock-status/v1",
                "authority_digest": AUTHORITY_DIGEST,
                "key_sha256": target.fingerprint,
                "target_hint": target.hint,
                "state": "ABSENT",
                "external_send_authorized": False,
                "provider_send_completed": False,
                "payment_or_revenue_inferred": False,
            }
        return {
            "schema": "prospect-contact-lock-status/v1",
            "authority_digest": AUTHORITY_DIGEST,
            "key_sha256": target.fingerprint,
            "target_hint": target.hint,
            "state": record["state"],
            "generation": record["generation"],
            "owner_agent_id": record.get("owner_agent_id"),
            "owner_operation_id": record.get("owner_operation_id"),
            "record_sha256": _sha256_json(record),
            "blob_sha": blob_sha,
            "external_send_authorized": False,
            "provider_send_completed": False,
            "payment_or_revenue_inferred": False,
        }

    def acquire(
        self, kind: str, raw_target: str, *, agent_id: str, operation_id: str
    ) -> dict[str, Any]:
        target = normalize_target(kind, raw_target)
        agent_id = _token(agent_id, "agent_id")
        operation_id = _token(operation_id, "operation_id")
        record, blob_sha, server_time = self._get(target)
        if record is None:
            new = _base_record(
                target, "ACTIVE", 1, agent_id, operation_id, server_time,
                ZERO_SHA256, ZERO_SHA256,
                created_at=server_time,
                contacted_count=0,
            )
            new_blob, commit = self._put(
                target, new, None, f"prospect-lock: acquire {target.fingerprint[:12]}"
            )
            return self._receipt("acquire", "ACQUIRED", target, new, new_blob, commit)

        state = record["state"]
        if state == "ACTIVE":
            if record["owner_agent_id"] == agent_id and record["owner_operation_id"] == operation_id:
                return self._receipt("acquire", "ALREADY_ACTIVE", target, record, blob_sha, None)
            raise ConflictError("prospect has an ACTIVE owner; there is no timeout takeover")
        if state == "RELEASED":
            previous_record = _sha256_json(record)
            new = _base_record(
                target, "ACTIVE", record["generation"] + 1, agent_id, operation_id,
                server_time, previous_record, record["history_sha256"],
                created_at=record.get("created_at", server_time),
                reacquired_at=server_time,
                contacted_count=record.get("contacted_count", 0),
            )
            new_blob, commit = self._put(
                target, new, blob_sha, f"prospect-lock: reacquire {target.fingerprint[:12]}"
            )
            return self._receipt(
                "acquire", "REACQUIRED_AFTER_EXPLICIT_RELEASE",
                target, new, new_blob, commit,
            )
        if state == "CONTACTED":
            raise ConflictError("prospect is CONTACTED and suppressed")
        if state == "ARMED":
            raise ConflictError("prospect is ARMED; release UNSENT before any reacquire")
        raise ConflictError(
            "prospect is OUTCOME_UNKNOWN; dispatch was consumed and ordinary retry is forbidden"
        )

    def arm(
        self,
        kind: str,
        raw_target: str,
        *,
        agent_id: str,
        operation_id: str,
        message_sha256: str,
        channel: str,
        compensation_path: str,
    ) -> dict[str, Any]:
        target = normalize_target(kind, raw_target)
        agent_id = _token(agent_id, "agent_id")
        operation_id = _token(operation_id, "operation_id")
        channel, category, compensation_sha = _bound_inputs(
            message_sha256, channel, compensation_path
        )
        record, blob_sha, server_time = self._get(target)
        if record is None:
            raise ConflictError("prospect claim missing")
        if record["state"] == "ARMED":
            if (
                record["owner_agent_id"] == agent_id
                and record["owner_operation_id"] == operation_id
                and record["message_sha256"] == message_sha256
                and record["channel"] == channel
                and record["compensation_path_sha256"] == compensation_sha
                and record["compensation_category"] == category
            ):
                return self._receipt("arm", "ALREADY_ARMED", target, record, blob_sha, None)
            raise ConflictError("prospect already ARMED to different owner or payload")
        if record["state"] != "ACTIVE":
            raise ConflictError("only ACTIVE claim may be ARMED")
        if record["owner_agent_id"] != agent_id or record["owner_operation_id"] != operation_id:
            raise ConflictError("only exact ACTIVE owner may arm")

        previous_record = _sha256_json(record)
        new = _base_record(
            target, "ARMED", record["generation"] + 1, agent_id, operation_id,
            server_time, previous_record, record["history_sha256"],
            created_at=record.get("created_at", server_time),
            armed_at=server_time,
            contacted_count=int(record.get("contacted_count", 0)),
            message_sha256=message_sha256,
            channel=channel,
            compensation_path_sha256=compensation_sha,
            compensation_category=category,
        )
        new_blob, commit = self._put(
            target, new, blob_sha, f"prospect-lock: arm {target.fingerprint[:12]}"
        )
        return self._receipt("arm", "ARMED", target, new, new_blob, commit)

    def dispatch(
        self,
        kind: str,
        raw_target: str,
        *,
        agent_id: str,
        operation_id: str,
    ) -> dict[str, Any]:
        """Consume the provider-attempt slot before any external provider call.

        A successful receipt still does not authorize the provider call. It only
        proves that this coordination layer has burned its replayable send slot.
        """
        target = normalize_target(kind, raw_target)
        agent_id = _token(agent_id, "agent_id")
        operation_id = _token(operation_id, "operation_id")
        record, blob_sha, server_time = self._get(target)
        if record is None:
            raise ConflictError("prospect claim missing")
        if record["state"] == "OUTCOME_UNKNOWN":
            raise ConflictError("dispatch slot already consumed; provider outcome requires reconciliation")
        if record["state"] != "ARMED":
            raise ConflictError("only ARMED claim may dispatch")
        if record["owner_agent_id"] != agent_id or record["owner_operation_id"] != operation_id:
            raise ConflictError("only exact ARMED owner may dispatch")

        previous_record = _sha256_json(record)
        new = _base_record(
            target, "OUTCOME_UNKNOWN", record["generation"] + 1,
            agent_id, operation_id, server_time,
            previous_record, record["history_sha256"],
            created_at=record.get("created_at", server_time),
            armed_at=record["armed_at"],
            dispatched_at=server_time,
            contacted_count=int(record.get("contacted_count", 0)),
            message_sha256=record["message_sha256"],
            channel=record["channel"],
            compensation_path_sha256=record["compensation_path_sha256"],
            compensation_category=record["compensation_category"],
        )
        new_blob, commit = self._put(
            target, new, blob_sha, f"prospect-lock: dispatch consume {target.fingerprint[:12]}"
        )
        return self._receipt(
            "dispatch", "OUTCOME_UNKNOWN_SLOT_CONSUMED", target, new, new_blob, commit
        )

    def finalize_contacted(
        self,
        kind: str,
        raw_target: str,
        *,
        agent_id: str,
        operation_id: str,
        message_sha256: str,
        channel: str,
        compensation_path: str,
        provider_receipt: str,
    ) -> dict[str, Any]:
        target = normalize_target(kind, raw_target)
        agent_id = _token(agent_id, "agent_id")
        operation_id = _token(operation_id, "operation_id")
        channel, category, compensation_sha = _bound_inputs(
            message_sha256, channel, compensation_path
        )
        if not isinstance(provider_receipt, str):
            raise ValidationError("provider_receipt must be text")
        provider_receipt = unicodedata.normalize("NFKC", provider_receipt.strip())
        if not provider_receipt or len(provider_receipt) > 1000 or CONTROL_RE.search(provider_receipt):
            raise ValidationError("provider_receipt invalid")
        provider_receipt_sha = hashlib.sha256(provider_receipt.encode()).hexdigest()

        record, blob_sha, server_time = self._get(target)
        if record is None:
            raise ConflictError("prospect claim missing")
        if record["state"] == "CONTACTED":
            if (
                record["owner_agent_id"] == agent_id
                and record["owner_operation_id"] == operation_id
                and record["message_sha256"] == message_sha256
                and record["channel"] == channel
                and record["compensation_path_sha256"] == compensation_sha
                and record["compensation_category"] == category
                and record["provider_receipt_sha256"] == provider_receipt_sha
            ):
                return self._receipt(
                    "finalize", "ALREADY_CONTACTED", target, record, blob_sha, None
                )
            raise ConflictError("prospect already CONTACTED")
        if record["state"] != "OUTCOME_UNKNOWN":
            raise ConflictError("CONTACTED finalization requires a consumed OUTCOME_UNKNOWN dispatch")
        if record["owner_agent_id"] != agent_id or record["owner_operation_id"] != operation_id:
            raise ConflictError("only exact dispatched owner may finalize")
        if (
            record["message_sha256"] != message_sha256
            or record["channel"] != channel
            or record["compensation_path_sha256"] != compensation_sha
            or record["compensation_category"] != category
        ):
            raise ConflictError("finalize evidence does not match exact ARMED dispatch payload")

        previous_record = _sha256_json(record)
        new = _base_record(
            target, "CONTACTED", record["generation"] + 1, agent_id, operation_id,
            server_time, previous_record, record["history_sha256"],
            created_at=record.get("created_at", server_time),
            armed_at=record["armed_at"],
            dispatched_at=record["dispatched_at"],
            contacted_at=server_time,
            contacted_count=int(record.get("contacted_count", 0)) + 1,
            message_sha256=record["message_sha256"],
            channel=record["channel"],
            compensation_path_sha256=record["compensation_path_sha256"],
            compensation_category=record["compensation_category"],
            provider_receipt_sha256=provider_receipt_sha,
        )
        new_blob, commit = self._put(
            target, new, blob_sha, f"prospect-lock: contacted {target.fingerprint[:12]}"
        )
        return self._receipt("finalize", "CONTACTED", target, new, new_blob, commit)

    def release_unsent(
        self,
        kind: str,
        raw_target: str,
        *,
        agent_id: str,
        operation_id: str,
        reason: str,
    ) -> dict[str, Any]:
        target = normalize_target(kind, raw_target)
        agent_id = _token(agent_id, "agent_id")
        operation_id = _token(operation_id, "operation_id")
        if not isinstance(reason, str):
            raise ValidationError("reason must be text")
        reason = unicodedata.normalize("NFKC", reason.strip())
        if not reason or len(reason) > 1000 or CONTROL_RE.search(reason):
            raise ValidationError("release reason invalid")

        record, blob_sha, server_time = self._get(target)
        if record is None:
            raise ConflictError("prospect claim missing")
        if record["state"] == "RELEASED":
            return self._receipt("release", "ALREADY_RELEASED", target, record, blob_sha, None)
        if record["state"] in {"OUTCOME_UNKNOWN", "CONTACTED"}:
            raise ConflictError(
                f"{record['state']} cannot be ordinary-released; provider effect may exist"
            )
        if record["state"] not in {"ACTIVE", "ARMED"}:
            raise ConflictError("only ACTIVE or ARMED claim may release UNSENT")
        if record["owner_agent_id"] != agent_id or record["owner_operation_id"] != operation_id:
            raise ConflictError("only exact owner may release UNSENT")

        previous_record = _sha256_json(record)
        released_from = record["state"]
        new = _base_record(
            target, "RELEASED", record["generation"] + 1, None, None,
            server_time, previous_record, record["history_sha256"],
            created_at=record.get("created_at", server_time),
            released_at=server_time,
            released_from_state=released_from,
            contacted_count=int(record.get("contacted_count", 0)),
            release_reason_sha256=hashlib.sha256(reason.encode()).hexdigest(),
        )
        new_blob, commit = self._put(
            target, new, blob_sha, f"prospect-lock: release unsent {target.fingerprint[:12]}"
        )
        return self._receipt("release", "RELEASED_UNSENT", target, new, new_blob, commit)
