#!/usr/bin/env python3
"""Fail-closed fleet runtime deployment provenance verifier.

This module is descriptive evidence infrastructure only.  It never grants
provider, outbound, payment, credential, or deployment authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Union

SCHEMA = "fleet-runtime-provenance/v1"
UNKNOWN = "UNKNOWN"
LIFECYCLES = {
    "DECLARED",
    "SOURCE_BOUND",
    "DEPLOYMENT_PROVEN",
    "STALE",
    "UNKNOWN",
    "RETIRED",
}
EVIDENCE_KINDS = {
    "SOURCE_COMMIT",
    "CONFIG_COMMIT",
    "REPO_MERGE",
    "OWNER_ATTESTATION",
    "DEPLOYMENT_RECEIPT",
    "PROVIDER_RUNTIME",
    "BLACK_BOX_PROBE",
}
PROBE_RESULTS = {"PASS", "FAIL", UNKNOWN}
MAX_AGE_SECONDS_DEFAULT = 24 * 60 * 60

_RUNTIME_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SECRET_KEY_RE = re.compile(
    r"(?:^|[_-])(secret|token|password|passwd|credential|authorization|api[_-]?key|private[_-]?key)(?:$|[_-])",
    re.I,
)
_SECRET_VALUE_PATTERNS = (
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:token|secret|password|api[_-]?key)=[^\s&]{4,}"),
)

_REQUIRED_RECORD_KEYS = {
    "runtime_id",
    "provider_ids",
    "custodian",
    "runtime_surface",
    "config_location",
    "deployed_generation",
    "source_commitment",
    "config_commitment",
    "trigger",
    "authority_surfaces",
    "decision_contract",
    "deployment_at",
    "evidence_at",
    "probe",
    "lifecycle",
    "evidence",
}


class RegistryError(ValueError):
    """Raised only for malformed registry structure or secret-bearing data."""


@dataclass(frozen=True)
class RecordAssessment:
    runtime_id: str
    declared_lifecycle: str
    effective_lifecycle: str
    deployment_proven: bool
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "runtime_id": self.runtime_id,
            "declared_lifecycle": self.declared_lifecycle,
            "effective_lifecycle": self.effective_lifecycle,
            "deployment_proven": self.deployment_proven,
            "reasons": list(self.reasons),
            "external_send_authorized": False,
            "provider_mutation_authorized": False,
            "payment_authorized": False,
            "credential_authorized": False,
            "deployment_mutation_authorized": False,
        }


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def registry_digest(registry: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(registry).encode("utf-8")).hexdigest()


def _require_exact_type(value: Any, typ: type, label: str) -> Any:
    if type(value) is not typ:
        raise RegistryError(f"{label}: expected {typ.__name__}")
    return value


def _require_nonempty_string(value: Any, label: str) -> str:
    value = _require_exact_type(value, str, label)
    if not value or value.strip() != value:
        raise RegistryError(f"{label}: must be a non-empty trimmed string")
    return value


def _contains_secret_like_data(value: Any, path: str = "$") -> Optional[str]:
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                return f"{path}: non-string object key"
            if _SECRET_KEY_RE.search(key):
                return f"{path}.{key}: secret-bearing key forbidden"
            hit = _contains_secret_like_data(child, f"{path}.{key}")
            if hit:
                return hit
    elif type(value) is list:
        for index, child in enumerate(value):
            hit = _contains_secret_like_data(child, f"{path}[{index}]")
            if hit:
                return hit
    elif type(value) is str:
        for pattern in _SECRET_VALUE_PATTERNS:
            if pattern.search(value):
                return f"{path}: secret-like value forbidden"
    return None


def _parse_time(value: Any, label: str, *, allow_null: bool = False) -> Optional[datetime]:
    if value is None:
        if allow_null:
            return None
        raise RegistryError(f"{label}: null is not allowed")
    value = _require_nonempty_string(value, label)
    if value == UNKNOWN:
        return None
    if not value.endswith("Z"):
        raise RegistryError(f"{label}: timestamp must be UTC and end in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RegistryError(f"{label}: invalid ISO-8601 timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise RegistryError(f"{label}: timestamp must be UTC")
    return parsed


def _validate_commitment(value: Any, label: str) -> None:
    value = _require_exact_type(value, dict, label)
    if set(value) != {"kind", "value"}:
        raise RegistryError(f"{label}: keys must be exactly kind,value")
    kind = _require_nonempty_string(value["kind"], f"{label}.kind")
    raw = _require_nonempty_string(value["value"], f"{label}.value")
    if kind == UNKNOWN:
        if raw != UNKNOWN:
            raise RegistryError(f"{label}: UNKNOWN kind requires UNKNOWN value")
        return
    if kind == "sha256":
        if not _SHA256_RE.fullmatch(raw):
            raise RegistryError(f"{label}: invalid sha256 commitment")
        return
    if kind == "git-commit":
        if not _GIT_SHA_RE.fullmatch(raw):
            raise RegistryError(f"{label}: invalid git commit commitment")
        return
    raise RegistryError(f"{label}: unsupported commitment kind {kind!r}")


