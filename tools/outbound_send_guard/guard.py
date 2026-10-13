"""Backward-compatible fail-closed facade for the outbound send guard.

The deterministic v1 engine remains available as helper/parsing machinery, but
embedded evaluation can never mint positive CURRENT authority. Positive CURRENT
is supported only by the direct isolated CLI process.

Public facade provenance is derived only from source material consumed here.
Parsed-object evaluation binds canonical snapshots. Exact-byte evaluation binds
the exact bytes parsed. Legacy digest keyword arguments remain accepted only so
older composed callers fail safely during migration; their values are inert and
can never replace derived provenance.
"""
from __future__ import annotations

import sys
from copy import deepcopy
from datetime import datetime
from typing import Any

from . import _guard_core as _legacy_core

for _name in dir(_legacy_core):
    if not _name.startswith("__") and _name not in {"evaluate", "main"}:
        globals()[_name] = getattr(_legacy_core, _name)

_EMBEDDED_REASON = (
    "embedded CURRENT authority is unavailable; use direct isolated startup: "
    "python -I -S tools/outbound_send_guard/cli.py ..."
)


def _snapshot_object(raw: Any, label: str) -> dict[str, Any]:
    """Detach one caller-owned object through the strict JSON boundary."""
    if type(raw) is not dict:
        raise _legacy_core.GuardError(f"{label} must be an object")
    try:
        encoded = _legacy_core.canonical_bytes(raw)
    except (TypeError, ValueError) as exc:
        raise _legacy_core.GuardError(f"{label} must be strict JSON data") from exc
    return _legacy_core.parse_json_bytes(encoded, label)


def _evaluate_snapshot(
    intent: dict[str, Any],
    evidence: dict[str, Any],
    *,
    exact_intent_sha256: str | None = None,
    exact_evidence_sha256: str | None = None,
) -> dict[str, Any]:
    if (exact_intent_sha256 is None) != (exact_evidence_sha256 is None):
        raise _legacy_core.GuardError("exact-byte custody requires both source digests")

    receipt = _legacy_core.evaluate(intent, evidence)
    payload = deepcopy(receipt["payload"])
    historical = payload["decision"]

    intent_object_sha256 = _legacy_core.digest_object(intent)
    evidence_object_sha256 = _legacy_core.digest_object(evidence)
    exact_bytes = exact_intent_sha256 is not None

    # These legacy fields are retained for shape compatibility, but they are
    # populated only from source material consumed by this facade. Parsed-object
    # evaluation therefore reports canonical-object hashes; evaluate_bytes()
    # reports exact consumed-byte hashes.
    payload["evidence"]["intent_sha256"] = (
        exact_intent_sha256 if exact_bytes else intent_object_sha256
    )
    payload["evidence"]["evidence_sha256"] = (
        exact_evidence_sha256 if exact_bytes else evidence_object_sha256
    )
    payload["source_custody"] = {
        "mode": "EXACT_CONSUMED_BYTES" if exact_bytes else "CANONICAL_OBJECT_SNAPSHOT",
        "intent": {
            "canonical_object_sha256": intent_object_sha256,
            "exact_bytes_sha256": exact_intent_sha256,
        },
        "evidence": {
            "canonical_object_sha256": evidence_object_sha256,
            "exact_bytes_sha256": exact_evidence_sha256,
        },
    }

    if historical in {"ALLOW_NEW", "REPLY_ONLY"}:
        payload["decision"] = "HOLD"
        payload["reasons"] = list(
            dict.fromkeys([*payload.get("reasons", []), _EMBEDDED_REASON])
        )
    payload["historical_decision"] = historical
    payload["current_preflight_clear"] = False
    payload["net_new_send_preflight_clear"] = False
    payload["reply_preflight_clear"] = False
    payload["side_effects_authorized"] = False
    return {"payload": payload, "receipt_sha256": _legacy_core.digest_object(payload)}


def evaluate(
    intent_raw: dict[str, Any],
    evidence_raw: dict[str, Any],
    *,
    intent_sha256: str | None = None,
    evidence_sha256: str | None = None,
) -> dict[str, Any]:
    """Evaluate detached objects; caller digest overrides are deliberately inert.

    ``intent_sha256`` and ``evidence_sha256`` are deprecated compatibility
    parameters. They are never read as provenance and may be removed once all
    external callers have migrated. Their presence cannot alter any custody
    digest in the returned receipt.
    """
    del intent_sha256, evidence_sha256
    intent = _snapshot_object(intent_raw, "intent")
    evidence = _snapshot_object(evidence_raw, "evidence")
    return _evaluate_snapshot(intent, evidence)


def evaluate_bytes(intent_bytes: bytes, evidence_bytes: bytes) -> dict[str, Any]:
    """Evaluate strict JSON and bind provenance to the exact consumed bytes."""
    if type(intent_bytes) is not bytes or type(evidence_bytes) is not bytes:
        raise _legacy_core.GuardError("evaluate_bytes requires bytes for both sources")
    intent = _legacy_core.parse_json_bytes(intent_bytes, "intent")
    evidence = _legacy_core.parse_json_bytes(evidence_bytes, "evidence")
    return _evaluate_snapshot(
        intent,
        evidence,
        exact_intent_sha256=_legacy_core.digest_bytes(intent_bytes),
        exact_evidence_sha256=_legacy_core.digest_bytes(evidence_bytes),
    )


def evaluate_historical_at(
    intent_raw: dict[str, Any],
    evidence_raw: dict[str, Any],
    *,
    historical_at: datetime,
) -> dict[str, Any]:
    from .current import compile_historical_at

    return compile_historical_at(
        intent_raw, evidence_raw, historical_at=historical_at
    )


def main(argv: list[str] | None = None) -> int:
    del argv
    print(
        "embedded guard CLI is non-authorizing; use direct isolated startup: "
        "python -I -S tools/outbound_send_guard/cli.py ...",
        file=sys.stderr,
    )
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
