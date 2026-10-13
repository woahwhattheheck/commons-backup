#!/usr/bin/env python3
"""Compile and replay an explicit batch of retained SEC Company Facts plans.

Each company uses the existing sec_facts_vintage compiler unchanged. The batch
adds navigation and query counts; it never combines financial values or chooses
concepts, periods, forms, units, or filing cutoffs for the operator.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import html
import io
import json
import os
from pathlib import Path
import re
import stat
import sys

import sec_facts_vintage as core

MAX_BATCH_BYTES = 256 * 1024 * 1024
MAX_JOBS = 100
INDEX_NAMES = frozenset({"batch.json", "review.csv", "review.html", "manifest.json"})
BAD_STATUSES = frozenset({"NO_ELIGIBLE_FACT", "AMBIGUOUS_LATEST", "AMBIGUOUS_BASELINE", "SOURCE_CONFLICT"})
_JOB_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def read_jobs(batch_bytes: bytes, parent: Path) -> list[dict]:
    raw = core.loads(batch_bytes, core.MAX_PLAN_BYTES)
    if type(raw) is not dict or set(raw) != {"schema", "jobs"}:
        raise core.InputError("batch requires exactly schema and jobs")
    if raw["schema"] != "sec-facts-vintage-batch/v1":
        raise core.InputError("unsupported batch schema")
    if type(raw["jobs"]) is not list or not 1 <= len(raw["jobs"]) <= MAX_JOBS:
        raise core.InputError(f"batch requires 1..{MAX_JOBS} jobs")
    jobs = []
    seen = set()
    for job in raw["jobs"]:
        if type(job) is not dict or set(job) != {"id", "source", "plan"}:
            raise core.InputError("job requires exactly id, source and plan")
        ident = job["id"]
        if type(ident) is not str or _JOB_ID.fullmatch(ident) is None:
            raise core.InputError("job id requires 1..64 ASCII letters, digits, hyphens or underscores, starting with a letter or digit")
        if ident.casefold() in seen:
            raise core.InputError("job ids must be unique, including letter case")
        seen.add(ident.casefold())
        paths = {}
        for field in ("source", "plan"):
            value = job[field]
            if type(value) is not str or not value or len(value) > 4096 or "\0" in value:
                raise core.InputError(f"job {ident}: {field} must be a nonempty file path")
            path = Path(value)
            paths[field] = path if path.is_absolute() else parent / path
        jobs.append({"id": ident, **paths})
    return sorted(jobs, key=lambda job: job["id"])


def render_index(summary: dict, rows: list[dict]) -> bytes:
    esc = lambda value: html.escape("—" if value is None else str(value), quote=True)
    job_rows = []
    for job in summary["jobs"]:
        counts = ", ".join(f"{name}: {count}" for name, count in job["status_counts"].items())
        job_rows.append(
            f"<tr><td><a href='companies/{job['id']}/review.html'>{esc(job['id'])}</a></td>"
            f"<td>{esc(job['entity_name'])}</td><td>{esc(job['cik'])}</td>"
            f"<td>{esc(job['filed_on_or_before'])}</td><td>{job['query_count']}</td><td>{esc(counts)}</td></tr>"
        )
    query_rows = []
    for row in rows:
        query_rows.append(
            f"<tr><td><a href='companies/{row['job_id']}/review.html'>{esc(row['job_id'])}</a></td>" +
            "".join(f"<td>{esc(row[field])}</td>" for field in
                    ("query_id", "concept", "unit", "start", "end", "status", "first_value", "latest_value", "change")) + "</tr>"
        )
    counts = ", ".join(f"{name}: {count}" for name, count in summary["status_counts"].items())
    page = (
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
        "<title>SEC facts batch review</title><style>body{font:16px/1.55 system-ui,sans-serif;max-width:1400px;margin:32px auto;padding:0 20px}"
        ".scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #ccc;padding:7px;text-align:left;white-space:nowrap}"
        "code{overflow-wrap:anywhere}a{color:#165aa7}</style>"
        f"<h1>SEC facts batch review</h1><p>{len(summary['jobs'])} jobs · {summary['query_count']} explicit queries.</p>"
        f"<p>{esc(counts)}</p><p>Counts describe query outcomes. Financial values are never added across jobs. "
        "Open a company review for its complete filing observations and interpretation limits.</p>"
        "<h2>Company reviews</h2><div class='scroll'><table><thead><tr><th>Job</th><th>Entity</th><th>CIK</th>"
        "<th>Filing cutoff</th><th>Queries</th><th>Outcomes</th></tr></thead><tbody>" + "".join(job_rows) +
        "</tbody></table></div><h2>All query outcomes</h2><div class='scroll'><table><thead><tr>"
        "<th>Job</th><th>Query</th><th>Concept</th><th>Unit</th><th>Start</th><th>End</th><th>Status</th>"
        "<th>First value</th><th>Latest value</th><th>Change</th></tr></thead><tbody>" + "".join(query_rows) +
        "</tbody></table></div><h2>Interpretation limits</h2><ul>" +
        "".join(f"<li>{esc(value)}</li>" for value in core.DISCLAIMERS) +
        f"</ul><p>Batch input SHA-256: <code>{esc(summary['batch_sha256'])}</code></p></html>\n"
    )
    return page.encode("utf-8")


def build_batch(batch_bytes: bytes, parent: Path) -> tuple[dict[str, bytes], dict[str, dict[str, bytes]]]:
    jobs = read_jobs(batch_bytes, parent)
    companies = {}
    summaries = []
    rows = []
    counts = Counter()
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    header = None
    native_size = 0
    # A native CSV accession cell can exceed the csv module's 128-KiB default.
    csv.field_size_limit(core.MAX_REPORT_BYTES)
    for job in jobs:
        ident = job["id"]
        try:
            source = core.read_regular(job["source"], core.MAX_SOURCE_BYTES)
            plan = core.read_regular(job["plan"], core.MAX_PLAN_BYTES)
            members = core.build_bundle(source, plan)
        except (core.InputError, OSError, ValueError, OverflowError) as exc:
            raise core.InputError(f"job {ident}: {exc}") from exc
        native_size += sum(map(len, members.values()))
        if native_size > MAX_BATCH_BYTES:
            raise core.InputError("batch exceeds 256-MiB output limit; split the batch")
        report = json.loads(members["report.json"])
        companies[ident] = members
        summaries.append({
            "id": ident, "cik": report["cik"], "entity_name": report["entity_name"],
            "filed_on_or_before": report["filed_on_or_before"], "forms": report["forms"],
            "source_sha256": report["source_sha256"], "plan_sha256": report["plan_sha256"],
            "normalized_plan_sha256": report["normalized_plan_sha256"],
            "query_count": len(report["results"]), "status_counts": report["status_counts"],
            "bundle": f"companies/{ident}", "manifest_sha256": core.digest(members["manifest.json"]),
        })
        counts.update(report["status_counts"])
        reader = csv.reader(io.StringIO(members["review.csv"].decode("utf-8"), newline=""))
        current_header = next(reader)
        if header is None:
            header = current_header
            writer.writerow(["job_id", *header])
        elif header != current_header:
            raise core.InputError("native CSV headers differ across jobs")
        for row in reader:
            writer.writerow([ident, *row])
        for result in report["results"]:
            query = result["query"]
            rows.append({"job_id": ident, "query_id": query["id"],
                         "concept": f"{query['taxonomy']}:{query['concept']}",
                         **{key: query[key] for key in ("unit", "start", "end")},
                         **{key: result[key] for key in ("status", "first_value", "latest_value", "change")}})
    summary = {"schema": "sec-facts-vintage-batch-report/v1", "engine_version": core.VERSION,
               "batch_sha256": core.digest(batch_bytes), "query_count": sum(counts.values()),
               "status_counts": dict(sorted(counts.items())), "jobs": summaries,
               "limitations": core.DISCLAIMERS.copy()}
    index = {"batch.json": core.canonical(summary), "review.csv": stream.getvalue().encode("utf-8"),
             "review.html": render_index(summary, rows)}
    manifest = {"schema": "sec-facts-vintage-batch-manifest/v1", "engine_version": core.VERSION,
                "batch_sha256": core.digest(batch_bytes),
                "members": {name: core.digest(value) for name, value in sorted(index.items())},
                "companies": {ident: core.digest(members["manifest.json"]) for ident, members in companies.items()}}
    index["manifest.json"] = core.canonical(manifest)
    if native_size + sum(map(len, index.values())) > MAX_BATCH_BYTES:
        raise core.InputError("batch exceeds 256-MiB output limit; split the batch")
    return index, companies


def _directory(path: Path, names: set | frozenset) -> None:
    if not stat.S_ISDIR(path.lstat().st_mode) or set(p.name for p in path.iterdir()) != names:
        raise core.InputError(f"bundle directory has missing, extra or unsupported members: {path}")


def verify_batch(target: Path, index: dict[str, bytes], companies: dict[str, dict[str, bytes]]) -> None:
    _directory(target, INDEX_NAMES | {"companies"})
    _directory(target / "companies", set(companies))
    for name, expected in index.items():
        if core.read_regular(target / name, MAX_BATCH_BYTES) != expected:
            raise core.InputError(f"batch verification failed: {name}")
    for ident, members in companies.items():
        folder = target / "companies" / ident
        _directory(folder, core.BUNDLE_NAMES)
        for name, expected in members.items():
            if core.read_regular(folder / name, core.MAX_REPORT_BYTES) != expected:
                raise core.InputError(f"batch verification failed: companies/{ident}/{name}")


def write_batch(target: Path, index: dict[str, bytes], companies: dict[str, dict[str, bytes]]) -> None:
    target.mkdir(mode=0o700, parents=False, exist_ok=False)
    owned = target.lstat()
    folder = target / "companies"
    folder.mkdir(mode=0o700)
    for ident, members in companies.items():
        core.write_bundle(folder / ident, members)
    for name in sorted(index, key=lambda name: (name == "manifest.json", name)):
        current = target.lstat()
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (owned.st_dev, owned.st_ino):
            raise core.InputError("output directory changed during publication")
        with (target / name).open("xb") as handle:
            handle.write(index[name])
            handle.flush()
            os.fsync(handle.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("compile", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--batch", type=Path, required=True, help="explicit job manifest; relative input paths use its directory")
        command.add_argument("--bundle", type=Path, required=True, help="new output directory / existing directory to verify")
        if name == "compile":
            command.add_argument("--require-unambiguous", action="store_true", help="publish all reviews, then exit 3 for any missing, ambiguous or conflicted query")
    args = parser.parse_args(argv)
    try:
        batch_bytes = core.read_regular(args.batch, core.MAX_PLAN_BYTES)
        index, companies = build_batch(batch_bytes, args.batch.parent)
        if args.command == "compile":
            write_batch(args.bundle, index, companies)
        verify_batch(args.bundle, index, companies)
        report = json.loads(index["batch.json"])
        print(json.dumps({"bundle": str(args.bundle), "jobs": len(companies), "query_count": report["query_count"],
                          "status_counts": report["status_counts"], "verified": True}, sort_keys=True))
        if args.command == "compile" and args.require_unambiguous and BAD_STATUSES.intersection(report["status_counts"]):
            return 3
        return 0
    except (core.InputError, OSError, ValueError, OverflowError, csv.Error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
