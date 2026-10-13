from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .schema import (
    AUTHORITY, DEADLINE_DATE, INPUT_SCHEMA, METHODOLOGY_BLUEPRINT, PACKET_SCHEMA,
    QUESTION_BY_ID, QUESTION_COUNT, QUESTION_SPECS, RECEIPT_SCHEMA, REQUIREMENT_MANIFEST,
    REQUIREMENT_MANIFEST_SHA256, RESPONSE_EMAIL, RFIError, SECTION_TITLES, SUBJECT_LINE,
    VENDOR_DUE_DILIGENCE_DOMAINS, _sha256, canonical_json, source_binding, strict_json_loads,
)
from .validate import (
    _arr, _exact_keys, _obj, _text, _timestamp, _validate_answer, _validate_assurances, _validate_pricing, _validate_source,
)

def empty_template() -> dict[str, Any]:
    return {
        "schema": INPUT_SCHEMA,
        "as_of": "2026-09-17T00:00:00-04:00",
        "source": source_binding(),
        "answers": [
            {"question_id": qid, "status": "OWNER_INPUT_REQUIRED", "answer": "", "evidence_refs": []}
            for qid, *_ in QUESTION_SPECS
        ],
        "pricing_options": [],
        "assurances": {
            "sensitive_information_screened": False,
            "claim_evidence_reviewed": False,
            "pricing_non_binding_ack": False,
        },
    }


def compile_rfi(payload: Any) -> dict[str, Any]:
    obj = _obj(payload, "input")
    _exact_keys(obj, {"schema", "as_of", "source", "answers", "pricing_options", "assurances"}, "input")
    if obj["schema"] != INPUT_SCHEMA:
        raise RFIError("input.schema invalid")
    as_of = _timestamp(obj["as_of"], "input.as_of")
    source = _validate_source(obj["source"])
    raw_answers = _arr(obj["answers"], "input.answers", max_items=31)
    answers: list[dict[str, Any]] = []
    seen_qids: set[str] = set()
    for i, raw in enumerate(raw_answers):
        answer = _validate_answer(raw, f"input.answers[{i}]")
        qid = answer["question_id"]
        if qid in seen_qids:
            raise RFIError(f"duplicate question answer: {qid}")
        seen_qids.add(qid)
        answers.append(answer)
    answers.sort(key=lambda row: row["question_id"])
    missing = sorted(set(QUESTION_BY_ID) - seen_qids)
    unresolved = sorted(row["question_id"] for row in answers if row["status"] == "OWNER_INPUT_REQUIRED")
    not_applicable = sorted(row["question_id"] for row in answers if row["status"] == "NOT_APPLICABLE")
    pricing = _validate_pricing(obj["pricing_options"])
    assurances = _validate_assurances(obj["assurances"])

    blockers: list[str] = []
    if missing:
        blockers.append("missing_question_rows")
    if unresolved:
        blockers.append("owner_input_required")
    for key, value in assurances.items():
        if value is not True:
            blockers.append(f"assurance_{key}_required")
    q25 = next((row for row in answers if row["question_id"] == "Q25"), None)
    if q25 is not None and q25["status"] == "ANSWERED" and not pricing:
        blockers.append("structured_pricing_ranges_missing")
    if pricing and assurances["pricing_non_binding_ack"] is not True:
        blockers.append("pricing_non_binding_ack_required")
    blockers = sorted(set(blockers))

    section_summary: list[dict[str, Any]] = []
    for section, title in SECTION_TITLES.items():
        ids = [qid for qid, sec, *_ in QUESTION_SPECS if sec == section]
        rows = [row for row in answers if row["section"] == section]
        section_summary.append({
            "section": section,
            "title": title,
            "expected_questions": len(ids),
            "present_questions": len(rows),
            "resolved_questions": sum(row["status"] != "OWNER_INPUT_REQUIRED" for row in rows),
            "not_applicable_questions": [row["question_id"] for row in rows if row["status"] == "NOT_APPLICABLE"],
        })

    packet: dict[str, Any] = {
        "schema": PACKET_SCHEMA,
        "as_of": as_of,
        "buyer": "Legal Aid Chicago",
        "source": source,
        "source_manifest": REQUIREMENT_MANIFEST,
        "answers": answers,
        "coverage": {
            "question_count_expected": QUESTION_COUNT,
            "question_count_present": len(answers),
            "question_count_resolved": sum(row["status"] != "OWNER_INPUT_REQUIRED" for row in answers),
            "missing_question_ids": missing,
            "owner_input_required_ids": unresolved,
            "not_applicable_ids": not_applicable,
            "sections": section_summary,
        },
        "methodology_blueprint": list(METHODOLOGY_BLUEPRINT),
        "vendor_due_diligence_domains": list(VENDOR_DUE_DILIGENCE_DOMAINS),
        "pricing_options": pricing,
        "assurances": assurances,
        "readiness": {
            "status": "READY_FOR_OWNER_RFI_REVIEW" if not blockers else "HOLD",
            "blockers": blockers,
            "submission_route": RESPONSE_EMAIL,
            "buyer_deadline_date": DEADLINE_DATE,
            "deadline_has_no_time_in_source": True,
            "owner_must_reverify_deadline_before_submission": True,
        },
        "authority": dict(AUTHORITY),
    }
    packet["receipt"] = {
        "schema": RECEIPT_SCHEMA,
        "sha256": _sha256(packet),
        "verified_by_recompile": True,
    }
    return packet


def verify_rfi(payload: Any, packet: Any) -> bool:
    try:
        return canonical_json(compile_rfi(payload)) == canonical_json(_obj(packet, "packet"))
    except RFIError:
        return False


def render_markdown(packet: Any) -> str:
    obj = _obj(packet, "packet")
    if obj.get("schema") != PACKET_SCHEMA:
        raise RFIError("packet.schema invalid")
    if not isinstance(obj.get("answers"), list) or not isinstance(obj.get("readiness"), dict):
        raise RFIError("packet missing rendered fields")
    lines = [
        "# DRAFT — OWNER REVIEW REQUIRED — NOT SUBMITTED",
        "",
        "## Legal Aid Chicago — AI Architecture, Governance, and Security RFI",
        "",
        f"**Readiness:** `{obj['readiness'].get('status', 'UNKNOWN')}`  ",
        f"**Buyer route:** `{RESPONSE_EMAIL}`  ",
        f"**Buyer subject:** {SUBJECT_LINE}  ",
        f"**Buyer due date:** {DEADLINE_DATE} (source gives no time; reverify before submission)",
        "",
        "> This document is an internal response draft. It does not authorize buyer contact, submission, pricing commitment, legal/security conclusions, contract acceptance, award, payment, or revenue recognition.",
        "",
    ]
    grouped: dict[str, list[dict[str, Any]]] = {section: [] for section in SECTION_TITLES}
    for row in obj["answers"]:
        if not isinstance(row, dict) or row.get("section") not in grouped:
            raise RFIError("packet contains malformed answer row")
        grouped[row["section"]].append(row)
    for section, title in SECTION_TITLES.items():
        lines.extend([f"## {section}. {title}", ""])
        for row in sorted(grouped[section], key=lambda item: item["question_id"]):
            lines.append(f"### {row['question_id']} — {row['key']}")
            lines.append("")
            lines.append(f"**Status:** `{row['status']}`")
            lines.append("")
            lines.append(row["answer"] if row["answer"] else "_[OWNER INPUT REQUIRED]_")
            lines.append("")
            refs = row.get("evidence_refs", [])
            if refs:
                lines.append("Evidence:")
                for ref in refs:
                    lines.append(f"- `{ref['kind']}` — {ref['ref']}")
                lines.append("")
    lines.extend(["## Non-binding pricing worksheet", ""])
    pricing = obj.get("pricing_options", [])
    if not pricing:
        lines.extend(["_[No structured pricing ranges compiled.]_", ""])
    else:
        lines.extend(["| Option | Range (minor units) | Currency | Model |", "|---|---:|---|---|"])
        for row in pricing:
            lines.append(f"| {row['option']} | {row['low_minor']}–{row['high_minor']} | {row['currency']} / {row['decimals']} decimals | {row['model']} |")
        lines.append("")
    lines.extend(["## Internal readiness blockers", ""])
    blockers = obj["readiness"].get("blockers", [])
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers)
    else:
        lines.append("- None at compile time; owner review and a fresh submission/deadline/collision check are still required.")
    lines.append("")
    return "\n".join(lines)


def _read_json(path: str) -> Any:
    try:
        return strict_json_loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise RFIError(f"cannot read {path}: {exc}") from None


def _write_text(path: str, text: str) -> None:
    try:
        Path(path).write_text(text, encoding="utf-8")
    except OSError as exc:
        raise RFIError(f"cannot write {path}: {exc}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile and verify a source-bound Legal Aid Chicago AI RFI response-readiness packet")
    sub = parser.add_subparsers(dest="command", required=True)
    cp = sub.add_parser("compile"); cp.add_argument("input_json"); cp.add_argument("packet_json")
    vp = sub.add_parser("verify"); vp.add_argument("input_json"); vp.add_argument("packet_json")
    rp = sub.add_parser("render"); rp.add_argument("input_json"); rp.add_argument("output_md")
    tp = sub.add_parser("template"); tp.add_argument("output_json")
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            _write_text(args.output_json, canonical_json(empty_template())); return 0
        payload = _read_json(args.input_json)
        packet = compile_rfi(payload)
        if args.command == "compile":
            _write_text(args.packet_json, canonical_json(packet)); return 0
        if args.command == "verify":
            return 0 if verify_rfi(payload, _read_json(args.packet_json)) else 2
        _write_text(args.output_md, render_markdown(packet)); return 0
    except RFIError as exc:
        parser.error(str(exc)); return 2


if __name__ == "__main__":
    raise SystemExit(main())
