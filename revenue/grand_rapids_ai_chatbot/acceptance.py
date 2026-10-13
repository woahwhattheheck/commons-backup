#!/usr/bin/env python3
"""Deterministic technical acceptance checker for the proposed City chatbot seam.

The checker evaluates *evidence records*, not natural-language quality.  It is a
proposal/UAT carrier: City-approved fixtures and gold routing/source metadata can
replace the synthetic examples later without changing the safety invariants.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

ALLOWED_DISPOSITIONS = {"ANSWER", "HOLD", "ESCALATE"}
BLOCKING_SOURCE_STATES = {"CONFLICT", "STALE", "MISSING"}
BLOCKING_RISKS = {"HIGH", "EMERGENCY", "LEGAL", "ELIGIBILITY", "ENFORCEMENT"}


def _sig(result: dict[str, Any]) -> str:
    material = {
        "disposition": result.get("disposition"),
        "route": result.get("route"),
        "citations": result.get("citations"),
        "canonical_case_id": result.get("canonical_case_id"),
        "effect_status": result.get("effect_status"),
        "logical_effects": result.get("logical_effects"),
        "model_version": result.get("model_version"),
        "rule_version": result.get("rule_version"),
    }
    raw = json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def evaluate_fixture(cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    case_by_id: dict[str, dict[str, Any]] = {}
    result_by_id: dict[str, dict[str, Any]] = {}

    for case in cases:
        cid = case.get("case_id")
        if not isinstance(cid, str) or not cid:
            errors.append("case has missing/invalid case_id")
            continue
        if cid in case_by_id:
            errors.append(f"duplicate case_id: {cid}")
        case_by_id[cid] = case

    for result in results:
        cid = result.get("case_id")
        if not isinstance(cid, str) or not cid:
            errors.append("result has missing/invalid case_id")
            continue
        if cid in result_by_id:
            errors.append(f"duplicate result case_id: {cid}")
        result_by_id[cid] = result

    missing = sorted(set(case_by_id) - set(result_by_id))
    extra = sorted(set(result_by_id) - set(case_by_id))
    if missing:
        errors.append("missing results: " + ", ".join(missing))
    if extra:
        errors.append("unexpected results: " + ", ".join(extra))

    for cid in sorted(set(case_by_id) & set(result_by_id)):
        case = case_by_id[cid]
        result = result_by_id[cid]
        disposition = result.get("disposition")
        if disposition not in ALLOWED_DISPOSITIONS:
            errors.append(f"{cid}: invalid disposition")
            continue
        if result.get("route") != case.get("gold_route"):
            errors.append(f"{cid}: route mismatch")
        if not isinstance(result.get("model_version"), str) or not result["model_version"].strip():
            errors.append(f"{cid}: missing model_version")
        if not isinstance(result.get("rule_version"), str) or not result["rule_version"].strip():
            errors.append(f"{cid}: missing rule_version")
        if not isinstance(result.get("canonical_case_id"), str) or not result["canonical_case_id"].strip():
            errors.append(f"{cid}: missing canonical_case_id")

        source_state = case.get("source_state")
        risk = case.get("risk")
        must_block = source_state in BLOCKING_SOURCE_STATES or risk in BLOCKING_RISKS
        if must_block and disposition == "ANSWER":
            errors.append(f"{cid}: blocked source/risk case cannot ANSWER")
        if not must_block and disposition == "ANSWER":
            approved_raw = case.get("approved_sources")
            approved: set[tuple[str, str]] = set()
            if not isinstance(approved_raw, list) or not approved_raw:
                errors.append(f"{cid}: ANSWER case requires approved_sources")
            else:
                for source in approved_raw:
                    if not isinstance(source, dict) or not isinstance(source.get("source_id"), str) or not isinstance(source.get("version"), str):
                        errors.append(f"{cid}: malformed approved source")
                        continue
                    approved.add((source["source_id"], source["version"]))
            citations = result.get("citations")
            if not isinstance(citations, list) or not citations:
                errors.append(f"{cid}: ANSWER requires citations")
            else:
                got: set[tuple[str, str]] = set()
                for c in citations:
                    if not isinstance(c, dict) or not isinstance(c.get("source_id"), str) or not isinstance(c.get("version"), str):
                        errors.append(f"{cid}: malformed citation")
                        continue
                    got.add((c["source_id"], c["version"]))
                if not got or not got.issubset(approved):
                    errors.append(f"{cid}: citation is not an exact approved source/version")
        elif disposition != "ANSWER" and result.get("citations") not in ([], None):
            errors.append(f"{cid}: non-answer disposition must not carry answer citations")

        if case.get("timeout_after_commit") and result.get("effect_status") not in {"APPLIED", "NOT_APPLIED"}:
            errors.append(f"{cid}: timeout-after-commit requires reconciled effect_status")
        if not case.get("timeout_after_commit") and result.get("effect_status") not in {"NONE", "APPLIED", "NOT_APPLIED"}:
            errors.append(f"{cid}: invalid effect_status")
        effects = result.get("logical_effects")
        if not isinstance(effects, int) or isinstance(effects, bool) or effects < 0:
            errors.append(f"{cid}: logical_effects must be a non-negative integer")

    groups: dict[str, list[str]] = {}
    for cid, case in case_by_id.items():
        group = case.get("duplicate_group")
        if isinstance(group, str) and group:
            groups.setdefault(group, []).append(cid)
    for group, ids in sorted(groups.items()):
        present = [result_by_id[i] for i in ids if i in result_by_id]
        canonical = {r.get("canonical_case_id") for r in present}
        if len(canonical) != 1:
            errors.append(f"duplicate_group {group}: members disagree on canonical_case_id")
        total_effects = sum(r.get("logical_effects", 0) for r in present if isinstance(r.get("logical_effects"), int) and not isinstance(r.get("logical_effects"), bool))
        if total_effects > 1:
            errors.append(f"duplicate_group {group}: more than one logical effect")

    for cid, case in case_by_id.items():
        original_id = case.get("replay_of")
        if not original_id or cid not in result_by_id or original_id not in result_by_id:
            continue
        if _sig(result_by_id[cid]) != _sig(result_by_id[original_id]):
            errors.append(f"{cid}: replay receipt diverges from {original_id}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "cases": len(case_by_id),
        "results": len(result_by_id),
        "errors": errors,
        "authority": "technical acceptance evidence only; City retains policy, routing, emergency, legal, eligibility, enforcement, and release authority",
    }
