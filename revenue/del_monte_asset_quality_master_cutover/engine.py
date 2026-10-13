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

ENGINE_SCHEMA = "del-monte-asset-quality-master-cutover/v1"
REPORT_SCHEMA = "del-monte-asset-quality-master-cutover-report/v1"
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
OPAQUE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_ROWS = 100_000
TEXT_MAX = 160

RECORD_KEYS = {
    "item_id",
    "batch_id",
    "site_id",
    "process_revision",
    "quality_master_revision",
    "inspection_evidence_sha256",
    "disposition",
    "last_updated_utc",
}
SNAPSHOT_KEYS = {
    "snapshot_id",
    "system_role",
    "schema_revision",
    "release_generation",
    "captured_at_utc",
    "complete_export",
    "rows_sha256",
    "rows",
}
POLICY_KEYS = {"max_target_age_minutes"}
COMPILE_INPUT_KEYS = {"source", "target", "policy"}
ROLES = {"SOURCE_CURRENT", "TARGET_CUTOVER"}
CLASSIFICATIONS = {"READY", "MISSING_TARGET", "STALE_TARGET", "DUPLICATE_KEY", "CONFLICT"}
COMPARE_FIELDS = (
    "process_revision",
    "quality_master_revision",
    "inspection_evidence_sha256",
    "disposition",
)


class CutoverError(ValueError):
    pass


def _reject_constant(value: str) -> None:
    raise CutoverError(f"non-finite JSON value is forbidden: {value}")


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise CutoverError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json_bytes(raw: bytes) -> Any:
    if type(raw) is not bytes:
        raise CutoverError("JSON input must be exact bytes")
    if len(raw) > MAX_JSON_BYTES:
        raise CutoverError("JSON input exceeds byte limit")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CutoverError("JSON input must be UTF-8") from exc
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_pairs, parse_constant=_reject_constant)
    except CutoverError:
        raise
    except json.JSONDecodeError as exc:
        raise CutoverError(f"invalid JSON: {exc.msg}") from exc


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _exact_object(value: Any, keys: set[str], name: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise CutoverError(f"{name} must be an object")
    actual = set(value)
    if actual != keys:
        raise CutoverError(f"{name} keys mismatch; missing={sorted(keys-actual)} unknown={sorted(actual-keys)}")
    return value


def _plain_text(value: Any, name: str, *, max_len: int = TEXT_MAX) -> str:
    if type(value) is not str or not value:
        raise CutoverError(f"{name} must be a non-empty string")
    if len(value) > max_len:
        raise CutoverError(f"{name} exceeds length limit")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise CutoverError(f"{name} contains control characters")
    return value


def _opaque(value: Any, name: str) -> str:
    text = _plain_text(value, name, max_len=80)
    if not OPAQUE_RE.fullmatch(text):
        raise CutoverError(f"{name} must be a bounded opaque identifier")
    if "@" in text or "/" in text or "\\" in text:
        raise CutoverError(f"{name} must not contain contact/path material")
    return text


def _sha(value: Any, name: str) -> str:
    if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise CutoverError(f"{name} must be lowercase SHA-256 hex")
    return value


def parse_utc(value: Any, name: str) -> datetime:
    if type(value) is not str or not UTC_RE.fullmatch(value):
        raise CutoverError(f"{name} must be canonical whole-second UTC ending in Z")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CutoverError(f"{name} is not a real UTC timestamp") from exc
    if dt.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise CutoverError(f"{name} is not canonical UTC")
    return dt


def format_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise CutoverError("trusted time must be timezone-aware")
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now() -> str:
    return format_utc(datetime.now(timezone.utc))


def normalize_record(value: Any, name: str, *, as_of: datetime) -> dict[str, Any]:
    row = _exact_object(value, RECORD_KEYS, name)
    updated = parse_utc(row["last_updated_utc"], f"{name}.last_updated_utc")
    if updated > as_of:
        raise CutoverError(f"{name}.last_updated_utc is in the future")
    return {
        "item_id": _opaque(row["item_id"], f"{name}.item_id"),
        "batch_id": _opaque(row["batch_id"], f"{name}.batch_id"),
        "site_id": _opaque(row["site_id"], f"{name}.site_id"),
        "process_revision": _opaque(row["process_revision"], f"{name}.process_revision"),
        "quality_master_revision": _opaque(row["quality_master_revision"], f"{name}.quality_master_revision"),
        "inspection_evidence_sha256": _sha(row["inspection_evidence_sha256"], f"{name}.inspection_evidence_sha256"),
        "disposition": _opaque(row["disposition"], f"{name}.disposition"),
        "last_updated_utc": format_utc(updated),
    }


def row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return row["item_id"], row["batch_id"], row["site_id"]


def normalize_snapshot(value: Any, name: str, *, expected_role: str, as_of: datetime) -> dict[str, Any]:
    snap = _exact_object(value, SNAPSHOT_KEYS, name)
    role = snap["system_role"]
    if type(role) is not str or role != expected_role:
        raise CutoverError(f"{name}.system_role must be {expected_role}")
    captured = parse_utc(snap["captured_at_utc"], f"{name}.captured_at_utc")
    if captured > as_of:
        raise CutoverError(f"{name}.captured_at_utc is in the future")
    if type(snap["complete_export"]) is not bool or snap["complete_export"] is not True:
        raise CutoverError(f"{name}.complete_export must be literal true")
    rows = snap["rows"]
    if type(rows) is not list:
        raise CutoverError(f"{name}.rows must be a list")
    if len(rows) > MAX_ROWS:
        raise CutoverError(f"{name}.rows exceeds row limit")
    normalized = [normalize_record(row, f"{name}.rows[{idx}]", as_of=as_of) for idx, row in enumerate(rows)]
    normalized.sort(key=lambda r: (*row_key(r), canonical_sha256(r)))
    rows_sha = canonical_sha256(normalized)
    if _sha(snap["rows_sha256"], f"{name}.rows_sha256") != rows_sha:
        raise CutoverError(f"{name}.rows_sha256 does not bind normalized rows")
    out = {
        "snapshot_id": _opaque(snap["snapshot_id"], f"{name}.snapshot_id"),
        "system_role": role,
        "schema_revision": _opaque(snap["schema_revision"], f"{name}.schema_revision"),
        "release_generation": _opaque(snap["release_generation"], f"{name}.release_generation"),
        "captured_at_utc": format_utc(captured),
        "complete_export": True,
        "rows_sha256": rows_sha,
        "rows": normalized,
    }
    out["snapshot_sha256"] = canonical_sha256(out)
    return out


def normalize_policy(value: Any) -> dict[str, Any]:
    policy = _exact_object(value, POLICY_KEYS, "policy")
    age = policy["max_target_age_minutes"]
    if type(age) is not int or type(age) is bool or age <= 0 or age > 60 * 24 * 365:
        raise CutoverError("policy.max_target_age_minutes must be a positive bounded integer")
    return {"max_target_age_minutes": age}


def _group(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row_key(row)].append(row)
    return grouped


def _key_obj(key: tuple[str, str, str]) -> dict[str, str]:
    return {"item_id": key[0], "batch_id": key[1], "site_id": key[2]}


def _row_sha(row: dict[str, Any]) -> str:
    return canonical_sha256(row)


def compile_cutover(source: Any, target: Any, policy: Any, *, as_of: str) -> dict[str, Any]:
    as_of_dt = parse_utc(as_of, "as_of")
    normalized_policy = normalize_policy(policy)
    src = normalize_snapshot(source, "source", expected_role="SOURCE_CURRENT", as_of=as_of_dt)
    tgt = normalize_snapshot(target, "target", expected_role="TARGET_CUTOVER", as_of=as_of_dt)
    if src["snapshot_id"] == tgt["snapshot_id"]:
        raise CutoverError("source and target snapshot_id must differ")
    if src["schema_revision"] != tgt["schema_revision"]:
        raise CutoverError("source and target schema_revision must match")
    if src["release_generation"] != tgt["release_generation"]:
        raise CutoverError("source and target release_generation must match")

    sgroups = _group(src["rows"])
    tgroups = _group(tgt["rows"])
    counts = Counter()
    results: list[dict[str, Any]] = []
    max_age = normalized_policy["max_target_age_minutes"]

    for key in sorted(sgroups):
        srows = sgroups[key]
        trows = tgroups.get(key, [])
        entry: dict[str, Any] = {"key": _key_obj(key)}
        if len(srows) != 1 or len(trows) > 1:
            classification = "DUPLICATE_KEY"
            entry.update({
                "classification": classification,
                "source_occurrences": len(srows),
                "target_occurrences": len(trows),
                "source_row_sha256": sorted(_row_sha(r) for r in srows),
                "target_row_sha256": sorted(_row_sha(r) for r in trows),
            })
        elif not trows:
            classification = "MISSING_TARGET"
            entry.update({"classification": classification, "source_row_sha256": _row_sha(srows[0])})
        else:
            srow = srows[0]
            trow = trows[0]
            diffs = []
            for field in COMPARE_FIELDS:
                if srow[field] != trow[field]:
                    diffs.append({
                        "field": field,
                        "source_value_sha256": canonical_sha256(srow[field]),
                        "target_value_sha256": canonical_sha256(trow[field]),
                    })
            target_updated = parse_utc(trow["last_updated_utc"], "normalized target last_updated_utc")
            age_minutes = int((as_of_dt - target_updated).total_seconds() // 60)
            if diffs:
                classification = "CONFLICT"
                entry.update({
                    "classification": classification,
                    "field_diffs": diffs,
                    "source_row_sha256": _row_sha(srow),
                    "target_row_sha256": _row_sha(trow),
                })
            elif age_minutes > max_age:
                classification = "STALE_TARGET"
                entry.update({
                    "classification": classification,
                    "target_age_minutes": age_minutes,
                    "max_target_age_minutes": max_age,
                    "target_last_updated_sha256": canonical_sha256(trow["last_updated_utc"]),
                })
            elif srow["last_updated_utc"] != trow["last_updated_utc"]:
                classification = "CONFLICT"
                entry.update({
                    "classification": classification,
                    "field_diffs": [{
                        "field": "last_updated_utc",
                        "source_value_sha256": canonical_sha256(srow["last_updated_utc"]),
                        "target_value_sha256": canonical_sha256(trow["last_updated_utc"]),
                    }],
                    "source_row_sha256": _row_sha(srow),
                    "target_row_sha256": _row_sha(trow),
                })
            else:
                classification = "READY"
                entry.update({"classification": classification, "row_sha256": _row_sha(srow)})
        counts[classification] += 1
        results.append(entry)

    target_only = []
    for key in sorted(set(tgroups) - set(sgroups)):
        target_only.append({
            "key": _key_obj(key),
            "occurrences": len(tgroups[key]),
            "row_sha256": sorted(_row_sha(r) for r in tgroups[key]),
        })

    all_ready = (
        len(results) > 0
        and counts["READY"] == len(results)
        and not target_only
        and len(sgroups) == len(src["rows"])
        and len(tgroups) == len(tgt["rows"])
    )
    report_without_receipt = {
        "schema": REPORT_SCHEMA,
        "engine_schema": ENGINE_SCHEMA,
        "as_of": format_utc(as_of_dt),
        "policy": normalized_policy,
        "source": src,
        "target": tgt,
        "summary": {
            "state": "READY_FOR_OWNER_REVIEW" if all_ready else "HOLD_FOR_RECONCILIATION",
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
            "food_safety_or_quality_decision": False,
            "manufacturing_disposition": False,
            "production_cutover": False,
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
        raise CutoverError("report must be an object")
    required = {
        "schema", "engine_schema", "as_of", "policy", "source", "target", "summary",
        "results", "target_only", "authority", "receipt_sha256",
    }
    if set(report) != required:
        raise CutoverError("report key set is invalid")
    if report["schema"] != REPORT_SCHEMA or report["engine_schema"] != ENGINE_SCHEMA:
        raise CutoverError("report schema mismatch")
    receipt = _sha(report["receipt_sha256"], "report.receipt_sha256")
    without = {k: report[k] for k in report if k != "receipt_sha256"}
    if canonical_sha256(without) != receipt:
        raise CutoverError("report receipt mismatch")

    def denormalize(snapshot: Any, name: str) -> dict[str, Any]:
        if type(snapshot) is not dict or set(snapshot) != SNAPSHOT_KEYS | {"snapshot_sha256"}:
            raise CutoverError(f"report.{name} key set invalid")
        plain = {k: snapshot[k] for k in SNAPSHOT_KEYS}
        if canonical_sha256(plain) != _sha(snapshot["snapshot_sha256"], f"report.{name}.snapshot_sha256"):
            raise CutoverError(f"report.{name}.snapshot_sha256 mismatch")
        return plain

    source = denormalize(report["source"], "source")
    target = denormalize(report["target"], "target")
    rebuilt = compile_cutover(source, target, report["policy"], as_of=report["as_of"])
    if canonical_json_bytes(rebuilt) != canonical_json_bytes(report):
        raise CutoverError("report does not recompile byte-identically")
    return {"verified": True, "state": report["summary"]["state"], "receipt_sha256": receipt}


def render_markdown(report: dict[str, Any]) -> str:
    verify_report(report)
    summary = report["summary"]
    lines = [
        "# Acquired-Asset Quality-Master Cutover Evidence",
        "",
        f"- State: `{summary['state']}`",
        f"- As of: `{report['as_of']}`",
        f"- Release generation: `{report['source']['release_generation']}`",
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
        lines.append(f"- `{name}`: `{summary['counts'][name]}`")
    lines += [
        "",
        "## Authority ceiling",
        "",
        "Read-only owner-review evidence only. This artifact does not authorize food-safety or quality decisions, manufacturing disposition, production cutover, deployment, buyer contact, payment, or revenue recognition.",
        "",
        f"Receipt SHA-256: `{report['receipt_sha256']}`",
        "",
    ]
    return "\n".join(lines)


def write_new_bytes(path: str | os.PathLike[str], data: bytes) -> None:
    p = Path(path)
    if type(data) is not bytes:
        raise CutoverError("output data must be bytes")
    if p.exists() or p.is_symlink():
        raise CutoverError(f"refusing to overwrite existing output: {p}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = None
    try:
        fd = os.open(p, flags, 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise CutoverError("output must be a regular file")
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short output write")
            view = view[written:]
        os.fsync(fd)
    except FileExistsError as exc:
        raise CutoverError(f"refusing to overwrite existing output: {p}") from exc
    finally:
        if fd is not None:
            os.close(fd)


def write_new_text(path: str | os.PathLike[str], text: str) -> None:
    if type(text) is not str:
        raise CutoverError("output text must be str")
    write_new_bytes(path, text.encode("utf-8"))


def _read_bounded(path: str | os.PathLike[str]) -> bytes:
    p = Path(path)
    st = p.stat()
    if not stat.S_ISREG(st.st_mode):
        raise CutoverError("input must be a regular file")
    if st.st_size > MAX_JSON_BYTES:
        raise CutoverError("input exceeds byte limit")
    raw = p.read_bytes()
    if len(raw) != st.st_size:
        raise CutoverError("input changed during read")
    return raw


def _compile_cli(args: argparse.Namespace) -> int:
    request = _exact_object(load_json_bytes(_read_bounded(args.input)), COMPILE_INPUT_KEYS, "compile input")
    report = compile_cutover(request["source"], request["target"], request["policy"], as_of=utc_now())
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
            raise CutoverError("Markdown projection mismatch")
    print(json.dumps(result, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only acquired-asset quality-master cutover evidence compiler")
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
    except CutoverError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
