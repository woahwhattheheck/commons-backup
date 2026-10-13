from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "banner-saas-student-record-parity/v1"
REPORT_SCHEMA = "banner-saas-student-record-parity-report/v1"
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
TEXT_MAX = 160
MAX_ROWS = 100_000
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_HOLDS = 32
MAX_HOLD_LEN = 80

RECORD_KEYS = {
    "student_id",
    "term",
    "program",
    "enrollment_status",
    "holds",
    "advisor",
    "last_sync_utc",
}
SNAPSHOT_KEYS = {
    "snapshot_id",
    "system_role",
    "schema_revision",
    "captured_at_utc",
    "complete_export",
    "rows_sha256",
    "rows",
}
POLICY_KEYS = {"max_sync_age_minutes"}
COMPILE_INPUT_KEYS = {"source", "target", "policy"}
ROLES = {"SOURCE_BANNER", "TARGET_SAAS"}
CLASSIFICATIONS = {
    "PARITY_OK",
    "MISSING_TARGET",
    "FIELD_MISMATCH",
    "DUPLICATE_ID",
    "STALE_SYNC",
}
BUSINESS_FIELDS = ("program", "enrollment_status", "holds", "advisor")


class ParityError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise ParityError(f"non-finite JSON value is forbidden: {value}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ParityError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_bytes(raw: bytes) -> Any:
    if type(raw) is not bytes:
        raise ParityError("JSON input must be exact bytes")
    if len(raw) > MAX_JSON_BYTES:
        raise ParityError("JSON input exceeds byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ParityError("JSON input must be UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except ParityError:
        raise
    except json.JSONDecodeError as exc:
        raise ParityError(f"invalid JSON: {exc.msg}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _exact_object(value: Any, keys: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ParityError(f"{name} must be an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        unknown = sorted(actual - keys)
        raise ParityError(f"{name} keys mismatch; missing={missing} unknown={unknown}")
    return value


def _plain_text(value: Any, name: str, *, max_len: int = TEXT_MAX, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise ParityError(f"{name} must be a string")
    if not allow_empty and not value:
        raise ParityError(f"{name} must not be empty")
    if len(value) > max_len:
        raise ParityError(f"{name} exceeds length limit")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ParityError(f"{name} contains control characters")
    return value


def _opaque_id(value: Any, name: str) -> str:
    text = _plain_text(value, name, max_len=80)
    if not ID_RE.fullmatch(text):
        raise ParityError(f"{name} must be a bounded opaque identifier")
    if "@" in text or "/" in text or "\\" in text:
        raise ParityError(f"{name} must not contain contact/path material")
    return text


def _sha(value: Any, name: str) -> str:
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ParityError(f"{name} must be lowercase SHA-256 hex")
    return value


def parse_utc(value: Any, name: str) -> datetime:
    if type(value) is not str or not UTC_RE.fullmatch(value):
        raise ParityError(f"{name} must be canonical whole-second UTC ending in Z")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ParityError(f"{name} is not a real UTC timestamp") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ParityError(f"{name} is not canonical UTC")
    return dt


def format_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ParityError("trusted time must be timezone-aware")
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> str:
    return format_utc(datetime.now(timezone.utc))


def _normalize_holds(value: Any, name: str) -> list[str]:
    if type(value) is not list:
        raise ParityError(f"{name} must be a list")
    if len(value) > MAX_HOLDS:
        raise ParityError(f"{name} exceeds item limit")
    out = []
    for idx, item in enumerate(value):
        out.append(_plain_text(item, f"{name}[{idx}]", max_len=MAX_HOLD_LEN))
    if len(set(out)) != len(out):
        raise ParityError(f"{name} contains duplicate hold values")
    return sorted(out)


def normalize_record(value: Any, name: str, *, as_of: datetime) -> dict[str, Any]:
    row = _exact_object(value, RECORD_KEYS, name)
    student_id = _opaque_id(row["student_id"], f"{name}.student_id")
    term = _opaque_id(row["term"], f"{name}.term")
    program = _plain_text(row["program"], f"{name}.program")
    enrollment_status = _plain_text(row["enrollment_status"], f"{name}.enrollment_status")
    holds = _normalize_holds(row["holds"], f"{name}.holds")
    advisor = _plain_text(row["advisor"], f"{name}.advisor", allow_empty=True)
    last_sync = parse_utc(row["last_sync_utc"], f"{name}.last_sync_utc")
    if last_sync > as_of:
        raise ParityError(f"{name}.last_sync_utc is in the future")
    return {
        "student_id": student_id,
        "term": term,
        "program": program,
        "enrollment_status": enrollment_status,
        "holds": holds,
        "advisor": advisor,
        "last_sync_utc": format_utc(last_sync),
    }


def row_key(row: dict[str, Any]) -> tuple[str, str]:
    return row["student_id"], row["term"]


def normalize_snapshot(value: Any, name: str, *, expected_role: str, as_of: datetime) -> dict[str, Any]:
    snap = _exact_object(value, SNAPSHOT_KEYS, name)
    snapshot_id = _opaque_id(snap["snapshot_id"], f"{name}.snapshot_id")
    role = snap["system_role"]
    if type(role) is not str or role not in ROLES or role != expected_role:
        raise ParityError(f"{name}.system_role must be {expected_role}")
    schema_revision = _opaque_id(snap["schema_revision"], f"{name}.schema_revision")
    captured = parse_utc(snap["captured_at_utc"], f"{name}.captured_at_utc")
    if captured > as_of:
        raise ParityError(f"{name}.captured_at_utc is in the future")
    if type(snap["complete_export"]) is not bool or snap["complete_export"] is not True:
        raise ParityError(f"{name}.complete_export must be literal true")
    claimed_rows_sha = _sha(snap["rows_sha256"], f"{name}.rows_sha256")
    rows = snap["rows"]
    if type(rows) is not list:
        raise ParityError(f"{name}.rows must be a list")
    if len(rows) > MAX_ROWS:
        raise ParityError(f"{name}.rows exceeds row limit")
    normalized = [normalize_record(row, f"{name}.rows[{idx}]", as_of=as_of) for idx, row in enumerate(rows)]
    normalized.sort(key=lambda r: (r["student_id"], r["term"], canonical_sha256(r)))
    actual_rows_sha = canonical_sha256(normalized)
    if claimed_rows_sha != actual_rows_sha:
        raise ParityError(f"{name}.rows_sha256 does not bind normalized rows")
    out = {
        "snapshot_id": snapshot_id,
        "system_role": role,
        "schema_revision": schema_revision,
        "captured_at_utc": format_utc(captured),
        "complete_export": True,
        "rows_sha256": actual_rows_sha,
        "rows": normalized,
    }
    out["snapshot_sha256"] = canonical_sha256(out)
    return out


def normalize_policy(value: Any) -> dict[str, Any]:
    policy = _exact_object(value, POLICY_KEYS, "policy")
    age = policy["max_sync_age_minutes"]
    if type(age) is not int or type(age) is bool or age <= 0 or age > 60 * 24 * 365:
        raise ParityError("policy.max_sync_age_minutes must be a positive bounded integer")
    return {"max_sync_age_minutes": age}


def _value_commitment(value: Any) -> str:
    return canonical_sha256(value)


def _group(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row_key(row)].append(row)
    return grouped


def _key_obj(key: tuple[str, str]) -> dict[str, str]:
    return {"student_id": key[0], "term": key[1]}


def _row_digest(row: dict[str, Any]) -> str:
    return canonical_sha256(row)


def compile_parity(source: Any, target: Any, policy: Any, *, as_of: str) -> dict[str, Any]:
    as_of_dt = parse_utc(as_of, "as_of")
    normalized_policy = normalize_policy(policy)
    src = normalize_snapshot(source, "source", expected_role="SOURCE_BANNER", as_of=as_of_dt)
    tgt = normalize_snapshot(target, "target", expected_role="TARGET_SAAS", as_of=as_of_dt)
    if src["snapshot_id"] == tgt["snapshot_id"]:
        raise ParityError("source and target snapshot_id must differ")
    if src["schema_revision"] != tgt["schema_revision"]:
        raise ParityError("source and target schema_revision must match")

    source_groups = _group(src["rows"])
    target_groups = _group(tgt["rows"])
    results: list[dict[str, Any]] = []
    counts = Counter()
    max_age = normalized_policy["max_sync_age_minutes"]

    for key in sorted(source_groups):
        srows = source_groups[key]
        trows = target_groups.get(key, [])
        base: dict[str, Any] = {"key": _key_obj(key)}
        if len(srows) != 1 or len(trows) > 1:
            classification = "DUPLICATE_ID"
            base.update(
                {
                    "classification": classification,
                    "source_occurrences": len(srows),
                    "target_occurrences": len(trows),
                    "source_row_sha256": sorted(_row_digest(r) for r in srows),
                    "target_row_sha256": sorted(_row_digest(r) for r in trows),
                }
            )
        elif not trows:
            classification = "MISSING_TARGET"
            base.update(
                {
                    "classification": classification,
                    "source_row_sha256": _row_digest(srows[0]),
                }
            )
        else:
            srow = srows[0]
            trow = trows[0]
            business_diffs = []
            for field in BUSINESS_FIELDS:
                if srow[field] != trow[field]:
                    business_diffs.append(
                        {
                            "field": field,
                            "source_value_sha256": _value_commitment(srow[field]),
                            "target_value_sha256": _value_commitment(trow[field]),
                        }
                    )
            target_sync = parse_utc(trow["last_sync_utc"], "normalized target last_sync_utc")
            age_minutes = int((as_of_dt - target_sync).total_seconds() // 60)
            if business_diffs:
                classification = "FIELD_MISMATCH"
                base.update(
                    {
                        "classification": classification,
                        "field_diffs": business_diffs,
                        "source_row_sha256": _row_digest(srow),
                        "target_row_sha256": _row_digest(trow),
                    }
                )
            elif age_minutes > max_age:
                classification = "STALE_SYNC"
                base.update(
                    {
                        "classification": classification,
                        "target_sync_age_minutes": age_minutes,
                        "max_sync_age_minutes": max_age,
                        "source_last_sync_sha256": _value_commitment(srow["last_sync_utc"]),
                        "target_last_sync_sha256": _value_commitment(trow["last_sync_utc"]),
                    }
                )
            elif srow["last_sync_utc"] != trow["last_sync_utc"]:
                classification = "FIELD_MISMATCH"
                base.update(
                    {
                        "classification": classification,
                        "field_diffs": [
                            {
                                "field": "last_sync_utc",
                                "source_value_sha256": _value_commitment(srow["last_sync_utc"]),
                                "target_value_sha256": _value_commitment(trow["last_sync_utc"]),
                            }
                        ],
                        "source_row_sha256": _row_digest(srow),
                        "target_row_sha256": _row_digest(trow),
                    }
                )
            else:
                classification = "PARITY_OK"
                base.update(
                    {
                        "classification": classification,
                        "row_sha256": _row_digest(srow),
                    }
                )
        counts[classification] += 1
        results.append(base)

    target_only = []
    for key in sorted(set(target_groups) - set(source_groups)):
        target_only.append(
            {
                "key": _key_obj(key),
                "occurrences": len(target_groups[key]),
                "row_sha256": sorted(_row_digest(r) for r in target_groups[key]),
            }
        )

    all_parity = (
        len(results) > 0
        and counts["PARITY_OK"] == len(results)
        and not target_only
        and len(source_groups) == len(src["rows"])
        and len(target_groups) == len(tgt["rows"])
    )
    report_without_receipt: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "engine_schema": SCHEMA,
        "as_of": format_utc(as_of_dt),
        "policy": normalized_policy,
        "source": src,
        "target": tgt,
        "summary": {
            "state": "PARITY_CLEAR_FOR_OWNER_REVIEW" if all_parity else "RECONCILIATION_REQUIRED",
            "source_record_count": len(src["rows"]),
            "target_record_count": len(tgt["rows"]),
            "classified_key_count": len(results),
            "target_only_key_count": len(target_only),
            "counts": {name: counts.get(name, 0) for name in sorted(CLASSIFICATIONS)},
        },
        "results": results,
        "target_only": target_only,
        "authority": {
            "read_only": True,
            "external_mutation": False,
            "migration_write": False,
            "buyer_contact": False,
            "deployment": False,
            "payment_or_revenue": False,
            "parity_state_is_owner_review_only": True,
        },
    }
    receipt = canonical_sha256(report_without_receipt)
    report = dict(report_without_receipt)
    report["receipt_sha256"] = receipt
    return report


def verify_report(report: Any) -> dict[str, Any]:
    if type(report) is not dict:
        raise ParityError("report must be an object")
    required = {
        "schema",
        "engine_schema",
        "as_of",
        "policy",
        "source",
        "target",
        "summary",
        "results",
        "target_only",
        "authority",
        "receipt_sha256",
    }
    if set(report) != required:
        raise ParityError("report key set is invalid")
    if report.get("schema") != REPORT_SCHEMA or report.get("engine_schema") != SCHEMA:
        raise ParityError("report schema mismatch")
    receipt = _sha(report["receipt_sha256"], "report.receipt_sha256")
    without = {k: report[k] for k in report if k != "receipt_sha256"}
    if canonical_sha256(without) != receipt:
        raise ParityError("report receipt mismatch")

    def denormalize_snapshot(snapshot: Any, name: str) -> dict[str, Any]:
        if type(snapshot) is not dict:
            raise ParityError(f"report.{name} must be object")
        expected = SNAPSHOT_KEYS | {"snapshot_sha256"}
        if set(snapshot) != expected:
            raise ParityError(f"report.{name} key set invalid")
        snap_without = {k: snapshot[k] for k in SNAPSHOT_KEYS}
        claimed = _sha(snapshot["snapshot_sha256"], f"report.{name}.snapshot_sha256")
        normalized_for_digest = dict(snap_without)
        if canonical_sha256(normalized_for_digest) != claimed:
            raise ParityError(f"report.{name}.snapshot_sha256 mismatch")
        return snap_without

    source = denormalize_snapshot(report["source"], "source")
    target = denormalize_snapshot(report["target"], "target")
    rebuilt = compile_parity(source, target, report["policy"], as_of=report["as_of"])
    if canonical_json_bytes(rebuilt) != canonical_json_bytes(report):
        raise ParityError("report does not recompile byte-identically")
    return {"verified": True, "receipt_sha256": receipt, "state": report["summary"]["state"]}


def render_markdown(report: dict[str, Any]) -> str:
    verify_report(report)
    summary = report["summary"]
    counts = summary["counts"]
    lines = [
        "# Banner SaaS Student-Record Parity Report",
        "",
        f"- State: `{summary['state']}`",
        f"- As of: `{report['as_of']}`",
        f"- Source snapshot: `{report['source']['snapshot_id']}` / `{report['source']['rows_sha256']}`",
        f"- Target snapshot: `{report['target']['snapshot_id']}` / `{report['target']['rows_sha256']}`",
        f"- Source records: `{summary['source_record_count']}`",
        f"- Target records: `{summary['target_record_count']}`",
        f"- Target-only keys: `{summary['target_only_key_count']}`",
        "",
        "## Classification counts",
        "",
    ]
    for name in sorted(CLASSIFICATIONS):
        lines.append(f"- `{name}`: `{counts[name]}`")
    lines.extend(
        [
            "",
            "## Authority ceiling",
            "",
            "Read-only owner-review evidence only. This report does not authorize migration writes, buyer contact, deployment, payment, or revenue recognition.",
            "",
            f"Receipt SHA-256: `{report['receipt_sha256']}`",
            "",
        ]
    )
    return "\n".join(lines)


def write_new_bytes(path: str | os.PathLike[str], data: bytes) -> None:
    p = Path(path)
    if type(data) is not bytes:
        raise ParityError("output data must be bytes")
    if p.exists() or p.is_symlink():
        raise ParityError(f"refusing to overwrite existing output: {p}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = None
    try:
        fd = os.open(p, flags, 0o600)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ParityError("output must be a regular file")
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short output write")
            view = view[written:]
        os.fsync(fd)
    except FileExistsError as exc:
        raise ParityError(f"refusing to overwrite existing output: {p}") from exc
    finally:
        if fd is not None:
            os.close(fd)


def write_new_text(path: str | os.PathLike[str], text: str) -> None:
    if type(text) is not str:
        raise ParityError("output text must be str")
    write_new_bytes(path, text.encode("utf-8"))


def _read_bounded(path: str | os.PathLike[str]) -> bytes:
    p = Path(path)
    st = p.stat()
    if not stat.S_ISREG(st.st_mode):
        raise ParityError("input must be a regular file")
    if st.st_size > MAX_JSON_BYTES:
        raise ParityError("input exceeds byte limit")
    raw = p.read_bytes()
    if len(raw) != st.st_size:
        raise ParityError("input changed during read")
    return raw


def _compile_cli(args: argparse.Namespace) -> int:
    request = load_json_bytes(_read_bounded(args.input))
    request = _exact_object(request, COMPILE_INPUT_KEYS, "compile input")
    report = compile_parity(request["source"], request["target"], request["policy"], as_of=utc_now())
    write_new_bytes(args.report, canonical_json_bytes(report))
    write_new_text(args.markdown, render_markdown(report))
    print(json.dumps({"state": report["summary"]["state"], "receipt_sha256": report["receipt_sha256"]}, sort_keys=True))
    return 0


def _verify_cli(args: argparse.Namespace) -> int:
    report = load_json_bytes(_read_bounded(args.report))
    result = verify_report(report)
    if args.markdown:
        actual = _read_bounded(args.markdown).decode("utf-8")
        expected = render_markdown(report)
        if actual != expected:
            raise ParityError("Markdown projection mismatch")
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only Banner SaaS student-record parity compiler")
    subs = parser.add_subparsers(dest="command", required=True)
    compile_p = subs.add_parser("compile")
    compile_p.add_argument("--input", required=True)
    compile_p.add_argument("--report", required=True)
    compile_p.add_argument("--markdown", required=True)
    compile_p.set_defaults(func=_compile_cli)
    verify_p = subs.add_parser("verify")
    verify_p.add_argument("--report", required=True)
    verify_p.add_argument("--markdown")
    verify_p.set_defaults(func=_verify_cli)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ParityError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
