"""Compile and verify deterministic procurement buyer Q&A answer deltas."""
from __future__ import annotations
from typing import Any
from .schema import (BOUNDARY, CLASSIFICATION, DELTA, INPUT, RECEIPT, Error, Output, _authority, _integer, _keys, _string, _timestamp, canon, digest, load)
from .upstream import _upstream
from .qa import _question, _source
from .classify import _conflict_delta, _valid_delta

def compile_delta(raw: bytes) -> Output:
    source_input = load(raw, "input")
    _keys(
        source_input,
        [
            "schema",
            "truth_boundary",
            "packet_id",
            "evaluated_at",
            "source_max_age_seconds",
            "upstream",
            "questions",
            "qa_sources",
        ],
        "input",
    )
    if source_input["schema"] != INPUT or source_input["truth_boundary"] != BOUNDARY:
        raise Error("input: unsupported schema/boundary")
    packet_id = _string(source_input["packet_id"], "input.packet_id", token=True)
    evaluated_raw, evaluated_dt = _timestamp(source_input["evaluated_at"], "input.evaluated_at")
    max_age = _integer(source_input["source_max_age_seconds"], "input.source_max_age_seconds", 1, 31536000)
    upstream = _upstream(source_input["upstream"])

    questions_raw = source_input["questions"]
    if type(questions_raw) is not list:
        raise Error("input.questions: list required")
    questions = [_question(row, idx, upstream) for idx, row in enumerate(questions_raw)]
    question_by_id = {}
    intent_owner = {}
    for q in questions:
        if q["question_id"] in question_by_id:
            raise Error("input.questions: duplicate question_id")
        question_by_id[q["question_id"]] = q
        prior = intent_owner.get(q["intent_id"])
        identity = (q["gap_id"], q["lineage_id"])
        if prior is not None and prior != identity:
            raise Error("input.questions: intent_id remapped across gap/lineage")
        intent_owner[q["intent_id"]] = identity

    sources_raw = source_input["qa_sources"]
    if type(sources_raw) is not list or not sources_raw:
        raise Error("input.qa_sources: non-empty list required")
    sources = [_source(row, idx, evaluated_dt, max_age) for idx, row in enumerate(sources_raw)]
    source_ids = [s["source_id"] for s in sources]
    if len(source_ids) != len(set(source_ids)):
        raise Error("input.qa_sources: duplicate source_id")
    sequence_counts = {}
    for source in sources:
        sequence_counts[source["sequence"]] = sequence_counts.get(source["sequence"], 0) + 1
    for source in sources:
        if sequence_counts[source["sequence"]] > 1:
            source["source_conflicts"].append("DUPLICATE_QA_SEQUENCE")

    answers = []
    answer_ids = set()
    for source in sorted(sources, key=lambda s: (s["sequence"], s["source_id"])):
        for answer in source["answers"]:
            if answer["answer_id"] in answer_ids:
                raise Error("input.qa_sources: duplicate answer_id")
            answer_ids.add(answer["answer_id"])
            answers.append(answer)

    prior_by_answer = {}
    latest_by_question = {}
    active_delta_by_answer = {}
    deltas = []
    for answer in answers:
        question = question_by_id.get(answer["question_id"])
        chronology_conflicts = list(answer["source"]["source_conflicts"])
        supersedes_id = answer["supersedes_answer_id"]
        latest_id = latest_by_question.get(answer["question_id"])
        prior_answer = None
        prior_delta = None
        if supersedes_id is not None:
            prior_answer = prior_by_answer.get(supersedes_id)
            prior_delta = active_delta_by_answer.get(supersedes_id)
            if prior_answer is None:
                chronology_conflicts.append("UNKNOWN_SUPERSEDED_ANSWER")
            else:
                if prior_answer["question_id"] != answer["question_id"]:
                    chronology_conflicts.append("SUPERSESSION_QUESTION_DRIFT")
                if prior_answer["source"]["sequence"] >= answer["source"]["sequence"]:
                    chronology_conflicts.append("SUPERSESSION_NOT_STRICTLY_LATER")
                if latest_id is not None and supersedes_id != latest_id:
                    chronology_conflicts.append("SUPERSESSION_SKIPS_ACTIVE_ANSWER")
        elif latest_id is not None:
            chronology_conflicts.append("MISSING_EXPLICIT_ANSWER_SUPERSESSION")

        if question is None:
            chronology_conflicts.append("UNKNOWN_QUESTION_ID")
        if chronology_conflicts:
            delta = _conflict_delta(answer, question, chronology_conflicts)
        else:
            delta = _valid_delta(answer, question, upstream, prior_delta)

        # A conflicting answer never displaces an earlier valid answer.
        if delta["classification"] != "SOURCE_CONFLICT":
            if prior_delta is not None:
                prior_delta["active"] = False
                prior_delta["superseded_by"] = answer["answer_id"]
            latest_by_question[answer["question_id"]] = answer["answer_id"]
            active_delta_by_answer[answer["answer_id"]] = delta
        prior_by_answer[answer["answer_id"]] = answer
        deltas.append(delta)

    # Questions with admitted source drift must HOLD even before a buyer answer
    # references them; they are retained as deterministic source-conflict rows.
    answered_questions = {a["question_id"] for a in answers}
    for q in sorted(questions, key=lambda row: row["question_id"]):
        if q["conflicts"] and q["question_id"] not in answered_questions:
            deltas.append(
                {
                    "delta_id": f"question:{q['question_id']}",
                    "classification": "SOURCE_CONFLICT",
                    "active": True,
                    "superseded_by": None,
                    "question_id": q["question_id"],
                    "intent_id": q["intent_id"],
                    "gap_id": q["gap_id"],
                    "lineage_id": q["lineage_id"],
                    "before": None,
                    "after": None,
                    "answer_text": "",
                    "affected_module_ids": q["affected_module_ids"],
                    "owner_actions": ["RESOLVE_SOURCE_CONFLICT_BEFORE_PROCEEDING"],
                    "conflict_reasons": q["conflicts"],
                }
            )

    deltas.sort(key=lambda row: row["delta_id"])
    active = [row for row in deltas if row["active"]]
    conflicts = [row for row in active if row["classification"] == "SOURCE_CONFLICT"]
    status = "HOLD_SOURCE_CONFLICT" if conflicts else "OWNER_REVIEW_READY"
    action_rows = []
    if status == "HOLD_SOURCE_CONFLICT":
        action_rows = [
            {
                "action": "RESOLVE_SOURCE_CONFLICT_BEFORE_PROCEEDING",
                "delta_ids": sorted(row["delta_id"] for row in conflicts),
            }
        ]
    else:
        grouped = {}
        for row in active:
            for action in row["owner_actions"]:
                grouped.setdefault(action, []).append(row["delta_id"])
        action_rows = [
            {"action": action, "delta_ids": sorted(ids)}
            for action, ids in sorted(grouped.items())
        ]

    counts = {name: 0 for name in sorted(CLASSIFICATION)}
    for row in active:
        counts[row["classification"]] += 1
    delta_obj = {
        "schema": DELTA,
        "truth_boundary": BOUNDARY,
        "packet_id": packet_id,
        "evaluated_at": evaluated_raw,
        "status": status,
        "upstream": {
            "pack_id": upstream["pack_id"],
            "active_set_sha256": upstream["active_sha256"],
            "gaps_sha256": upstream["gaps_sha256"],
            "receipt_sha256": upstream["receipt_sha256"],
        },
        "counts": {
            "total_delta_rows": len(deltas),
            "active_delta_rows": len(active),
            "superseded_delta_rows": len([row for row in deltas if not row["active"]]),
            "active_by_classification": counts,
        },
        "deltas": deltas,
        "owner_review_actions": action_rows,
        "authority": _authority(),
    }
    delta_bytes = canon(delta_obj)
    markdown_bytes = _markdown(delta_obj)
    receipt = {
        "schema": RECEIPT,
        "truth_boundary": BOUNDARY,
        "packet_id": packet_id,
        "status": status,
        "input_sha256": digest(raw),
        "delta_sha256": digest(delta_bytes),
        "markdown_sha256": digest(markdown_bytes),
        "upstream_active_set_sha256": upstream["active_sha256"],
        "upstream_gaps_sha256": upstream["gaps_sha256"],
        "upstream_receipt_sha256": upstream["receipt_sha256"],
        "active_delta_rows": len(active),
        "source_conflict_rows": len(conflicts),
        "authority": _authority(),
    }
    return Output(delta_bytes, markdown_bytes, canon(receipt), status)


def _markdown(delta_obj: dict[str, Any]):
    lines = [
        "# Procurement buyer Q&A answer delta",
        "",
        f"- Packet: `{delta_obj['packet_id']}`",
        f"- Status: **{delta_obj['status']}**",
        "- Authority: **internal owner review only; no outbound/commercial authority**",
        f"- Upstream active set: `{delta_obj['upstream']['active_set_sha256']}`",
        f"- Upstream gaps: `{delta_obj['upstream']['gaps_sha256']}`",
        "",
        "## Active deltas",
        "",
    ]
    active = [row for row in delta_obj["deltas"] if row["active"]]
    if not active:
        lines.append("No active buyer-answer deltas were emitted.")
    for row in active:
        lines.append(f"### `{row['delta_id']}` — {row['classification']}")
        lines.append("")
        lines.append(f"- Question: `{row['question_id']}`")
        lines.append(f"- Intent: `{row['intent_id'] or 'none'}`")
        lines.append(f"- Gap: `{row['gap_id'] or 'none'}`")
        lines.append(f"- Lineage: `{row['lineage_id'] or 'none'}`")
        if row["conflict_reasons"]:
            lines.append("- Conflicts: " + ", ".join(f"`{x}`" for x in row["conflict_reasons"]))
        if row["affected_module_ids"]:
            lines.append("- Affected modules: " + ", ".join(f"`{x}`" for x in row["affected_module_ids"]))
        lines.append("- Owner actions: " + ", ".join(f"`{x}`" for x in row["owner_actions"]))
        lines.append("")
    lines += ["## Owner-review action list", ""]
    for row in delta_obj["owner_review_actions"]:
        lines.append(f"- `{row['action']}` → " + ", ".join(f"`{x}`" for x in row["delta_ids"]))
    lines += [
        "",
        "## Authority ceiling",
        "",
        "This artifact does not contact the buyer, submit clarification questions or proposals, sign or certify anything, commit price, accept a contract, claim an award, move money, or recognize revenue.",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def verify(input_bytes: bytes, delta_bytes: bytes, markdown_bytes: bytes, receipt_bytes: bytes):
    expected = compile_delta(input_bytes)
    for label, got, want in (
        ("delta", delta_bytes, expected.delta),
        ("markdown", markdown_bytes, expected.markdown),
        ("receipt", receipt_bytes, expected.receipt),
    ):
        if label != "markdown":
            parsed = load(got, label)
            if canon(parsed) != got:
                raise Error(f"{label}: non-canonical bytes")
        if got != want:
            raise Error(f"{label}: mismatch")
    return {
        "verified": True,
        "status": expected.status,
        "delta_sha256": digest(expected.delta),
        "receipt_sha256": digest(expected.receipt),
    }
