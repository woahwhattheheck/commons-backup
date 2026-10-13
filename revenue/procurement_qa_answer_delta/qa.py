"""Validation for retained clarification question and buyer-answer facts."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from .schema import (EFFECT, QUESTION_CLASS, SOURCE_CLASS, Error, _keys, _nullable_token, _requirement, _sha, _string, _timestamp, _tokens, _integer)

def _question(value: Any, idx: int, upstream: dict[str, Any]):
    where = f"questions[{idx}]"
    _keys(
        value,
        [
            "question_id",
            "intent_id",
            "question_class",
            "gap_id",
            "lineage_id",
            "section_id",
            "source_id",
            "source_sha256",
            "affected_module_ids",
        ],
        where,
    )
    qclass = _string(value["question_class"], where + ".question_class", token=True, limit=48)
    if qclass not in QUESTION_CLASS:
        raise Error(f"{where}: unsupported question class")
    gap_id = _nullable_token(value["gap_id"], where + ".gap_id")
    lineage_id = _nullable_token(value["lineage_id"], where + ".lineage_id")
    section_id = _string(value["section_id"], where + ".section_id", token=True)
    source_id = _string(value["source_id"], where + ".source_id", token=True)
    source_sha = _sha(value["source_sha256"], where + ".source_sha256")
    conflicts = []
    if lineage_id is not None:
        req = upstream["requirements"].get(lineage_id)
        if req is None:
            conflicts.append("QUESTION_UNKNOWN_ACTIVE_LINEAGE")
        else:
            if section_id != req["section_id"]:
                conflicts.append("QUESTION_SECTION_DRIFT")
            if source_id != req["source_id"] or source_sha != req["source_sha256"]:
                conflicts.append("QUESTION_SOURCE_DRIFT")
        if gap_id is None:
            conflicts.append("QUESTION_MISSING_GAP_MAPPING")
        else:
            gap = upstream["gaps_by_id"].get(gap_id)
            if gap is None:
                conflicts.append("QUESTION_UNKNOWN_GAP")
            elif gap.get("lineage_id") != lineage_id:
                conflicts.append("QUESTION_GAP_LINEAGE_DRIFT")
            elif gap.get("source_id") != source_id or gap.get("source_sha256") != source_sha:
                conflicts.append("QUESTION_GAP_SOURCE_DRIFT")
    else:
        if qclass not in {"COMMERCIAL_ASSUMPTION", "INFORMATIONAL_CURIOSITY"}:
            conflicts.append("QUESTION_CLASS_REQUIRES_LINEAGE")
        if source_id != upstream["current_source"]["source_id"] or source_sha != upstream["current_source"]["sha256"]:
            conflicts.append("QUESTION_SOURCE_DRIFT")
        if gap_id is not None and gap_id not in upstream["gaps_by_id"]:
            conflicts.append("QUESTION_UNKNOWN_GAP")
    return {
        "question_id": _string(value["question_id"], where + ".question_id", token=True),
        "intent_id": _string(value["intent_id"], where + ".intent_id", token=True),
        "question_class": qclass,
        "gap_id": gap_id,
        "lineage_id": lineage_id,
        "section_id": section_id,
        "source_id": source_id,
        "source_sha256": source_sha,
        "affected_module_ids": sorted(_tokens(value["affected_module_ids"], where + ".affected_module_ids")),
        "conflicts": sorted(set(conflicts)),
    }


def _answer(value: Any, source: dict[str, Any], idx: int):
    where = f"source[{source['source_id']}].answers[{idx}]"
    _keys(
        value,
        [
            "answer_id",
            "supersedes_answer_id",
            "question_id",
            "lineage_id",
            "section_id",
            "effect",
            "answer_text",
            "requirement_after",
            "deadline_after",
            "affected_module_ids",
        ],
        where,
    )
    effect = _string(value["effect"], where + ".effect", token=True, limit=48)
    if effect not in EFFECT:
        raise Error(f"{where}: unsupported effect")
    req_after = value["requirement_after"]
    if req_after is not None:
        req_after = _requirement(req_after, where + ".requirement_after", upstream=False)
    deadline_after = value["deadline_after"]
    if deadline_after is not None:
        deadline_after, deadline_dt = _timestamp(deadline_after, where + ".deadline_after")
    else:
        deadline_dt = None
    return {
        "answer_id": _string(value["answer_id"], where + ".answer_id", token=True),
        "supersedes_answer_id": _nullable_token(value["supersedes_answer_id"], where + ".supersedes_answer_id"),
        "question_id": _string(value["question_id"], where + ".question_id", token=True),
        "lineage_id": _nullable_token(value["lineage_id"], where + ".lineage_id"),
        "section_id": _string(value["section_id"], where + ".section_id", token=True),
        "effect": effect,
        "answer_text": _string(value["answer_text"], where + ".answer_text"),
        "requirement_after": req_after,
        "deadline_after": deadline_after,
        "deadline_after_dt": deadline_dt,
        "affected_module_ids": sorted(_tokens(value["affected_module_ids"], where + ".affected_module_ids")),
        "source": source,
    }


def _source(value: Any, idx: int, evaluated_dt: datetime, max_age: int):
    where = f"qa_sources[{idx}]"
    _keys(
        value,
        ["source_id", "identity", "ref", "sha256", "captured_at", "sequence", "source_class", "answers"],
        where,
    )
    source_class = _string(value["source_class"], where + ".source_class", token=True, limit=32)
    if source_class not in SOURCE_CLASS:
        raise Error(f"{where}: unsupported source class")
    captured_raw, captured_dt = _timestamp(value["captured_at"], where + ".captured_at")
    age = int((evaluated_dt - captured_dt).total_seconds())
    source = {
        "source_id": _string(value["source_id"], where + ".source_id", token=True),
        "identity": _string(value["identity"], where + ".identity"),
        "ref": _string(value["ref"], where + ".ref"),
        "sha256": _sha(value["sha256"], where + ".sha256"),
        "captured_at": captured_raw,
        "captured_dt": captured_dt,
        "sequence": _integer(value["sequence"], where + ".sequence", 0),
        "source_class": source_class,
        "source_conflicts": [],
    }
    if captured_dt > evaluated_dt:
        source["source_conflicts"].append("FUTURE_QA_SOURCE")
    elif age > max_age:
        source["source_conflicts"].append("STALE_QA_SOURCE")
    if source_class != "BUYER_OFFICIAL":
        source["source_conflicts"].append("NON_BUYER_OFFICIAL_SOURCE")
    if type(value["answers"]) is not list or not value["answers"]:
        raise Error(f"{where}: answers required")
    source["answers"] = [_answer(row, source, ans_idx) for ans_idx, row in enumerate(value["answers"])]
    return source
