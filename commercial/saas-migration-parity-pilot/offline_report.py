#!/usr/bin/env python3
"""Render the existing parity report as a portable, read-only HTML document."""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import sys
from pathlib import Path
from typing import Any

from errors import ParityError
from parity import compile_bytes
from parity_schema import CLASSIFICATIONS, MAX_INPUT_BYTES, canonical_bytes
from secure_io import read_bounded_regular, write_pair_exclusive

STYLE = """
:root{color-scheme:light;--ink:#15313b;--muted:#536975;--line:#d4dfe2;--wash:#f0f5f5;--accent:#126054}
*{box-sizing:border-box}body{margin:0;color:var(--ink);background:var(--wash);font:15px/1.5 system-ui,-apple-system,sans-serif}main{max-width:1180px;margin:0 auto;padding:2rem 1rem 4rem}header{border-bottom:3px solid var(--accent);padding-bottom:1rem;margin-bottom:1.5rem}.eyebrow{font-size:.75rem;text-transform:uppercase;letter-spacing:.14em;font-weight:700}h1{font-size:clamp(1.8rem,4vw,2.7rem);line-height:1.1;margin:.5rem 0}h2{font-size:1.2rem;margin:0 0 .7rem}h3{font-size:1rem;margin:0 0 .6rem}p{margin:.5rem 0}.muted{color:var(--muted)}.panel{background:white;border:1px solid var(--line);border-radius:8px;padding:1.2rem;margin:1.1rem 0}.state{font-weight:700;overflow-wrap:anywhere}.grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.counts{display:grid;grid-template-columns:repeat(auto-fit,minmax(135px,1fr));gap:.7rem;margin:1rem 0}.count{background:white;border:1px solid var(--line);border-radius:6px;padding:.85rem}.count strong{font-size:1.7rem;display:block}.count span{font-size:.72rem;overflow-wrap:anywhere}dl{margin:0}dt{font-size:.8rem;color:var(--muted);margin-top:.7rem}dd{margin:0;overflow-wrap:anywhere}code{font: .78rem ui-monospace,SFMono-Regular,monospace;overflow-wrap:anywhere}.digest{display:block;margin:.25rem 0}.tools{display:flex;gap:.7rem;flex-wrap:wrap;align-items:end}.tools label{display:block;font-size:.85rem;font-weight:600}.tools input,.tools select{display:block;width:100%;min-width:180px}.search{flex:1}.tools button,.tools a{white-space:nowrap}input,select,button,a.download{font:inherit;border:1px solid #a3b7bf;border-radius:5px;padding:.55rem .7rem;background:white;color:var(--ink)}button,a.download{cursor:pointer;text-decoration:none}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #ca8a17;outline-offset:2px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:.85rem;text-align:left}th,td{padding:.65rem;border-bottom:1px solid var(--line);vertical-align:top}th{background:var(--wash)}.classification{font-size:.72rem;font-weight:700;white-space:nowrap}.key{min-width:160px;max-width:250px}.mismatch{margin:.55rem 0;padding-left:.65rem;border-left:2px solid var(--line)}.mismatch p{margin:.15rem 0;font-size:.77rem}.boundary{font-size:.88rem;color:var(--muted)}.mapping{margin-top:1rem}.mapping span{display:inline-block;border:1px solid var(--line);border-radius:4px;padding:.25rem .4rem;margin:.15rem;font-size:.8rem}[hidden]{display:none!important}
@media(max-width:700px){.grid{grid-template-columns:1fr}.panel{padding:.85rem}main{padding-top:1.2rem}.tools>*{width:100%}.key{max-width:180px}}
@media print{body{background:white;font-size:10pt}main{max-width:none;padding:0}.tools,#visible-count,.interactive-note{display:none!important}.panel,.count{border-color:#aaa;break-inside:avoid}.table-wrap{overflow:visible}tr{break-inside:avoid}thead{display:table-header-group}tr.result-row[hidden]{display:table-row!important}.grid{grid-template-columns:1fr 1fr}a{text-decoration:none;color:inherit}}
""".strip()

SCRIPT = """
(() => {
  'use strict';
  const byId = (id) => document.getElementById(id);
  const rows = Array.from(document.querySelectorAll('tr.result-row'));
  function filter() {
    const classification = byId('classification').value;
    const query = byId('search').value.toLowerCase();
    let visible = 0;
    for (const row of rows) {
      const matches = (!classification || row.dataset.classification === classification)
        && row.dataset.search.includes(query);
      row.hidden = !matches;
      if (matches) visible += 1;
    }
    byId('visible-count').textContent = `${visible} of ${rows.length} keys shown. Printing includes every key, regardless of filters.`;
  }
  byId('classification').addEventListener('change', filter);
  byId('search').addEventListener('input', filter);
  byId('reset').addEventListener('click', () => {
    byId('classification').value = '';
    byId('search').value = '';
    filter();
  });
  byId('print').addEventListener('click', () => window.print());
  let downloadUrl = null;
  byId('download-json').addEventListener('click', () => {
    if (downloadUrl !== null) return;
    const binary = atob(byId('report-bytes').textContent.trim());
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    downloadUrl = URL.createObjectURL(new Blob([bytes], {type:'application/json;charset=utf-8'}));
    byId('download-json').href = downloadUrl;
  });
  window.addEventListener('beforeunload', () => {
    if (downloadUrl !== null) URL.revokeObjectURL(downloadUrl);
  });
  byId('tools').hidden = false;
  filter();
})();
""".strip()


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _csp_hash(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def _snapshot(label: str, snapshot: dict[str, Any]) -> str:
    pairs = [
        ("Snapshot / schema", f"{snapshot['snapshot_id']} / {snapshot['schema_revision']}"),
        ("Captured at (UTC)", snapshot["captured_at_utc"]),
        ("Records", snapshot["record_count"]),
        ("Declared complete", "yes" if snapshot["complete"] else "no"),
        ("Fresh at cutover", "yes" if snapshot["fresh_at_cutover"] else "no"),
        ("Age at cutover (seconds)", snapshot["age_seconds_at_cutover"]),
    ]
    entries = "".join(f"<dt>{escape(key)}</dt><dd>{escape(value)}</dd>" for key, value in pairs)
    return (
        f"<section class=panel><h2>{escape(label)}</h2><dl>{entries}"
        f"<dt>Normalized records SHA-256</dt><dd><code>{escape(snapshot['records_sha256'])}</code></dd>"
        "</dl></section>"
    )


def _mapping(label: str, mapping: list[dict[str, str]]) -> str:
    items = "".join(
        f"<span>{escape(row['source'])} → {escape(row['target'])} · {escape(row['type'])}</span>"
        for row in mapping
    )
    return f"<div class=mapping><h3>{escape(label)}</h3>{items}</div>"


def render_html(report: dict[str, Any]) -> str:
    """Render a compiled report, never record values or a second comparison.

    The embedded JSON is the exact canonical report bytes, encoded as base64 so
    neither HTML parsing nor JavaScript numeric serialization can alter it.
    This presentation is not a signed or independently re-verified attestation.
    """
    report_raw = canonical_bytes(report)
    embedded = base64.b64encode(report_raw).decode("ascii")
    summary = report["summary"]
    counts = summary["counts"]
    count_cards = "".join(
        f"<div class=count><strong>{counts[name]}</strong><span>{escape(name)}</span></div>"
        for name in CLASSIFICATIONS
    )
    options = "".join(
        f'<option value="{escape(name)}">{escape(name)} ({counts[name]})</option>'
        for name in CLASSIFICATIONS
    )
    rows = []
    for row in report["rows"]:
        reasons = ", ".join(row["reason_codes"]) or "Mapped fields match."
        field_names = " ".join(
            f"{item['source_field']} {item['target_field']}" for item in row["mismatch_fields"]
        )
        search = f"{row['key_commitment']} {row['classification']} {reasons} {field_names}".lower()
        mismatches = "".join(
            f"<div class=mismatch><p><strong>{escape(item['source_field'])} → {escape(item['target_field'])}</strong></p>"
            f"<p>Source value digest</p><code class=digest>{escape(item['source_value_sha256'])}</code>"
            f"<p>Target value digest</p><code class=digest>{escape(item['target_value_sha256'])}</code></div>"
            for item in row["mismatch_fields"]
        )
        rows.append(
            f'<tr class="result-row" data-classification="{escape(row["classification"])}" data-search="{escape(search)}">'
            f'<td class=classification>{escape(row["classification"])}</td>'
            f'<td class=key><code>{escape(row["key_commitment"])}</code></td>'
            f'<td>{escape(reasons)}{mismatches}</td></tr>'
        )
    if not rows:
        rows.append('<tr><td colspan="3">The supplied snapshots contain no union keys.</td></tr>')
    policy = (
        f"default-src 'none'; script-src 'sha256-{_csp_hash(SCRIPT)}'; "
        f"style-src 'sha256-{_csp_hash(STYLE)}'; base-uri 'none'; form-action 'none'; connect-src 'none'"
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{escape(policy)}">
<meta name="referrer" content="no-referrer"><title>Migration parity report</title>
<style>{STYLE}</style></head><body><main>
<header><span class="eyebrow">Supplied export comparison · Read-only report</span><h1>Migration parity report</h1>
<p class="state">{escape(summary['diagnostic_state'])}</p>
<p class="muted">Cutover {escape(report['cutover_at_utc'])} · {summary['union_key_count']} union keys · maximum snapshot age {report['max_snapshot_age_seconds']} seconds</p></header>
<p class="boundary">This standalone report contains classifications, supplied snapshot metadata and opaque key/value digests. It does not contain the input manifest's record values. Hashes are not encryption or guaranteed anonymization; keep this file private.</p>
<div class="counts">{count_cards}</div>
<div class="grid">{_snapshot('Source snapshot', report['source_snapshot'])}{_snapshot('Target snapshot', report['target_snapshot'])}</div>
<section class="panel"><h2>Declared comparison contract</h2>
{_mapping('Record key', report['key_map'])}{_mapping('Compared fields', report['field_map'])}</section>
<section class="panel"><h2>Results</h2>
<div id="tools" class="tools" hidden><label>Classification<select id="classification"><option value="">All classifications</option>{options}</select></label>
<label class="search">Search keys, fields or reasons<input id="search" type="search" placeholder="Opaque key prefix or field name"></label>
<button id="reset" type="button">Reset filters</button><button id="print" type="button">Print all rows</button>
<a id="download-json" class="download" download="parity-report.json" href="#">Download exact JSON</a></div>
<p id="visible-count" class="muted" role="status"></p><noscript><p>All rows are displayed below. Use your browser's Print command; interactive filtering and JSON download require JavaScript.</p></noscript>
<div class="table-wrap"><table><thead><tr><th scope="col">Classification</th><th scope="col">Opaque key</th><th scope="col">Reason / value digests</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>
<section class="panel"><h2>Report identity</h2><dl>
<dt>Generated input manifest SHA-256</dt><dd><code>{escape(report['input']['raw_input_sha256'])}</code></dd>
<dt>Semantic manifest SHA-256</dt><dd><code>{escape(report['input']['semantic_manifest_sha256'])}</code></dd>
<dt>Report core SHA-256</dt><dd><code>{escape(report['receipt']['report_core_sha256'])}</code></dd>
<dt>Engine / report schema</dt><dd>{escape(report['engine_version'])} / {escape(report['schema'])}</dd></dl></section>
<footer class="boundary"><p>This is a presentation of the compiled report, not independent verification, a signature, or production cutover certification. It cannot establish that unseen records are absent. The input digest binds the generated engine manifest, not the original pre-conversion CSV/JSON export files.</p>
<p>The exact embedded JSON can be checked against its supplied manifest with the existing parity.py verifier. This document makes no external network requests and performs no provider, customer-contact, contract, payment, or migration action. Printing includes all report rows, regardless of screen filters.</p></footer>
</main><script id="report-bytes" type="application/octet-stream">{embedded}</script><script>{SCRIPT}</script></body></html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="existing engine manifest, not raw CSV")
    parser.add_argument("--report-json", required=True, type=Path, help="new exact JSON output")
    parser.add_argument("--report-html", required=True, type=Path, help="new standalone HTML output")
    args = parser.parse_args(argv)
    try:
        report, _ = compile_bytes(read_bounded_regular(args.input, MAX_INPUT_BYTES))
        write_pair_exclusive(
            args.report_json, canonical_bytes(report),
            args.report_html, render_html(report).encode("utf-8"),
        )
        print(f"{report['summary']['diagnostic_state']} · {report['summary']['union_key_count']} union keys")
        print(f"JSON: {args.report_json}\nHTML: {args.report_html}")
        return 0
    except (ParityError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
