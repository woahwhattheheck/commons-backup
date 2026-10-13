"""Evidence-first decision core for ProofLens.

This module deliberately has no OpenCV/AWS dependency. It accepts only a strict,
versioned perception packet and can request human review; it cannot authorize an
external high-authority action.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Any, Iterable, Mapping

ALGORITHM = "prooflens-opencv5-v1"
POLICY_VERSION = "prooflens-policy-v1"
DECISIONS = {
    "NO_ACTION",
    "HOLD_LOW_QUALITY",
    "REQUEST_HUMAN_REVIEW",
    "REPLAY_IGNORED",
}
EVIDENCE_KEYS = {
    "algorithm",
    "source_ref",
    "baseline_sha256",
    "current_sha256",
    "width",
    "height",
    "changed_fraction",
    "edge_delta",
    "mean_delta",
    "quality_score",
    "alignment_confidence",
    "opencv_version",
    "event_id",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _strict_number(value: Any, field: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{field} must be an int or float, not {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be finite")
    return result


def _hex64(value: Any, field: str) -> str:
    if type(value) is not str or len(value) != 64:
        raise ValueError(f"{field} must be 64 lowercase hex characters")
    if value != value.lower() or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{field} must be 64 lowercase hex characters")
    return value


@dataclass(frozen=True)
class Policy:
    min_quality: float = 0.55
    review_changed_fraction: float = 0.025
    review_edge_delta: float = 0.018
    review_mean_delta: float = 10.0

    def validate(self) -> "Policy":
        for name in ("min_quality", "review_changed_fraction", "review_edge_delta"):
            value = _strict_number(getattr(self, name), name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0,1]")
        mean_delta = _strict_number(self.review_mean_delta, "review_mean_delta")
        if not 0.0 <= mean_delta <= 255.0:
            raise ValueError("review_mean_delta must be in [0,255]")
        return self

    @property
    def policy_id(self) -> str:
        payload = {"version": POLICY_VERSION, **asdict(self)}
        return sha256_json(payload)


@dataclass(frozen=True)
class DecisionReceipt:
    decision: str
    reason_codes: tuple[str, ...]
    event_id: str
    policy_id: str
    external_action_authorized: bool = False
    receipt_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason_codes": list(self.reason_codes),
            "event_id": self.event_id,
            "policy_id": self.policy_id,
            "external_action_authorized": self.external_action_authorized,
            "receipt_sha256": self.receipt_sha256,
        }


def validate_evidence(raw: Mapping[str, Any]) -> dict[str, Any]:
    if type(raw) is not dict:
        raise ValueError("evidence must be a JSON object")
    if set(raw) != EVIDENCE_KEYS:
        missing = sorted(EVIDENCE_KEYS - set(raw))
        extra = sorted(set(raw) - EVIDENCE_KEYS)
        raise ValueError(f"evidence keys mismatch: missing={missing} extra={extra}")

    if raw["algorithm"] != ALGORITHM:
        raise ValueError("unsupported evidence algorithm")
    if type(raw["source_ref"]) is not str or not raw["source_ref"].strip():
        raise ValueError("source_ref must be a non-empty string")
    if len(raw["source_ref"].encode("utf-8")) > 2048:
        raise ValueError("source_ref is too large")
    _hex64(raw["baseline_sha256"], "baseline_sha256")
    _hex64(raw["current_sha256"], "current_sha256")
    _hex64(raw["event_id"], "event_id")

    for name in ("width", "height"):
        value = raw[name]
        if type(value) is not int or value < 32 or value > 32768:
            raise ValueError(f"{name} must be an integer in [32,32768]")

    normalized = dict(raw)
    for name in ("changed_fraction", "edge_delta", "quality_score", "alignment_confidence"):
        value = _strict_number(raw[name], name)
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0,1]")
        normalized[name] = value
    mean_delta = _strict_number(raw["mean_delta"], "mean_delta")
    if not 0.0 <= mean_delta <= 255.0:
        raise ValueError("mean_delta must be in [0,255]")
    normalized["mean_delta"] = mean_delta

    version = raw["opencv_version"]
    if type(version) is not str or not version:
        raise ValueError("opencv_version must be a non-empty string")
    try:
        major = int(version.split(".", 1)[0])
    except (ValueError, IndexError) as exc:
        raise ValueError("opencv_version must start with an integer major version") from exc
    if major < 5:
        raise ValueError("ProofLens competition evidence requires OpenCV 5+")

    semantic = {k: normalized[k] for k in sorted(EVIDENCE_KEYS - {"event_id"})}
    expected = sha256_json(semantic)
    if normalized["event_id"] != expected:
        raise ValueError("event_id does not match canonical evidence payload")
    return normalized


def _make_receipt(decision: str, reasons: Iterable[str], event_id: str, policy: Policy) -> DecisionReceipt:
    if decision not in DECISIONS:
        raise ValueError("unknown decision")
    reason_codes = tuple(sorted(set(reasons)))
    unsigned = {
        "decision": decision,
        "reason_codes": list(reason_codes),
        "event_id": event_id,
        "policy_id": policy.policy_id,
        "external_action_authorized": False,
    }
    digest = sha256_json(unsigned)
    return DecisionReceipt(
        decision=decision,
        reason_codes=reason_codes,
        event_id=event_id,
        policy_id=policy.policy_id,
        external_action_authorized=False,
        receipt_sha256=digest,
    )


def decide(raw_evidence: Mapping[str, Any], *, seen_event_ids: Iterable[str] = (), policy: Policy | None = None) -> DecisionReceipt:
    evidence = validate_evidence(raw_evidence)
    active = (policy or Policy()).validate()
    seen = set(seen_event_ids)
    for event_id in seen:
        _hex64(event_id, "seen_event_id")
    if evidence["event_id"] in seen:
        return _make_receipt("REPLAY_IGNORED", ("EVENT_ALREADY_RECORDED",), evidence["event_id"], active)

    if evidence["quality_score"] < active.min_quality:
        reasons = ["QUALITY_BELOW_POLICY"]
        if evidence["alignment_confidence"] < 0.25:
            reasons.append("ALIGNMENT_WEAK")
        return _make_receipt("HOLD_LOW_QUALITY", reasons, evidence["event_id"], active)

    review_reasons: list[str] = []
    if evidence["changed_fraction"] >= active.review_changed_fraction:
        review_reasons.append("CHANGED_FRACTION_THRESHOLD")
    if evidence["edge_delta"] >= active.review_edge_delta:
        review_reasons.append("EDGE_DELTA_THRESHOLD")
    if evidence["mean_delta"] >= active.review_mean_delta:
        review_reasons.append("MEAN_DELTA_THRESHOLD")

    if review_reasons:
        return _make_receipt("REQUEST_HUMAN_REVIEW", review_reasons, evidence["event_id"], active)
    return _make_receipt("NO_ACTION", ("BELOW_REVIEW_THRESHOLDS",), evidence["event_id"], active)


def verify_receipt(
    raw_evidence: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    seen_event_ids: Iterable[str] = (),
    policy: Policy | None = None,
) -> bool:
    """Verify integrity *and* recompile the exact policy semantics.

    Replay receipts are state-dependent, so callers verifying `REPLAY_IGNORED` must
    provide the same retained event-id set that made the event a replay.
    """
    if type(receipt) is not dict:
        return False
    try:
        expected = decide(raw_evidence, seen_event_ids=seen_event_ids, policy=policy).to_dict()
    except ValueError:
        return False
    return receipt == expected
