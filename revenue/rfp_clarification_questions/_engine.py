"""Compilation engine for source-bound clarification packets."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

from ._core import (
    BOUNDARY, INPUT, PACKET, RECEIPT, STATUS,
    UPSTREAM_ACTIVE, UPSTREAM_GAPS, UPSTREAM_RECEIPT,
    Error, Output, _authority, _buyer_safe, _compile_upstream, _keys, _string,
    _to_z, canon, digest, load,
)
from ._rows import _candidate_rows, _deadline_rows, _resolution_rows, _source_registry
from ._render import _markdown

def _compile_at(raw: bytes, now: datetime) -> Output:
    root = load(raw)
    _keys(root, ["schema", "truth_boundary", "solicitation_pack", "question_deadlines", "candidate_questions", "resolutions"], "input")
    if root["schema"] != INPUT or root["truth_boundary"] != BOUNDARY:
        raise Error("input: unsupported schema/boundary")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise Error("internal clock must be timezone-aware")
    now = now.astimezone(timezone.utc)

    pack = root["solicitation_pack"]
    if not isinstance(pack, dict):
        raise Error("solicitation_pack: object required")
    pack_bytes = canon(pack)
    pack_id = _string(pack.get("pack_id"), "solicitation_pack.pack_id", token=True)
    registry = _source_registry(pack)
    active, gaps, upstream_receipt, upstream_status, upstream_error = _compile_upstream(pack_bytes)

    conflicts = []
    if upstream_error:
        conflicts.append(upstream_error)
        active = {"schema": UPSTREAM_ACTIVE, "pack_id": pack_id, "killed_sources": [], "requirements": [], "authority": _authority()}
        gaps = {"schema": UPSTREAM_GAPS, "pack_id": pack_id, "gaps": [], "hold_reasons": ["UPSTREAM_SOURCE_CONFLICT"], "authority": _authority()}
        upstream_receipt = {"schema": UPSTREAM_RECEIPT, "pack_id": pack_id, "pack_sha256": digest(pack_bytes)}
    else:
        if active.get("schema") != UPSTREAM_ACTIVE or gaps.get("schema") != UPSTREAM_GAPS or upstream_receipt.get("schema") != UPSTREAM_RECEIPT:
            conflicts.append("UPSTREAM_SCHEMA_DRIFT")
        if active.get("pack_id") != pack_id or gaps.get("pack_id") != pack_id or upstream_receipt.get("pack_id") != pack_id:
            conflicts.append("UPSTREAM_PACK_ID_DRIFT")
        if upstream_receipt.get("pack_sha256") != digest(pack_bytes):
            conflicts.append("UPSTREAM_PACK_DIGEST_DRIFT")

    killed_raw = active.get("killed_sources", []) if isinstance(active, dict) else []
    killed = set(killed_raw) if isinstance(killed_raw, list) and all(isinstance(v, str) for v in killed_raw) else set()
    _, deadline, deadline_conflicts = _deadline_rows(root["question_deadlines"], registry, killed)
    conflicts.extend(deadline_conflicts)
    resolutions, resolution_conflicts = _resolution_rows(root["resolutions"], registry, killed)
    conflicts.extend(resolution_conflicts)
    candidates, candidate_conflicts = _candidate_rows(root["candidate_questions"], registry, gaps, killed)
    conflicts.extend(candidate_conflicts)

    retained = []
    suppressed = []
    unresolved_candidates = []
    resolution_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for resolution in resolutions:
        resolution_by_key.setdefault((resolution["gap_id"], resolution["intent_id"]), []).append(resolution)

    if not conflicts:
        for candidate in candidates:
            if not candidate["buyer_safe"]:
                suppressed.append({
                    "question_id": candidate["question_id"],
                    "gap_id": candidate["gap_id"],
                    "intent_id": candidate["intent_id"],
                    "reason": "INTERNAL_ONLY_NOT_PROJECTED",
                })
                continue
            if not _buyer_safe(candidate["question_text"]):
                suppressed.append({
                    "question_id": candidate["question_id"],
                    "gap_id": candidate["gap_id"],
                    "intent_id": candidate["intent_id"],
                    "reason": "BUYER_SAFE_LEAKAGE_GUARD",
                })
                continue
            later = [
                r
                for r in resolution_by_key.get((candidate["gap_id"], candidate["intent_id"]), [])
                if r["sequence"] > candidate["sequence"]
            ]
            if later:
                winner = sorted(later, key=lambda r: (r["sequence"], r["resolution_id"]))[-1]
                suppressed.append({
                    "question_id": candidate["question_id"],
                    "gap_id": candidate["gap_id"],
                    "intent_id": candidate["intent_id"],
                    "reason": "ANSWERED_BY_LATER_AMENDMENT",
                    "resolution_id": winner["resolution_id"],
                    "resolution_source_id": winner["source_id"],
                    "resolution_source_sha256": winner["source_sha256"],
                    "resolution_section_id": winner["section_id"],
                })
                continue
            unresolved_candidates.append(candidate)

        by_intent: dict[str, list[dict[str, Any]]] = {}
        for candidate in unresolved_candidates:
            by_intent.setdefault(candidate["intent_id"], []).append(candidate)
        for intent_id in sorted(by_intent):
            group = by_intent[intent_id]
            classes = {row["question_class"] for row in group}
            if len(classes) != 1:
                conflicts.append(f"SEMANTIC_INTENT_CLASS_CONFLICT:{intent_id}")
                continue
            winner = sorted(group, key=lambda row: (row["priority"], row["question_id"]))[0]
            coords = [
                {
                    "gap_id": row["gap_id"],
                    "source_id": row["source_id"],
                    "source_sha256": row["source_sha256"],
                    "section_id": row["section_id"],
                }
                for row in sorted(group, key=lambda row: (row["gap_id"], row["question_id"]))
            ]
            retained.append({
                "question_id": winner["question_id"],
                "intent_id": intent_id,
                "question_class": winner["question_class"],
                "priority": min(row["priority"] for row in group),
                "question_text": winner["question_text"],
                "bid_risk": winner["bid_risk"],
                "covered_gap_ids": sorted({row["gap_id"] for row in group}),
                "source_coordinates": coords,
                "merged_question_ids": sorted(row["question_id"] for row in group),
            })
            for row in group:
                if row["question_id"] != winner["question_id"]:
                    suppressed.append({
                        "question_id": row["question_id"],
                        "gap_id": row["gap_id"],
                        "intent_id": row["intent_id"],
                        "reason": "SEMANTIC_DUPLICATE",
                        "retained_question_id": winner["question_id"],
                    })

    if conflicts:
        status = "HOLD_SOURCE_CONFLICT"
        retained = []
    elif deadline is not None and deadline["dt"] is not None and now >= deadline["dt"]:
        status = "HOLD_DEADLINE_PASSED"
    else:
        status = "READY_FOR_OWNER_REVIEW"
    if status not in STATUS:
        raise Error("internal invalid status")

    retained = sorted(retained, key=lambda row: (row["priority"], row["question_class"], row["question_id"]))
    suppressed = sorted(suppressed, key=lambda row: (row["reason"], row["question_id"]))
    active_deadline = None
    if deadline is not None:
        active_deadline = {
            key: deadline[key]
            for key in ("deadline_id", "source_id", "source_sha256", "section_id", "value", "utc")
        }

    packet_body = {
        "schema": PACKET,
        "truth_boundary": BOUNDARY,
        "status": status,
        "evaluated_at": _to_z(now),
        "pack_id": pack_id,
        "active_question_deadline": active_deadline,
        "source_conflicts": sorted(set(conflicts)),
        "upstream": {
            "status": upstream_status,
            "pack_sha256": digest(pack_bytes),
            "active_set_sha256": None if upstream_error else digest(canon(active)),
            "gaps_sha256": None if upstream_error else digest(canon(gaps)),
            "receipt_sha256": None if upstream_error else digest(canon(upstream_receipt)),
        },
        "questions": retained,
        "suppressed": suppressed,
        "counts": {
            "candidate": len(candidates),
            "retained": len(retained),
            "suppressed": len(suppressed),
            "source_conflicts": len(set(conflicts)),
        },
        "classification": {
            "buyer_safe_draft_only": True,
            "owner_review_required": True,
            "outbound_not_authorized": True,
        },
        "authority": _authority(),
    }
    packet = {**packet_body, "packet_sha256": digest(canon(packet_body))}
    packet_bytes = canon(packet)
    markdown = _markdown(packet).encode("utf-8")
    receipt = {
        "schema": RECEIPT,
        "truth_boundary": BOUNDARY,
        "status": status,
        "evaluated_at": packet["evaluated_at"],
        "pack_id": pack_id,
        "input_sha256": digest(raw),
        "solicitation_pack_sha256": digest(pack_bytes),
        "packet_sha256": digest(packet_bytes),
        "markdown_sha256": digest(markdown),
        "authority": _authority(),
    }
    return Output(packet_bytes, markdown, canon(receipt), status)


