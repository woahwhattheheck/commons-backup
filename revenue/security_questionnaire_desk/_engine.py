#!/usr/bin/env python3
"""Evidence-bound Security Questionnaire Desk.

Offline fulfillment compiler for the Commons ``ho-security-questionnaire`` candidate.
The module never contacts a buyer, changes provider state, mints certifications,
or performs payment/revenue actions.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SCHEMA_VERSION = 1
MAX_INPUT_BYTES = 1_048_576
MAX_ITEMS = 2000
MAX_TEXT = 8000
MAX_SHORT = 240
MAX_REF = 512
SAFE_INT = (1 << 53) - 1

MODES = {"BOOLEAN", "TEXT", "ENUM", "MULTI"}
ASSURANCE_KINDS = {"GENERAL", "CERTIFICATION"}
EVIDENCE_KINDS = {
    "PUBLIC_REPO",
    "PUBLIC_POLICY",
    "PUBLIC_DOC",
    "OWNER_ATTESTATION",
    "THIRD_PARTY_REPORT_REFERENCE",
    "CERTIFICATION_REFERENCE",
}
DISCLOSURES = {"PUBLIC", "NON_PUBLIC"}
REQUESTED_STATES = {"SUPPORTED_PROPOSED_ANSWER", "UNMEASURED", "OWNER_INPUT_REQUIRED"}
DISPOSITIONS = {"APPROVED_FOR_RETURN", "REVISE", "REJECT"}

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]{1,64}@[\w.-]{1,190}\.[A-Za-z]{2,24}(?![\w.-])")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)")
_SECRET_RE = re.compile(
    r"(?:-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|"
    r"\bAKIA[0-9A-Z]{16}\b|"
    r"\bASIA[0-9A-Z]{16}\b|"
    r"\bsk-[A-Za-z0-9_-]{20,}\b|"
    r"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|passwd)\s*[:=]\s*\S{8,})",
    re.IGNORECASE,
)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
_CLAIM_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,119}$")
_LONG_NUMBER_RE = re.compile(r"(?<!\d)\d{13,19}(?!\d)")


class DeskError(ValueError):
    """Fail-closed input, verification, or publication error."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_hex(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _expect_exact_keys(obj: Mapping[str, Any], expected: set[str], where: str) -> None:
    if set(obj) != expected:
        missing = sorted(expected - set(obj))
        extra = sorted(set(obj) - expected)
        raise DeskError(f"{where}: key mismatch missing={missing} extra={extra}")


def _expect_dict(value: Any, where: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise DeskError(f"{where}: expected object")
    return value


def _expect_list(value: Any, where: str, *, max_items: int = MAX_ITEMS) -> list[Any]:
    if type(value) is not list:
        raise DeskError(f"{where}: expected array")
    if len(value) > max_items:
        raise DeskError(f"{where}: too many items")
    return value


def _expect_bool(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise DeskError(f"{where}: expected boolean")
    return value


def _expect_int(value: Any, where: str, *, min_value: int = 0, max_value: int = SAFE_INT) -> int:
    if type(value) is not int:
        raise DeskError(f"{where}: expected integer")
    if value < min_value or value > max_value:
        raise DeskError(f"{where}: integer out of range")
    return value


def _check_text_safety(text: str, where: str, *, allow_pii: bool = False) -> None:
    if "\ufeff" in text:
        raise DeskError(f"{where}: BOM not allowed")
    if _CONTROL_RE.search(text):
        raise DeskError(f"{where}: control character not allowed")
    if _SECRET_RE.search(text):
        raise DeskError(f"{where}: secret-shaped material not allowed")
    if not allow_pii:
        if _EMAIL_RE.search(text) or _PHONE_RE.search(text):
            raise DeskError(f"{where}: direct contact PII not allowed")
        if _LONG_NUMBER_RE.search(text):
            raise DeskError(f"{where}: long credential/account-number-shaped material not allowed")


def _expect_text(
    value: Any,
    where: str,
    *,
    min_len: int = 1,
    max_len: int = MAX_TEXT,
    id_like: bool = False,
    claim_key: bool = False,
    allow_pii: bool = False,
) -> str:
    if type(value) is not str:
        raise DeskError(f"{where}: expected string")
    if not (min_len <= len(value) <= max_len):
        raise DeskError(f"{where}: string length out of range")
    _check_text_safety(value, where, allow_pii=allow_pii)
    if id_like and not _ID_RE.fullmatch(value):
        raise DeskError(f"{where}: invalid identifier")
    if claim_key and not _CLAIM_KEY_RE.fullmatch(value):
        raise DeskError(f"{where}: invalid claim key")
    return value


def _expect_sha(value: Any, where: str) -> str:
    text = _expect_text(value, where, min_len=64, max_len=64)
    if not re.fullmatch(r"[0-9a-f]{64}", text):
        raise DeskError(f"{where}: expected lowercase SHA-256")
    return text


def _parse_utc(value: Any, where: str) -> datetime:
    text = _expect_text(value, where, min_len=20, max_len=20)
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", text):
        raise DeskError(f"{where}: expected whole-second UTC")
    try:
        dt = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise DeskError(f"{where}: invalid UTC timestamp") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != text:
        raise DeskError(f"{where}: noncanonical UTC timestamp")
    return dt


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        raise DeskError("trusted time must be timezone-aware")
    value = value.astimezone(timezone.utc)
    if value.microsecond:
        raise DeskError("trusted time must be whole-second")
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _bounded_int_token(token: str) -> int:
    if len(token.lstrip("-")) > 16:
        raise DeskError("JSON integer token too long")
    value = int(token)
    if abs(value) > SAFE_INT:
        raise DeskError("JSON integer outside safe range")
    return value


def _reject_float(token: str) -> Any:
    raise DeskError(f"JSON floats are not accepted: {token[:24]}")


def _reject_constant(token: str) -> Any:
    raise DeskError(f"non-finite JSON constant is not accepted: {token}")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise DeskError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(raw: bytes | str) -> Any:
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise DeskError("input is not strict UTF-8") from exc
    if raw.startswith("\ufeff"):
        raise DeskError("UTF-8 BOM is not accepted")
    try:
        return json.loads(raw, object_pairs_hook=_pairs_no_duplicates, parse_int=_bounded_int_token, parse_float=_reject_float, parse_constant=_reject_constant)
    except DeskError:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise DeskError(f"invalid JSON: {exc}") from exc


def _read_regular_file(path: str | os.PathLike[str], *, max_bytes: int = MAX_INPUT_BYTES) -> bytes:
    p = os.fspath(path)
    try:
        pre = os.lstat(p)
    except OSError as exc:
        raise DeskError(f"cannot stat input: {exc}") from exc
    if stat.S_ISLNK(pre.st_mode) or not stat.S_ISREG(pre.st_mode):
        raise DeskError("input must be a regular non-symlink file")
    if pre.st_size > max_bytes:
        raise DeskError("input exceeds size limit")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        fd = os.open(p, flags)
    except OSError as exc:
        raise DeskError(f"cannot open input safely: {exc}") from exc
    try:
        post = os.fstat(fd)
        if not stat.S_ISREG(post.st_mode):
            raise DeskError("opened input is not a regular file")
        if (pre.st_dev, pre.st_ino) != (post.st_dev, post.st_ino):
            raise DeskError("input pathname changed during open")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > max_bytes:
            raise DeskError("input exceeds size limit")
        post2 = os.fstat(fd)
        if (post.st_dev, post.st_ino, post.st_size, post.st_mtime_ns) != (post2.st_dev, post2.st_ino, post2.st_size, post2.st_mtime_ns):
            raise DeskError("input generation changed while reading")
        return raw
    finally:
        os.close(fd)


def load_json_file(path: str | os.PathLike[str]) -> Any:
    return loads_strict(_read_regular_file(path))


@dataclass(frozen=True)
class Question:
    question_id: str
    section: str
    prompt: str
    mode: str
    assurance_kind: str
    required: bool
    allowed_values: tuple[str, ...]
    source_ref: str
    source_sha256: str
    digest: str


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    supports_question_id: str
    supports_question_source_sha256: str
    claim_key: str
    claim_value: str
    statement: str
    kind: str
    disclosure: str
    source_ref: str
    source_sha256: str
    captured_at: datetime
    fresh_for_days: int
    digest: str


@dataclass(frozen=True)
class ProposedAnswer:
    question_id: str
    answer: str
    requested_state: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class Disposition:
    question_id: str
    answer_generation_sha256: str
    disposition: str
    reviewed_at: datetime
    reviewer_ref: str


def _normalize_question(obj: Any, index: int) -> Question:
    where = f"questions[{index}]"
    row = _expect_dict(obj, where)
    expected = {"question_id", "section", "prompt", "mode", "assurance_kind", "required", "allowed_values", "source_ref", "source_sha256"}
    _expect_exact_keys(row, expected, where)
    qid = _expect_text(row["question_id"], f"{where}.question_id", max_len=MAX_SHORT, id_like=True)
    section = _expect_text(row["section"], f"{where}.section", max_len=MAX_SHORT)
    prompt = _expect_text(row["prompt"], f"{where}.prompt", max_len=MAX_TEXT)
    mode = _expect_text(row["mode"], f"{where}.mode", max_len=16)
    if mode not in MODES:
        raise DeskError(f"{where}.mode: unsupported mode")
    assurance = _expect_text(row["assurance_kind"], f"{where}.assurance_kind", max_len=32)
    if assurance not in ASSURANCE_KINDS:
        raise DeskError(f"{where}.assurance_kind: unsupported")
    required = _expect_bool(row["required"], f"{where}.required")
    allowed_raw = _expect_list(row["allowed_values"], f"{where}.allowed_values", max_items=100)
    allowed = tuple(_expect_text(v, f"{where}.allowed_values[{i}]", max_len=MAX_SHORT) for i, v in enumerate(allowed_raw))
    if len(set(allowed)) != len(allowed):
        raise DeskError(f"{where}.allowed_values: duplicates")
    if mode in {"ENUM", "MULTI"} and not allowed:
        raise DeskError(f"{where}.allowed_values: required for {mode}")
    if mode not in {"ENUM", "MULTI"} and allowed:
        raise DeskError(f"{where}.allowed_values: only valid for ENUM/MULTI")
    source_ref = _expect_text(row["source_ref"], f"{where}.source_ref", max_len=MAX_REF, id_like=True)
    source_sha = _expect_sha(row["source_sha256"], f"{where}.source_sha256")
    normalized = {"question_id": qid, "section": section, "prompt": prompt, "mode": mode, "assurance_kind": assurance, "required": required, "allowed_values": list(allowed), "source_ref": source_ref, "source_sha256": source_sha}
    return Question(qid, section, prompt, mode, assurance, required, allowed, source_ref, source_sha, sha256_hex(canonical_bytes(normalized)))


def _normalize_evidence(obj: Any, index: int) -> Evidence:
    where = f"evidence[{index}]"
    row = _expect_dict(obj, where)
    expected = {"evidence_id", "supports_question_id", "supports_question_source_sha256", "claim_key", "claim_value", "statement", "kind", "disclosure", "source_ref", "source_sha256", "captured_at", "fresh_for_days"}
    _expect_exact_keys(row, expected, where)
    eid = _expect_text(row["evidence_id"], f"{where}.evidence_id", max_len=MAX_SHORT, id_like=True)
    supports_qid = _expect_text(row["supports_question_id"], f"{where}.supports_question_id", max_len=MAX_SHORT, id_like=True)
    supports_qsha = _expect_sha(row["supports_question_source_sha256"], f"{where}.supports_question_source_sha256")
    claim_key = _expect_text(row["claim_key"], f"{where}.claim_key", max_len=120, claim_key=True)
    claim_value = _expect_text(row["claim_value"], f"{where}.claim_value", max_len=MAX_TEXT)
    statement = _expect_text(row["statement"], f"{where}.statement", max_len=MAX_TEXT)
    kind = _expect_text(row["kind"], f"{where}.kind", max_len=64)
    if kind not in EVIDENCE_KINDS:
        raise DeskError(f"{where}.kind: unsupported")
    disclosure = _expect_text(row["disclosure"], f"{where}.disclosure", max_len=16)
    if disclosure not in DISCLOSURES:
        raise DeskError(f"{where}.disclosure: unsupported")
    source_ref = _expect_text(row["source_ref"], f"{where}.source_ref", max_len=MAX_REF, id_like=True)
    source_sha = _expect_sha(row["source_sha256"], f"{where}.source_sha256")
    captured_at = _parse_utc(row["captured_at"], f"{where}.captured_at")
    fresh_days = _expect_int(row["fresh_for_days"], f"{where}.fresh_for_days", min_value=0, max_value=3650)
    normalized = {"evidence_id": eid, "supports_question_id": supports_qid, "supports_question_source_sha256": supports_qsha, "claim_key": claim_key, "claim_value": claim_value, "statement": statement, "kind": kind, "disclosure": disclosure, "source_ref": source_ref, "source_sha256": source_sha, "captured_at": _format_utc(captured_at), "fresh_for_days": fresh_days}
    return Evidence(eid, supports_qid, supports_qsha, claim_key, claim_value, statement, kind, disclosure, source_ref, source_sha, captured_at, fresh_days, sha256_hex(canonical_bytes(normalized)))


def _normalize_answer(obj: Any, index: int) -> ProposedAnswer:
    where = f"proposed_answers[{index}]"
    row = _expect_dict(obj, where)
    _expect_exact_keys(row, {"question_id", "answer", "state", "evidence_ids"}, where)
    qid = _expect_text(row["question_id"], f"{where}.question_id", max_len=MAX_SHORT, id_like=True)
    answer = _expect_text(row["answer"], f"{where}.answer", max_len=MAX_TEXT)
    requested = _expect_text(row["state"], f"{where}.state", max_len=64)
    if requested not in REQUESTED_STATES:
        raise DeskError(f"{where}.state: unsupported")
    evidence_raw = _expect_list(row["evidence_ids"], f"{where}.evidence_ids", max_items=200)
    evidence_ids = tuple(_expect_text(v, f"{where}.evidence_ids[{i}]", max_len=MAX_SHORT, id_like=True) for i, v in enumerate(evidence_raw))
    if len(set(evidence_ids)) != len(evidence_ids):
        raise DeskError(f"{where}.evidence_ids: duplicates")
    if requested == "UNMEASURED" and (answer != "UNMEASURED" or evidence_ids):
        raise DeskError(f"{where}: UNMEASURED must be literal with no evidence")
    if requested == "SUPPORTED_PROPOSED_ANSWER" and not evidence_ids:
        raise DeskError(f"{where}: supported answer requires evidence")
    return ProposedAnswer(qid, answer, requested, evidence_ids)


def _normalize_disposition(obj: Any, index: int) -> Disposition:
    where = f"owner_dispositions[{index}]"
    row = _expect_dict(obj, where)
    _expect_exact_keys(row, {"question_id", "answer_generation_sha256", "disposition", "reviewed_at", "reviewer_ref"}, where)
    qid = _expect_text(row["question_id"], f"{where}.question_id", max_len=MAX_SHORT, id_like=True)
    generation = _expect_sha(row["answer_generation_sha256"], f"{where}.answer_generation_sha256")
    disposition = _expect_text(row["disposition"], f"{where}.disposition", max_len=32)
    if disposition not in DISPOSITIONS:
        raise DeskError(f"{where}.disposition: unsupported")
    reviewed_at = _parse_utc(row["reviewed_at"], f"{where}.reviewed_at")
    reviewer_ref = _expect_text(row["reviewer_ref"], f"{where}.reviewer_ref", max_len=MAX_REF, id_like=True)
    return Disposition(qid, generation, disposition, reviewed_at, reviewer_ref)


def _validate_answer_shape(question: Question, answer: str) -> None:
    if answer in {"UNMEASURED", "OWNER INPUT REQUIRED"}:
        return
    if question.mode == "BOOLEAN" and answer not in {"YES", "NO"}:
        raise DeskError(f"answer {question.question_id}: BOOLEAN must be YES or NO")
    if question.mode == "ENUM" and answer not in question.allowed_values:
        raise DeskError(f"answer {question.question_id}: value outside allowed ENUM")
    if question.mode == "MULTI":
        parts = tuple(part.strip() for part in answer.split(",") if part.strip())
        if not parts or len(parts) != len(set(parts)) or any(p not in question.allowed_values for p in parts):
            raise DeskError(f"answer {question.question_id}: invalid MULTI selection")


def _is_current(evidence: Evidence, as_of: datetime) -> tuple[bool, str]:
    if evidence.captured_at > as_of:
        return False, "FUTURE_EVIDENCE"
    expiry = evidence.captured_at + timedelta(days=evidence.fresh_for_days)
    if as_of > expiry:
        return False, "STALE_EVIDENCE"
    return True, "CURRENT"


def _answer_generation(question: Question, answer: ProposedAnswer, evidence_rows: Sequence[Evidence], effective_state: str) -> str:
    generation = {"question_id": question.question_id, "question_sha256": question.digest, "answer": answer.answer, "requested_state": answer.requested_state, "effective_state": effective_state, "evidence": [{"evidence_id": ev.evidence_id, "evidence_sha256": ev.digest} for ev in sorted(evidence_rows, key=lambda e: e.evidence_id)]}
    return sha256_hex(canonical_bytes(generation))


def normalize_input(raw: Any) -> dict[str, Any]:
    top = _expect_dict(raw, "root")
    expected = {"schema_version", "questionnaire_id", "questionnaire_source_ref", "questionnaire_sha256", "questions", "evidence", "proposed_answers", "owner_dispositions"}
    _expect_exact_keys(top, expected, "root")
    version = _expect_int(top["schema_version"], "schema_version", min_value=1, max_value=1)
    qnaire_id = _expect_text(top["questionnaire_id"], "questionnaire_id", max_len=MAX_SHORT, id_like=True)
    qnaire_ref = _expect_text(top["questionnaire_source_ref"], "questionnaire_source_ref", max_len=MAX_REF, id_like=True)
    qnaire_sha = _expect_sha(top["questionnaire_sha256"], "questionnaire_sha256")
    questions = [_normalize_question(v, i) for i, v in enumerate(_expect_list(top["questions"], "questions"))]
    evidence = [_normalize_evidence(v, i) for i, v in enumerate(_expect_list(top["evidence"], "evidence"))]
    answers = [_normalize_answer(v, i) for i, v in enumerate(_expect_list(top["proposed_answers"], "proposed_answers"))]
    dispositions = [_normalize_disposition(v, i) for i, v in enumerate(_expect_list(top["owner_dispositions"], "owner_dispositions"))]
    if not questions:
        raise DeskError("questions: at least one question required")

    def unique(rows: Iterable[Any], attr: str, where: str) -> None:
        seen: set[str] = set()
        for row in rows:
            value = getattr(row, attr)
            if value in seen:
                raise DeskError(f"{where}: duplicate identity {value}")
            seen.add(value)

    unique(questions, "question_id", "questions")
    unique(evidence, "evidence_id", "evidence")
    unique(answers, "question_id", "proposed_answers")
    unique(dispositions, "question_id", "owner_dispositions")
    question_ids = {q.question_id for q in questions}
    answer_ids = {a.question_id for a in answers}
    if answer_ids != question_ids:
        raise DeskError(f"proposed_answers must cover questions exactly; missing={sorted(question_ids-answer_ids)} extra={sorted(answer_ids-question_ids)}")
    if any(d.question_id not in question_ids for d in dispositions):
        raise DeskError("owner_dispositions: unknown question_id")
    evidence_ids = {e.evidence_id for e in evidence}
    for answer in answers:
        unknown = sorted(set(answer.evidence_ids) - evidence_ids)
        if unknown:
            raise DeskError(f"answer {answer.question_id}: unknown evidence ids {unknown}")
    return {"schema_version": version, "questionnaire_id": qnaire_id, "questionnaire_source_ref": qnaire_ref, "questionnaire_sha256": qnaire_sha, "questions": questions, "evidence": evidence, "answers": answers, "dispositions": dispositions}


def compile_packet(raw: Any, as_of: datetime) -> dict[str, Any]:
    as_of_text = _format_utc(as_of)
    normalized = normalize_input(raw)
    questions: list[Question] = normalized["questions"]
    evidence: list[Evidence] = normalized["evidence"]
    answers: list[ProposedAnswer] = normalized["answers"]
    dispositions: list[Disposition] = normalized["dispositions"]
    evidence_map = {e.evidence_id: e for e in evidence}
    answer_map = {a.question_id: a for a in answers}
    disposition_map = {d.question_id: d for d in dispositions}
    rows: list[dict[str, Any]] = []
    public_rows: list[dict[str, Any]] = []
    hold_count = 0
    approved_required = 0
    required_count = sum(1 for q in questions if q.required)

    for question in sorted(questions, key=lambda q: q.question_id):
        proposed = answer_map[question.question_id]
        _validate_answer_shape(question, proposed.answer)
        cited = [evidence_map[eid] for eid in proposed.evidence_ids]
        reasons: list[str] = []
        current_rows: list[Evidence] = []
        scoped_rows: list[Evidence] = []
        for ev in cited:
            if ev.supports_question_id != question.question_id or ev.supports_question_source_sha256 != question.source_sha256:
                reasons.append(f"EVIDENCE_SCOPE_MISMATCH:{ev.evidence_id}")
                continue
            scoped_rows.append(ev)
            current, reason = _is_current(ev, as_of)
            if current:
                current_rows.append(ev)
            else:
                reasons.append(f"{reason}:{ev.evidence_id}")

        effective = proposed.requested_state
        if proposed.requested_state == "SUPPORTED_PROPOSED_ANSWER":
            if not current_rows or len(current_rows) != len(cited) or len(scoped_rows) != len(cited):
                effective = "HOLD"
            claim_values: dict[str, set[str]] = {}
            for ev in current_rows:
                claim_values.setdefault(ev.claim_key, set()).add(ev.claim_value)
            conflicts = sorted(key for key, values in claim_values.items() if len(values) > 1)
            if conflicts:
                effective = "HOLD"
                reasons.extend(f"CONFLICTING_EVIDENCE:{key}" for key in conflicts)
            if question.assurance_kind == "CERTIFICATION" and not any(ev.kind == "CERTIFICATION_REFERENCE" for ev in current_rows):
                effective = "HOLD"
                reasons.append("CERTIFICATION_REFERENCE_REQUIRED")
        elif proposed.requested_state == "OWNER_INPUT_REQUIRED" and proposed.answer == "UNMEASURED":
            raise DeskError(f"answer {question.question_id}: OWNER_INPUT_REQUIRED cannot use UNMEASURED literal")

        if effective == "HOLD":
            hold_count += 1
        generation = _answer_generation(question, proposed, cited, effective)
        disposition = disposition_map.get(question.question_id)
        disposition_state = "NONE"
        disposition_value: str | None = None
        if disposition is not None:
            disposition_value = disposition.disposition
            if disposition.reviewed_at > as_of:
                disposition_state = "FUTURE_REVIEW"
            elif disposition.answer_generation_sha256 != generation:
                disposition_state = "STALE_GENERATION"
            elif effective == "HOLD" and disposition.disposition == "APPROVED_FOR_RETURN":
                disposition_state = "INVALID_APPROVAL_ON_HOLD"
            elif effective == "OWNER_INPUT_REQUIRED" and disposition.disposition == "APPROVED_FOR_RETURN":
                disposition_state = "INVALID_APPROVAL_REQUIRES_RESOLUTION"
            else:
                disposition_state = "CURRENT"
                if question.required and disposition.disposition == "APPROVED_FOR_RETURN":
                    approved_required += 1

        evidence_projection = [{"evidence_id": ev.evidence_id, "evidence_sha256": ev.digest, "supports_question_id": ev.supports_question_id, "supports_question_source_sha256": ev.supports_question_source_sha256, "claim_key": ev.claim_key, "claim_value": ev.claim_value, "statement": ev.statement, "kind": ev.kind, "disclosure": ev.disclosure, "source_ref": ev.source_ref, "source_sha256": ev.source_sha256, "captured_at": _format_utc(ev.captured_at), "fresh_for_days": ev.fresh_for_days, "current_at_compile": _is_current(ev, as_of)[0]} for ev in sorted(cited, key=lambda e: e.evidence_id)]
        row = {"question_id": question.question_id, "question_sha256": question.digest, "section": question.section, "prompt": question.prompt, "mode": question.mode, "assurance_kind": question.assurance_kind, "required": question.required, "allowed_values": list(question.allowed_values), "source_ref": question.source_ref, "source_sha256": question.source_sha256, "answer": proposed.answer, "requested_state": proposed.requested_state, "state": effective, "reasons": sorted(set(reasons)), "evidence": evidence_projection, "answer_generation_sha256": generation, "owner_disposition": disposition_value, "owner_disposition_status": disposition_state}
        rows.append(row)

        public_evidence = [{"evidence_id": ev.evidence_id, "supports_question_id": ev.supports_question_id, "supports_question_source_sha256": ev.supports_question_source_sha256, "kind": ev.kind, "source_ref": ev.source_ref, "source_sha256": ev.source_sha256, "evidence_sha256": ev.digest} for ev in sorted(current_rows, key=lambda e: e.evidence_id) if ev.disclosure == "PUBLIC"]
        private_dependency = any(ev.disclosure == "NON_PUBLIC" for ev in cited)
        public_answer = proposed.answer
        public_state = effective
        public_reasons = list(sorted(set(reasons)))
        if private_dependency and effective == "SUPPORTED_PROPOSED_ANSWER":
            public_answer = "UNMEASURED"
            public_state = "UNMEASURED"
            public_reasons.append("NON_PUBLIC_EVIDENCE_STRIPPED")
        public_rows.append({"question_id": question.question_id, "required": question.required, "state": public_state, "answer": public_answer, "reasons": sorted(set(public_reasons)), "public_evidence": public_evidence})

    overall = "HOLD" if hold_count else ("OWNER_APPROVED_RETURN_SET" if approved_required == required_count else "READY_FOR_OWNER_REVIEW")
    normalized_input_commitment = {
        "schema_version": SCHEMA_VERSION,
        "questionnaire_id": normalized["questionnaire_id"],
        "questionnaire_source_ref": normalized["questionnaire_source_ref"],
        "questionnaire_sha256": normalized["questionnaire_sha256"],
        "question_digests": sorted((q.question_id, q.digest) for q in questions),
        "evidence_digests": sorted((e.evidence_id, e.digest) for e in evidence),
        "answers": [{"question_id": a.question_id, "answer": a.answer, "state": a.requested_state, "evidence_ids": list(a.evidence_ids)} for a in sorted(answers, key=lambda a: a.question_id)],
        "dispositions": [{"question_id": d.question_id, "answer_generation_sha256": d.answer_generation_sha256, "disposition": d.disposition, "reviewed_at": _format_utc(d.reviewed_at), "reviewer_ref": d.reviewer_ref} for d in sorted(dispositions, key=lambda d: d.question_id)],
    }
    input_digest = sha256_hex(canonical_bytes(normalized_input_commitment))
    packet_core = {
        "schema_version": SCHEMA_VERSION,
        "kind": "SECURITY_QUESTIONNAIRE_DESK_PACKET",
        "questionnaire_id": normalized["questionnaire_id"],
        "questionnaire_source_ref": normalized["questionnaire_source_ref"],
        "questionnaire_sha256": normalized["questionnaire_sha256"],
        "as_of": as_of_text,
        "input_generation_sha256": input_digest,
        "status": overall,
        "counts": {"questions": len(questions), "required": required_count, "holds": hold_count, "required_approved_for_return": approved_required},
        "rows": rows,
        "public_safe_projection": {"kind": "SECURITY_QUESTIONNAIRE_PUBLIC_SAFE_PROJECTION", "questionnaire_id": normalized["questionnaire_id"], "status": overall, "rows": public_rows},
        "authority": {"buyer_contact": False, "questionnaire_send": False, "certification_or_compliance_claim": False, "provider_or_account_mutation": False, "security_testing": False, "contract_signature": False, "pricing_or_checkout": False, "payment_or_refund": False, "revenue_recognition": False, "catalog_promotion": False},
    }
    packet = dict(packet_core)
    packet["receipt_sha256"] = sha256_hex(canonical_bytes(packet_core))
    return packet


def verify_packet(raw_input: Any, packet: Any, trusted_now: datetime) -> dict[str, Any]:
    candidate = _expect_dict(packet, "packet")
    if "receipt_sha256" not in candidate:
        raise DeskError("packet: missing receipt_sha256")
    receipt = _expect_sha(candidate["receipt_sha256"], "packet.receipt_sha256")
    core = dict(candidate)
    core.pop("receipt_sha256")
    if sha256_hex(canonical_bytes(core)) != receipt:
        raise DeskError("packet receipt mismatch")
    compiled_at = _parse_utc(candidate.get("as_of"), "packet.as_of")
    now_text = _format_utc(trusted_now)
    now = _parse_utc(now_text, "trusted_now")
    if compiled_at > now:
        raise DeskError("packet compile time is in the trusted future")
    recomputed = compile_packet(raw_input, compiled_at)
    if canonical_bytes(recomputed) != canonical_bytes(candidate):
        raise DeskError("packet does not match exact inputs at its bound compile time")
    normalized = normalize_input(raw_input)
    evidence_map = {e.evidence_id: e for e in normalized["evidence"]}
    for row in candidate.get("rows", []):
        if row.get("state") != "SUPPORTED_PROPOSED_ANSWER":
            continue
        for ev in row.get("evidence", []):
            eid = ev.get("evidence_id")
            current, reason = _is_current(evidence_map[eid], now)
            if not current:
                raise DeskError(f"packet support is no longer current: {reason}:{eid}")
    return {"verified": True, "receipt_sha256": receipt, "status": candidate["status"], "verified_at": now_text}


def render_markdown(packet: Mapping[str, Any]) -> str:
    lines = ["# Security Questionnaire Desk", "", f"- Questionnaire: `{packet['questionnaire_id']}`", f"- Status: **{packet['status']}**", f"- Trusted compile time: `{packet['as_of']}`", f"- Receipt: `{packet['receipt_sha256']}`", "", "This is an offline owner-review artifact. It is not a certification, audit result, buyer acceptance, legal conclusion, or send authority.", "", "## Answer matrix", ""]
    for row in packet["rows"]:
        lines += [f"### {row['question_id']} — {row['section']}", "", f"**State:** `{row['state']}`  ", f"**Required:** `{str(row['required']).lower()}`  ", f"**Owner disposition:** `{row['owner_disposition_status']}`" + (f" / `{row['owner_disposition']}`" if row["owner_disposition"] else ""), "", row["prompt"], "", f"**Proposed answer:** {row['answer']}", ""]
        if row["reasons"]:
            lines.append("Reasons: " + ", ".join(f"`{r}`" for r in row["reasons"]))
            lines.append("")
        if row["evidence"]:
            lines.append("Evidence:")
            for ev in row["evidence"]:
                lines.append(f"- `{ev['evidence_id']}` · `{ev['kind']}` · `{ev['disclosure']}` · current=`{str(ev['current_at_compile']).lower()}` · `{ev['source_ref']}`")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_csv(packet: Mapping[str, Any]) -> str:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["question_id", "required", "state", "answer", "owner_disposition_status", "owner_disposition", "evidence_ids", "answer_generation_sha256"])
    for row in packet["rows"]:
        writer.writerow([row["question_id"], "true" if row["required"] else "false", row["state"], row["answer"], row["owner_disposition_status"], row["owner_disposition"] or "", ";".join(ev["evidence_id"] for ev in row["evidence"]), row["answer_generation_sha256"]])
    return out.getvalue()


def render_public_safe_json(packet: Mapping[str, Any]) -> str:
    return canonical_bytes(packet["public_safe_projection"]).decode("utf-8") + "\n"


def artifact_bytes(packet: Mapping[str, Any]) -> dict[str, bytes]:
    return {"packet.json": canonical_bytes(packet) + b"\n", "review.md": render_markdown(packet).encode("utf-8"), "answers.csv": render_csv(packet).encode("utf-8"), "public-safe.json": render_public_safe_json(packet).encode("utf-8"), "receipt.sha256": (packet["receipt_sha256"] + "  packet.json\n").encode("ascii")}


def _validate_output_dir(path: str | os.PathLike[str]) -> Path:
    out = Path(path)
    try:
        st = os.lstat(out)
    except FileNotFoundError:
        out.mkdir(mode=0o700, parents=False, exist_ok=False)
        st = os.lstat(out)
    except OSError as exc:
        raise DeskError(f"cannot stat output directory: {exc}") from exc
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise DeskError("output path must be an ordinary directory")
    return out


def publish_artifacts(packet: Mapping[str, Any], output_dir: str | os.PathLike[str]) -> list[str]:
    out = _validate_output_dir(output_dir)
    artifacts = artifact_bytes(packet)
    for name in artifacts:
        target = out / name
        try:
            st = os.lstat(target)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(st.st_mode):
            raise DeskError(f"refusing final symlink: {target.name}")
        raise DeskError(f"refusing existing output: {target.name}")
    published: list[str] = []
    for name, payload in artifacts.items():
        target = out / name
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        try:
            fd = os.open(target, flags, 0o600)
        except OSError as exc:
            raise DeskError(f"failed create-exclusive publication for {name}: {exc}") from exc
        try:
            total = 0
            while total < len(payload):
                written = os.write(fd, payload[total:])
                if written <= 0:
                    raise DeskError(f"short write while publishing {name}")
                total += written
            os.fsync(fd)
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise DeskError(f"published target is not regular: {name}")
        finally:
            os.close(fd)
        published.append(str(target))
    return published


def _trusted_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _cmd_compile(args: argparse.Namespace) -> int:
    raw = load_json_file(args.input)
    packet = compile_packet(raw, _trusted_now())
    publish_artifacts(packet, args.output_dir)
    print(packet["receipt_sha256"])
    return 0 if packet["status"] != "HOLD" else 2


def _cmd_verify(args: argparse.Namespace) -> int:
    raw = load_json_file(args.input)
    packet = load_json_file(args.packet)
    result = verify_packet(raw, packet, _trusted_now())
    print(canonical_bytes(result).decode("utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Offline evidence-bound security questionnaire fulfillment desk.")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile", help="compile one questionnaire review packet")
    compile_p.add_argument("input")
    compile_p.add_argument("output_dir")
    compile_p.set_defaults(func=_cmd_compile)
    verify_p = sub.add_parser("verify", help="recompile at trusted current time and verify an exact packet")
    verify_p.add_argument("input")
    verify_p.add_argument("packet")
    verify_p.set_defaults(func=_cmd_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return int(args.func(args))
    except DeskError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
