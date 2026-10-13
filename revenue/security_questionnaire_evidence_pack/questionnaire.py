#!/usr/bin/env python3
"""Deterministic, evidence-bound enterprise security questionnaire compiler."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Any

SCHEMA = "security-questionnaire-evidence-v1"
REPORT_SCHEMA = "security-questionnaire-report-v1"
MAX_EVIDENCE = 300
MAX_QUESTIONS = 150
MAX_ARTIFACT_BYTES = 2_000_000
ID_RE = re.compile(r"^[A-Z][A-Z0-9_.-]{0,63}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
STATUSES = (
    "SUPPORTED",
    "PARTIAL",
    "HOLD_MISSING_EVIDENCE",
    "HOLD_STALE_EVIDENCE",
    "NOT_APPLICABLE",
)
AUTHORITY = {
    "certifies_compliance": False,
    "attests_soc2": False,
    "attests_hipaa": False,
    "buyer_contact_authorized": False,
    "contract_acceptance_authorized": False,
    "payment_authorized": False,
    "revenue_recognition_authorized": False,
}
OFFER = {
    "fixed_sprint_usd_cents": 1_500_000,
    "optional_quarterly_refresh_usd_cents": 200_000,
    "commercial_state": "PROPOSED_NOT_ACCEPTED",
}


class PackError(ValueError):
    """Closed validation/verification failure for this evidence pack."""


def _reject_float(value: str) -> None:
    raise PackError(f"floating-point JSON is not allowed: {value}")


def _reject_constant(value: str) -> None:
    raise PackError(f"non-finite JSON is not allowed: {value}")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise PackError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def loads_strict(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackError("input must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except PackError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise PackError(f"invalid JSON: {exc}") from exc


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PackError(f"value is not canonical JSON: {exc}") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _keys(obj: Any, required: set[str], optional: set[str], where: str) -> dict[str, Any]:
    if type(obj) is not dict:
        raise PackError(f"{where} must be an object")
    actual = set(obj)
    missing = required - actual
    extra = actual - required - optional
    if missing or extra:
        raise PackError(f"{where} keys invalid: missing={sorted(missing)} extra={sorted(extra)}")
    return obj


def _text(value: Any, where: str, *, max_len: int = 1000) -> str:
    if type(value) is not str or not value.strip() or len(value) > max_len:
        raise PackError(f"{where} must be a non-empty string <= {max_len} chars")
    return value


def _id(value: Any, where: str) -> str:
    text = _text(value, where, max_len=64)
    if not ID_RE.fullmatch(text):
        raise PackError(f"{where} has invalid identifier syntax")
    return text


def _timestamp(value: Any, where: str) -> dt.datetime:
    text = _text(value, where, max_len=40)
    if not text.endswith("Z"):
        raise PackError(f"{where} must be an explicit UTC Z timestamp")
    try:
        parsed = dt.datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise PackError(f"{where} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise PackError(f"{where} must be UTC")
    return parsed


def _artifact_path(value: Any, where: str) -> str:
    text = _text(value, where, max_len=240)
    if "\\" in text:
        raise PackError(f"{where} must use POSIX separators")
    pure = PurePosixPath(text)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise PackError(f"{where} must be a clean relative path")
    return pure.as_posix()


def validate_manifest(value: Any) -> dict[str, Any]:
    obj = _keys(
        value,
        {"schema", "as_of", "questionnaire_id", "evidence", "questions"},
        set(),
        "manifest",
    )
    if obj["schema"] != SCHEMA:
        raise PackError(f"schema must equal {SCHEMA}")
    _timestamp(obj["as_of"], "manifest.as_of")
    questionnaire_id = _id(obj["questionnaire_id"], "manifest.questionnaire_id")

    if type(obj["evidence"]) is not list or len(obj["evidence"]) > MAX_EVIDENCE:
        raise PackError(f"manifest.evidence must be a list with <= {MAX_EVIDENCE} items")
    normalized_evidence: list[dict[str, Any]] = []
    seen_evidence: set[str] = set()
    for index, raw in enumerate(obj["evidence"]):
        item = _keys(
            raw,
            {"id", "statement", "source_ref", "artifact_path", "sha256", "observed_at", "valid_until", "scope"},
            set(),
            f"evidence[{index}]",
        )
        eid = _id(item["id"], f"evidence[{index}].id")
        if eid in seen_evidence:
            raise PackError(f"duplicate evidence id: {eid}")
        seen_evidence.add(eid)
        statement = _text(item["statement"], f"evidence[{index}].statement", max_len=800)
        source_ref = _text(item["source_ref"], f"evidence[{index}].source_ref", max_len=500)
        if not (source_ref.startswith("https://") or source_ref.startswith("repo://") or source_ref.startswith("fixture://")):
            raise PackError(f"evidence[{index}].source_ref must use https://, repo://, or fixture://")
        artifact_path = _artifact_path(item["artifact_path"], f"evidence[{index}].artifact_path")
        digest = _text(item["sha256"], f"evidence[{index}].sha256", max_len=64)
        if not SHA_RE.fullmatch(digest):
            raise PackError(f"evidence[{index}].sha256 must be lowercase SHA-256")
        observed = _timestamp(item["observed_at"], f"evidence[{index}].observed_at")
        valid_until = _timestamp(item["valid_until"], f"evidence[{index}].valid_until")
        if valid_until < observed:
            raise PackError(f"evidence[{index}] valid_until precedes observed_at")
        normalized_evidence.append(
            {
                "id": eid,
                "statement": statement,
                "source_ref": source_ref,
                "artifact_path": artifact_path,
                "sha256": digest,
                "observed_at": item["observed_at"],
                "valid_until": item["valid_until"],
                "scope": _text(item["scope"], f"evidence[{index}].scope", max_len=300),
            }
        )

    if type(obj["questions"]) is not list or len(obj["questions"]) > MAX_QUESTIONS:
        raise PackError(f"manifest.questions must be a list with <= {MAX_QUESTIONS} items")
    normalized_questions: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    for index, raw in enumerate(obj["questions"]):
        item = _keys(
            raw,
            {"id", "prompt", "required_evidence_ids"},
            {"not_applicable_reason"},
            f"questions[{index}]",
        )
        qid = _id(item["id"], f"questions[{index}].id")
        if qid in seen_questions:
            raise PackError(f"duplicate question id: {qid}")
        seen_questions.add(qid)
        refs = item["required_evidence_ids"]
        if type(refs) is not list or any(type(ref) is not str for ref in refs):
            raise PackError(f"questions[{index}].required_evidence_ids must be a string list")
        normalized_refs = [_id(ref, f"questions[{index}].required_evidence_ids") for ref in refs]
        if len(set(normalized_refs)) != len(normalized_refs):
            raise PackError(f"questions[{index}] repeats an evidence id")
        na_reason = item.get("not_applicable_reason")
        if na_reason is not None:
            na_reason = _text(na_reason, f"questions[{index}].not_applicable_reason", max_len=500)
            if normalized_refs:
                raise PackError(f"questions[{index}] cannot be NOT_APPLICABLE and require evidence")
        elif not normalized_refs:
            raise PackError(f"questions[{index}] needs evidence or an explicit not_applicable_reason")
        normalized_questions.append(
            {
                "id": qid,
                "prompt": _text(item["prompt"], f"questions[{index}].prompt", max_len=1000),
                "required_evidence_ids": sorted(normalized_refs),
                "not_applicable_reason": na_reason,
            }
        )

    return {
        "schema": SCHEMA,
        "as_of": obj["as_of"],
        "questionnaire_id": questionnaire_id,
        "evidence": sorted(normalized_evidence, key=lambda item: item["id"]),
        "questions": sorted(normalized_questions, key=lambda item: item["id"]),
    }


def _read_verified_artifact(root: Path, item: dict[str, Any]) -> bytes:
    root = root.resolve(strict=True)
    pure = PurePosixPath(item["artifact_path"])
    cursor = root
    for part in pure.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise PackError(f"evidence {item['id']} artifact path contains a symlink")
    try:
        resolved = cursor.resolve(strict=True)
    except FileNotFoundError as exc:
        raise PackError(f"evidence {item['id']} artifact is missing") from exc
    try:
        common = os.path.commonpath((str(root), str(resolved)))
    except ValueError as exc:
        raise PackError(f"evidence {item['id']} artifact escaped evidence root") from exc
    if common != str(root) or not resolved.is_file():
        raise PackError(f"evidence {item['id']} artifact is outside root or not a regular file")
    raw = resolved.read_bytes()
    if len(raw) > MAX_ARTIFACT_BYTES:
        raise PackError(f"evidence {item['id']} artifact exceeds byte ceiling")
    actual = _sha(raw)
    if actual != item["sha256"]:
        raise PackError(f"evidence {item['id']} SHA-256 mismatch")
    return raw


def _evidence_state(item: dict[str, Any], as_of: dt.datetime) -> str:
    observed = _timestamp(item["observed_at"], f"evidence {item['id']} observed_at")
    valid_until = _timestamp(item["valid_until"], f"evidence {item['id']} valid_until")
    if observed > as_of:
        return "FUTURE"
    if as_of > valid_until:
        return "STALE"
    return "CURRENT"


def compile_bytes(raw: bytes, evidence_root: Path | str) -> tuple[dict[str, Any], str]:
    manifest = validate_manifest(loads_strict(raw))
    as_of = _timestamp(manifest["as_of"], "manifest.as_of")
    root = Path(evidence_root)
    registry: dict[str, dict[str, Any]] = {}
    evidence_rows: list[dict[str, Any]] = []
    for item in manifest["evidence"]:
        artifact = _read_verified_artifact(root, item)
        state = _evidence_state(item, as_of)
        row = {
            **item,
            "artifact_sha256_verified": True,
            "artifact_bytes": len(artifact),
            "freshness_state": state,
        }
        registry[item["id"]] = row
        evidence_rows.append(row)

    counts = {status: 0 for status in STATUSES}
    question_rows: list[dict[str, Any]] = []
    for question in manifest["questions"]:
        refs = question["required_evidence_ids"]
        if question["not_applicable_reason"] is not None:
            status = "NOT_APPLICABLE"
            current_ids: list[str] = []
            held_ids: list[str] = []
            missing_ids: list[str] = []
            fragments: list[dict[str, str]] = []
        else:
            missing_ids = sorted(ref for ref in refs if ref not in registry)
            known = [registry[ref] for ref in refs if ref in registry]
            current_ids = sorted(row["id"] for row in known if row["freshness_state"] == "CURRENT")
            held_ids = sorted(row["id"] for row in known if row["freshness_state"] != "CURRENT")
            if missing_ids:
                status = "HOLD_MISSING_EVIDENCE"
            elif held_ids and current_ids:
                status = "PARTIAL"
            elif held_ids:
                status = "HOLD_STALE_EVIDENCE"
            else:
                status = "SUPPORTED"
            fragments = [
                {"evidence_id": eid, "statement": registry[eid]["statement"]}
                for eid in current_ids
            ] if status in ("SUPPORTED", "PARTIAL") else []
        counts[status] += 1
        question_rows.append(
            {
                "id": question["id"],
                "prompt": question["prompt"],
                "status": status,
                "required_evidence_ids": refs,
                "current_evidence_ids": current_ids,
                "held_evidence_ids": held_ids,
                "missing_evidence_ids": missing_ids,
                "answer_fragments": fragments,
                "not_applicable_reason": question["not_applicable_reason"],
            }
        )

    body = {
        "schema": REPORT_SCHEMA,
        "questionnaire_id": manifest["questionnaire_id"],
        "as_of": manifest["as_of"],
        "summary": {"question_count": len(question_rows), "counts": counts},
        "questions": question_rows,
        "evidence": evidence_rows,
        "offer": dict(OFFER),
        "authority": dict(AUTHORITY),
    }
    receipt = {
        "raw_input_sha256": _sha(raw),
        "semantic_manifest_sha256": _sha(canonical_bytes(manifest)),
        "report_body_sha256": _sha(canonical_bytes(body)),
    }
    report = {**body, "receipt": receipt}
    return report, render_markdown(report)


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Security Questionnaire Evidence Pack",
        "",
        f"Questionnaire: `{report['questionnaire_id']}`  ",
        f"Evidence as-of: `{report['as_of']}`  ",
        f"Commercial state: `{report['offer']['commercial_state']}`",
        "",
        "| Question | Status | Current evidence | Hold / missing |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["questions"]:
        hold = row["held_evidence_ids"] + row["missing_evidence_ids"]
        lines.append(
            f"| {_md(row['id'])} | `{row['status']}` | {_md(', '.join(row['current_evidence_ids']) or '—')} | {_md(', '.join(hold) or '—')} |"
        )
    lines += ["", "## Evidence-backed answer fragments", ""]
    for row in report["questions"]:
        lines.append(f"### {row['id']} — `{row['status']}`")
        lines.append("")
        lines.append(row["prompt"])
        lines.append("")
        if row["status"] == "NOT_APPLICABLE":
            lines.append(f"Explicit N/A reason: {row['not_applicable_reason']}")
        elif row["answer_fragments"]:
            for fragment in row["answer_fragments"]:
                lines.append(f"- `{fragment['evidence_id']}` — {fragment['statement']}")
        else:
            lines.append("No answer asserted while required evidence is held or missing.")
        lines.append("")
    lines += [
        "## Truth boundary",
        "",
        "This packet reports only statements bound to verified local evidence bytes and declared currentness. It does not certify compliance, attest SOC 2 or HIPAA status, contact a buyer, accept a contract, authorize payment, or recognize revenue.",
        "",
        f"Fixed evidence-pack sprint hypothesis: **${report['offer']['fixed_sprint_usd_cents'] // 100:,}**. Optional quarterly evidence refresh: **${report['offer']['optional_quarterly_refresh_usd_cents'] // 100:,}**. These are `PROPOSED_NOT_ACCEPTED` terms, not evidence of a buyer or sale.",
        "",
        f"Receipt: `{report['receipt']['report_body_sha256']}`",
        "",
    ]
    return "\n".join(lines)


def verify_bytes(raw: bytes, report_raw: bytes, evidence_root: Path | str) -> None:
    expected, _ = compile_bytes(raw, evidence_root)
    supplied = loads_strict(report_raw)
    if canonical_bytes(supplied) != canonical_bytes(expected):
        raise PackError("report does not exactly match deterministic recompilation")


def _read_limited(path: Path, ceiling: int = 5_000_000) -> bytes:
    p = os.fspath(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_NONBLOCK"):
        flags |= os.O_NONBLOCK
    try:
        before = os.lstat(p)
    except OSError as exc:
        raise PackError(f"cannot stat input {p}: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise PackError(f"input must be a regular non-symlink file: {p}")
    if before.st_size > ceiling:
        raise PackError(f"{p} exceeds byte ceiling")
    try:
        fd = os.open(p, flags)
    except OSError as exc:
        raise PackError(f"cannot open input {p}: {exc}") from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise PackError(f"input must be a regular non-symlink file: {p}")
        if opened.st_size > ceiling:
            raise PackError(f"{p} exceeds byte ceiling")
        chunks: list[bytes] = []
        total = 0
        while True:
            try:
                chunk = os.read(fd, min(1024 * 1024, ceiling + 1 - total))
            except BlockingIOError as exc:
                raise PackError(f"input would block: {p}") from exc
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > ceiling:
                raise PackError(f"{p} exceeds byte ceiling")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _write_exclusive(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise PackError(f"refusing to overwrite existing output: {path}") from exc


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile")
    compile_p.add_argument("--input", required=True, type=Path)
    compile_p.add_argument("--evidence-root", required=True, type=Path)
    compile_p.add_argument("--report-json", required=True, type=Path)
    compile_p.add_argument("--report-md", required=True, type=Path)
    verify_p = sub.add_parser("verify")
    verify_p.add_argument("--input", required=True, type=Path)
    verify_p.add_argument("--evidence-root", required=True, type=Path)
    verify_p.add_argument("--report-json", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        raw = _read_limited(args.input)
        if args.command == "compile":
            if args.report_json.exists() or args.report_md.exists():
                raise PackError("refusing to overwrite an existing report output")
            report, markdown = compile_bytes(raw, args.evidence_root)
            _write_exclusive(args.report_json, canonical_bytes(report) + b"\n")
            _write_exclusive(args.report_md, markdown.encode("utf-8"))
        else:
            verify_bytes(raw, _read_limited(args.report_json), args.evidence_root)
    except (PackError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
