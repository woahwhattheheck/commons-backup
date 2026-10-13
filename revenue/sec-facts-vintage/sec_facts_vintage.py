#!/usr/bin/env python3
"""Offline SEC Company Facts selection. Exact periods, decimals and filing dates.

This module does not fetch data, trade, infer accounting policy, or authenticate
SEC provenance. Its hashes bind the local inputs, not their origin/completeness.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import csv
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

VERSION = "1.0.0"
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_PLAN_BYTES = 256 * 1024
MAX_REPORT_BYTES = 64 * 1024 * 1024
MAX_NODES = 2_000_000
MAX_RECORDS = 250_000
MAX_QUERIES = 256
BUNDLE_NAMES = frozenset({"report.json", "review.csv", "review.html", "manifest.json"})
DISCLAIMERS = [
    "Local retained input only; origin, completeness and filing accuracy are not authenticated.",
    "Inclusive filing-date filtering is not intraday point-in-time availability or a complete vintage archive.",
    "Company Facts coverage is non-custom taxonomy and entity-wide facts; missing facts are not zero.",
    "Exact taxonomy, concept, unit and actual start/end dates are required; no automatic mappings, FX or YTD subtraction.",
    "Different reported values are not automatically restatements, accounting errors or fraud.",
    "Data-engineering review only; no investment recommendation, filing, accounting entry or transaction is authorized.",
]
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
_TAXONOMY = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,99}\Z")
_CONCEPT = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,299}\Z")
_UNIT = re.compile(r"[A-Za-z0-9][A-Za-z0-9./:_-]{0,79}\Z")
_ACCESSION = re.compile(r"[0-9]{10}-[0-9]{2}-[0-9]{6}\Z")


class InputError(ValueError):
    """Stable user-facing validation error, including malformed retained data."""


def _number(token: str, *, integer: bool = False) -> int | Decimal:
    if len(token) > 128:
        raise InputError("numeric token exceeds 128 characters")
    try:
        value = int(token) if integer else Decimal(token)
    except (ValueError, InvalidOperation) as exc:
        raise InputError("invalid numeric token") from exc
    if isinstance(value, Decimal):
        _decimal_text(value)
    elif len(str(abs(value))) > 96:
        raise InputError("integer exceeds 96 digits")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate JSON object key")
        result[key] = value
    return result


def _nonfinite(_: str) -> None:
    raise InputError("non-finite JSON number")


def loads(data: bytes, limit: int) -> Any:
    """Decode bounded strict UTF-8 JSON, preserving every decimal exactly."""
    if type(data) is not bytes or not 0 < len(data) <= limit:
        raise InputError("input is empty, not bytes, or exceeds its size limit")
    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                         parse_int=lambda s: _number(s, integer=True),
                         parse_float=_number, parse_constant=_nonfinite)
        stack = [(obj, 0)]
        nodes = 0
        while stack:
            value, depth = stack.pop()
            nodes += 1
            if nodes > MAX_NODES or depth > 32:
                raise InputError("JSON structure exceeds node/depth limit")
            if type(value) is dict:
                for key, child in value.items():
                    key.encode("utf-8")  # Reject unpaired surrogate escapes.
                    stack.append((child, depth + 1))
            elif type(value) is list:
                stack.extend((child, depth + 1) for child in value)
            elif type(value) is str:
                value.encode("utf-8")
        return obj
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise InputError("invalid UTF-8 JSON or excessive nesting") from exc


def _keys(value: Any, required: set[str], optional: set[str], where: str) -> dict:
    if type(value) is not dict or not required <= value.keys() or value.keys() - required - optional:
        raise InputError(f"{where}: missing or unsupported fields")
    return value


def _text(value: Any, where: str, maximum: int = 1024) -> str:
    if type(value) is not str or not 0 < len(value) <= maximum:
        raise InputError(f"{where}: expected nonempty bounded text")
    if any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise InputError(f"{where}: control/surrogate characters are unsupported")
    return value


def _matches(value: Any, pattern: re.Pattern, where: str) -> str:
    value = _text(value, where, 300)
    if pattern.fullmatch(value) is None:
        raise InputError(f"{where}: invalid identifier")
    return value


def _date(value: Any, where: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise InputError(f"{where}: expected YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f"{where}: invalid calendar date") from exc
    return value


def _cik(value: Any) -> str:
    if type(value) is int and 0 < value < 10**10:
        return f"{value:010d}"
    if type(value) is str and re.fullmatch(r"[0-9]{10}", value) and int(value) > 0:
        return value
    raise InputError("CIK must be a positive integer or exact ten-digit string")


def _decimal_text(value: Any, *, computed: bool = False) -> str:
    if type(value) not in (int, Decimal):
        raise InputError("fact value must be a JSON number, not bool, float, string or null")
    dec = Decimal(value)
    t = dec.as_tuple()
    if not dec.is_finite() or len(t.digits) > (192 if computed else 96) or not -40 <= t.exponent <= 40:
        raise InputError("fact value is non-finite or exceeds precision/exponent limits")
    text = format(dec, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if dec.is_zero() else text


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("utf-8")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_plan(raw: Any) -> dict:
    p = _keys(raw, {"schema", "cik", "filed_on_or_before", "forms", "queries"}, set(), "plan")
    if p["schema"] != "sec-facts-vintage-plan/v1":
        raise InputError("unsupported plan schema")
    forms = p["forms"]
    if type(forms) is not list or not 0 < len(forms) <= 32:
        raise InputError("forms: expected 1..32 explicit form names")
    forms = [_text(f, "form", 32) for f in forms]
    if len(set(forms)) != len(forms):
        raise InputError("forms: duplicate form")
    queries = p["queries"]
    if type(queries) is not list or not 0 < len(queries) <= MAX_QUERIES:
        raise InputError("queries: expected 1..256 extraction queries")
    normalized = []
    seen = set()
    scopes = set()
    for q in queries:
        _keys(q, {"id", "taxonomy", "concept", "unit", "start", "end"}, set(), "query")
        ident = _matches(q["id"], _IDENTIFIER, "query id")
        if ident in seen:
            raise InputError("duplicate query id")
        seen.add(ident)
        start = None if q["start"] is None else _date(q["start"], "query start")
        end = _date(q["end"], "query end")
        if start is not None and start > end:
            raise InputError("query start is after end")
        normalized.append({"id": ident, "taxonomy": _matches(q["taxonomy"], _TAXONOMY, "taxonomy"),
                           "concept": _matches(q["concept"], _CONCEPT, "concept"),
                           "unit": _matches(q["unit"], _UNIT, "unit"), "start": start, "end": end})
    for q in normalized:
        scope = tuple(q[k] for k in ("taxonomy", "concept", "unit", "start", "end"))
        if scope in scopes:
            raise InputError("duplicate extraction scope under a different query id")
        scopes.add(scope)
    return {"schema": p["schema"], "cik": _cik(p["cik"]),
            "filed_on_or_before": _date(p["filed_on_or_before"], "filing cutoff"),
            "forms": sorted(forms), "queries": sorted(normalized, key=lambda q: q["id"])}


def validate_source(raw: Any) -> dict:
    s = _keys(raw, {"cik", "entityName", "facts"}, set(), "Company Facts root")
    _cik(s["cik"])
    _text(s["entityName"], "entityName")
    if type(s["facts"]) is not dict or len(s["facts"]) > 100:
        raise InputError("facts: expected a bounded taxonomy object")
    return s


def _observations(source: dict, q: dict) -> tuple[str | None, list]:
    """Validate the selected concept/unit. Unrequested taxonomy data is untouched."""
    if q["taxonomy"] not in source["facts"]:
        return "TAXONOMY_ABSENT", []
    taxonomy = source["facts"][q["taxonomy"]]
    if type(taxonomy) is not dict:
        raise InputError("selected taxonomy must be an object")
    if q["concept"] not in taxonomy:
        return "CONCEPT_ABSENT", []
    concept = taxonomy[q["concept"]]
    if type(concept) is not dict or type(concept.get("units")) is not dict:
        raise InputError("selected concept has no valid units object")
    if q["unit"] not in concept["units"]:
        return "UNIT_ABSENT", []
    unit_rows = concept["units"][q["unit"]]
    if type(unit_rows) is not list or len(unit_rows) > MAX_RECORDS:
        raise InputError("selected unit has invalid/oversized observation array")
    return None, unit_rows


def _observation(raw: Any) -> dict:
    r = _keys(raw, {"end", "val", "accn", "form", "filed"}, {"start", "fy", "fp", "frame"}, "observation")
    start = _date(r["start"], "observation start") if "start" in r else None
    end = _date(r["end"], "observation end")
    if start is not None and start > end:
        raise InputError("observation start is after end")
    result = {"start": start, "end": end, "value": _decimal_text(r["val"]),
              "accession": _matches(r["accn"], _ACCESSION, "accession"),
              "form": _text(r["form"], "form", 32), "filed": _date(r["filed"], "filed")}
    if "fy" in r:
        if r["fy"] is not None and (type(r["fy"]) is not int or not 0 <= r["fy"] <= 9999):
            raise InputError("fy must be null or an integer from 0 to 9999")
        result["fy"] = r["fy"]
    for field in ("fp", "frame"):
        if field in r:
            result[field] = None if field == "fp" and r[field] is None else _text(r[field], field, 80)
    return result


def _select(q: dict, cutoff: str, forms: set[str], absent: str | None, rows_for_period: list) -> dict:
    unique: dict[bytes, dict] = {}
    admitted = 0
    for row in rows_for_period:
        if row["form"] not in forms or row["filed"] > cutoff:
            continue
        admitted += 1
        unique[canonical(row)] = row
    rows = sorted(unique.values(), key=lambda r: (r["filed"], r["accession"], canonical(r)))
    by_date: dict[str, list] = defaultdict(list)
    by_accession: dict[str, set] = defaultdict(set)
    for row in rows:
        by_date[row["filed"]].append(row)
        by_accession[row["accession"]].add((row["filed"], row["value"], row["form"]))
    conflicts = sorted(a for a, facts in by_accession.items() if len(facts) > 1)
    chronology = sorted({r["accession"] for r in rows if r["filed"] < r["end"]})
    vintages = []
    for filed, members in sorted(by_date.items()):
        values = sorted({r["value"] for r in members}, key=Decimal)
        vintages.append({"filed": filed, "values": values, "ambiguous": len(values) != 1,
                         "observations": members})
    first = vintages[0] if vintages else None
    last = vintages[-1] if vintages else None
    first_value = first["values"][0] if first and not first["ambiguous"] else None
    last_value = last["values"][0] if last and not last["ambiguous"] else None
    delta = None
    if conflicts or chronology:
        status = "SOURCE_CONFLICT"
        first_value = last_value = None
    elif not vintages:
        status = "NO_ELIGIBLE_FACT"
    elif last["ambiguous"]:
        status = "AMBIGUOUS_LATEST"
    elif first["ambiguous"]:
        status = "AMBIGUOUS_BASELINE"
    else:
        with localcontext() as ctx:
            ctx.prec = 256
            delta = _decimal_text(Decimal(last_value) - Decimal(first_value), computed=True)
        status = "SINGLE_VINTAGE" if len(vintages) == 1 else ("UNCHANGED" if delta == "0" else "CHANGED")
    return {"query": q, "status": status, "absence_reason": absent,
            "first_observed_filed": first["filed"] if first else None,
            "latest_observed_filed": last["filed"] if last else None,
            "first_value": first_value, "latest_value": last_value, "change": delta,
            "unit": q["unit"], "unique_observations": len(rows),
            "exact_replays_collapsed": admitted - len(rows),
            "conflicting_accessions": conflicts, "pre_period_close_accessions": chronology,
            "vintages": vintages}


def compile_report(source_bytes: bytes, plan_bytes: bytes) -> dict:
    source = validate_source(loads(source_bytes, MAX_SOURCE_BYTES))
    plan = validate_plan(loads(plan_bytes, MAX_PLAN_BYTES))
    if _cik(source["cik"]) != plan["cik"]:
        raise InputError("source CIK does not match extraction plan")
    # Index each requested concept/unit only once. Thousands of dates must not
    # cause repeated parsing of the same large observation history.
    cache = {}
    results = []
    record_count = 0
    forms = set(plan["forms"])
    for q in plan["queries"]:
        key = (q["taxonomy"], q["concept"], q["unit"])
        if key not in cache:
            absent, raw_rows = _observations(source, q)
            record_count += len(raw_rows)
            if record_count > MAX_RECORDS:
                raise InputError("combined selected histories exceed observation limit")
            periods = defaultdict(list)
            for raw in raw_rows:
                row = _observation(raw)
                periods[(row["start"], row["end"])].append(row)
            cache[key] = (absent, periods)
        absent, periods = cache[key]
        results.append(_select(q, plan["filed_on_or_before"], forms, absent,
                               periods.get((q["start"], q["end"]), [])))
    return {"schema": "sec-facts-vintage-report/v1", "engine_version": VERSION,
            "source_sha256": digest(source_bytes), "plan_sha256": digest(plan_bytes),
            "normalized_plan_sha256": digest(canonical(plan)),
            "cik": plan["cik"], "entity_name": source["entityName"],
            "filed_on_or_before": plan["filed_on_or_before"], "forms": plan["forms"],
            "temporal_basis": "FILED_DATE_INCLUSIVE_NOT_INTRADAY_AVAILABILITY",
            "evidence_basis": "UNAUTHENTICATED_RETAINED_INPUT",
            "status_counts": dict(sorted(Counter(r["status"] for r in results).items())),
            "limitations": DISCLAIMERS.copy(), "results": results}


def _csv_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def render_csv(report: dict) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["query_id", "cik", "entity_name", "taxonomy", "concept", "unit", "start", "end",
                     "status", "first_filed", "latest_filed", "first_value", "latest_value", "change",
                     "latest_accessions"])
    for r in report["results"]:
        q = r["query"]
        latest = r["vintages"][-1]["observations"] if r["vintages"] else []
        text_cells = [q["id"], report["cik"], report["entity_name"], q["taxonomy"], q["concept"], q["unit"],
                      q["start"], q["end"], r["status"], r["first_observed_filed"], r["latest_observed_filed"]]
        # Numeric columns come exclusively from exact normalized Decimal values.
        writer.writerow([_csv_text(v) for v in text_cells] +
                        ["" if r[k] is None else r[k] for k in ("first_value", "latest_value", "change")] +
                        [";".join(sorted({v["accession"] for v in latest}))])
    return stream.getvalue().encode("utf-8")


def render_html(report: dict) -> bytes:
    esc = lambda value: html.escape("—" if value is None else str(value), quote=True)
    items = []
    for r in report["results"]:
        q = r["query"]
        history = "".join("<tr>" + "".join(f"<td>{esc(row.get(k))}</td>" for k in
                           ("filed", "accession", "form", "value", "start", "end", "fy", "fp", "frame")) + "</tr>"
                          for v in r["vintages"] for row in v["observations"])
        items.append(f"<section><h2>{esc(q['id'])}</h2><p><strong>{esc(r['status'])}</strong> · "
                     f"{esc(q['taxonomy'])}:{esc(q['concept'])} · {esc(q['unit'])}</p>"
                     f"<p>Exact period: {esc(q['start'])} → {esc(q['end'])}. "
                     f"First: {esc(r['first_value'])}; latest: {esc(r['latest_value'])}; change: {esc(r['change'])}.</p>"
                     f"<p>Absent scope: {esc(r['absence_reason'])}. Conflicting accessions: {esc(', '.join(r['conflicting_accessions']) or None)}. "
                     f"Pre-close accessions: {esc(', '.join(r['pre_period_close_accessions']) or None)}.</p>"
                     "<details open><summary>Retained observation lineage</summary><div class='scroll'><table><thead><tr>"
                     "<th>Filed</th><th>Accession</th><th>Form</th><th>Value</th><th>Start</th><th>End</th><th>fy</th><th>fp</th><th>frame</th>"
                     f"</tr></thead><tbody>{history}</tbody></table></div></details></section>")
    page = ("<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">"
            "<title>SEC facts vintage review</title><style>body{font:16px/1.55 system-ui,sans-serif;max-width:1200px;margin:40px auto;padding:0 24px}"
            "section{border-top:1px solid #bbb;padding:20px 0}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}"
            "th,td{border:1px solid #ccc;padding:7px;text-align:left;white-space:nowrap}code{overflow-wrap:anywhere}</style>"
            f"<h1>SEC facts vintage review</h1><p>{esc(report['entity_name'])} · CIK {esc(report['cik'])}</p>"
            f"<p>Inclusive filing-date cutoff: <strong>{esc(report['filed_on_or_before'])}</strong>. Values retain their source units.</p>"
            "<h2>Interpretation limits</h2><ul>" + "".join(f"<li>{esc(v)}</li>" for v in report["limitations"]) + "</ul>" +
            "".join(items) + f"<footer><p>Source SHA-256: <code>{esc(report['source_sha256'])}</code><br>"
            f"Plan SHA-256: <code>{esc(report['plan_sha256'])}</code></p></footer></html>\n")
    return page.encode("utf-8")


def build_bundle(source: bytes, plan: bytes) -> dict[str, bytes]:
    report = compile_report(source, plan)
    members = {"report.json": canonical(report), "review.csv": render_csv(report), "review.html": render_html(report)}
    if sum(map(len, members.values())) > MAX_REPORT_BYTES:
        raise InputError("report bundle exceeds output size limit; narrow the extraction plan")
    manifest = {"schema": "sec-facts-vintage-manifest/v1", "engine_version": VERSION,
                "source_sha256": digest(source), "plan_sha256": digest(plan),
                "members": {name: digest(value) for name, value in sorted(members.items())}}
    members["manifest.json"] = canonical(manifest)
    return members


def read_regular(path: Path, limit: int) -> bytes:
    """Read bounded ordinary files; refuse final symlinks and detect mutation.

    Parent directories must be trusted and stable. This is not a hostile shared
    filesystem sandbox or a defense against another process with the same UID.
    """
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise InputError("input must be an ordinary non-symlink file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if not stat.S_ISREG(opened.st_mode) or identity(before) != identity(opened) or opened.st_size > limit:
            raise InputError("input changed, is not regular, or exceeds size limit")
        chunks = []
        total = 0
        while total <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        if total > limit or identity(os.fstat(fd)) != identity(opened) or identity(path.lstat()) != identity(opened):
            raise InputError("input changed during bounded read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def write_bundle(target: Path, members: dict[str, bytes]) -> None:
    """Create a new private output directory. Never overwrite existing output.

    manifest.json is written last: interruption leaves an incomplete bundle
    that verify refuses. We deliberately never delete a caller-visible path on
    failure. Keep the owner-controlled parent stable throughout publication.
    """
    target.mkdir(mode=0o700, parents=False, exist_ok=False)
    owned = target.lstat()
    for name in sorted(members, key=lambda n: (n == "manifest.json", n)):
        current = target.lstat()
        if (current.st_dev, current.st_ino) != (owned.st_dev, owned.st_ino) or not stat.S_ISDIR(current.st_mode):
            raise InputError("output directory changed during publication")
        with (target / name).open("xb") as handle:
            handle.write(members[name])
            handle.flush()
            os.fsync(handle.fileno())
    if set(p.name for p in target.iterdir()) != set(members):
        raise InputError("unexpected output member")


def verify_bundle(target: Path, source: bytes, plan: bytes) -> None:
    st = target.lstat()
    if not stat.S_ISDIR(st.st_mode):
        raise InputError("bundle must be a non-symlink directory")
    if set(p.name for p in target.iterdir()) != BUNDLE_NAMES:
        raise InputError("bundle contains missing or extra members")
    for name, expected in build_bundle(source, plan).items():
        if read_regular(target / name, MAX_REPORT_BYTES) != expected:
            raise InputError(f"bundle verification failed: {name}")


def inventory(source_bytes: bytes) -> dict:
    source = validate_source(loads(source_bytes, MAX_SOURCE_BYTES))
    concepts = []
    for taxonomy, tags in sorted(source["facts"].items()):
        if type(tags) is not dict:
            raise InputError("taxonomy must be an object")
        for tag, entry in sorted(tags.items()):
            if type(entry) is not dict or type(entry.get("units")) is not dict:
                raise InputError("concept must have a units object")
            units = {}
            for unit, observations in sorted(entry["units"].items()):
                if type(observations) is not list or len(observations) > MAX_RECORDS:
                    raise InputError("invalid/oversized unit observations")
                units[unit] = len(observations)
            concepts.append({"taxonomy": taxonomy, "concept": tag, "units_observation_counts": units})
    return {"schema": "sec-facts-vintage-inventory/v1", "cik": _cik(source["cik"]),
            "entity_name": source["entityName"], "source_sha256": digest(source_bytes),
            "coverage": "LOCAL_SNAPSHOT_NOT_HISTORICAL_COVERAGE", "concepts": concepts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("compile", "verify", "inventory"):
        sub = commands.add_parser(name)
        sub.add_argument("--source", type=Path, required=True, help="retained Company Facts JSON file")
        if name != "inventory":
            sub.add_argument("--plan", type=Path, required=True)
            sub.add_argument("--bundle", type=Path, required=True, help="new output directory / existing directory to verify")
        if name == "compile":
            sub.add_argument("--require-unambiguous", action="store_true", help="write report, then return 3 if any query is missing/ambiguous/conflicted")
    args = parser.parse_args(argv)
    try:
        source = read_regular(args.source, MAX_SOURCE_BYTES)
        if args.command == "inventory":
            sys.stdout.buffer.write(canonical(inventory(source)))
            return 0
        plan = read_regular(args.plan, MAX_PLAN_BYTES)
        if args.command == "verify":
            verify_bundle(args.bundle, source, plan)
            print("VERIFIED: exact retained inputs and all bundle members; not source authenticity.")
            return 0
        members = build_bundle(source, plan)
        write_bundle(args.bundle, members)
        verify_bundle(args.bundle, source, plan)
        report = json.loads(members["report.json"])
        print(json.dumps({"bundle": str(args.bundle), "status_counts": report["status_counts"]}, sort_keys=True))
        bad = {"NO_ELIGIBLE_FACT", "AMBIGUOUS_LATEST", "AMBIGUOUS_BASELINE", "SOURCE_CONFLICT"}
        return 3 if args.require_unambiguous and bad.intersection(report["status_counts"]) else 0
    except (InputError, OSError, ValueError, OverflowError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
