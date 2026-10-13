"""GitHub metadata writes through the existing account publishing service."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from threading import Lock
from time import monotonic

from commons_publication_policy import check_publication
from integrations.shared_equipment.provider_io import EquipmentError, redacted


_IDENTITY_TERMS = ("Codex", "Claude", "Opus", "Fable", "Astra", "Sol", "Grok")
_VISIBLE_FIELDS = {
    "issue.create": ("title", "body"),
    "issue.update": ("title", "body"),
    "issue.comment.create": ("body", "comment"),
    "issue.comment.update": ("body", "comment"),
    "pull.create": ("title", "body", "head", "base"),
    "pull.update": ("title", "body", "base"),
    "pull.comment.create": ("body", "comment"),
    "pull.comment.update": ("body", "comment"),
    "pull.review.create": ("body", "review"),
    "commit.create": ("message",),
    "commit.merge": ("commit_title", "commit_message", "message"),
    "branch.create": ("branch", "branch_name", "ref"),
    "branch.update": ("branch", "branch_name", "ref"),
    "release.create": ("name", "title", "body", "tag_name"),
    "release.update": ("name", "title", "body", "tag_name"),
}
_PROSE_OPERATIONS = {
    "issue.create",
    "issue.update",
    "issue.comment.create",
    "issue.comment.update",
    "pull.create",
    "pull.update",
    "pull.comment.create",
    "pull.comment.update",
    "pull.review.create",
    "release.create",
    "release.update",
}
_CAPABILITY_DRIFT_TTL_SECONDS = 300.0
_CAPABILITY_DRIFT_LOCK = Lock()
_CAPABILITY_DRIFT: dict[tuple[str, str], dict[str, object]] = {}


def _identity_token_char(value: str) -> bool:
    return bool(value) and unicodedata.category(value)[0] in {"L", "M", "N"}


def _identity_matches(value: str) -> tuple[str, ...]:
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFKC", value)
        if unicodedata.category(character) != "Cf"
    ).casefold()
    found = []
    for term in _IDENTITY_TERMS:
        needle = term.casefold()
        offset = 0
        while True:
            start = normalized.find(needle, offset)
            if start < 0:
                break
            end = start + len(needle)
            before = normalized[start - 1] if start else ""
            after = normalized[end] if end < len(normalized) else ""
            if not _identity_token_char(before) and not _identity_token_char(after):
                found.append(term)
                break
            offset = start + 1
    return tuple(found)


def _private_hold(code: str, instruction: str, *, fields=(), terms=()):
    error = EquipmentError(
        "publication held privately before provider dispatch; " + instruction,
        code=code,
        uncertain=False,
    )
    error.incident = False
    error.delivered = False
    error.matched_fields = tuple(fields)
    error.matched_terms = tuple(terms)
    error.private_instruction = instruction
    return error


def _preflight(operation, arguments):
    if not isinstance(arguments, dict):
        raise _private_hold(
            "outbound_field_mapping_missing",
            "supply a mapped GitHub publication argument object and retry the same operation",
        )
    names = _VISIBLE_FIELDS.get(operation)
    if names is None:
        raise _private_hold(
            "outbound_field_mapping_missing",
            "use a mapped GitHub publication operation and retry; no fallback notification was created",
        )
    fields = {
        name: arguments[name]
        for name in names
        if isinstance(arguments.get(name), str)
    }
    matched_fields = []
    matched_terms = set()
    for name, value in fields.items():
        terms = _identity_matches(value)
        if terms:
            matched_fields.append(name)
            matched_terms.update(terms)
    if matched_fields:
        ordered_terms = [term for term in _IDENTITY_TERMS if term in matched_terms]
        raise _private_hold(
            "outbound_identity_attribution",
            "remove " + ", ".join(ordered_terms) + " from outward field(s) "
            + ", ".join(matched_fields) + ", then retry the same operation",
            fields=matched_fields,
            terms=ordered_terms,
        )
    if operation in _PROSE_OPERATIONS:
        title = fields.get("title", "")
        body = "\n".join(
            fields[name]
            for name in ("body", "comment", "review")
            if fields.get(name)
        )
        decision = check_publication(body, title)
        if not decision["allowed"]:
            raise _private_hold(
                decision["code"],
                "revise the provider-visible title or body and retry the same operation; no fallback notification was created",
                fields=tuple(fields),
            )


def _client_key(client: Path) -> str:
    return str(client.expanduser().resolve(strict=False))


def _capability_drift_result(
    operation: str,
    operation_id: str,
    *,
    publisher_version: str | None,
    cached: bool,
    retry_after_seconds: int | None = None,
) -> dict:
    publication = {
        "allow": False,
        "incident": False,
        "operation_id": operation_id,
        "error": "INVALID_OPERATION",
        "cached_capability_drift": cached,
    }
    if publisher_version:
        publication["version"] = publisher_version
    drift = {
        "operation": operation,
        "publisher_version": publisher_version,
        "cached": cached,
        "quarantine_seconds": int(_CAPABILITY_DRIFT_TTL_SECONDS),
    }
    result = {
        "ok": False,
        "operation_id": operation_id,
        "uncertain": False,
        "actor": None,
        "publication": publication,
        "code": "publisher_capability_drift",
        "retryable": False,
        "capability_drift": drift,
    }
    if retry_after_seconds is not None:
        result["retry_after_seconds"] = retry_after_seconds
    return result


def _cached_capability_drift(client: Path, operation: str, operation_id: str) -> dict | None:
    key = (_client_key(client), operation)
    now = monotonic()
    with _CAPABILITY_DRIFT_LOCK:
        entry = _CAPABILITY_DRIFT.get(key)
        if entry is None:
            return None
        expires_at = float(entry["expires_at"])
        if expires_at <= now:
            _CAPABILITY_DRIFT.pop(key, None)
            return None
        version = entry.get("publisher_version")
    remaining = max(1, int(expires_at - now + 0.999))
    return _capability_drift_result(
        operation,
        operation_id,
        publisher_version=version if isinstance(version, str) else None,
        cached=True,
        retry_after_seconds=remaining,
    )


def _record_capability_drift(client: Path, operation: str, receipt: dict) -> None:
    version = receipt.get("version")
    if not isinstance(version, str) or not version:
        version = None
    with _CAPABILITY_DRIFT_LOCK:
        _CAPABILITY_DRIFT[(_client_key(client), operation)] = {
            "publisher_version": version,
            "expires_at": monotonic() + _CAPABILITY_DRIFT_TTL_SECONDS,
        }


GH = Path.home() / "AppData/Local/Programs/GitHub CLI/gh.exe"


def _named_actor_token(actor: str) -> str:
    """Select an existing shared GitHub credential by login name.

    A direct gh keyring read scoped to this call: the global active account
    is never switched, and the token exists only in memory and the scoped
    child-process environment. Any named login resolves or fails generically.
    """
    if not isinstance(actor, str) or not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", actor):
        raise EquipmentError("actor must be a GitHub login name")
    completed = subprocess.run(
        [str(GH), "auth", "token", "--hostname", "github.com", "--user", actor],
        capture_output=True, text=True, encoding="utf-8", timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode or not completed.stdout.strip():
        raise EquipmentError("named shared GitHub credential unavailable for actor " + actor)
    return completed.stdout.strip()


def _actor_readback(token: str) -> dict:
    env = {**os.environ, "GH_TOKEN": token}
    completed = subprocess.run(
        [str(GH), "api", "graphql", "-f", "query=query { viewer { login databaseId } }"],
        capture_output=True, text=True, encoding="utf-8", timeout=30, env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if completed.returncode:
        raise EquipmentError("actor readback unavailable for the named credential")
    try:
        viewer = json.loads(completed.stdout)["data"]["viewer"]
    except (ValueError, KeyError, TypeError):
        raise EquipmentError("actor readback response invalid") from None
    if not isinstance(viewer.get("login"), str) or not isinstance(viewer.get("databaseId"), int):
        raise EquipmentError("actor readback response invalid")
    return {"login": viewer["login"], "id": viewer["databaseId"]}


def publish(operation, arguments, operation_id, *, runner=None, client=None, actor=None):
    if not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", operation_id):
        raise EquipmentError(
            "operation_id must contain 8 to 128 ASCII letters, digits, dots, underscores, colons, or hyphens",
            code="invalid_operation_id", delivered=False, uncertain=False,
        )
    _preflight(operation, arguments)
    client = Path(client) if client is not None else Path.home() / ".commons/tjlabs-publication/publish.py"
    if not client.is_file():
        raise EquipmentError("existing account publishing client is unavailable; restore its shared installation")
    quarantined = _cached_capability_drift(client, operation, operation_id)
    if quarantined is not None:
        return quarantined
    envelope = {"operation_id": operation_id, "operation": operation, "args": arguments}
    env = None
    resolved_actor = None
    if actor is not None:
        token = _named_actor_token(actor)
        resolved_actor = _actor_readback(token)
        if resolved_actor["login"].lower() != actor.lower():
            raise EquipmentError("named credential resolved to a different actor")
        env = {**os.environ, "GH_TOKEN": token}
    try:
        result = (runner or subprocess.run)(
            [sys.executable, str(client), "publish"],
            input=json.dumps(envelope, ensure_ascii=False), text=True, encoding="utf-8",
            capture_output=True, timeout=150, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        raise EquipmentError("publication response unavailable; reconcile the same operation_id",
                             code="publisher_transport_failed", uncertain=True) from None
    try:
        receipt = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise EquipmentError("publication receipt unavailable; reconcile the same operation_id",
                             code="publisher_response_invalid", uncertain=True) from None
    if not isinstance(receipt, dict) or receipt.get("operation_id") != operation_id:
        raise EquipmentError("publication receipt identity mismatch; reconcile the same operation_id",
                             code="publisher_response_invalid", uncertain=True)
    ok = result.returncode == 0 and receipt.get("allow") is True and isinstance(receipt.get("receipt"), dict)
    uncertain = receipt.get("error") in {
        "GITHUB_DELIVERY_UNCERTAIN", "OPERATION_IN_PROGRESS_OR_REQUIRES_RECONCILIATION",
    } or receipt.get("state") in {"DISPATCHING", "DELIVERY_UNCERTAIN"}
    response = {"ok": ok, "operation_id": operation_id, "uncertain": uncertain,
                "actor": resolved_actor, "publication": redacted(receipt)}
    if (not ok and not uncertain and receipt.get("error") == "INVALID_OPERATION"
            and receipt.get("incident") is not True):
        _record_capability_drift(client, operation, receipt)
        version = receipt.get("version")
        if not isinstance(version, str) or not version:
            version = None
        response["code"] = "publisher_capability_drift"
        response["retryable"] = False
        response["retry_after_seconds"] = int(_CAPABILITY_DRIFT_TTL_SECONDS)
        response["capability_drift"] = {
            "operation": operation,
            "publisher_version": version,
            "cached": False,
            "quarantine_seconds": int(_CAPABILITY_DRIFT_TTL_SECONDS),
        }
    return response
