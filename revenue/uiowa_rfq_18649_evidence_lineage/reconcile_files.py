"""Build a complete offline evidence-lineage bundle from CSV source registers."""
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

import lineage

REQUIRED = {"record_id", "document_id", "version", "title", "location"}
OPTIONAL = {"sha256", "metadata_json", "supersedes_record_id", "supersedes_sha256"}
LINK_FIELDS = {"record_id", "predecessor_record_id", "predecessor_sha256"}
FINDING_FIELDS = {"finding_id", "record_id", "sha256", "locator"}
MAX_ROWS = 10_000


def read_csv(path: Path, required: set[str], optional: set[str] | None = None,
             *, metadata_columns: bool = False) -> tuple[list[dict[str, str]], str]:
    """Read bounded UTF-8 CSV without dropping extra cells or duplicate headers."""
    lineage.require(path.is_file() and not path.is_symlink(),
                    f"{path}: a regular, non-symlink CSV file is required")
    with path.open("rb") as stream:
        lineage.require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode),
                        f"{path}: not a regular file")
        data = stream.read(lineage.MAX_BYTES + 1)
    lineage.require(len(data) <= lineage.MAX_BYTES,
                    f"{path}: CSV exceeds {lineage.MAX_BYTES} bytes")
    reader = csv.reader(io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True)
    header = next(reader, None)
    lineage.require(bool(header), f"{path}: CSV header required")
    lineage.require(len(header) == len(set(header)), f"{path}: duplicate CSV header")
    lineage.require(required <= set(header),
                    f"{path}: missing columns: {', '.join(sorted(required - set(header)))}")
    unknown = set(header) - required - (optional or set())
    if metadata_columns:
        unknown = {name for name in unknown if not (name.startswith("metadata.") and len(name) > 9)}
    lineage.require(not unknown, f"{path}: unknown columns: {', '.join(sorted(unknown))}")
    rows = []
    for cells in reader:
        # Blank physical lines and malformed rows are not silently skipped.
        lineage.require(len(cells) == len(header),
                        f"{path}: line {reader.line_num}: expected {len(header)} cells, got {len(cells)}")
        lineage.require(len(rows) < MAX_ROWS, f"{path}: more than {MAX_ROWS} rows")
        rows.append(dict(zip(header, cells)))
    return rows, hashlib.sha256(data).hexdigest()


def catalog_from_csv(path: Path, collection_id: str, synthetic: bool,
                     links_path: Path | None = None) -> dict[str, Any]:
    rows, register_digest = read_csv(path, REQUIRED, OPTIONAL, metadata_columns=True)
    records = []
    by_id = {}
    for number, row in enumerate(rows, 2):
        where = f"{path}: record row {number}"
        record = {key: lineage.text(row[key], where + "." + key) for key in REQUIRED}
        rid = record["record_id"]
        lineage.require(rid not in by_id, f"{where}: duplicate record_id: {rid}")
        if row.get("sha256"):
            record["sha256"] = lineage.digest(row["sha256"], where + ".sha256")
        metadata = {}
        if row.get("metadata_json"):
            metadata = json.loads(row["metadata_json"], object_pairs_hook=lineage._pairs,
                                  parse_constant=lineage._constant)
            lineage.require(isinstance(metadata, dict), where + ": metadata_json must be an object")
        for column, value in row.items():
            if column.startswith("metadata."):
                key = column[9:]
                lineage.require(key not in metadata, f"{where}: duplicate metadata key: {key}")
                metadata[key] = value
        if metadata:
            record["metadata"] = metadata
        predecessor_id = row.get("supersedes_record_id", "")
        predecessor_sha = row.get("supersedes_sha256", "")
        lineage.require(bool(predecessor_id) == bool(predecessor_sha),
                        where + ": supersedes_record_id and supersedes_sha256 must be supplied together")
        if predecessor_id:
            record["supersedes"] = [{
                "record_id": lineage.text(predecessor_id, where + ".supersedes_record_id"),
                "sha256": lineage.digest(predecessor_sha, where + ".supersedes_sha256"),
            }]
        records.append(record)
        by_id[rid] = record
    intake = {"register_sha256": register_digest, "format": "csv-explicit-identities/v1"}
    if links_path:
        links, links_digest = read_csv(links_path, LINK_FIELDS)
        intake["links_sha256"] = links_digest
        for number, row in enumerate(links, 2):
            where = f"{links_path}: link row {number}"
            lineage.require(row["record_id"] in by_id,
                            f"{where}: successor record is absent from this register: {row['record_id']}")
            by_id[row["record_id"]].setdefault("supersedes", []).append({
                "record_id": lineage.text(row["predecessor_record_id"], where + ".predecessor_record_id"),
                "sha256": lineage.digest(row["predecessor_sha256"], where + ".predecessor_sha256"),
            })
    return {"schema": lineage.SCHEMA, "collection_id": lineage.text(collection_id, "collection_id"),
            "synthetic": synthetic, "intake": intake, "records": records}


def findings_from_csv(path: Path) -> dict[str, Any]:
    rows, register_digest = read_csv(path, FINDING_FIELDS)
    findings: dict[str, dict[str, Any]] = {}
    empty_ids = set()
    seen_citations: set[tuple[str, str, str, str]] = set()
    for number, row in enumerate(rows, 2):
        where = f"{path}: citation row {number}"
        fid = lineage.text(row["finding_id"], where + ".finding_id")
        fields = (row["record_id"], row["sha256"], row["locator"])
        finding = findings.setdefault(fid, {"finding_id": fid, "citations": []})
        if not any(fields):
            lineage.require(fid not in empty_ids and not finding["citations"],
                            f"{where}: duplicate or mixed no-citation declaration for {fid}")
            empty_ids.add(fid)
            continue
        lineage.require(fid not in empty_ids and all(fields),
                        f"{where}: citation requires record_id, sha256 and locator; do not mix with a blank declaration")
        key = (fid, *fields)
        lineage.require(key not in seen_citations, f"{where}: duplicate citation")
        seen_citations.add(key)
        finding["citations"].append({
            "record_id": lineage.text(fields[0], where + ".record_id"),
            "sha256": lineage.digest(fields[1], where + ".sha256"),
            "locator": lineage.text(fields[2], where + ".locator"),
        })
    return {"findings": list(findings.values()), "register_sha256": register_digest}


def portable_html(report: dict[str, Any]) -> str:
    """Render arbitrary real/private reports, not the seven-case synthetic reader."""
    def escaped(value: Any) -> str:
        return html.escape(str(value), quote=True)

    def table(headers: list[str], rows: list[list[Any]]) -> str:
        if not rows:
            return "<p>None in the supplied collections.</p>"
        head = "".join("<th scope=\"col\">" + escaped(value) + "</th>" for value in headers)
        body = "".join("<tr>" + "".join("<td>" + escaped(cell) + "</td>" for cell in row) + "</tr>"
                       for row in rows)
        return '<div class="table"><table><thead><tr>' + head + "</tr></thead><tbody>" + body + "</tbody></table></div>"

    def refs(rows: list[dict[str, Any]]) -> str:
        return "\n".join(row["record_id"] + " / " + row["sha256"] for row in rows) or "None"

    classification = "SYNTHETIC" if report["synthetic"] else "PRIVATE — keep on your approved evidence surface"
    summary = report["summary"]
    sections = [
        '<!doctype html><html lang="en"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
        '<title>Evidence lineage review</title>',
        '<style>body{font:16px/1.55 system-ui,sans-serif;max-width:1100px;margin:auto;padding:2rem}'
        'h1{line-height:1.15}.notice{border:2px solid;padding:1rem}.table{overflow:auto}'
        'table{border-collapse:collapse;width:100%;margin:1rem 0}th,td{border:1px solid;padding:.6rem;text-align:left;vertical-align:top}'
        'td{white-space:pre-wrap;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
        'details{margin:1rem 0}summary{cursor:pointer}a{overflow-wrap:anywhere}'
        '@media print{body{padding:0;font-size:10pt}.table{overflow:visible}tr{break-inside:avoid}}</style>',
        '<h1>Evidence lineage review</h1><div class="notice"><strong>DRAFT_NON_AUTHORITATIVE</strong><br>',
        escaped(classification),
        '<p>Processing succeeded. This is not a pass, approval or assessment score. '
        'Absent records are not proven deleted. Citation locators have not been revalidated.</p></div>',
        '<p>' + escaped(report["before"]["collection_id"]) + ' → ' + escaped(report["after"]["collection_id"]) + '</p>',
        '<p>' + str(summary["before_records"]) + ' before records; ' + str(summary["after_records"]) +
        ' after records; ' + str(len(report["finding_impacts"])) + ' citation-review rows (not unique findings).</p>',
        '<nav><a href="review.json">Complete JSON</a> · <a href="review.md">Markdown</a> · '
        '<a href="before.json">Before manifest</a> · <a href="after.json">After manifest</a> · '
        '<a href="findings.json">Original findings</a></nav>',
        '<h2>Collection changes</h2>',
        table(["Record", "Classification", "Prior record / SHA-256"],
              [[row["record_id"], row["kind"], refs(row["before_candidates"])] for row in report["changes"]]),
        '<h2>Finding follow-up queue</h2>',
        table(["Finding", "Original citation / SHA-256 / locator", "Status", "Supplied successors", "Missing declared successors"],
              [[row["finding_id"], "\n".join(str(row.get("citation", {}).get(key, "None"))
                                            for key in ("record_id", "sha256", "locator")),
                row["status"], refs(row.get("declared_successors", [])),
                refs(row.get("missing_declared_successors", []))] for row in report["finding_impacts"]]),
        '<h2>Records absent from the after collection</h2>',
        table(["Record", "SHA-256", "Status"], [[row["record_id"], row["sha256"], row["status"]]
                                                  for row in report["departures"]]),
        '<h2>Duplicate byte groups</h2>',
        table(["SHA-256", "Records", "Logical documents"],
              [[row["sha256"], "\n".join(row["record_ids"]), "\n".join(row["document_ids"])]
               for row in report["duplicates_after"]]),
        '<h2>Record anomalies</h2><pre>' + escaped(lineage.encoded(report["anomalies"])) + '</pre>',
        '<h2>Interpretation limits</h2><ul>' + ''.join('<li>' + escaped(value) + '</li>'
                                                     for value in report["limitations"]) + '</ul>',
        '<p>Source files are not copied into this bundle. Register metadata and findings are retained and may be private. '
        'No source authenticity, source-text extraction, semantic comparison or directory completeness is claimed.</p>',
        '<details><summary>Complete report, including retained metadata</summary><pre>' +
        escaped(lineage.encoded(report)) + '</pre></details></html>\n',
    ]
    return "\n".join(sections)


def write_bundle(output: Path, report: dict[str, Any]) -> None:
    # Render before publishing so malformed inputs never create a partial bundle.
    artifacts = {
        "before.json": lineage.encoded(report["before"]),
        "after.json": lineage.encoded(report["after"]),
        "findings.json": lineage.encoded(report["input_findings"]),
        "review.json": lineage.encoded(report),
        "review.md": lineage.markdown(report),
        "review.html": portable_html(report),
    }
    output.mkdir(mode=0o700)  # Atomic create-only; an existing or dangling path fails.
    try:
        for name, text in artifacts.items():
            fd = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(text.encode("utf-8"))
    except OSError as exc:
        raise OSError(f"Incomplete bundle in {output}; preserve it and choose a new output directory: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for side in ("before", "after"):
        parser.add_argument(f"--{side}-csv", type=Path, required=True)
        parser.add_argument(f"--{side}-root", type=Path, required=True)
        parser.add_argument(f"--{side}-id", required=True)
        parser.add_argument(f"--{side}-links", type=Path)
    findings = parser.add_mutually_exclusive_group()
    findings.add_argument("--findings", type=Path, help="Existing native findings JSON")
    findings.add_argument("--findings-csv", type=Path, help="One exact citation per CSV row")
    parser.add_argument("--data-kind", choices=("private", "synthetic"), default="private")
    parser.add_argument("--output", type=Path, required=True, help="New directory in an existing parent")
    args = parser.parse_args(argv)
    try:
        lineage.require(not os.path.lexists(args.output), "Output already exists; choose a new directory")
        manifests = []
        for side in ("before", "after"):
            catalog = catalog_from_csv(getattr(args, side + "_csv"), getattr(args, side + "_id"),
                                       args.data_kind == "synthetic", getattr(args, side + "_links"))
            manifests.append(lineage.snapshot(catalog, getattr(args, side + "_root")))
        supplied_findings = (findings_from_csv(args.findings_csv) if args.findings_csv else
                             lineage.load(args.findings) if args.findings else None)
        report = lineage.compare(*manifests, supplied_findings)
        write_bundle(args.output, report)
        print(lineage.encoded({"output": str(args.output), "reader": str(args.output / "review.html"),
                               "data_kind": args.data_kind, "status": report["status"],
                               "summary": report["summary"]}), end="")
        return 0
    except (ValueError, OSError, UnicodeError, TypeError, csv.Error, RecursionError) as exc:
        print(f"Reconciliation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
