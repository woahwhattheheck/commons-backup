"""Provider boundary for FlourishRelay.

No network code lives here.  This adapter creates a handoff envelope only.  In
particular, provider evidence never converts into CONTACT/SPEND/COMMIT authority.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from flourish_relay import SCHEMA_VERSION, ContractError


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_provider_handoff(result: Mapping[str, Any], provider_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(result, Mapping) or not isinstance(result.get("packet"), Mapping) or not isinstance(result.get("receipt"), Mapping):
        raise ContractError("provider handoff requires a complete local route result")
    packet = result["packet"]
    receipt = result["receipt"]
    if receipt.get("packet_sha256") != _sha(packet):
        raise ContractError("provider handoff packet hash mismatch")

    evidence_digest = None
    provider_state = "PROVIDER_EVIDENCE_REQUIRED"
    if provider_evidence is not None:
        if not isinstance(provider_evidence, Mapping):
            raise ContractError("provider evidence must be object")
        allowed = {"provider", "captured_at", "artifact_sha256", "verified"}
        if set(provider_evidence) != allowed:
            raise ContractError("provider evidence must use exact evidence schema")
        if provider_evidence.get("verified") is not True:
            raise ContractError("provider evidence is not verified")
        provider = provider_evidence.get("provider")
        captured = provider_evidence.get("captured_at")
        digest = provider_evidence.get("artifact_sha256")
        if not isinstance(provider, str) or not provider.strip() or not isinstance(captured, str) or not captured.strip():
            raise ContractError("provider evidence names/timestamp are invalid")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ContractError("provider evidence artifact_sha256 invalid")
        evidence_digest = _sha(dict(provider_evidence))
        provider_state = "EVIDENCE_PRESENT_EXTERNAL_AUTHORITY_STILL_REQUIRED"

    envelope = {
        "schema": SCHEMA_VERSION,
        "provider_state": provider_state,
        "local_packet_sha256": receipt["packet_sha256"],
        "provider_evidence_sha256": evidence_digest,
        "packet": packet,
        "executable_external_actions": [],
        "authority": {
            "provider_call": False,
            "contact": False,
            "spend": False,
            "commit": False,
            "schedule": False,
            "share_sensitive": False,
        },
    }
    envelope["envelope_sha256"] = _sha(envelope)
    return envelope
