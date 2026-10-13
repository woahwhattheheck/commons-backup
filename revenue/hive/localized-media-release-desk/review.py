#!/usr/bin/env python3
"""Read-only portfolio review of the existing localized-media ReleaseDesk.

Uses the native status projector against one retained SQLite snapshot. This is
not a rights decision, release package, approval tool or publication interface.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import html
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from typing import Any

from desk import ReleaseDesk

MAX_DATABASE_BYTES = 128 * 1024 * 1024
MAX_REPORT_BYTES = 16 * 1024 * 1024
MAX_REQUIRED_SLOTS = 25000
TABLES = {
    "titles": ({"title_id", "source_name", "source_sha256", "source_size", "required_json", "rights_ready", "created_at", "updated_at"}, 2500),
    "variants": ({"title_id", "locale", "territory", "kind", "revision", "artifact_name", "content_sha256", "content_size", "source_sha256", "updated_at"}, 25000),
    "approvals": ({"id", "title_id", "locale", "territory", "kind", "revision", "content_sha256", "reviewer_id", "approved_at"}, 100000),
    "events": ({"seq", "title_id", "event_kind", "detail_json", "at_utc"}, 100000),
    "requests": ({"request_id", "op", "payload_sha256", "result_json"}, None),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


class BorrowedConnection:
    """Let the native projector close each read without discarding the snapshot."""
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def execute(self, sql: str, parameters: tuple = ()):
        return self.connection.execute(sql, parameters)

    def close(self) -> None:
        if self.connection.in_transaction:
            self.connection.rollback()


class SnapshotDesk(ReleaseDesk):
    def __init__(self, connection: sqlite3.Connection):
        # Deliberately do not call ReleaseDesk.__init__: it executes schema DDL.
        self.snapshot = connection

    def conn(self) -> BorrowedConnection:
        return BorrowedConnection(self.snapshot)


def collect(db_path: Path) -> dict[str, Any]:
    path = db_path.resolve(strict=True)
    if not path.is_file():
        raise ValueError("--db must name an existing regular SQLite database")
    started = utc_now()
    deadline = time.monotonic() + 30
    with closing(sqlite3.connect(":memory:", isolation_level=None)) as snapshot:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True,
                                     timeout=5, isolation_level=None)) as source:
            source.execute("PRAGMA query_only=ON")
            page_size = source.execute("PRAGMA page_size").fetchone()[0]
            if source.execute("PRAGMA page_count").fetchone()[0] * page_size > MAX_DATABASE_BYTES:
                raise ValueError("database exceeds the 128 MiB review limit")

            def progress(status: int, remaining: int, total: int) -> None:
                if total * page_size > MAX_DATABASE_BYTES:
                    raise ValueError("database grew beyond the 128 MiB review limit")
                if time.monotonic() > deadline:
                    raise ValueError("snapshot acquisition exceeded 30 seconds; retry when the writer is quiet")

            source.backup(snapshot, pages=128, progress=progress, sleep=0.05)
        captured = utc_now()
        snapshot.row_factory = sqlite3.Row
        snapshot.execute("PRAGMA query_only=ON")
        snapshot.execute("PRAGMA trusted_schema=OFF")
        counts = {}
        for name, (columns, limit) in TABLES.items():
            schema = snapshot.execute("SELECT type,sql FROM sqlite_master WHERE name=?", (name,)).fetchone()
            if not schema or schema["type"] != "table" or "VIRTUAL TABLE" in (schema["sql"] or "").upper():
                raise ValueError("not a supported release desk: missing ordinary table " + name)
            present = {row["name"] for row in snapshot.execute('PRAGMA table_info("' + name + '")')}
            if not columns.issubset(present):
                raise ValueError("not a supported release desk: incompatible columns in " + name)
            if limit is not None:
                count = snapshot.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0]
                if count > limit:
                    raise ValueError(f"{name} exceeds its {limit:,}-row review limit")
                counts[name] = count
        desk = SnapshotDesk(snapshot)
        titles = []
        slots = 0
        # Check the required-slot count before the native per-variant queries.
        for row in snapshot.execute("SELECT title_id,required_json FROM titles ORDER BY title_id").fetchall():
            required = json.loads(row["required_json"])
            if not isinstance(required, list):
                raise ValueError("invalid required variants for title " + str(row["title_id"]))
            slots += len(required)
            if slots > MAX_REQUIRED_SLOTS:
                raise ValueError("required variant slots exceed the 25,000-slot review limit")
            titles.append(desk.status(row["title_id"]))
        report = {
            "schema_version": 1,
            "source_database_label": path.name,
            "snapshot_acquisition_started_utc": started,
            "snapshot_acquisition_completed_utc": captured,
            "scope": "All titles; native required-variant, current-approval and event projections from one SQLite backup",
            "external_publish_authorized": False,
            "database_row_counts": counts,
            "title_count": len(titles),
            "required_variant_count": slots,
            "ready_for_local_handoff_count": sum(t["release_status"] == "READY_FOR_LOCAL_HANDOFF" for t in titles),
            "hold_count": sum(t["release_status"] == "HOLD" for t in titles),
            "titles": titles,
        }
        if len(json_bytes(report)) > MAX_REPORT_BYTES:
            raise ValueError("native JSON projection exceeds the 16 MiB review limit; nothing was exported")
        return report


def csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str) and (value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@"))):
        return "'" + value
    return value


def csv_bytes(headers: list[str], rows: list[list[Any]]) -> bytes:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([csv_cell(value) for value in row])
    return out.getvalue().encode("utf-8")


def exports(report: dict[str, Any]) -> dict[str, bytes]:
    titles, variants, approvals, events = [], [], [], []
    for title in report["titles"]:
        tid = title["title_id"]
        source = title["source"]
        titles.append([tid, title["release_status"], title["owner_supplied_rights_ready"],
                       source["name"], source["sha256"], source["size"], title["created_at"],
                       title["updated_at"], json.dumps(title["holds"], ensure_ascii=False), False])
        for variant in title["variants"]:
            key = [tid, variant["locale"], variant["territory"], variant["kind"]]
            variants.append(key + [variant["status"], variant.get("revision"), variant.get("artifact_name"),
                                  variant.get("content_sha256"), variant.get("content_size"),
                                  variant.get("source_sha256"), variant.get("source_current"),
                                  len(variant.get("approvals", []))])
            for approval in variant.get("approvals", []):
                approvals.append(key + [variant["revision"], variant["content_sha256"],
                                        approval["reviewer_id"], approval["approved_at"]])
        for event in title["events"]:
            events.append([tid, event["seq"], event["event_kind"], event["at_utc"],
                           json.dumps(event["detail"], ensure_ascii=False, sort_keys=True, allow_nan=False)])
    return {
        "portfolio.json": json_bytes(report),
        "titles.csv": csv_bytes(["title_id", "release_status", "owner_supplied_rights_ready", "source_name", "source_sha256", "source_size", "created_at", "updated_at", "holds_json", "external_publish_authorized"], titles),
        "variants.csv": csv_bytes(["title_id", "locale", "territory", "kind", "status", "revision", "artifact_name", "content_sha256", "content_size", "source_sha256", "source_current", "current_approval_count"], variants),
        "approvals.csv": csv_bytes(["title_id", "locale", "territory", "kind", "revision", "content_sha256", "reviewer_id", "approved_at"], approvals),
        "events.csv": csv_bytes(["title_id", "seq", "event_kind", "at_utc", "detail_json"], events),
    }


STYLE = """
:root{font-family:system-ui,sans-serif;color:#17293a;background:#f3f5f6;line-height:1.55}
body{margin:0}header,main{max-width:1180px;margin:auto;padding:26px}header{padding-top:40px}
h1{font-size:2.3rem;line-height:1.15;margin:.2em 0}h2{font-size:1.1rem}small,.muted{color:#526574}
.notice{border-left:4px solid #966200;background:#fff5d7;padding:14px 18px}
.stats{display:flex;gap:14px;flex-wrap:wrap;margin:22px 0}.stats div{background:white;border:1px solid #ccd6dd;padding:12px 20px;flex:1}.stats strong{display:block;font-size:1.9rem}
.controls{display:flex;gap:12px;flex-wrap:wrap;margin:20px 0}label{display:grid;gap:4px}input,select,button{font:inherit;padding:9px;border:1px solid #718596;border-radius:4px}input{min-width:260px}button{cursor:pointer;background:#16394f;color:white}
a{color:#154c74}nav{display:flex;gap:16px;flex-wrap:wrap}article{background:white;border:1px solid #c6d1d9;margin:16px 0;padding:18px;break-inside:avoid}summary{cursor:pointer;font-weight:650}.badge{font-size:.75rem;margin-right:10px;border:1px solid;padding:3px 7px;border-radius:3px}.HOLD{color:#855800}.READY_FOR_LOCAL_HANDOFF{color:#176447}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.88rem}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #dbe1e5;padding:9px}th{background:#edf2f5}code{overflow-wrap:anywhere;font-size:.86em}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7f8;padding:12px;max-height:420px;overflow:auto}.hash{display:block;max-width:260px;overflow-wrap:anywhere}li{margin:4px 0}[hidden]{display:none!important}button:focus-visible,a:focus-visible,summary:focus-visible{outline:3px solid #ad6700;outline-offset:3px}
@media(max-width:620px){header,main{padding:16px}h1{font-size:1.7rem}input{min-width:0;width:100%}.controls label{width:100%}}
@media print{body{background:white}.controls,nav{display:none}header,main{padding:6px}article{break-inside:auto}.scroll{overflow:visible}pre{max-height:none;overflow:visible}.stats strong{font-size:1.4rem}}
"""
SCRIPT = """
const cards=Array.from(document.querySelectorAll('article'));
const query=document.getElementById('query');
const state=document.getElementById('state');
function filter(){const q=query.value.toLowerCase().trim();let visible=0;
for(const card of cards){const match=(!state.value||card.dataset.state===state.value)&&(!q||card.textContent.toLowerCase().includes(q));card.hidden=!match;if(match)visible++;}
document.getElementById('visible').textContent='Showing '+visible+' of '+cards.length+' titles. Downloads contain the complete snapshot.';}
query.addEventListener('input',filter);state.addEventListener('change',filter);
document.getElementById('expand').addEventListener('click',()=>{for(const card of cards)if(!card.hidden)for(const d of card.querySelectorAll('details'))d.open=true;});
document.getElementById('collapse').addEventListener('click',()=>{for(const d of document.querySelectorAll('details'))d.open=false;});
let printState=[];
window.addEventListener('beforeprint',()=>{printState=Array.from(document.querySelectorAll('article:not([hidden]) details')).map(d=>[d,d.open]);for(const [d]of printState)d.open=true;});
window.addEventListener('afterprint',()=>{for(const [d,open]of printState)d.open=open;});
document.getElementById('print').addEventListener('click',()=>window.print());filter();
"""


def render(report: dict[str, Any], files: dict[str, bytes]) -> bytes:
    def esc(value: Any) -> str:
        return html.escape(str(value), quote=True)

    def shown(value: Any) -> str:
        if value is None:
            return "Not supplied"
        return "true" if value is True else "false" if value is False else str(value)

    links = []
    for name, data in files.items():
        mime = "application/json" if name.endswith(".json") else "text/csv"
        links.append(f'<a download="{name}" href="data:{mime};base64,{base64.b64encode(data).decode()}">{name}</a>')
    cards = []
    for title in report["titles"]:
        status = title["release_status"]
        rows = []
        for variant in title["variants"]:
            reviewers = "; ".join(a["reviewer_id"] + " · " + a["approved_at"] for a in variant.get("approvals", []))
            rows.append("<tr>" + "".join("<td>" + value + "</td>" for value in [
                esc("/".join([variant["locale"], variant["territory"], variant["kind"]])),
                esc(variant["status"]), esc(shown(variant.get("revision"))),
                esc(variant.get("artifact_name", "Not supplied")),
                '<code class="hash">' + esc(variant.get("content_sha256", "Not supplied")) + "</code>",
                '<code class="hash">' + esc(variant.get("source_sha256", "Not supplied")) + "</code>",
                esc(shown(variant.get("source_current"))), esc(reviewers or "None recorded for this revision"),
            ]) + "</tr>")
        holds = "".join("<li>" + esc(hold) + "</li>" for hold in title["holds"])
        holds = "<ul>" + holds + "</ul>" if holds else "<p>No native holds in this retained snapshot.</p>"
        source = title["source"]
        cards.append(f'''<article data-state="{status}"><details><summary><span class="badge {status}">{status}</span>{esc(title["title_id"])}</summary>
<p>Owner-supplied rights ready: <strong>{esc(shown(title["owner_supplied_rights_ready"]))}</strong> · Updated {esc(title["updated_at"])}</p>
<p>Source: {esc(source["name"])} · {esc(source["size"])} bytes<br><code>{esc(source["sha256"])}</code></p>
{holds}<div class="scroll"><table><thead><tr><th>Required variant</th><th>Status</th><th>Revision</th><th>Artifact</th><th>Content SHA-256</th><th>Parent source SHA-256</th><th>Parent current</th><th>Current approvals</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<details><summary>Retained event history ({len(title["events"])})</summary><pre>{esc(json.dumps(title["events"], ensure_ascii=False, indent=2, allow_nan=False))}</pre></details>
</details></article>''')
    script_hash = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    policy = "default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-" + script_hash + "'; base-uri 'none'; form-action 'none'"
    page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="{esc(policy)}"><title>Localized media — portfolio review</title><style>{STYLE}</style></head><body>
<header><small>LOCALIZED MEDIA / RETAINED OPERATIONS REVIEW</small><h1>See what still needs attention.</h1>
<p>Database: {esc(report["source_database_label"])}. Snapshot acquired between {esc(report["snapshot_acquisition_started_utc"])} and {esc(report["snapshot_acquisition_completed_utc"])}.</p>
<p class="notice"><strong>Read-only, point-in-time review.</strong> READY_FOR_LOCAL_HANDOFF is not external publication authority or a rights/translation-quality assessment. Recheck the live desk before a later handoff. Reopening this file does not refresh it.</p>
<div class="stats"><div><strong>{report["title_count"]}</strong>Titles</div><div><strong>{report["hold_count"]}</strong>Titles on hold</div><div><strong>{report["ready_for_local_handoff_count"]}</strong>Ready for local handoff</div><div><strong>{report["required_variant_count"]}</strong>Required variant slots</div></div>
<nav aria-label="Complete snapshot downloads">{''.join(links)}</nav><p class="muted">Downloads include all titles, native required variants, current approvals and events. CSV formula-like text is prefixed with an apostrophe; JSON preserves original values. Historical approvals not returned by the native status projector are not exported.</p></header>
<main><div class="controls"><label>Search titles, variants, reviewers or holds<input id="query" type="search" placeholder="Title, locale, reviewer or hold reason"></label><label>Title status<select id="state"><option value="">All statuses</option><option value="HOLD">On hold</option><option value="READY_FOR_LOCAL_HANDOFF">Ready for local handoff</option></select></label><button id="expand" type="button">Expand visible</button><button id="collapse" type="button">Collapse all</button><button id="print" type="button">Print current view</button></div><p id="visible" role="status"></p><noscript><p>All retained titles and downloads are available below; filtering needs JavaScript.</p></noscript>
{''.join(cards) if cards else '<p>No titles are stored in this snapshot.</p>'}<p class="muted">No database writes, approvals, rights changes, package releases or platform requests are performed by this review.</p></main><script>{SCRIPT}</script></body></html>'''
    return page.encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="existing localized-media SQLite desk")
    parser.add_argument("--out", required=True, type=Path, help="new, non-existing output directory; parent must exist")
    args = parser.parse_args(argv)
    created = False
    try:
        # Output collisions are rejected before reading any database content.
        if os.path.lexists(args.out):
            raise FileExistsError("--out already exists; choose a new directory")
        report = collect(args.db)
        files = exports(report)
        files["review.html"] = render(report, files)
        args.out.mkdir(mode=0o700)
        created = True
        for name, data in files.items():
            with os.fdopen(os.open(args.out / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as handle:
                handle.write(data)
        print(json.dumps({"output": str(args.out), "open": str(args.out / "review.html"),
                          "titles": report["title_count"], "holds": report["hold_count"],
                          "files": list(files), "external_publish_authorized": False}, indent=2))
        return 0
    except Exception as exc:
        print(f"Review not completed: {type(exc).__name__}: {exc}", file=sys.stderr)
        if created:
            print("A partial output directory remains; inspect it and choose a new output path for a retry.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
