#!/usr/bin/env python3
"""Prepare a remediation input or build a private, offline operator review."""
from __future__ import annotations

import argparse
import base64
import csv
import io
import json
import os
from pathlib import Path
import stat
import sys
from html import escape
from typing import Any

from tools.procurement_win_loss import compile_record
from tools.procurement_win_loss.compiler import loads_strict
from .core import INPUT_SCHEMA
from .policy import compile_plan

MAX_INPUT_BYTES = 256 * 1024


def _read(path: Path) -> tuple[bytes, Any]:
    # One bounded read supplies both the compiler and the retained input copy.
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("input must be a regular file")
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ValueError("input exceeds 256 KiB")
    return raw, loads_strict(raw.decode("utf-8"))


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True,
                       allow_nan=False) + "\n").encode("utf-8")


def _write_new(path: Path, payload: bytes) -> None:
    # Neither preparation nor report delivery can overwrite an existing file.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)


def prepare(source: Path, destination: Path) -> dict[str, Any]:
    _, outcome = _read(source)
    receipt = compile_record(outcome)
    plan = {
        "schema": INPUT_SCHEMA,
        "outcome_record": outcome,
        "outcome_receipt": receipt,
        "buyer_reason_mappings": [],
        "internal_hypotheses": [],
        "remediation_gaps": [],
    }
    # This is generated input, not authentication of the source or its labels.
    payload = _json_bytes(plan)
    if len(payload) > MAX_INPUT_BYTES:
        raise ValueError("prepared plan exceeds 256 KiB; reduce the explicitly selected outcome scope")
    _write_new(destination, payload)
    return {"plan": str(destination), "source_outcome": receipt["outcome"],
            "note": "No reasons, hypotheses or actions have been inferred."}


def _text(value: Any) -> str:
    if value is None:
        return ""
    if type(value) is bool:
        return "true" if value else "false"
    return str(value)


def _csv_cell(value: Any) -> str:
    text = _text(value)
    # Spreadsheet-friendly export only; native JSON retains the original text.
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def gaps_csv(receipt: dict[str, Any]) -> bytes:
    columns = ["opportunity_id", "compiled_at", "status", "source_outcome",
               "gap_id", "version", "gap_kind", "rail", "basis_type",
               "basis_id", "basis_valid", "action"]
    output = io.StringIO(newline="")
    writer = csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(columns)
    for gap in receipt["remediation_gaps"]:
        row = {**gap, **{key: receipt[key] for key in columns[:4]}}
        writer.writerow([_csv_cell(row[key]) for key in columns])
    return output.getvalue().encode("utf-8")


def _table(title: str, headings: list[str], rows: list[list[Any]]) -> str:
    header = "".join("<th scope=\"col\">" + escape(item) + "</th>" for item in headings)
    body = "".join("<tr data-row>" + "".join("<td>" + escape(_text(item)) + "</td>"
                                            for item in row) + "</tr>" for row in rows)
    if not rows:
        return "<section><h2>" + escape(title) + "</h2><p>No entries supplied.</p></section>"
    return ("<section><h2>" + escape(title) + "</h2><div class=\"table-wrap\"><table>"
            "<thead><tr>" + header + "</tr></thead><tbody>" + body + "</tbody></table></div></section>")


def render_html(receipt: dict[str, Any], *, retained_input: bytes | None = None) -> str:
    """Render an output from compile_plan; never promote or reclassify it."""
    e = lambda value: escape(_text(value))
    # Chromium may navigate to file:// JSON despite the download attribute.
    # Data links retain exact native bytes and also work with JavaScript off.
    downloads = [("report.json", "Native report JSON", _json_bytes(receipt)),
                 ("gaps.csv", "All gap rows CSV", gaps_csv(receipt)),
                 ("input.json", "Private retained input", retained_input)]
    links = []
    for name, label, payload in downloads:
        href = name if payload is None else (
            "data:application/octet-stream;base64," + base64.b64encode(payload).decode("ascii")
        )
        links.append(f'<a href="{e(href)}" download="{e(name)}">{e(label)}</a>')
    download_links = "".join(links)
    private_input_note = (
        "This HTML and its download directory include the complete private input. Do not publish them by default."
        if retained_input is not None else
        "The download directory includes the complete private input. Do not publish it by default."
    )
    holds = receipt["source_hold_reasons"] + receipt["hold_reasons"]
    held = receipt["status"].startswith("HOLD_")
    hold_box = ("<section class=\"notice\"><h2>Source and plan holds</h2><ul>" +
                "".join("<li>" + e(item) + "</li>" for item in holds) + "</ul></section>") if holds else ""
    unmatched = receipt["unattributed_source_statement_ids"]
    if unmatched:
        hold_box += ("<section class=\"notice\"><h2>Unclassified source statements</h2><p>" +
                     ", ".join(e(item) for item in unmatched) + "</p></section>")
    gaps = _table("Remediation gaps — all supplied versions", ["Gap", "Version", "Kind", "Rail",
                   "Basis namespace", "Basis ID", "Basis valid", "Proposed internal action"],
                  [[g[k] for k in ("gap_id", "version", "gap_kind", "rail", "basis_type",
                                   "basis_id", "basis_valid", "action")]
                   for g in receipt["remediation_gaps"]])
    hypotheses = _table("Internal hypotheses — not buyer facts", ["Hypothesis", "Text", "Confidence",
                         "Basis valid", "Retained evidence references", "Attribution"],
                        [[h["hypothesis_id"], h["text"], h["confidence"], h["basis_valid"],
                          "; ".join(r["evidence_id"] + " / " + r["observed_at"] + " / " +
                                    r["source_digest_sha256"] for r in h["evidence_basis"]),
                          h["attribution"]] for h in receipt["internal_hypotheses"]])
    reasons = _table("Retained statement diagnostics — not authenticated buyer findings",
                     ["Reason", "Evidence", "Operator category", "Retained statement", "Attribution",
                      "Buyer authenticated", "Source digest"],
                     [[r["reason_id"], r["evidence_id"], r["category"], r["statement"],
                       r["statement_attribution"], r["buyer_source_authenticated"], r["source_digest_sha256"]]
                      for r in receipt["buyer_reasons"]])
    sources = _table("Caller-retained source evidence", ["Evidence", "Declared source kind", "Observed at",
                     "Recorded currentness", "Decision signal", "Mapped outcome", "Source digest"],
                    [[s[k] for k in ("evidence_id", "source_kind", "observed_at", "evidence_status",
                                     "decision_signal", "mapped_outcome", "source_digest_sha256")]
                     for s in receipt["source_evidence"]])
    authority = _table("Native authority fields", ["Field", "Value"],
                       [[key, value] for key, value in sorted(receipt["authority"].items())])
    explanation = ("The entire plan is on hold. A basis-valid row does not override the global hold."
                   if held else
                   "This is an internal review backlog, not a buyer finding, authorized task or causal conclusion.")
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>Procurement remediation review</title>
<style>
:root{font-family:system-ui,sans-serif;color:#15202b;background:#f5f7f9}body{max-width:1200px;margin:auto;padding:24px}
h1{font-size:2rem}h2{font-size:1.2rem}section,header{background:white;padding:20px;margin:18px 0;border:1px solid #d5dce2;border-radius:8px}
p{line-height:1.6}.notice{border-left:6px solid #965d00;overflow-wrap:anywhere}.status{font-weight:700;font-size:1.25rem}
.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:.9rem}th,td{text-align:left;vertical-align:top;padding:10px;border-bottom:1px solid #d5dce2;overflow-wrap:anywhere}th{background:#edf2f6}td{min-width:80px;white-space:pre-wrap}
input,button{font:inherit;padding:10px}input{width:min(600px,90%)}nav{display:flex;gap:16px;flex-wrap:wrap}a{color:#174c77}code{overflow-wrap:anywhere}
@media print{body{max-width:none;padding:0;background:white}.search,nav{display:none}section,header{border:0;padding:8px;margin:8px 0}h2{break-after:avoid}.table-wrap{overflow:visible}table{font-size:8pt}td{min-width:0}tr[hidden]{display:table-row}thead{display:table-header-group}tr{break-inside:avoid}}
</style></head><body><header><p>PRIVATE • OFFLINE • INTERNAL REVIEW</p><h1>Procurement remediation</h1>
""" + f"""<p class="status">{e(receipt['status'])}</p><p>{e(explanation)}</p>
<p><strong>Opportunity:</strong> {e(receipt['opportunity_id'])}<br><strong>Recorded outcome:</strong> {e(receipt['source_outcome'])}<br>
<strong>Packet compiled at:</strong> {e(receipt['compiled_at'])}</p>
<p>Opening or rebuilding this report does not refresh evidence. Currentness is evaluated against the supplied packet's clock and labels, not a live buyer or provider read. All supplied gap versions are retained; this page does not select the latest version.</p>
<nav aria-label="Local report downloads">{download_links}</nav>
</header>""" + hold_box + """<section class="search"><label for="query">Filter table rows</label><p><input id="query" type="search" placeholder="Search IDs, actions, rails or evidence" autocomplete="off"></p>
<p id="visible" role="status" aria-live="polite"></p><button id="print" type="button">Print complete report</button><p>Filtering never hides the global status or holds. Printing includes every row.</p></section>""" + gaps + hypotheses + reasons + sources + authority + f"""<footer><p>Native report digest: <code>{e(receipt['receipt_sha256'])}</code><br>
Upstream receipt digest: <code>{e(receipt['source_receipt_sha256'])}</code></p><p>Hashes bind the supplied packet; they do not authenticate its author or prove a buyer's intent. {e(private_input_note)}</p></footer>""" + """
<script>
const query=document.getElementById('query'),rows=Array.from(document.querySelectorAll('tr[data-row]'));
function filter(){const needle=query.value.toLocaleLowerCase();let visible=0;for(const row of rows){row.hidden=!row.textContent.toLocaleLowerCase().includes(needle);if(!row.hidden)visible++;}document.getElementById('visible').textContent=visible+' of '+rows.length+' table rows shown';}
query.addEventListener('input',filter);document.getElementById('print').addEventListener('click',()=>window.print());filter();
</script></body></html>
"""


def build(source: Path, destination: Path) -> dict[str, Any]:
    raw, plan = _read(source)
    receipt = compile_plan(plan)
    # Finish compilation/serialization before reserving a new output directory.
    payloads = [("input.json", raw), ("report.json", _json_bytes(receipt)),
                ("gaps.csv", gaps_csv(receipt)),
                ("report.html", render_html(receipt, retained_input=raw).encode("utf-8"))]
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        # The human entrypoint is last. On I/O failure keep already-written
        # private files for inspection; never remove or replace foreign work.
        for name, payload in payloads:
            _write_new(destination / name, payload)
    except OSError as exc:
        raise OSError(f"review delivery incomplete in {destination}; use a new directory after fixing the I/O error") from exc
    return {"report": str(destination / "report.html"), "status": receipt["status"],
            "gap_versions": len(receipt["remediation_gaps"]),
            "note": "Offline snapshot only; no buyer, provider, task or payment action."}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare", help="wrap an outcome record as editable remediation input")
    prep.add_argument("outcome", type=Path)
    prep.add_argument("plan", type=Path, help="new JSON file; parent directory must exist")
    review = commands.add_parser("build", help="compile a plan and create a private offline review")
    review.add_argument("plan", type=Path)
    review.add_argument("output", type=Path, help="new directory; parent directory must exist")
    args = parser.parse_args(argv)
    try:
        result = prepare(args.outcome, args.plan) if args.command == "prepare" else build(args.plan, args.output)
    except (ValueError, OSError, RecursionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
