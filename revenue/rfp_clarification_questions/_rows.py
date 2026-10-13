"""Strict source/deadline/question lineage validation for clarification packets."""
from __future__ import annotations
from typing import Any, Mapping
from ._core import (
    Error, QUESTION_CLASS, SOURCE_CLASS, _boolean, _integer, _keys, _sha, _string,
    _timestamp, _to_z,
)

SOURCE_KIND = {"SOLICITATION", "AMENDMENT"}


def _source_registry(pack: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(pack, dict):
        raise Error("solicitation_pack: object required")
    sources = pack.get("sources")
    if not isinstance(sources, list) or not sources:
        raise Error("solicitation_pack.sources: nonempty list required")
    registry: dict[str, dict[str, Any]] = {}
    official_sequences: set[int] = set()
    for index, source in enumerate(sources):
        where = f"solicitation_pack.sources[{index}]"
        if not isinstance(source, dict):
            raise Error(f"{where}: object required")
        sid = _string(source.get("source_id"), where + ".source_id", token=True)
        klass = _string(source.get("source_class"), where + ".source_class", token=True, limit=32)
        if klass not in SOURCE_CLASS:
            raise Error(f"{where}: unsupported source_class")
        kind = _string(source.get("kind"), where + ".kind", token=True, limit=32)
        if kind not in SOURCE_KIND:
            raise Error(f"{where}: unsupported kind")
        sha = _sha(source.get("sha256"), where + ".sha256")
        seq = _integer(source.get("sequence"), where + ".sequence", 1, 10**6)
        if sid in registry:
            raise Error("solicitation_pack: duplicate source identity")
        if klass == "BUYER_OFFICIAL":
            if seq in official_sequences:
                raise Error("solicitation_pack: duplicate official sequence")
            official_sequences.add(seq)
        registry[sid] = {
            "source_id": sid,
            "source_class": klass,
            "kind": kind,
            "sha256": sha,
            "sequence": seq,
        }
    return registry


def _deadline_rows(rows: Any, registry: Mapping[str, Mapping[str, Any]], killed: set[str]):
    if not isinstance(rows, list) or not rows:
        raise Error("question_deadlines: nonempty list required")
    normalized = []
    ids = set()
    conflicts = []
    for index, row in enumerate(rows):
        where = f"question_deadlines[{index}]"
        _keys(row, ["deadline_id", "source_id", "source_sha256", "section_id", "value", "supersedes_deadline_ids"], where)
        did = _string(row["deadline_id"], where + ".deadline_id", token=True)
        sid = _string(row["source_id"], where + ".source_id", token=True)
        sha = _sha(row["source_sha256"], where + ".source_sha256")
        section = _string(row["section_id"], where + ".section_id", token=True)
        value = _string(row["value"], where + ".value", limit=32)
        supersedes = row["supersedes_deadline_ids"]
        if not isinstance(supersedes, list) or len(supersedes) > 32:
            raise Error(where + ".supersedes_deadline_ids: list required")
        supersedes = [_string(v, where + ".supersedes_deadline_ids", token=True) for v in supersedes]
        if len(supersedes) != len(set(supersedes)):
            raise Error(where + ": duplicate supersession target")
        if did in ids:
            raise Error("question_deadlines: duplicate deadline_id")
        ids.add(did)
        source = registry.get(sid)
        if source is None or source["source_class"] != "BUYER_OFFICIAL" or source["sha256"] != sha or sid in killed:
            conflicts.append(f"DEADLINE_SOURCE_DRIFT:{did}")
            seq = -1
        else:
            seq = int(source["sequence"])
        try:
            dt = _timestamp(value, where + ".value")
        except Error:
            conflicts.append(f"DEADLINE_TIMEZONE_OR_FORMAT:{did}")
            dt = None
        normalized.append({
            "deadline_id": did,
            "source_id": sid,
            "source_sha256": sha,
            "section_id": section,
            "value": value,
            "utc": None if dt is None else _to_z(dt),
            "dt": dt,
            "sequence": seq,
            "supersedes_deadline_ids": supersedes,
        })
    by_id = {row["deadline_id"]: row for row in normalized}
    superseded = set()
    for row in normalized:
        for target_id in row["supersedes_deadline_ids"]:
            target = by_id.get(target_id)
            if target is None:
                conflicts.append(f"UNKNOWN_DEADLINE_SUPERSESSION:{row['deadline_id']}:{target_id}")
                continue
            if row["sequence"] <= target["sequence"]:
                conflicts.append(f"NON_LATER_DEADLINE_SUPERSESSION:{row['deadline_id']}:{target_id}")
            superseded.add(target_id)
    active = [row for row in normalized if row["deadline_id"] not in superseded]
    if len(active) != 1:
        conflicts.append(f"ACTIVE_QUESTION_DEADLINE_COUNT:{len(active)}")
    return normalized, active[0] if len(active) == 1 else None, conflicts


def _resolution_rows(rows: Any, registry: Mapping[str, Mapping[str, Any]], killed: set[str]):
    if not isinstance(rows, list) or len(rows) > 512:
        raise Error("resolutions: list required")
    out = []
    seen = set()
    conflicts = []
    for index, row in enumerate(rows):
        where = f"resolutions[{index}]"
        _keys(row, ["resolution_id", "intent_id", "gap_id", "source_id", "source_sha256", "section_id", "answer_summary"], where)
        rid = _string(row["resolution_id"], where + ".resolution_id", token=True)
        intent = _string(row["intent_id"], where + ".intent_id", token=True)
        gap = _string(row["gap_id"], where + ".gap_id", token=True)
        sid = _string(row["source_id"], where + ".source_id", token=True)
        sha = _sha(row["source_sha256"], where + ".source_sha256")
        section = _string(row["section_id"], where + ".section_id", token=True)
        answer = _string(row["answer_summary"], where + ".answer_summary", limit=4096)
        if rid in seen:
            raise Error("resolutions: duplicate resolution_id")
        seen.add(rid)
        source = registry.get(sid)
        if source is None or source["source_class"] != "BUYER_OFFICIAL" or source["sha256"] != sha or sid in killed:
            conflicts.append(f"RESOLUTION_SOURCE_DRIFT:{rid}")
            seq = -1
        elif source["kind"] != "AMENDMENT":
            conflicts.append(f"RESOLUTION_SOURCE_NOT_AMENDMENT:{rid}")
            seq = -1
        else:
            seq = int(source["sequence"])
        out.append({
            "resolution_id": rid,
            "intent_id": intent,
            "gap_id": gap,
            "source_id": sid,
            "source_sha256": sha,
            "section_id": section,
            "answer_summary": answer,
            "sequence": seq,
        })
    by_tuple: dict[tuple[str, str, str], str] = {}
    for row in out:
        key = (row["gap_id"], row["intent_id"], row["source_id"])
        prior = by_tuple.get(key)
        if prior is not None and prior != row["answer_summary"]:
            conflicts.append(f"CONTRADICTORY_RESOLUTION:{row['gap_id']}:{row['intent_id']}:{row['source_id']}")
        by_tuple[key] = row["answer_summary"]
    return out, conflicts


def _candidate_rows(rows: Any, registry: Mapping[str, Mapping[str, Any]], gaps: Mapping[str, Any], killed: set[str]):
    if not isinstance(rows, list) or len(rows) > 512:
        raise Error("candidate_questions: list required")
    gap_rows = gaps.get("gaps") if isinstance(gaps, dict) else None
    if not isinstance(gap_rows, list):
        raise Error("upstream gaps: gap list required")
    gap_by_id = {}
    for gap in gap_rows:
        if isinstance(gap, dict) and isinstance(gap.get("gap_id"), str):
            gap_by_id[gap["gap_id"]] = gap
    out = []
    conflicts = []
    seen = set()
    for index, row in enumerate(rows):
        where = f"candidate_questions[{index}]"
        _keys(
            row,
            ["question_id", "intent_id", "gap_id", "question_class", "priority", "question_text", "bid_risk", "buyer_safe", "source_id", "source_sha256", "section_id", "internal_note"],
            where,
        )
        qid = _string(row["question_id"], where + ".question_id", token=True)
        intent = _string(row["intent_id"], where + ".intent_id", token=True)
        gap_id = _string(row["gap_id"], where + ".gap_id", token=True)
        qclass = _string(row["question_class"], where + ".question_class", token=True, limit=40)
        if qclass not in QUESTION_CLASS:
            raise Error(where + ": unsupported question_class")
        priority = _integer(row["priority"], where + ".priority", 1, 5)
        question = _string(row["question_text"], where + ".question_text", limit=2000)
        risk = _string(row["bid_risk"], where + ".bid_risk", limit=2000)
        buyer_safe = _boolean(row["buyer_safe"], where + ".buyer_safe")
        sid = _string(row["source_id"], where + ".source_id", token=True)
        sha = _sha(row["source_sha256"], where + ".source_sha256")
        section = _string(row["section_id"], where + ".section_id", token=True)
        internal = _string(row["internal_note"], where + ".internal_note", limit=4000, allow_empty=True)
        if qid in seen:
            raise Error("candidate_questions: duplicate question_id")
        seen.add(qid)

        source = registry.get(sid)
        gap = gap_by_id.get(gap_id)
        if source is None or source["source_class"] != "BUYER_OFFICIAL" or source["sha256"] != sha or sid in killed:
            conflicts.append(f"QUESTION_SOURCE_DRIFT:{qid}")
            seq = -1
        else:
            seq = int(source["sequence"])
        if gap is None:
            conflicts.append(f"UNKNOWN_GAP:{qid}:{gap_id}")
        else:
            if gap.get("source_id") != sid or gap.get("source_sha256") != sha or gap.get("section_id") != section:
                conflicts.append(f"QUESTION_GAP_BINDING_DRIFT:{qid}:{gap_id}")
            kind = gap.get("kind")
            if qclass == "MANDATORY_AMBIGUITY" and kind != "MANDATORY":
                conflicts.append(f"QUESTION_CLASS_GAP_MISMATCH:{qid}")
            if qclass == "SCORED_AMBIGUITY" and kind != "SCORED":
                conflicts.append(f"QUESTION_CLASS_GAP_MISMATCH:{qid}")
            if qclass == "INFORMATIONAL_CURIOSITY" and kind not in {"INFORMATIONAL", None}:
                conflicts.append(f"QUESTION_CLASS_GAP_MISMATCH:{qid}")
        out.append({
            "question_id": qid,
            "intent_id": intent,
            "gap_id": gap_id,
            "question_class": qclass,
            "priority": priority,
            "question_text": question,
            "bid_risk": risk,
            "buyer_safe": buyer_safe,
            "source_id": sid,
            "source_sha256": sha,
            "section_id": section,
            "internal_note": internal,
            "sequence": seq,
        })
    return out, conflicts
