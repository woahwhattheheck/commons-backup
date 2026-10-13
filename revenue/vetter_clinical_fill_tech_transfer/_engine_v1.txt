from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ENGINE_SCHEMA = "vetter-clinical-fill-tech-transfer/v1"
REPORT_SCHEMA = "vetter-clinical-fill-tech-transfer-report/v1"
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
OPAQUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_ROWS = 50_000
TEXT_MAX = 160

RECORD_KEYS = {
    "project_id",
    "molecule_id",
    "batch_id",
    "site_id",
    "receiving_site_id",
    "process_version",
    "method_version",
    "container_configuration",
    "equipment_id",
    "equipment_calibration_sha256",
    "operator_qualification_sha256",
    "qc_inspection_sha256",
    "microbiology_evidence_sha256",
    "storage_condition",
    "transfer_evidence_sha256",
    "release_evidence_sha256",
    "last_updated_utc",
}
SNAPSHOT_KEYS = {
    "snapshot_id",
    "system_role",
    "schema_revision",
    "transfer_generation",
    "captured_at_utc",
    "complete_export",
    "rows_sha256",
    "rows",
}
POLICY_KEYS = {"max_evidence_age_minutes"}
COMPILE_INPUT_KEYS = {"source", "receiving", "policy"}
ROLES = {"SOURCE_SITE", "RECEIVING_SITE"}
CLASSIFICATIONS = {
    "TRANSFER_READY",
    "METHOD_OR_VERSION_MISMATCH",
    "LOT_OR_RELEASE_GAP",
    "CONTAINER_OR_BATCH_CONFIG_MISMATCH",
    "EQUIPMENT_OR_CALIBRATION_GAP",
    "OPERATOR_QUALIFICATION_GAP",
    "MICROBIOLOGY_OR_INSPECTION_GAP",
    "STALE_EVIDENCE",
    "DUPLICATE_PACKET",
    "MISSING_RECEIVING_PACKET",
    "TRANSFER_CONFLICT",
}
NAMED_FAMILY_ORDER = (
    "METHOD_OR_VERSION_MISMATCH",
    "LOT_OR_RELEASE_GAP",
    "CONTAINER_OR_BATCH_CONFIG_MISMATCH",
    "EQUIPMENT_OR_CALIBRATION_GAP",
    "OPERATOR_QUALIFICATION_GAP",
    "MICROBIOLOGY_OR_INSPECTION_GAP",
)
FAMILY_FIELDS = {
    "METHOD_OR_VERSION_MISMATCH": ("process_version", "method_version"),
    "LOT_OR_RELEASE_GAP": ("transfer_evidence_sha256", "release_evidence_sha256"),
    "CONTAINER_OR_BATCH_CONFIG_MISMATCH": ("container_configuration",),
    "EQUIPMENT_OR_CALIBRATION_GAP": ("equipment_id", "equipment_calibration_sha256"),
    "OPERATOR_QUALIFICATION_GAP": ("operator_qualification_sha256",),
    "MICROBIOLOGY_OR_INSPECTION_GAP": ("qc_inspection_sha256", "microbiology_evidence_sha256"),
}
EVIDENCE_FIELDS = {
    "equipment_calibration_sha256",
    "operator_qualification_sha256",
    "qc_inspection_sha256",
    "microbiology_evidence_sha256",
    "transfer_evidence_sha256",
    "release_evidence_sha256",
}
GENERIC_COMPARE_FIELDS = ("receiving_site_id", "storage_condition")


class TransferError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise TransferError(f"non-finite JSON value is forbidden: {value}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise TransferError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_bytes(raw: bytes) -> Any:
    if type(raw) is not bytes:
        raise TransferError("JSON input must be exact bytes")
    if len(raw) > MAX_JSON_BYTES:
        raise TransferError("JSON input exceeds byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TransferError("JSON input must be UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_pairs, parse_constant=_reject_constant)
    except TransferError:
        raise
    except json.JSONDecodeError as exc:
        raise TransferError(f"invalid JSON: {exc.msg}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _exact_object(value: Any, keys: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise TransferError(f"{name} must be an object")
    actual = set(value)
    if actual != keys:
        raise TransferError(f"{name} keys mismatch; missing={sorted(keys-actual)} unknown={sorted(actual-keys)}")
    return value


def _plain_text(value: Any, name: str, *, max_len: int = TEXT_MAX) -> str:
    if type(value) is not str or not value:
        raise TransferError(f"{name} must be a non-empty string")
    if len(value) > max_len:
        raise TransferError(f"{name} exceeds length limit")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise TransferError(f"{name} contains control characters")
    return value


def _opaque(value: Any, name: str) -> str:
    text = _plain_text(value, name, max_len=80)
    if not OPAQUE_RE.fullmatch(text):
        raise TransferError(f"{name} must be a bounded opaque identifier")
    if "@" in text or "/" in text or "\\" in text:
        raise TransferError(f"{name} must not contain contact/path material")
    return text


def _sha_or_none(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise TransferError(f"{name} must be null or lowercase SHA-256 hex")
    return value


def _sha(value: Any, name: str) -> str:
    parsed = _sha_or_none(value, name)
    if parsed is None:
        raise TransferError(f"{name} must not be null")
    return parsed


def parse_utc(value: Any, name: str) -> datetime:
    if type(value) is not str or not UTC_RE.fullmatch(value):
        raise TransferError(f"{name} must be canonical whole-second UTC ending in Z")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise TransferError(f"{name} is not a real UTC timestamp") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise TransferError(f"{name} is not canonical UTC")
    return dt


def format_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise TransferError("trusted time must be timezone-aware")
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> str:
    return format_utc(datetime.now(timezone.utc))


def normalize_record(value: Any, name: str, *, as_of: datetime) -> dict[str, Any]:
    row = _exact_object(value, RECORD_KEYS, name)
    updated = parse_utc(row["last_updated_utc"], f"{name}.last_updated_utc")
    if updated > as_of:
        raise TransferError(f"{name}.last_updated_utc is in the future")
    out = {
        "project_id": _opaque(row["project_id"], f"{name}.project_id"),
        "molecule_id": _opaque(row["molecule_id"], f"{name}.molecule_id"),
        "batch_id": _opaque(row["batch_id"], f"{name}.batch_id"),
        "site_id": _opaque(row["site_id"], f"{name}.site_id"),
        "receiving_site_id": _opaque(row["receiving_site_id"], f"{name}.receiving_site_id"),
        "process_version": _opaque(row["process_version"], f"{name}.process_version"),
        "method_version": _opaque(row["method_version"], f"{name}.method_version"),
        "container_configuration": _plain_text(row["container_configuration"], f"{name}.container_configuration"),
        "equipment_id": _opaque(row["equipment_id"], f"{name}.equipment_id"),
        "storage_condition": _plain_text(row["storage_condition"], f"{name}.storage_condition"),
        "last_updated_utc": format_utc(updated),
    }
    for field in sorted(EVIDENCE_FIELDS):
        out[field] = _sha_or_none(row[field], f"{name}.{field}")
    if out["site_id"] == out["receiving_site_id"]:
        raise TransferError(f"{name} source and receiving site must differ")
    return out


def row_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return row["project_id"], row["molecule_id"], row["batch_id"], row["site_id"]


def normalize_snapshot(value: Any, name: str, *, expected_role: str, as_of: datetime) -> dict[str, Any]:
    snap = _exact_object(value, SNAPSHOT_KEYS, name)
    role = snap["system_role"]
    if type(role) is not str or role != expected_role:
        raise TransferError(f"{name}.system_role must be {expected_role}")
    captured = parse_utc(snap["captured_at_utc"], f"{name}.captured_at_utc")
    if captured > as_of:
        raise TransferError(f"{name}.captured_at_utc is in the future")
    if type(snap["complete_export"]) is not bool or snap["complete_export"] is not True:
        raise TransferError(f"{name}.complete_export must be literal true")
    rows = snap["rows"]
    if type(rows) is not list:
        raise TransferError(f"{name}.rows must be a list")
    if len(rows) > MAX_ROWS:
        raise TransferError(f"{name}.rows exceeds row limit")
    normalized = [normalize_record(row, f"{name}.rows[{idx}]", as_of=as_of) for idx, row in enumerate(rows)]
    normalized.sort(key=lambda r: (*row_key(r), canonical_sha256(r)))
    rows_sha = canonical_sha256(normalized)
    if _sha(snap["rows_sha256"], f"{name}.rows_sha256") != rows_sha:
        raise TransferError(f"{name}.rows_sha256 does not bind normalized rows")
    out = {
        "snapshot_id": _opaque(snap["snapshot_id"], f"{name}.snapshot_id"),
        "system_role": role,
        "schema_revision": _opaque(snap["schema_revision"], f"{name}.schema_revision"),
        "transfer_generation": _opaque(snap["transfer_generation"], f"{name}.transfer_generation"),
        "captured_at_utc": format_utc(captured),
        "complete_export": True,
        "rows_sha256": rows_sha,
        "rows": normalized,
    }
    out["snapshot_sha256"] = canonical_sha256(out)
    return out


def normalize_policy(value: Any) -> dict[str, Any]:
    policy = _exact_object(value, POLICY_KEYS, "policy")
    age = policy["max_evidence_age_minutes"]
    if type(age) is not int or type(age) is bool or age <= 0 or age > 60 * 24 * 365:
        raise TransferError("policy.max_evidence_age_minutes must be a positive bounded integer")
    return {"max_evidence_age_minutes": age}


def _group(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row_key(row)].append(row)
    return grouped


def _key_obj(key: tuple[str, str, str, str]) -> dict[str, str]:
    return {"project_id": key[0], "molecule_id": key[1], "batch_id": key[2], "site_id": key[3]}


def _row_sha(row: dict[str, Any]) -> str:
    return canonical_sha256(row)


def _diff(field: str, source: Any, target: Any) -> dict[str, str]:
    return {
        "field": field,
        "source_value_sha256": canonical_sha256(source),
        "receiving_value_sha256": canonical_sha256(target),
    }


def _family_diffs(source: dict[str, Any], target: dict[str, Any], family: str) -> list[dict[str, str]]:
    diffs: list[dict[str, str]] = []
    for field in FAMILY_FIELDS[family]:
        s = source[field]
        t = target[field]
        if field in EVIDENCE_FIELDS:
            if s is None or t is None or s != t:
                diffs.append(_diff(field, s, t))
        elif s != t:
            diffs.append(_diff(field, s, t))
    return diffs


def compile_transfer(source: Any, receiving: Any, policy: Any, *, as_of: str) -> dict[str, Any]:
    as_of_dt = parse_utc(as_of, "as_of")
    normalized_policy = normalize_policy(policy)
    src = normalize_snapshot(source, "source", expected_role="SOURCE_SITE", as_of=as_of_dt)
    recv = normalize_snapshot(receiving, "receiving", expected_role="RECEIVING_SITE", as_of=as_of_dt)
    if src["snapshot_id"] == recv["snapshot_id"]:
        raise TransferError("source and receiving snapshot_id must differ")
    if src["schema_revision"] != recv["schema_revision"]:
        raise TransferError("source and receiving schema_revision must match")
    if src["transfer_generation"] != recv["transfer_generation"]:
        raise TransferError("source and receiving transfer_generation must match")

    sgroups = _group(src["rows"])
    rgroups = _group(recv["rows"])
    counts = Counter()
    results: list[dict[str, Any]] = []
    max_age = normalized_policy["max_evidence_age_minutes"]

    for key in sorted(sgroups):
        srows = sgroups[key]
        rrows = rgroups.get(key, [])
        entry: dict[str, Any] = {"key": _key_obj(key)}
        if len(srows) != 1 or len(rrows) > 1:
            classification = "DUPLICATE_PACKET"
            entry.update({
                "classification": classification,
                "source_occurrences": len(srows),
                "receiving_occurrences": len(rrows),
                "source_row_sha256": sorted(_row_sha(r) for r in srows),
                "receiving_row_sha256": sorted(_row_sha(r) for r in rrows),
            })
        elif not rrows:
            classification = "MISSING_RECEIVING_PACKET"
            entry.update({"classification": classification, "source_row_sha256": _row_sha(srows[0])})
        else:
            srow = srows[0]
            rrow = rrows[0]
            classification = ""
            family_diffs: list[dict[str, str]] = []
            for family in NAMED_FAMILY_ORDER:
                diffs = _family_diffs(srow, rrow, family)
                if diffs:
                    classification = family
                    family_diffs = diffs
                    break
            if classification:
                entry.update({
                    "classification": classification,
                    "field_diffs": family_diffs,
                    "source_row_sha256": _row_sha(srow),
                    "receiving_row_sha256": _row_sha(rrow),
                })
            else:
                generic_diffs = [_diff(field, srow[field], rrow[field]) for field in GENERIC_COMPARE_FIELDS if srow[field] != rrow[field]]
                if generic_diffs:
                    classification = "TRANSFER_CONFLICT"
                    entry.update({
                        "classification": classification,
                        "field_diffs": generic_diffs,
                        "source_row_sha256": _row_sha(srow),
                        "receiving_row_sha256": _row_sha(rrow),
                    })
                else:
                    source_age = int((as_of_dt - parse_utc(srow["last_updated_utc"], "normalized source last_updated_utc")).total_seconds() // 60)
                    receiving_age = int((as_of_dt - parse_utc(rrow["last_updated_utc"], "normalized receiving last_updated_utc")).total_seconds() // 60)
                    if source_age > max_age or receiving_age > max_age:
                        classification = "STALE_EVIDENCE"
                        entry.update({
                            "classification": classification,
                            "source_age_minutes": source_age,
                            "receiving_age_minutes": receiving_age,
                            "max_evidence_age_minutes": max_age,
                            "source_last_updated_sha256": canonical_sha256(srow["last_updated_utc"]),
                            "receiving_last_updated_sha256": canonical_sha256(rrow["last_updated_utc"]),
                        })
                    else:
                        classification = "TRANSFER_READY"
                        entry.update({
                            "classification": classification,
                            "source_row_sha256": _row_sha(srow),
                            "receiving_row_sha256": _row_sha(rrow),
                        })
        counts[classification] += 1
        results.append(entry)

    target_only = []
    for key in sorted(set(rgroups) - set(sgroups)):
        target_only.append({
            "key": _key_obj(key),
            "occurrences": len(rgroups[key]),
            "row_sha256": sorted(_row_sha(r) for r in rgroups[key]),
        })

    all_ready = (
        len(results) > 0
        and counts["TRANSFER_READY"] == len(results)
        and not target_only
        and len(sgroups) == len(src["rows"])
        and len(rgroups) == len(recv["rows"])
    )
    report_without_receipt = {
        "schema": REPORT_SCHEMA,
        "engine_schema": ENGINE_SCHEMA,
        "as_of": format_utc(as_of_dt),
        "policy": normalized_policy,
        "source": src,
        "receiving": recv,
        "summary": {
            "state": "TRANSFER_READY_FOR_OWNER_REVIEW" if all_ready else "HOLD_FOR_OWNER_RECONCILIATION",
            "source_packet_count": len(src["rows"]),
            "receiving_packet_count": len(recv["rows"]),
            "classified_key_count": len(results),
            "receiving_only_key_count": len(target_only),
            "counts": {name: counts.get(name, 0) for name in sorted(CLASSIFICATIONS)},
        },
        "results": results,
        "receiving_only": target_only,
        "authority": {
            "read_only": True,
            "external_mutation": False,
            "process_parameter_recommendation": False,
            "deviation_disposition": False,
            "gmp_or_quality_decision": False,
            "batch_release": False,
            "scientific_or_regulatory_decision": False,
            "deployment": False,
            "buyer_contact": False,
            "payment_or_revenue": False,
            "ready_state_is_owner_review_only": True,
        },
    }
    report = dict(report_without_receipt)
    report["receipt_sha256"] = canonical_sha256(report_without_receipt)
    return report


def verify_report(report: Any) -> dict[str, Any]:
    if type(report) is not dict:
        raise TransferError("report must be an object")
    required = {
        "schema", "engine_schema", "as_of", "policy", "source", "receiving", "summary",
        "results", "receiving_only", "authority", "receipt_sha256",
    }
    if set(report) != required:
        raise TransferError("report key set is invalid")
    if report["schema"] != REPORT_SCHEMA or report["engine_schema"] != ENGINE_SCHEMA:
        raise TransferError("report schema mismatch")
    receipt = _sha(report["receipt_sha256"], "report.receipt_sha256")
    without = {k: report[k] for k in report if k != "receipt_sha256"}
    if canonical_sha256(without) != receipt:
        raise TransferError("report receipt mismatch")

    def denormalize(snapshot: Any, name: str) -> dict[str, Any]:
        if type(snapshot) is not dict or set(snapshot) != SNAPSHOT_KEYS | {"snapshot_sha256"}:
            raise TransferError(f"report.{name} key set invalid")
        plain = {k: snapshot[k] for k in SNAPSHOT_KEYS}
        if canonical_sha256(plain) != _sha(snapshot["snapshot_sha256"], f"report.{name}.snapshot_sha256"):
            raise TransferError(f"report.{name}.snapshot_sha256 mismatch")
        return plain

    source = denormalize(report["source"], "source")
    receiving = denormalize(report["receiving"], "receiving")
    rebuilt = compile_transfer(source, receiving, report["policy"], as_of=report["as_of"])
    if canonical_json_bytes(rebuilt) != canonical_json_bytes(report):
        raise TransferError("report does not recompile byte-identically")
    return {"verified": True, "state": report["summary"]["state"], "receipt_sha256": receipt}


def render_markdown(report: dict[str, Any]) -> str:
    verify_report(report)
    summary = report["summary"]
    lines = [
        "# Cross-Site Clinical Fill Tech-Transfer Evidence",
        "",
        f"- State: `{summary['state']}`",
        f"- As of: `{report['as_of']}`",
        f"- Transfer generation: `{report['source']['transfer_generation']}`",
        f"- Source snapshot: `{report['source']['snapshot_id']}` / `{report['source']['rows_sha256']}`",
        f"- Receiving snapshot: `{report['receiving']['snapshot_id']}` / `{report['receiving']['rows_sha256']}`",
        f"- Source packets: `{summary['source_packet_count']}`",
        f"- Receiving packets: `{summary['receiving_packet_count']}`",
        f"- Receiving-only keys: `{summary['receiving_only_key_count']}`",
        "",
        "## Classification counts",
        "",
    ]
    for name in sorted(CLASSIFICATIONS):
        lines.append(f"- `{name}`: `{summary['counts'][name]}`")
    lines += [
        "",
        "## Authority ceiling",
        "",
        "Read-only owner-review evidence only. This artifact does not authorize GMP/quality/scientific/regulatory decisions, process-parameter changes, deviation disposition, batch release, deployment, buyer contact, payment, or revenue recognition.",
        "",
        f"Receipt SHA-256: `{report['receipt_sha256']}`",
        "",
    ]
    return "\n".join(lines)


def write_new_bytes(path: str | os.PathLike[str], data: bytes) -> None:
    p = Path(path)
    if type(data) is not bytes:
        raise TransferError("output data must be bytes")
    if p.exists() or p.is_symlink():
        raise TransferError(f"refusing to overwrite existing output: {p}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = None
    try:
        fd = os.open(p, flags, 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise TransferError("output must be a regular file")
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short output write")
            view = view[written:]
        os.fsync(fd)
    except FileExistsError as exc:
        raise TransferError(f"refusing to overwrite existing output: {p}") from exc
    finally:
        if fd is not None:
            os.close(fd)


def write_new_text(path: str | os.PathLike[str], text: str) -> None:
    if type(text) is not str:
        raise TransferError("output text must be str")
    write_new_bytes(path, text.encode("utf-8"))


def _read_bounded(path: str | os.PathLike[str]) -> bytes:
    p = Path(path)
    st = p.stat()
    if not stat.S_ISREG(st.st_mode):
        raise TransferError("input must be a regular file")
    if st.st_size > MAX_JSON_BYTES:
        raise TransferError("input exceeds byte limit")
    raw = p.read_bytes()
    if len(raw) != st.st_size:
        raise TransferError("input changed during read")
    return raw


def _compile_cli(args: argparse.Namespace) -> int:
    request = _exact_object(load_json_bytes(_read_bounded(args.input)), COMPILE_INPUT_KEYS, "compile input")
    report = compile_transfer(request["source"], request["receiving"], request["policy"], as_of=utc_now())
    write_new_bytes(args.report, canonical_json_bytes(report))
    write_new_text(args.markdown, render_markdown(report))
    print(json.dumps({"state": report["summary"]["state"], "receipt_sha256": report["receipt_sha256"]}, sort_keys=True))
    return 0


def _verify_cli(args: argparse.Namespace) -> int:
    report = load_json_bytes(_read_bounded(args.report))
    result = verify_report(report)
    if args.markdown:
        actual = _read_bounded(args.markdown).decode("utf-8")
        if actual != render_markdown(report):
            raise TransferError("Markdown projection mismatch")
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only cross-site clinical fill tech-transfer evidence compiler")
    subs = parser.add_subparsers(dest="command", required=True)
    cp = subs.add_parser("compile")
    cp.add_argument("--input", required=True)
    cp.add_argument("--report", required=True)
    cp.add_argument("--markdown", required=True)
    cp.set_defaults(func=_compile_cli)
    vp = subs.add_parser("verify")
    vp.add_argument("--report", required=True)
    vp.add_argument("--markdown")
    vp.set_defaults(func=_verify_cli)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except TransferError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
