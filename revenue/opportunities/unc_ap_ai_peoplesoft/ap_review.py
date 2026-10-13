"""Offline AP consistency review, exact-cent exports, and semantic replay.

Consumes normalized USD invoice cases through the existing v2 evaluator.
No network, procurement readiness, provider authentication, or accounting action.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from html import escape
import io
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any, Sequence
import unicodedata

try:
    from . import unc_ap_ai_v2 as engine
except ImportError:
    import unc_ap_ai_v2 as engine

INPUT_SCHEMA = "unc.ap-review-input/v1"
REPORT_SCHEMA = "unc.ap-review-report/v1"
MAX_BYTES = 2 * 1024 * 1024
MAX_REPORT_BYTES = 8 * MAX_BYTES
MAX_INTEGER = (1 << 63) - 1
_ENGINE_SHA256 = hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest()
_INPUT_KEYS = {"schema", "evidence_class", "currency", "extraction_threshold_basis_points", "cases"}
_CASE_KEYS = {
    "invoice_id", "supplier_id", "extracted_supplier_id", "expected_amount_cents",
    "extracted_amount_cents", "match_mode", "purchase_order_amount_cents",
    "receipt_amount_cents", "routing_signoff_needed", "routing_signoff_present",
    "extraction_fields_total", "extraction_fields_correct", "duplicate_seen",
    "integration", "audit_events",
}
_INTEGRATION_KEYS = {"request_sha256", "ack_sha256", "effect_key", "retry_effect_key", "effect_count", "retry_count"}
_FILES = ("review.json", "review.csv", "review.html", "manifest.json")


class ReviewError(ValueError):
    """Input or retained output does not satisfy the review contract."""


def _check_plain(value: Any, *, report: bool = False) -> None:
    """Bound plain JSON before encoding; never invoke user-defined conversion."""
    seen: set[int] = set()
    nodes = 0

    def walk(item: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > (300_000 if report else 100_000) or depth > 24:
            raise ReviewError("JSON structure exceeds limits")
        kind = type(item)
        if item is None or kind is bool:
            return
        if kind is int:
            limit = MAX_INTEGER * (1000 if report else 1)
            if not -limit <= item <= limit:
                raise ReviewError("integer exceeds signed 64-bit input range")
            return
        if kind is str:
            if len(item) > 8192 or any(unicodedata.category(c) == "Cs" for c in item):
                raise ReviewError("invalid or oversized Unicode string")
            return
        if kind not in (dict, list):
            raise ReviewError("only plain integer JSON is supported")
        if id(item) in seen:
            raise ReviewError("cyclic JSON is not supported")
        seen.add(id(item))
        if kind is dict:
            for key, child in item.items():
                if type(key) is not str:
                    raise ReviewError("object keys must be strings")
                walk(key, depth + 1)
                walk(child, depth + 1)
        else:
            for child in item:
                walk(child, depth + 1)
        seen.remove(id(item))

    walk(value, 0)


def canonical(value: Any) -> bytes:
    # Report totals may exceed the per-invoice input range; they are exact Python
    # integers, not floats. Plain validation belongs at the ingress boundary.
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise ReviewError("value is not canonical JSON") from exc


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _reject_number(_: str) -> None:
    raise ReviewError("floating-point or non-finite JSON is not supported")


def _integer(value: str) -> int:
    if len(value.lstrip("-")) > 24:
        raise ReviewError("integer token exceeds limit")
    return int(value)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReviewError("duplicate decoded JSON key")
        result[key] = value
    return result


def parse(raw: bytes, *, report: bool = False) -> Any:
    cap = MAX_REPORT_BYTES if report else MAX_BYTES
    if type(raw) is not bytes or not 0 < len(raw) <= cap:
        raise ReviewError("JSON byte limit exceeded or empty input")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_float=_reject_number, parse_constant=_reject_number, parse_int=_integer)
    except (UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, ReviewError):
            raise
        raise ReviewError("invalid UTF-8 JSON") from exc


def _keys(value: Any, keys: set[str], label: str) -> None:
    if type(value) is not dict or set(value) != keys:
        raise ReviewError(f"{label} requires exact documented fields")


def _identity(value: Any, label: str, *, limit: int = 256) -> None:
    if (type(value) is not str or not value or len(value) > limit
            or value.strip() != value
            or unicodedata.normalize("NFC", value) != value
            or any(unicodedata.category(c).startswith("C") for c in value)):
        raise ReviewError(f"{label} must be bounded, NFC, nonblank text without controls")


def normalize_input(value: Any) -> dict[str, Any]:
    if type(value) is bytes:
        value = parse(value)
    _check_plain(value)
    raw = canonical(value)
    if len(raw) > MAX_BYTES:
        raise ReviewError("input exceeds byte limit")
    value = parse(raw)
    _keys(value, _INPUT_KEYS, "input")
    if value["schema"] != INPUT_SCHEMA or value["currency"] != "USD":
        raise ReviewError("unsupported schema or currency; only USD cents are supported")
    if value["evidence_class"] not in ("SYNTHETIC", "OPERATOR_SUPPLIED_UNVERIFIED"):
        raise ReviewError("unsupported evidence class")
    threshold = value["extraction_threshold_basis_points"]
    if type(threshold) is not int or not 0 <= threshold <= 10_000:
        raise ReviewError("threshold must be integer basis points from 0 to 10000")
    cases = value["cases"]
    if type(cases) is not list or not 1 <= len(cases) <= 1000:
        raise ReviewError("input requires 1 to 1000 invoice cases")
    invoice_ids: set[tuple[str, str]] = set()
    effect_ids: set[str] = set()
    for case in cases:
        _keys(case, _CASE_KEYS, "case")
        for field in ("invoice_id", "supplier_id", "extracted_supplier_id"):
            _identity(case[field], field)
        identity = (case["supplier_id"], case["invoice_id"])
        if identity in invoice_ids:
            raise ReviewError("duplicate supplier/invoice identity")
        invoice_ids.add(identity)
        _keys(case["integration"], _INTEGRATION_KEYS, "integration")
        effect = case["integration"]["effect_key"]
        _identity(effect, "effect_key", limit=512)
        if effect in effect_ids:
            raise ReviewError("duplicate supplied integration effect_key")
        effect_ids.add(effect)
        if type(case["match_mode"]) is not str:
            raise ReviewError("match_mode must be string")
        # Perform full semantic type/schema admission before report construction.
        try:
            engine.evaluate_invoice_case(case, extraction_threshold_basis_points=threshold)
        except (engine.ContractError, ValueError, TypeError, KeyError) as exc:
            raise ReviewError(f"invalid invoice case: {exc}") from exc
    cases.sort(key=lambda case: (case["supplier_id"], case["invoice_id"]))
    return value


def compile_review(value: Any) -> dict[str, Any]:
    data = normalize_input(value)
    rows = []
    for case in data["cases"]:
        result = engine.evaluate_invoice_case(
            case, extraction_threshold_basis_points=data["extraction_threshold_basis_points"])
        rows.append({
            "invoice_id": case["invoice_id"], "supplier_id": case["supplier_id"],
            "match_mode": case["match_mode"], "expected_amount_cents": case["expected_amount_cents"],
            "extracted_amount_cents": case["extracted_amount_cents"],
            "difference_cents": case["extracted_amount_cents"] - case["expected_amount_cents"],
            "disposition": result["disposition"], "input_sha256": digest(case),
            "engine_result": result,
        })
    exceptions = [row for row in rows if row["disposition"] != "PASS"]
    summary = {
        "invoice_count": len(rows), "consistent_count": len(rows) - len(exceptions),
        "exception_count": len(exceptions),
        "expected_amount_cents": sum(row["expected_amount_cents"] for row in rows),
        "extracted_amount_cents": sum(row["extracted_amount_cents"] for row in rows),
        "net_difference_cents": sum(row["difference_cents"] for row in rows),
        "absolute_difference_cents": sum(abs(row["difference_cents"]) for row in rows),
        "exceptions_expected_amount_cents": sum(row["expected_amount_cents"] for row in exceptions),
    }
    report = {
        "schema": REPORT_SCHEMA, "status": "REVIEW_REQUIRED" if exceptions else "CONSISTENT",
        "evidence_class": data["evidence_class"], "currency": "USD",
        "engine_source_sha256": _ENGINE_SHA256, "input_sha256": digest(data),
        "normalized_input": data, "rows": rows, "summary": summary,
        "authority": {
            "provider_authenticated": False, "procurement_ready": False,
            "accounting_write": False, "payment": False, "outbound": False,
            "contract_acceptance": False, "revenue_recognition": False,
        },
    }
    report["receipt_sha256"] = digest(report)
    return report


def verify_review(report: Any, *, against: Any = None) -> dict[str, Any]:
    if type(report) is bytes:
        report = parse(report, report=True)
    if type(report) is not dict or "normalized_input" not in report:
        raise ReviewError("report has no replay input")
    try:
        _check_plain(report, report=True)
        expected = compile_review(report["normalized_input"])
        if canonical(report) != canonical(expected):
            raise ReviewError("report does not match independent semantic replay")
        if against is not None and canonical(normalize_input(against)) != canonical(expected["normalized_input"]):
            raise ReviewError("report input differs from supplied original input")
    except (ValueError, TypeError, RecursionError, KeyError) as exc:
        if isinstance(exc, ReviewError):
            raise
        raise ReviewError("invalid report") from exc
    return expected


def _money(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) // 100:,}.{abs(cents) % 100:02d}"


def _cell(value: str) -> str:
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def _csv(report: dict[str, Any]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out, quoting=csv.QUOTE_ALL, lineterminator="\n")
    writer.writerow(["invoice_id", "supplier_id", "currency", "expected_amount_cents",
                     "extracted_amount_cents", "difference_cents", "disposition", "input_sha256"])
    for row in report["rows"]:
        writer.writerow([_cell(row["invoice_id"]), _cell(row["supplier_id"]), "USD",
                         row["expected_amount_cents"], row["extracted_amount_cents"],
                         row["difference_cents"], row["disposition"], row["input_sha256"]])
    return out.getvalue().encode("utf-8")


def _html(report: dict[str, Any]) -> bytes:
    s = report["summary"]
    cards = "".join(f'<div class="card"><span>{escape(label)}</span><strong>{escape(value)}</strong></div>' for label, value in (
        ("Invoices", str(s["invoice_count"])), ("Needs review", str(s["exception_count"])),
        ("Net difference", _money(s["net_difference_cents"])),
        ("Absolute differences", _money(s["absolute_difference_cents"]))))
    rows = "".join("<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in (
        row["invoice_id"], row["supplier_id"], row["match_mode"],
        _money(row["expected_amount_cents"]), _money(row["extracted_amount_cents"]),
        _money(row["difference_cents"]), row["disposition"])) + "</tr>" for row in report["rows"])
    text = '''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>AP evidence review</title><style>
body{font:16px/1.5 system-ui,sans-serif;margin:0;background:#f5f7fa;color:#192d40}
main{max-width:1200px;margin:auto;padding:32px 24px}h1{font-size:2.2rem;line-height:1.15;margin:8px 0 16px}
.eyebrow{font-weight:700;font-size:.8rem;letter-spacing:.12em}.notice{border-left:4px solid #536d83;padding:12px 20px;background:white}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:16px;margin:24px 0}
.card{background:white;padding:20px;border:1px solid #d7e0e8;border-radius:8px}.card span{display:block;font-size:.9rem}
.card strong{display:block;font-size:1.8rem;margin-top:10px;overflow-wrap:anywhere}
.table{overflow:auto;border:1px solid #d7e0e8;background:white}table{border-collapse:collapse;width:100%;font-size:.9rem}
caption{text-align:left;font-weight:700;padding:16px}th,td{padding:12px;text-align:left;border-bottom:1px solid #d7e0e8;vertical-align:top}
th{background:#eaf0f5}td{overflow-wrap:anywhere;max-width:300px}code{overflow-wrap:anywhere}
footer{margin-top:24px;font-size:.8rem;color:#42596c} @media(max-width:500px){main{padding:20px 12px}h1{font-size:1.8rem}}
</style></head><body><main><div class="eyebrow">READ-ONLY / USD / NORMALIZED INVOICE EVIDENCE</div>
<h1>AP evidence review</h1>'''
    text += f'<p><strong>{escape(report["status"])}</strong> &middot; {escape(report["evidence_class"])}</p>'
    text += '<p class="notice">Consistency checks only. No provider acknowledgment is independently authenticated. '
    text += 'This report does not establish procurement readiness, authorize payment, or change an accounting system. '
    text += 'A matching net total does not cancel individual exceptions. Differences are not a fraud, loss, or savings finding.</p>'
    text += f'<section class="cards" aria-label="Review totals">{cards}</section><div class="table"><table><caption>Invoice exceptions and consistency checks</caption>'
    text += '<thead><tr>' + ''.join(f'<th scope="col">{h}</th>' for h in ("Invoice", "Supplier", "Match", "Expected", "Extracted", "Difference", "Check")) + '</tr></thead>'
    text += f'<tbody>{rows}</tbody></table></div><footer><p>Input SHA-256: <code>{report["input_sha256"]}</code></p>'
    text += f'<p>Report receipt: <code>{report["receipt_sha256"]}</code></p><p>Keep the original input to verify input identity, not just internal report consistency.</p></footer></main></body></html>\n'
    return text.encode("utf-8")


def render_outputs(report: Any) -> dict[str, bytes]:
    report = verify_review(report)
    outputs = {"review.json": canonical(report) + b"\n", "review.csv": _csv(report), "review.html": _html(report)}
    manifest = {"schema": "unc.ap-review-files/v1", "files": {
        name: {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        for name, raw in outputs.items()}}
    outputs["manifest.json"] = canonical(manifest) + b"\n"
    return outputs


def _read_file(path: Path, *, cap: int, directory_fd: int | None = None) -> bytes:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ReviewError("file intake requires POSIX no-follow support")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        fd = os.open(path, flags, dir_fd=directory_fd)
        with os.fdopen(fd, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= cap:
                raise ReviewError("input must be a bounded nonempty regular file")
            raw = handle.read(cap + 1)
            after = os.fstat(handle.fileno())
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
            if len(raw) != before.st_size or any(getattr(before, f) != getattr(after, f) for f in fields):
                raise ReviewError("file changed during intake")
            return raw
    except OSError as exc:
        raise ReviewError(f"file read refused: {exc.strerror}") from exc


def write_pack(path: Path, report: Any) -> None:
    outputs = render_outputs(report)
    if not hasattr(os, "O_NOFOLLOW"):
        raise ReviewError("output requires POSIX no-follow support")
    try:
        os.mkdir(path, 0o700)  # Existing directories, files and symlinks are refused.
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for name in _FILES:  # manifest is the final completion marker.
                file_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                  0o600, dir_fd=fd)
                with os.fdopen(file_fd, "wb") as handle:
                    handle.write(outputs[name])
                    handle.flush()
                    os.fsync(handle.fileno())
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        raise ReviewError(f"new output directory not completed: {exc.strerror}") from exc


def verify_pack(path: Path, *, against: Any = None) -> dict[str, Any]:
    if not hasattr(os, "O_NOFOLLOW"):
        raise ReviewError("verification requires POSIX no-follow support")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if set(os.listdir(fd)) != set(_FILES):
                raise ReviewError("review directory must contain exactly four documented files")
            files = {name: _read_file(Path(name), cap=MAX_REPORT_BYTES, directory_fd=fd) for name in _FILES}
        finally:
            os.close(fd)
    except OSError as exc:
        raise ReviewError(f"review directory unavailable: {exc.strerror}") from exc
    report = verify_review(files["review.json"], against=against)
    if files != render_outputs(report):
        raise ReviewError("retained files do not match complete report regeneration")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="write a NEW private local review directory")
    build.add_argument("--input", required=True, type=Path)
    build.add_argument("--out", required=True, type=Path)
    verify = sub.add_parser("verify", help="recompute report semantics and all retained exports")
    verify.add_argument("--out", required=True, type=Path)
    verify.add_argument("--against", type=Path, help="original intake: also verify input identity")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            report = compile_review(_read_file(args.input, cap=MAX_BYTES))
            write_pack(args.out, report)
        else:
            against = _read_file(args.against, cap=MAX_BYTES) if args.against else None
            report = verify_pack(args.out, against=against)
        print(f'{args.command.upper()} OK / {report["status"]} / {report["receipt_sha256"]}')
        # Successful construction/verification is not payment or readiness approval.
        return 0
    except (ReviewError, engine.ContractError, OSError) as exc:
        print(f"AP review rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
