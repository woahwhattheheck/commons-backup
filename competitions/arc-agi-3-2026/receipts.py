"""Canonical, offline-verifiable SAGE trace receipts."""
from __future__ import annotations

import json
from hashlib import sha256
from typing import Any, Mapping, Sequence

from sage import Transition, animation_signature, grid_digest, trace_digest

SCHEMA = "arc3-sage-trace-receipt/v1"


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def transition_record(t: Transition) -> dict[str, Any]:
    return {
        "before_sha256": grid_digest(t.before.frame),
        "action": {"name": t.action.name, "x": t.action.x, "y": t.action.y},
        "effect_sha256": t.effect.digest,
        "after_sha256": grid_digest(t.after.frame),
        "animation_sha256": animation_signature(t.after),
        "animation_frames": len(t.after.frames),
        "state": t.after.state,
        "levels_completed": t.after.levels_completed,
    }


def compile_receipt(trace: Sequence[Transition], *, agent_revision: str, source_refs: Mapping[str, str]) -> dict[str, Any]:
    if not trace:
        raise ValueError("trace must be non-empty")
    if not agent_revision or len(agent_revision) > 200:
        raise ValueError("agent_revision required")
    refs = []
    for key, value in sorted(source_refs.items()):
        if not key or not value or len(key) > 200 or len(value) > 500:
            raise ValueError("invalid source ref")
        refs.append({"name": key, "ref": value})
    body = {
        "schema": SCHEMA,
        "agent_revision": agent_revision,
        "trace_sha256": trace_digest(trace),
        "steps": [transition_record(t) for t in trace],
        "source_refs": refs,
        "external_authority": {
            "kaggle_submission": False,
            "competition_rules_acceptance": False,
            "prize_or_revenue": False,
        },
    }
    body["receipt_sha256"] = sha256(canonical_json(body)).hexdigest()
    return body


def verify_receipt(receipt: Mapping[str, Any]) -> bool:
    if set(receipt) != {"schema", "agent_revision", "trace_sha256", "steps", "source_refs", "external_authority", "receipt_sha256"}:
        return False
    if receipt.get("schema") != SCHEMA:
        return False
    digest = receipt.get("receipt_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        return False
    body = dict(receipt)
    body.pop("receipt_sha256")
    if sha256(canonical_json(body)).hexdigest() != digest:
        return False
    authority = receipt.get("external_authority")
    if authority != {"kaggle_submission": False, "competition_rules_acceptance": False, "prize_or_revenue": False}:
        return False
    steps = receipt.get("steps")
    if not isinstance(steps, list) or not steps:
        return False
    for step in steps:
        if not isinstance(step, dict):
            return False
        for key in ("before_sha256", "effect_sha256", "after_sha256", "animation_sha256"):
            value = step.get(key)
            if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                return False
        action = step.get("action")
        if not isinstance(action, dict) or set(action) != {"name", "x", "y"}:
            return False
    return True
