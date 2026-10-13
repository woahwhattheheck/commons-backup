#!/usr/bin/env python3
"""Read-only structural checks for the synthetic UIOWA-093 trace bundle.

PASS checks references and declarations, not whether evidence is authentic or
whether a sentence is justified by it. See VALIDATOR.md for the Markdown subset.
"""

import argparse
import csv
import json
import re
from pathlib import Path

TABLES = (
    ("evidence.csv", "evidence_id", ("locator",)),
    ("findings.csv", "finding_id", ("evidence_ids",)),
    ("recommendations.csv", "recommendation_id", ("linked_findings",)),
    ("trace-map.csv", "statement_id", ("report_location", "finding_ids",
                                         "recommendation_ids", "evidence_ids")),
)
REPORTS = ("executive-summary.md", "final-report.md")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]*\Z")
DECLARATION = re.compile(
    r"^\s{0,3}\*\*([A-Za-z0-9][A-Za-z0-9_.:-]*)"
    r"(?:\s*/\s*([A-Za-z0-9][A-Za-z0-9_.:-]*))?\.\*\*")
HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
CITATION = re.compile(r"\[([EFR]):([^\]\r\n]*)\]")


def load(path: Path) -> list[dict]:
    """Compatibility CSV reader; validate() additionally checks shape and IDs."""
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream, strict=True))


def split_ids(value: str) -> set[str]:
    return {part.strip() for part in (value or "").replace(",", ";").split(";")
            if part.strip()}


def _issue(items, code, file, row, record_id, field, detail, kind="trace"):
    items.append(dict(code=code, file=file, row=row, record_id=record_id,
                      field=field, detail=detail, kind=kind))


def _table(root, name, key, fields, issues):
    records = {}
    try:
        with (root / name).open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream, strict=True)
            header = reader.fieldnames or []
            if (not header or len(set(header)) != len(header)
                    or any(not field.strip() for field in header)
                    or not {key, *fields}.issubset(header)):
                _issue(issues, "CSV_HEADER", name, 1, "", "", "Missing, blank or repeated required/header names", "input")
                return records
            for row in reader:
                line = reader.line_num
                if None in row or any(value is None for value in row.values()):
                    _issue(issues, "CSV_WIDTH", name, line, "", "", "Row width differs from header", "input")
                    continue
                identifier = row[key]
                if not ID.fullmatch(identifier):
                    _issue(issues, "INVALID_ID", name, line, identifier, key, "ID must be a nonempty ASCII token without whitespace or link separators", "input")
                    continue
                if identifier in records:
                    _issue(issues, "DUPLICATE_ID", name, line, identifier, key, "ID repeats an earlier row", "input")
                    continue
                records[identifier] = (line, row)
    except (OSError, UnicodeError, csv.Error) as exc:
        # Use a stable class, not a host-specific absolute path in the report.
        _issue(issues, "INPUT_READ", name, 0, "", "", type(exc).__name__, "input")
    return records


def _uncomment(text, inside):
    output = []
    while text:
        marker = "-->" if inside else "<!--"
        pos = text.find(marker)
        if pos < 0:
            if not inside:
                output.append(text)
            break
        if not inside:
            output.append(text[:pos])
        text = text[pos + len(marker):]
        inside = not inside
    return "".join(output), inside


def _reports(root, statement_ids, issues):
    """Index native statement paragraphs once; ignore fenced/comment examples."""
    blocks, lines = {}, 0
    for name in REPORTS:
        active = None
        anchor, anchors, fence, inside_comment = "", set(), "", False
        try:
            with (root / name).open(encoding="utf-8-sig") as stream:
                for number, raw in enumerate(stream, 1):
                    lines += 1
                    if fence:
                        # Leading indentation is syntax, not disposable space.
                        # A tab/four-space false closer must remain code content.
                        closer = re.fullmatch(r" {0,3}(`{3,}|~{3,})[ \t]*", raw.rstrip("\r\n"))
                        if (closer and closer.group(1)[0] == fence[0]
                                and len(closer.group(1)) >= len(fence)):
                            fence = ""
                        continue
                    text, inside_comment = _uncomment(raw, inside_comment)
                    stripped = text.strip()
                    fenced = re.match(r"^ {0,3}(`{3,}|~{3,})", text)
                    if fenced:
                        active, fence = None, fenced.group(1)
                        continue
                    heading = HEADING.match(text)
                    if heading:
                        base = re.sub(r"[^\w\s-]", "", heading.group(1).lower())
                        base = re.sub(r"\s", "-", base)
                        anchor, suffix = base, 0
                        while anchor in anchors:
                            suffix += 1
                            anchor = f"{base}-{suffix}"
                        anchors.add(anchor)
                        active = None
                        continue
                    if not stripped:
                        active = None
                        continue
                    declaration = DECLARATION.match(text)
                    if declaration and (declaration.group(1) in statement_ids
                                        or declaration.group(1).startswith("S-")):
                        sid, rid = declaration.groups()
                        active = dict(file=name, row=number, location=name + "#" + anchor,
                                      refs={"E": set(), "F": set(), "R": set()})
                        if rid:
                            active["refs"]["R"].add(rid)
                        blocks.setdefault(sid, []).append(active)
                    if active:
                        for family, values in CITATION.findall(text):
                            active["refs"][family].update(split_ids(values))
        except (OSError, UnicodeError) as exc:
            _issue(issues, "INPUT_READ", name, 0, "", "", type(exc).__name__, "input")
    return blocks, lines


def validate(root: Path) -> dict:
    """Return deterministic JSON-shaped diagnostics without writing any file."""
    root, issues = Path(root), []
    tables = [_table(root, name, key, fields, issues) for name, key, fields in TABLES]
    evidence, findings, recommendations, trace = tables
    counts = dict(zip(("evidence", "findings", "recommendations", "statements"),
                      (len(table) for table in tables)))
    report_lines = 0
    if not issues:
        for name, table in (("evidence.csv", evidence), ("findings.csv", findings),
                            ("trace-map.csv", trace)):
            if not table:
                _issue(issues, "NO_RECORDS", name, 1, "", "", "No records to assess")
        for eid, (line, row) in evidence.items():
            if not row["locator"].strip():
                _issue(issues, "MISSING_LOCATOR", "evidence.csv", line, eid, "locator", "Source locator is empty")

        def links(table, filename, field, targets, required=True):
            result = {}
            for identifier, (line, row) in table.items():
                refs = split_ids(row[field])
                result[identifier] = refs
                if required and not refs:
                    _issue(issues, "MISSING_LINK", filename, line, identifier, field, "At least one reference is required")
                missing = refs - targets.keys()
                if missing:
                    _issue(issues, "BROKEN_LINK", filename, line, identifier, field, ", ".join(sorted(missing)))
            return result

        fe = links(findings, "findings.csv", "evidence_ids", evidence)
        rf = links(recommendations, "recommendations.csv", "linked_findings", findings)
        sf = links(trace, "trace-map.csv", "finding_ids", findings)
        sr = links(trace, "trace-map.csv", "recommendation_ids", recommendations, False)
        se = links(trace, "trace-map.csv", "evidence_ids", evidence)
        evidence_findings = {}
        for fid, refs in fe.items():
            for eid in refs:
                evidence_findings.setdefault(eid, set()).add(fid)
        for sid, (line, row) in trace.items():
            # Invert finding links once, rather than expanding every finding
            # again for every statement that cites it.
            unrelated = {eid for eid in se[sid] & evidence.keys()
                         if sf[sid].isdisjoint(evidence_findings.get(eid, set()))}
            if unrelated:
                _issue(issues, "DISCONNECTED_EVIDENCE", "trace-map.csv", line, sid, "evidence_ids", ", ".join(sorted(unrelated)))
            for rid in sorted(sr[sid] & recommendations.keys()):
                if not (rf[rid] & sf[sid]):
                    _issue(issues, "DISCONNECTED_RECOMMENDATION", "trace-map.csv", line, sid, "recommendation_ids", rid)

        blocks, report_lines = _reports(root, trace.keys(), issues)
        for sid, occurrences in blocks.items():
            if sid not in trace:
                for block in occurrences:
                    _issue(issues, "UNMAPPED_STATEMENT", block["file"], block["row"], sid, "", "Declaration has no trace-map row")
            if len(occurrences) > 1:
                for block in occurrences:
                    _issue(issues, "DUPLICATE_STATEMENT", block["file"], block["row"], sid, "", "Statement is declared more than once")
        for sid, (line, row) in trace.items():
            occurrences = blocks.get(sid, [])
            if not occurrences:
                _issue(issues, "MISSING_STATEMENT", "trace-map.csv", line, sid, "report_location", "No exact statement declaration in either report")
            for block in occurrences:
                if block["location"] != row["report_location"]:
                    _issue(issues, "WRONG_LOCATION", block["file"], block["row"], sid, "report_location", "Expected " + row["report_location"] + "; found " + block["location"])
                for family, expected in (("F", sf[sid]), ("R", sr[sid]), ("E", se[sid])):
                    actual = block["refs"][family]
                    if actual != expected:
                        detail = "missing=" + ",".join(sorted(expected - actual)) + "; extra=" + ",".join(sorted(actual - expected))
                        _issue(issues, "CITATION_MISMATCH", block["file"], block["row"], sid, family, detail)
    issues.sort(key=lambda item: (item["file"], item["row"], item["code"], item["record_id"], item["field"], item["detail"]))
    status = "INVALID_INPUT" if any(i["kind"] == "input" for i in issues) else ("INCOMPLETE" if issues else "PASS")
    return dict(schema_version=1, status=status, counts=counts, issues=issues,
                report_lines=report_lines,
                scope="STRUCTURAL_ONLY_NOT_EVIDENCE_AUTHENTICATION")


def main(root: Path, *, json_output=False) -> int:
    result = validate(root)
    if json_output:
        print(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2))
    elif result["status"] == "PASS":
        print(" ".join(f"{key}={value}" for key, value in result["counts"].items()))
        print("trace validation: PASS")
    else:
        for item in result["issues"]:
            print(f"{item['file']}:{item['row']} {item['code']} {item['record_id']} {item['field']}: {item['detail']}")
        print("trace validation: " + result["status"])
    return {"PASS": 0, "INCOMPLETE": 1, "INVALID_INPUT": 2}[result["status"]]


def cli(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--json", action="store_true", help="emit deterministic structured diagnostics")
    args = parser.parse_args(argv)
    return main(args.root, json_output=args.json)


if __name__ == "__main__":
    raise SystemExit(cli())
