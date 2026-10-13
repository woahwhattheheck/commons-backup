"""Offline peer-research metadata screen; not a scorer or source authenticator."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import itertools
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

AREAS = ("software_development", "security", "deployment_operations", "ai_readiness")
KINDS = ("policy", "reported_practice", "measured_outcome", "framework", "proposal")
MODES = ("SYNTHETIC_REHEARSAL", "PUBLIC_SOURCE_RESEARCH")
MAX_BYTES = 4_000_000
MAX_PAIRS = 2_000
SOURCE_KEYS = "id title publisher url version published_on accessed_on".split()
RECORD_KEYS = "id institution service_context assessment_areas evidence_kind statement source_refs transfer_notes local_unknowns".split()
METRIC_KEYS = "id record_id metric_key kind value definition unit statistic population collection_method exclusions period_start period_end sample_size numerator_definition denominator_definition denominator_count source_refs".split()
MATCH_FIELDS = "metric_key kind definition unit statistic population collection_method exclusions period_start period_end".split()


class InputError(ValueError):
    """A packet cannot be interpreted without losing or inventing information."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InputError(message)


def shape(obj, keys, where, optional=()):
    require(type(obj) is dict, f"{where}: expected object")
    require(set(keys) <= obj.keys() <= set(keys) | set(optional),
            f"{where}: required keys {keys}; optional {list(optional)}")


def text(value, where, nullable=False):
    if value is None and nullable:
        return
    require(type(value) is str and bool(value.strip()) and len(value) <= 8000,
            f"{where}: expected nonempty text <=8000 characters" )
    require(not any(ord(c) < 32 and c not in '\n\r\t' for c in value),
            f"{where}: control character")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise InputError(f"{where}: invalid Unicode") from exc


def identifier(value, where):
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value),
            f"{where}: expected stable identifier <=80 characters")


def day(value, where, nullable=False):
    if value is None and nullable:
        return
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value),
            f"{where}: expected YYYY-MM-DD or explicit null where allowed")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise InputError(f"{where}: invalid calendar date") from exc


def collection(value, where, maximum):
    require(type(value) is list and len(value) <= maximum,
            f"{where}: expected list with at most {maximum} entries")


def decimal_text(value, where):
    if value is None:
        return
    require(type(value) is str and len(value) <= 64
            and re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", value),
            f"{where}: expected decimal string (no exponent) or null")


def count(value, where):
    require(value is None or (type(value) is int and 0 <= value <= 10**12),
            f"{where}: expected integer 0..10^12 or null")


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value):
    raise InputError(f"non-finite JSON number: {value}")


def loads(raw: bytes):
    require(type(raw) is bytes and len(raw) <= MAX_BYTES, "input exceeds 4 MB or is not bytes")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                          parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise InputError(f"invalid JSON: {exc}") from exc


def source_refs(refs, sources):
    collection(refs, "source_refs", 100)
    require(bool(refs), "record or metric needs at least one source reference")
    seen = set()
    for ref in refs:
        shape(ref, ["source_id", "locator"], "source_ref")
        identifier(ref["source_id"], "source_ref.source_id")
        require(ref["source_id"] in sources, "source_ref: unknown source id")
        text(ref["locator"], "source_ref.locator")
        key = (ref["source_id"], ref["locator"])
        require(key not in seen, "duplicate source reference")
        seen.add(key)


def validate(packet):
    shape(packet, ["schema_version", "mode", "as_of", "sources", "records", "metrics"],
          "packet", ["comparisons"])
    require(packet["schema_version"] == "1.0", "unsupported schema_version")
    require(packet["mode"] in MODES, "unsupported mode")
    day(packet["as_of"], "as_of")
    indexes = {}
    for name, keys, maximum in (("sources", SOURCE_KEYS, 1000),
                                ("records", RECORD_KEYS, 1000),
                                ("metrics", METRIC_KEYS, 500)):
        collection(packet[name], name, maximum)
        indexes[name] = {}
        for obj in packet[name]:
            shape(obj, keys, name)
            identifier(obj["id"], f"{name}.id")
            require(obj["id"] not in indexes[name], f"duplicate {name} id: {obj['id']}")
            indexes[name][obj["id"]] = obj
    for source in packet["sources"]:
        for key in ("title", "publisher", "url"):
            text(source[key], f"source.{key}")
        try:
            url = urlsplit(source["url"])
            require(url.scheme in ("http", "https") and bool(url.hostname)
                    and url.username is None and url.password is None
                    and not any(c.isspace() for c in source["url"]), "source.url: invalid public URL")
            _ = url.port
        except ValueError as exc:
            raise InputError("source.url: malformed URL") from exc
        text(source["version"], "source.version", nullable=True)
        day(source["published_on"], "source.published_on", nullable=True)
        day(source["accessed_on"], "source.accessed_on")
        require(source["accessed_on"] <= packet["as_of"], "source accessed after packet as_of")
    for record in packet["records"]:
        for key in ("institution", "service_context", "statement", "transfer_notes"):
            text(record[key], f"record.{key}")
        require(record["evidence_kind"] in KINDS, "record: unknown evidence_kind")
        collection(record["assessment_areas"], "assessment_areas", 4)
        areas = record["assessment_areas"]
        require(bool(areas) and all(type(x) is str and x in AREAS for x in areas), "invalid assessment area")
        require(len(set(areas)) == len(areas), "duplicate assessment area")
        collection(record["local_unknowns"], "local_unknowns", 100)
        for unknown in record["local_unknowns"]:
            text(unknown, "local_unknown")
        source_refs(record["source_refs"], indexes["sources"])
    for metric in packet["metrics"]:
        identifier(metric["record_id"], "metric.record_id")
        require(metric["record_id"] in indexes["records"], "metric: unknown record id")
        identifier(metric["metric_key"], "metric.metric_key")
        require(metric["kind"] in ("count", "gauge", "duration", "ratio", "rate"), "invalid metric.kind")
        decimal_text(metric["value"], "metric.value")
        for key in ("definition", "unit", "statistic", "population", "collection_method",
                    "numerator_definition", "denominator_definition"):
            text(metric[key], f"metric.{key}", nullable=True)
        if metric["exclusions"] is not None:
            collection(metric["exclusions"], "exclusions", 100)
            for exclusion in metric["exclusions"]:
                text(exclusion, "exclusion")
        for key in ("period_start", "period_end"):
            day(metric[key], f"metric.{key}", nullable=True)
        start, end = metric["period_start"], metric["period_end"]
        require(not (start and end and start > end), "metric: reversed observation period")
        require(end is None or end <= packet["as_of"], "metric: future observation period")
        count(metric["sample_size"], "metric.sample_size")
        count(metric["denominator_count"], "metric.denominator_count")
        source_refs(metric["source_refs"], indexes["sources"])
        require(start is None or start <= packet["as_of"], "metric: future observation start")
    if "comparisons" in packet:
        collection(packet["comparisons"], "comparisons", MAX_PAIRS)
        seen = set()
        for pair in packet["comparisons"]:
            collection(pair, "comparison pair", 2)
            require(len(pair) == 2, "comparison needs exactly two metric ids")
            for key in pair:
                identifier(key, "comparison metric id")
                require(key in indexes["metrics"], "comparison: unknown metric id")
            require(pair[0] != pair[1], "cannot compare a metric with itself")
            key = tuple(sorted(pair))
            require(key not in seen, "duplicate comparison pair")
            seen.add(key)
    return indexes


def normalized(packet):
    # Validation occurs before this JSON-only copy; source inputs are never mutated.
    result = json.loads(canonical(packet))
    for key in ("sources", "records", "metrics"):
        result[key].sort(key=lambda row: row["id"])
    for row in result["records"]:
        row["assessment_areas"].sort()
        row["local_unknowns"].sort()
        row["source_refs"].sort(key=lambda ref: (ref["source_id"], ref["locator"]))
    for row in result["metrics"]:
        row["source_refs"].sort(key=lambda ref: (ref["source_id"], ref["locator"]))
        if row["exclusions"] is not None:
            row["exclusions"].sort()
    if "comparisons" in result:
        result["comparisons"] = sorted(sorted(pair) for pair in result["comparisons"])
    return result


def metric_context(metric, records):
    fields = [field for field in MATCH_FIELDS if field not in ("metric_key", "kind")]
    fields += ["value", "sample_size"]
    if metric["kind"] in ("ratio", "rate"):
        fields += ["numerator_definition", "denominator_definition", "denominator_count"]
    missing = sorted(field for field in fields if metric[field] is None)
    notes = []
    if metric["sample_size"] == 0:
        notes.append("zero observed sample")
    if metric["kind"] in ("ratio", "rate") and metric["denominator_count"] == 0:
        notes.append("zero denominator")
    if records[metric["record_id"]]["evidence_kind"] != "measured_outcome":
        notes.append("supporting record is not a measured outcome")
    return {"metric_id": metric["id"], "status": "NEEDS_CONTEXT" if missing or notes else "CONTEXT_RECORDED",
            "missing": missing, "notes": notes}


def compare(left, right, records):
    missing, different, notes = [], [], []
    contexts = [metric_context(row, records) for row in (left, right)]
    for context in contexts:
        missing.extend(f"{context['metric_id']}.{field}" for field in context["missing"])
        notes.extend(f"{context['metric_id']}: {note}" for note in context["notes"])
    fields = list(MATCH_FIELDS)
    if left["kind"] in ("ratio", "rate") or right["kind"] in ("ratio", "rate"):
        fields += ["numerator_definition", "denominator_definition"]
    for field in fields:
        a, b = left[field], right[field]
        if a is not None and b is not None and a != b:
            different.append(field)
    if left["sample_size"] is not None and right["sample_size"] is not None and left["sample_size"] != right["sample_size"]:
        notes.append("sample sizes differ; precision and representativeness need review")
    if different:
        status = "CONTEXT_DIFFERS"
    elif any(c["status"] == "NEEDS_CONTEXT" for c in contexts):
        status = "NEEDS_CONTEXT"
    else:
        status = "ALIGNED_METADATA_REVIEW_REQUIRED"
    return {"left": left["id"], "right": right["id"], "status": status,
            "missing": sorted(missing), "different": sorted(different), "notes": sorted(notes)}


def compile_packet(packet):
    validate(packet)
    packet = normalized(packet)
    indexes = {key: {row["id"]: row for row in packet[key]}
               for key in ("sources", "records", "metrics")}
    pairs = packet.get("comparisons")
    if pairs is None:
        groups = {}
        for row in packet["metrics"]:
            groups.setdefault(row["metric_key"], []).append(row["id"])
        require(sum(len(g) * (len(g) - 1) // 2 for g in groups.values()) <= MAX_PAIRS,
                "too many candidate pairs; supply an explicit comparisons list <=2000")
        pairs = sorted(pair for group in groups.values() for pair in itertools.combinations(group, 2))
    comparisons = [compare(indexes["metrics"][a], indexes["metrics"][b], indexes["records"])
                   for a, b in pairs]
    coverage = {area: dict(sorted(Counter(row["evidence_kind"] for row in packet["records"]
                                        if area in row["assessment_areas"]).items())) for area in AREAS}
    warnings = []
    for source in packet["sources"]:
        if source["version"] is None:
            warnings.append(f"{source['id']}: version not recorded")
        if source["published_on"] is None:
            warnings.append(f"{source['id']}: publication/version date not recorded")
        elif source["published_on"] > source["accessed_on"]:
            warnings.append(f"{source['id']}: publication date follows access date; reconcile source version")
    return {"report_kind": "PEER_CONTEXT_NOT_LOCAL_ASSESSMENT", "schema_version": "1.0",
            "method": "metadata_screen_v1_not_statistical_validation",
            "source_verification": "NOT_PERFORMED", "mode": packet["mode"], "as_of": packet["as_of"],
            "input_sha256": hashlib.sha256(canonical(packet).encode("utf-8")).hexdigest(),
            "sources": packet["sources"], "records": packet["records"], "metrics": packet["metrics"],
            "comparisons": comparisons,
            "metric_context": [metric_context(row, indexes["records"]) for row in packet["metrics"]],
            "coverage": coverage, "warnings": sorted(warnings),
            "limitations": ["Source metadata is supplied by the researcher; no URL was fetched or authenticated.",
                            "Aligned metadata does not establish statistical comparability or local practice.",
                            "No maturity score, percentile, procurement recommendation or assessment finding is generated."]}


def md(value):
    if value is None:
        return "UNKNOWN"
    value = html.escape(str(value), quote=True).replace("\n", " ").replace("\r", " ").replace("\t", " ")
    for char in "\\`|[]!*_#":
        value = value.replace(char, f"&#{ord(char)};")
    return value


def render_markdown(report):
    lines = ["# Peer evidence — metadata comparability screen", "",
             f"**{report['mode']} · not a local assessment finding**", "",
             f"As of: {report['as_of']}  ", f"Input SHA-256: `{report['input_sha256']}`", "",
             "The digest identifies supplied input, not source authenticity. All comparisons require analyst judgment.", "",
             "## Comparison candidates", "", "| Left | Right | Status | Missing | Different | Notes |",
             "|---|---|---|---|---|---|"]
    for row in report["comparisons"]:
        lines.append("| " + " | ".join(md("; ".join(row[k]) if isinstance(row[k], list) else row[k])
                     for k in ("left", "right", "status", "missing", "different", "notes")) + " |")
    if not report["comparisons"]:
        lines += ["", "No metric pairs were selected. This does not establish comparability."]
    lines += ["", "## Metric register", "", "| Metric | Record | Value | Unit | Period | Context | Missing | Notes |",
              "|---|---|---|---|---|---|---|---|"]
    contexts = {row["metric_id"]: row for row in report["metric_context"]}
    for row in report["metrics"]:
        context = contexts[row["id"]]
        values = [row["id"], row["record_id"], row["value"], row["unit"],
                  f"{row['period_start'] or 'UNKNOWN'} / {row['period_end'] or 'UNKNOWN'}",
                  context["status"], "; ".join(context["missing"]), "; ".join(context["notes"])]
        lines.append("| " + " | ".join(md(value) for value in values) + " |")
    lines += ["", "Exact metric locators are retained in metrics.csv and report.json.", "", "## Evidence register", ""]
    sources = {s["id"]: s for s in report["sources"]}
    for row in report["records"]:
        lines += [f"### {md(row['id'])}: {md(row['institution'])}", "",
                  f"Kind: **{md(row['evidence_kind'])}**. Service: {md(row['service_context'])}.", "",
                  md(row["statement"]), "", f"Proposed transfer: {md(row['transfer_notes'])}", "",
                  "Local unknowns: " + ("; ".join(md(x) for x in row["local_unknowns"]) or "None recorded; not proof that none exist."), ""]
        for ref in row["source_refs"]:
            source = sources[ref["source_id"]]
            lines.append(f"Source {md(source['id'])}: {md(source['title'])}; {md(source['publisher'])}; "
                         f"clause {md(ref['locator'])}; version {md(source['version'])}; published {md(source['published_on'])}; "
                         f"accessed {source['accessed_on']}; {md(source['url'])}")
        lines.append("")
    lines += ["## Limits and source notes", ""]
    lines += ["- " + md(line) for line in report["limitations"] + report["warnings"]]
    return "\n".join(lines) + "\n"


def csv_text(rows, fields):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(fields)
    for row in rows:
        values = []
        for key in fields:
            value = row.get(key)
            value = "" if value is None else canonical(value) if isinstance(value, (dict, list)) else str(value)
            # Treat researcher-controlled cells as text in spreadsheet programs.
            if value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return stream.getvalue()


def bundle(report):
    return {"report.json": json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
            "peer-evidence.md": render_markdown(report),
            "sources.csv": csv_text(report["sources"], SOURCE_KEYS),
            "records.csv": csv_text(report["records"], RECORD_KEYS),
            "metrics.csv": csv_text(report["metrics"], METRIC_KEYS),
            "comparisons.csv": csv_text(report["comparisons"], ["left", "right", "status", "missing", "different", "notes"]),
            "metric-context.csv": csv_text(report["metric_context"], ["metric_id", "status", "missing", "notes"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet", type=Path)
    parser.add_argument("--out", type=Path, help="new output directory; existing directories are never overwritten")
    args = parser.parse_args(argv)
    try:
        with args.packet.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        report = compile_packet(loads(raw))
        output = bundle(report)
        if args.out is not None:
            args.out.mkdir(parents=False, exist_ok=False)
            for name, content in output.items():
                (args.out / name).write_text(content, encoding="utf-8", newline="\n")
            print(json.dumps({"output": str(args.out), "files": sorted(output), "input_sha256": report["input_sha256"]}))
        else:
            sys.stdout.write(output["report.json"])
        return 0
    except (InputError, OSError, ValueError, RecursionError) as exc:
        print(f"peer-evidence: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
