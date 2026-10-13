"""Self-contained, replay-verifiable local artifacts. No network calls."""
from __future__ import annotations

import csv
import hashlib
import html
import io
import json
import os
import stat
from pathlib import Path

from .core import InputError, MAX_BYTES, canonical, reconcile

FILE_LIMIT = 32 * 1024 * 1024
DATA_FILES = {"input.json", "report.json", "batches.csv", "deposits.csv", "transactions.csv", "exceptions.csv", "report.html"}
ALL_FILES = DATA_FILES | {"manifest.json"}


def _cell(value):
    if value is None:
        return "MISSING"
    if type(value) in (dict, list):
        value = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def as_csv(rows: list[dict], columns: list[str]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(["N/A" if key == "original_id" and row.get("kind") == "RECEIPT"
                         else _cell(row.get(key)) for key in columns])
    return buf.getvalue().encode("utf-8")


def _table(rows: list[dict], columns: list[str]) -> str:
    headings = "".join(f'<th scope="col">{html.escape(c.replace("_", " "))}</th>' for c in columns)
    body = []
    for row in rows:
        cells = []
        for col in columns:
            value = row.get(col)
            if value is None:
                text = "N/A" if (col == "original_id" and row.get("kind") == "RECEIPT") or col in {"currency", "variance_minor"} else "MISSING"
            elif type(value) is list and col in {"tenders", "allocations"}:
                codekey = "type" if col == "tenders" else "account_id"
                text = "; ".join(f"{p[codekey]}: {p['amount_minor']:,}" for p in value)
            elif type(value) is list and col == "batch_ids":
                text = ", ".join(value)
            elif type(value) in (dict, list):
                text = json.dumps(value, ensure_ascii=True, sort_keys=True)
            else:
                text = str(value)
            cells.append(f"<td>{html.escape(text)}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    if not body:
        body.append(f'<tr><td colspan="{len(columns)}">No rows</td></tr>')
    return f'<div class="table-wrap" role="region" aria-label="Scrollable report table" tabindex="0"><table><thead><tr>{headings}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def as_html(report: dict) -> bytes:
    esc = html.escape
    status = report["status"].replace("_", " ")
    content = f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Cashiering review — {esc(report['case_id'])}</title>
<style>
:root{{font-family:system-ui,-apple-system,sans-serif;line-height:1.5}}body{{max-width:1180px;margin:2rem auto;padding:0 1.2rem}}
h1{{font-size:2.1rem;line-height:1.12;overflow-wrap:anywhere}}h2{{margin-top:2.5rem}}.eyebrow{{font-size:.85rem;letter-spacing:.12em;text-transform:uppercase}}
.banner{{border:2px solid currentColor;padding:1rem;margin:1.5rem 0}}.table-wrap{{overflow-x:auto;margin:1rem 0}}table{{border-collapse:collapse;width:100%;min-width:960px;font-size:.88rem}}
th,td{{text-align:left;vertical-align:top;padding:.65rem;min-width:4rem;border-bottom:1px solid #aaa;overflow-wrap:anywhere}}th{{border-bottom:2px solid currentColor}}code{{overflow-wrap:anywhere}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:1rem}}.metric{{border:1px solid currentColor;padding:1rem}}.metric strong{{display:block;font-size:1.7rem}}
@media print{{body{{max-width:none;margin:.2in}}.table-wrap{{overflow:visible}}table{{min-width:0}}thead{{display:table-header-group}}tr{{break-inside:avoid}}h2{{break-after:avoid}}}}
</style></head><body>
<p class="eyebrow">Internal acceptance laboratory / normalized input review</p>
<h1>Cashiering reconciliation</h1><p><strong>Case:</strong> <code>{esc(report['case_id'])}</code></p>
<div class="banner"><strong>{esc(status)}</strong><p>This report checks the supplied normalized dataset, not source authenticity, source completeness, payment settlement, regulatory compliance, or production readiness. Invalid economic rows remain visible in candidate totals. No payment, posting, outreach, or money movement is performed.</p></div>
<div class="summary"><div class="metric"><strong>{len(report['batches'])}</strong>Batches</div><div class="metric"><strong>{len(report['transactions'])}</strong>Transactions</div><div class="metric"><strong>{len(report['deposits'])}</strong>Deposits</div><div class="metric"><strong>{report['findings_count']}</strong>Exceptions</div></div>
<p>All monetary columns use integer minor units. Currency scales: <code>{esc(json.dumps(report['currency_scale'],sort_keys=True))}</code>. No cross-currency grand total is calculated.</p>
<p>On smaller screens, scroll tables horizontally to see every column.</p><h2>Exceptions</h2>{_table(report['findings'], ['entity','code','currency','variance_minor','message'])}
<h2>Batch and drawer review</h2><p>Expected drawer = opening float + recorded cash receipts/refunds. Drawer variance = counted − expected. Available cash for deposit = counted − retained float.</p>
{_table(report['batches'], ['batch_id','currency','transaction_count','net_collected_minor','expected_drawer_minor','counted_drawer_minor','drawer_variance_minor','available_cash_for_deposit_minor'])}
<h2>Deposit review</h2><p>Cash deposit expectations start from actual counted cash less retained float, not theoretical collections. A shortage is therefore not automatically counted again as a deposit discrepancy. Noncash expectations use the supplied recorded tender activity; processor fees and timing are not inferred.</p>
{_table(report['deposits'], ['deposit_id','currency','tender','batch_ids','expected_minor','observed_minor','deposit_variance_minor'])}
<h2>Transaction detail</h2>{_table(report['transactions'], ['id','batch_id','kind','original_id','currency','original_minor','rounding_minor','collected_minor','tenders','allocations','evidence_ref'])}
<h2>Replay evidence and limits</h2><p>Input SHA-256: <code>{report['input_sha256']}</code>. Engine version: {report['engine_version']}. Replay compares every generated artifact against computation from retained input bytes. Anyone who can replace the input and regenerate the whole bundle can create a different internally consistent bundle; hashes do not authenticate a bank, State system, or cashier.</p>
<p>CSV, JSON, and HTML are generated locally. Browser print is a convenience, not a validated PDF/Excel export feature. This report contains no external scripts, fonts, links, telemetry, or services.</p>
</body></html>'''
    return content.encode("utf-8")


def bundle(raw: bytes) -> dict[str, bytes]:
    report = reconcile(raw)
    generated = {
        "input.json": raw,
        "report.json": canonical(report),
        "batches.csv": as_csv(report["batches"], ["batch_id", "agency", "business_unit", "department", "location", "bank_account", "currency", "cashier", "transaction_count", "net_collected_minor", "gross_receipts_minor", "refund_reversal_minor", "original_minor", "rounding_minor", "tender_totals_minor", "declared_total_minor", "expected_drawer_minor", "counted_drawer_minor", "drawer_variance_minor", "retained_cash_minor", "available_cash_for_deposit_minor", "variance_reason"]),
        "deposits.csv": as_csv(report["deposits"], ["deposit_id", "agency", "business_unit", "department", "location", "bank_account", "currency", "tender", "batch_ids", "expected_minor", "observed_minor", "deposit_variance_minor", "variance_reason", "evidence_ref"]),
        "transactions.csv": as_csv(report["transactions"], ["id", "batch_id", "kind", "timestamp", "original_id", "currency", "original_minor", "rounding_minor", "collected_minor", "tenders", "allocations", "evidence_ref"]),
        "exceptions.csv": as_csv(report["findings"], ["entity", "code", "currency", "variance_minor", "message"]),
        "report.html": as_html(report),
    }
    manifest = {"schema": "cashiering-bundle/1", "engine_version": report["engine_version"],
                "evidence_boundary": report["evidence_boundary"],
                "files": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                          for name, data in sorted(generated.items())}}
    generated["manifest.json"] = canonical(manifest)
    return generated


def _require_posix() -> None:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise InputError("CLI filesystem mode requires POSIX O_NOFOLLOW and directory descriptors; the pure-byte API is portable")


def _read_fd(fd: int, limit: int) -> bytes:
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        raise InputError("a regular file is required")
    chunks = []
    total = 0
    while True:
        chunk = os.read(fd, min(65536, limit + 1 - total))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > limit:
            raise InputError("file exceeds the size bound")


def read_input(path: str | Path) -> bytes:
    _require_posix()
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        return _read_fd(fd, MAX_BYTES)
    finally:
        os.close(fd)


def write_bundle(path: str | Path, artifacts: dict[str, bytes]) -> None:
    """Exclusive directory creation, files via directory FD, manifest written last.

    The destination's parent must already exist. Partial failure leaves a visibly
    incomplete directory; no automatic deletion of possibly foreign files occurs.
    Parent-directory components must be trusted against concurrent replacement.
    """
    _require_posix()
    if set(artifacts) != ALL_FILES:
        raise InputError("artifact set must be complete")
    if any(type(v) is not bytes or len(v) > FILE_LIMIT for v in artifacts.values()):
        raise InputError("artifact exceeds output size bound")
    path = Path(path)
    os.mkdir(path, 0o700)
    dfd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in sorted(DATA_FILES) + ["manifest.json"]:
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
            try:
                remaining = memoryview(artifacts[name])
                while remaining:
                    written = os.write(fd, remaining)
                    if written <= 0:
                        raise OSError("short write without progress")
                    remaining = remaining[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
        os.fsync(dfd)
    finally:
        os.close(dfd)


def verify(path: str | Path) -> dict:
    _require_posix()
    dfd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if set(os.listdir(dfd)) != ALL_FILES:
            raise InputError("bundle is incomplete or contains undeclared files")
        actual = {}
        for name in sorted(ALL_FILES):
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dfd)
            try:
                actual[name] = _read_fd(fd, MAX_BYTES if name == "input.json" else FILE_LIMIT)
            finally:
                os.close(fd)
        expected = bundle(actual["input.json"])
        mismatches = sorted(name for name in ALL_FILES if actual[name] != expected[name])
        if mismatches:
            raise InputError("replay mismatch: " + ", ".join(mismatches))
        report = json.loads(actual["report.json"])
        return {"verification": "EXACT_REPLAY_MATCH", "report_status": report["status"],
                "findings_count": report["findings_count"], "input_sha256": report["input_sha256"],
                "authority": report["authority"], "source_authenticity": "NOT_ATTESTED"}
    finally:
        os.close(dfd)
