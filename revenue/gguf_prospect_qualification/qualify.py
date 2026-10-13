#!/usr/bin/env python3
"""Deterministic qualification for the Commons 10-day GGUF diagnostic.

This module ranks *research targets*. It never grants contact/send authority.
Provider-side deconfliction remains a separate mandatory gate.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REQUIRED_EVIDENCE = ("gguf_control", "evaluation_harness", "quantization_gap")


@dataclass(frozen=True)
class Decision:
    organization: str
    state: str
    score: int
    reasons: tuple[str, ...]
    send_authority: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "organization": self.organization,
            "state": self.state,
            "score": self.score,
            "reasons": list(self.reasons),
            "send_authority": self.send_authority,
        }


def _proof(candidate: dict[str, Any], key: str) -> bool:
    evidence = candidate.get("evidence", {}).get(key, {})
    return bool(evidence.get("verified") and evidence.get("url"))


def qualify(candidate: dict[str, Any]) -> Decision:
    organization = str(candidate.get("organization") or "UNKNOWN")
    reasons: list[str] = []

    # Hard collision / truth gates. These are intentionally stronger than scoring.
    if candidate.get("known_do_not_resend"):
        return Decision(organization, "DNR", 0, ("known_do_not_resend",))
    if candidate.get("known_prior_contact"):
        return Decision(organization, "HOLD_PRIOR_CONTACT", 0, ("known_prior_contact",))

    missing = [key for key in REQUIRED_EVIDENCE if not _proof(candidate, key)]
    if missing:
        return Decision(
            organization,
            "RESEARCH_INCOMPLETE",
            0,
            tuple(f"missing_verified_{key}" for key in missing),
        )

    score = 60  # all three acceptance-fit proofs are present
    reasons.extend(["controls_target_gguf", "evaluation_capability_public", "quantization_gap_public"])

    if candidate.get("commercial_entity"):
        score += 5
        reasons.append("commercial_entity")
    if candidate.get("public_business_channel"):
        score += 5
        reasons.append("public_business_channel")
    if candidate.get("gap_is_current"):
        score += 5
        reasons.append("current_gap")

    # Problem specificity matters more than logo size. A prospect that explicitly names
    # the missing quantized evaluation is a stronger fit than a large model vendor with
    # only an inferred comparison surface.
    gap_strength = candidate.get("gap_strength", "inferred")
    gap_points = {"named_missing_eval": 25, "documented_regression": 20, "comparison_surface": 10, "inferred": 0}.get(gap_strength, 0)
    score += gap_points
    reasons.append(f"gap_strength_{gap_strength}")

    budget_signal = candidate.get("budget_signal")
    if budget_signal in {"strong", "medium"}:
        score += 5 if budget_signal == "strong" else 2
        reasons.append(f"budget_signal_{budget_signal}")

    # Deep internal quantization/evaluation capability is a real conversion penalty:
    # it lowers expected need for an outside fixed diagnostic even when technical fit is high.
    internal_capability = candidate.get("internal_capability", "unknown")
    penalty = {"very_high": 25, "high": 15, "medium": 5, "low": 0, "unknown": 0}.get(internal_capability, 0)
    if penalty:
        score -= penalty
        reasons.append(f"internal_capability_penalty_{internal_capability}")

    score = max(0, min(score, 100))
    # Even a 100/100 research target is not authorized for outreach here.
    state = "RESEARCH_READY_SEND_AUTHORITY_PENDING" if score >= 75 else "RESEARCH_READY_LOW_PRIORITY"
    return Decision(organization, state, score, tuple(reasons))


def validate_packet(packet: dict[str, Any]) -> None:
    if packet.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    candidates = packet.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a non-empty list")
    names: set[str] = set()
    for idx, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidate {idx} must be an object")
        name = candidate.get("organization")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"candidate {idx} missing organization")
        if name in names:
            raise ValueError(f"duplicate organization: {name}")
        names.add(name)
        for key, evidence in candidate.get("evidence", {}).items():
            if evidence.get("verified") and not str(evidence.get("url", "")).startswith("https://"):
                raise ValueError(f"{name}: verified {key} evidence requires https URL")


def compile_packet(packet: dict[str, Any]) -> dict[str, Any]:
    validate_packet(packet)
    decisions = [qualify(c).as_dict() for c in packet["candidates"]]
    decisions.sort(key=lambda d: (-d["score"], d["organization"].lower()))
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "GGUF_DIAGNOSTIC_RESEARCH_QUALIFICATION",
        "offer_id": packet.get("offer_id"),
        "send_authority": False,
        "decisions": decisions,
        "research_ready_count": sum(d["state"].startswith("RESEARCH_READY") for d in decisions),
        "blocked_count": sum(not d["state"].startswith("RESEARCH_READY") for d in decisions),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("packet", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    out = compile_packet(packet)
    print(json.dumps(out, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
