"""Exact parsed-object admission and answer-generation binding."""
from __future__ import annotations

import copy
from typing import Any, Mapping

try:
    from . import _engine as core
except ImportError:
    import _engine as core  # type: ignore[no-redef]

DeskError = core.DeskError
SUPPORT_DIGEST_KEY = "supports_answer_sha256"
SUPPORTED_REQUEST = "SUPPORTED_PROPOSED_ANSWER"
LINKED_STATE = "EVIDENCE_LINKED_PROPOSED_ANSWER"


def require_plain_json(value: Any, where: str = "root") -> None:
    """Reject Python aliases/coercions before snapshotting a parsed-object API."""
    value_type = type(value)
    if value_type is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise DeskError(f"{where}: object keys must be exact strings")
            require_plain_json(item, f"{where}.{key}")
        return
    if value_type is list:
        for index, item in enumerate(value):
            require_plain_json(item, f"{where}[{index}]")
        return
    if value is None or value_type in (str, int, bool):
        return
    raise DeskError(f"{where}: expected plain JSON value")


def question_contract(question: Mapping[str, Any]) -> dict[str, Any]:
    keys = {
        "question_id", "section", "prompt", "mode", "assurance_kind",
        "required", "allowed_values", "source_ref", "source_sha256",
    }
    if type(question) is not dict or set(question) != keys:
        raise DeskError("question contract: exact legacy question object required")
    return {key: copy.deepcopy(question[key]) for key in sorted(keys)}


def answer_binding_sha256(question: Mapping[str, Any], answer: str) -> str:
    """Bind evidence to an exact question contract and proposed answer."""
    if type(answer) is not str:
        raise DeskError("answer binding: answer must be an exact string")
    contract = question_contract(question)
    commitment = {
        "kind": "SECURITY_QUESTIONNAIRE_ANSWER_BINDING_V1",
        "question_contract_sha256": core.sha256_hex(core.canonical_bytes(contract)),
        "question_id": contract["question_id"],
        "answer": answer,
    }
    return core.sha256_hex(core.canonical_bytes(commitment))


def prepare_input(raw: Any) -> tuple[
    dict[str, Any], dict[str, list[str]], int, dict[str, Any]
]:
    require_plain_json(raw)
    if type(raw) is not dict:
        raise DeskError("root: expected object")
    candidate = copy.deepcopy(raw)

    raw_bindings: dict[str, dict[str, Any]] = {}
    evidence = candidate.get("evidence")
    if type(evidence) is list:
        for row in evidence:
            if type(row) is not dict:
                continue
            evidence_id = row.get("evidence_id")
            if type(evidence_id) is not str:
                continue
            present = SUPPORT_DIGEST_KEY in row
            value = row.pop(SUPPORT_DIGEST_KEY, None)
            raw_bindings[evidence_id] = {"present": present, "value": value}

    # Preserve the legacy exact schema/type/identity boundary before removing
    # candidate disposition authority. The only extension is the binding field
    # already removed above.
    core.normalize_input(candidate)

    questions = candidate["questions"]
    answers = candidate["proposed_answers"]
    dispositions = candidate["owner_dispositions"]
    question_by_id = {row["question_id"]: row for row in questions}
    answer_by_id = {row["question_id"]: row for row in answers}
    evidence_by_id = {row["evidence_id"]: row for row in candidate["evidence"]}

    failures: dict[str, list[str]] = {}
    for question_id, answer_row in answer_by_id.items():
        if answer_row["state"] != SUPPORTED_REQUEST:
            continue
        question = question_by_id[question_id]
        answer = answer_row["answer"]
        expected = answer_binding_sha256(question, answer)
        for evidence_id in answer_row["evidence_ids"]:
            if evidence_id not in evidence_by_id:
                continue  # normalize_input already emits the precise failure
            binding = raw_bindings.get(
                evidence_id, {"present": False, "value": None}
            )
            supplied = binding["value"] if binding["present"] else None
            if type(supplied) is not str or supplied != expected:
                failures.setdefault(question_id, []).append(
                    f"ANSWER_BINDING_MISMATCH:{evidence_id}"
                )

    lineage = {
        "support_bindings": [
            {
                "evidence_id": evidence_id,
                "present": raw_bindings.get(
                    evidence_id, {"present": False}
                )["present"],
                "value": raw_bindings.get(
                    evidence_id, {"value": None}
                )["value"],
            }
            for evidence_id in sorted(evidence_by_id)
        ],
        "candidate_dispositions": sorted(
            copy.deepcopy(dispositions), key=lambda row: core.canonical_bytes(row)
        ),
    }
    disposition_count = len(dispositions)
    # Commons is open-door. Candidate dispositions remain context, never a gate
    # or owner authority. Strip them before legacy compilation and report that.
    candidate["owner_dispositions"] = []
    return candidate, failures, disposition_count, lineage
