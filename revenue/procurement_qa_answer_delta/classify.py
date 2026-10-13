"""Pure delta classification and source-coordinate logic."""
from __future__ import annotations
from typing import Any, Optional

def _coordinate(source: dict[str, Any], answer: dict[str, Any]):
    return {
        "source_id": source["source_id"],
        "source_identity": source["identity"],
        "source_ref": source["ref"],
        "source_sha256": source["sha256"],
        "captured_at": source["captured_at"],
        "sequence": source["sequence"],
        "section_id": answer["section_id"],
        "answer_id": answer["answer_id"],
    }


def _conflict_delta(answer: dict[str, Any], question: Optional[dict[str, Any]], reasons):
    source = answer["source"]
    return {
        "delta_id": f"answer:{answer['answer_id']}",
        "classification": "SOURCE_CONFLICT",
        "active": True,
        "superseded_by": None,
        "question_id": answer["question_id"],
        "intent_id": None if question is None else question["intent_id"],
        "gap_id": None if question is None else question["gap_id"],
        "lineage_id": answer["lineage_id"],
        "before": None,
        "after": {"answer_coordinate": _coordinate(source, answer)},
        "answer_text": answer["answer_text"],
        "affected_module_ids": sorted(set(answer["affected_module_ids"] + ([] if question is None else question["affected_module_ids"]))),
        "owner_actions": ["RESOLVE_SOURCE_CONFLICT_BEFORE_PROCEEDING"],
        "conflict_reasons": sorted(set(reasons)),
    }


def _valid_delta(answer: dict[str, Any], question: dict[str, Any], upstream: dict[str, Any], prior: Optional[dict[str, Any]]):
    effect = answer["effect"]
    lineage = question["lineage_id"]
    req = upstream["requirements"].get(lineage) if lineage else None
    gap = upstream["gaps_by_id"].get(question["gap_id"]) if question["gap_id"] else None
    conflicts = []
    if answer["lineage_id"] != lineage:
        conflicts.append("ANSWER_LINEAGE_MISMATCH")
    if question["conflicts"]:
        conflicts.extend(question["conflicts"])

    req_after = answer["requirement_after"]
    deadline_after = answer["deadline_after"]
    if effect == "CLOSE_GAP":
        if gap is None:
            conflicts.append("CLOSE_GAP_WITHOUT_MAPPED_GAP")
        if req_after is not None or deadline_after is not None:
            conflicts.append("CLOSE_GAP_HAS_UNEXPECTED_AFTER_FACT")
        classification = "CLOSED_GAP"
        actions = ["REMOVE_GAP_FROM_OWNER_WORKLIST", "REVIEW_ANSWER_FOR_PROPOSAL_IMPACT"]
        after = {"gap_state": "CLOSED", "requirement": None, "deadline": None}
    elif effect == "REOPEN_GAP":
        if prior is None or prior.get("classification") != "CLOSED_GAP":
            conflicts.append("REOPEN_WITHOUT_PRIOR_CLOSED_GAP")
        if gap is None:
            conflicts.append("REOPEN_GAP_WITHOUT_MAPPED_GAP")
        if req_after is not None or deadline_after is not None:
            conflicts.append("REOPEN_GAP_HAS_UNEXPECTED_AFTER_FACT")
        classification = "REOPENED_GAP"
        actions = ["ADD_GAP_TO_OWNER_WORKLIST", "RECHECK_RESPONSE_MODULES"]
        after = {"gap_state": "OPEN", "requirement": None, "deadline": None}
    elif effect == "REQUIREMENT_CHANGE":
        if req is None or req_after is None:
            conflicts.append("REQUIREMENT_CHANGE_MISSING_ACTIVE_OR_AFTER")
        elif req_after["lineage_id"] != req["lineage_id"]:
            conflicts.append("REQUIREMENT_CHANGE_LINEAGE_DRIFT")
        elif {k: req_after[k] for k in ("lineage_id", "section_id", "kind", "family", "tags", "text")} == {k: req[k] for k in ("lineage_id", "section_id", "kind", "family", "tags", "text")}:
            conflicts.append("REQUIREMENT_CHANGE_HAS_NO_DELTA")
        if deadline_after is not None:
            conflicts.append("REQUIREMENT_CHANGE_HAS_DEADLINE_FACT")
        classification = "REQUIREMENT_CHANGED"
        actions = ["UPDATE_REQUIREMENT_LINEAGE", "REBUILD_EVIDENCE_GAP", "RESELECT_RESPONSE_MODULES"]
        after = {"gap_state": "REVIEW_REQUIRED", "requirement": req_after, "deadline": None}
    elif effect == "DEADLINE_CHANGE":
        if upstream["deadline"] is None or deadline_after is None:
            conflicts.append("DEADLINE_CHANGE_MISSING_BEFORE_OR_AFTER")
        elif deadline_after == upstream["deadline"]["value"] or deadline_after == upstream["deadline"]["utc"]:
            conflicts.append("DEADLINE_CHANGE_HAS_NO_DELTA")
        if req_after is not None:
            conflicts.append("DEADLINE_CHANGE_HAS_REQUIREMENT_FACT")
        classification = "DEADLINE_CHANGED"
        actions = ["UPDATE_DEADLINE_CONTROL", "REPLAN_SUBMISSION_SCHEDULE"]
        after = {"gap_state": "UNCHANGED", "requirement": None, "deadline": deadline_after}
    else:
        if req_after is not None or deadline_after is not None:
            conflicts.append("INFORMATIONAL_HAS_MUTATING_AFTER_FACT")
        classification = "INFORMATIONAL_ONLY"
        actions = ["REVIEW_INFORMATIONAL_ANSWER"]
        after = {"gap_state": "UNCHANGED", "requirement": None, "deadline": None}

    if conflicts:
        return _conflict_delta(answer, question, conflicts)

    before = {
        "gap": None
        if gap is None
        else {
            "gap_id": gap.get("gap_id"),
            "state": "OPEN",
            "severity": gap.get("severity"),
            "reason": gap.get("reason"),
            "source_id": gap.get("source_id"),
            "source_sha256": gap.get("source_sha256"),
            "section_id": gap.get("section_id"),
        },
        "requirement": None
        if req is None
        else {k: req[k] for k in ("lineage_id", "section_id", "kind", "family", "tags", "text", "source_id", "source_ref", "source_sha256", "sequence")},
        "deadline": upstream["deadline"] if effect == "DEADLINE_CHANGE" else None,
        "question_source": {
            "source_id": question["source_id"],
            "source_sha256": question["source_sha256"],
            "section_id": question["section_id"],
        },
    }
    after["answer_coordinate"] = _coordinate(answer["source"], answer)
    return {
        "delta_id": f"answer:{answer['answer_id']}",
        "classification": classification,
        "active": True,
        "superseded_by": None,
        "question_id": question["question_id"],
        "intent_id": question["intent_id"],
        "gap_id": question["gap_id"],
        "lineage_id": lineage,
        "before": before,
        "after": after,
        "answer_text": answer["answer_text"],
        "affected_module_ids": sorted(set(question["affected_module_ids"] + answer["affected_module_ids"])),
        "owner_actions": actions,
        "conflict_reasons": [],
    }
