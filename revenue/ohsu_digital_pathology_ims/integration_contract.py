# SPDX-License-Identifier: Apache-2.0
"""Synthetic, PHI-free Epic Beaker/IMS integration evidence model.

This is not an Epic interface implementation. It proves that a proposed adapter
can preserve correlation, directionality, idempotency and provenance in a
synthetic acceptance fixture without claiming clinical interoperability.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from typing import Any

class ContractError(ValueError):
    pass


def _canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()

@dataclass(frozen=True)
class Message:
    message_id: str
    correlation_id: str
    direction: str
    kind: str
    payload: dict[str, Any]

    def validate(self) -> None:
        for field in ("message_id", "correlation_id", "direction", "kind"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value:
                raise ContractError(f"{field} must be non-empty")
        if self.direction not in {"BEAKER_TO_IMS", "IMS_TO_BEAKER"}:
            raise ContractError("invalid direction")
        if self.kind not in {"CASE_ORDER", "IMAGE_READY", "AI_RESULT", "CASE_STATUS"}:
            raise ContractError("invalid kind")
        if not isinstance(self.payload, dict):
            raise ContractError("payload must be object")
        forbidden = {"patient_name", "mrn", "dob", "ssn", "email", "phone"}
        if forbidden.intersection(self.payload):
            raise ContractError("fixture must not contain direct patient identifiers")

    @property
    def digest(self) -> str:
        self.validate()
        return _sha(asdict(self))


def evaluate_trace(messages: list[Message]) -> dict[str, Any]:
    if not messages:
        raise ContractError("trace must not be empty")
    seen_ids: dict[str, str] = {}
    correlations: dict[str, set[str]] = {}
    kinds: dict[str, set[str]] = {}
    replay_count = 0
    for msg in messages:
        msg.validate()
        d = msg.digest
        prior = seen_ids.get(msg.message_id)
        if prior is not None:
            if prior != d:
                raise ContractError("message id reused with different payload")
            replay_count += 1
            continue
        seen_ids[msg.message_id] = d
        correlations.setdefault(msg.correlation_id, set()).add(msg.direction)
        kinds.setdefault(msg.correlation_id, set()).add(msg.kind)

    broken = sorted(cid for cid, dirs in correlations.items() if dirs != {"BEAKER_TO_IMS", "IMS_TO_BEAKER"})
    incomplete = sorted(
        cid for cid, ks in kinds.items()
        if "CASE_ORDER" not in ks or not ({"IMAGE_READY", "AI_RESULT", "CASE_STATUS"} & ks)
    )
    decision = "PASS" if not broken and not incomplete else "HOLD"
    receipt = {
        "schema": "ohsu-digital-pathology-synthetic-trace/v1",
        "decision": decision,
        "message_count": len(seen_ids),
        "exact_replays_collapsed": replay_count,
        "broken_bidirectional_correlations": broken,
        "incomplete_correlations": incomplete,
        "trace_digest": _sha(sorted(seen_ids.items())),
        "authority": "SYNTHETIC_EVIDENCE_ONLY_NO_CLINICAL_INTEROPERABILITY_CLAIM",
        "contains_phi": False,
    }
    receipt["receipt_digest"] = _sha(receipt)
    return receipt
