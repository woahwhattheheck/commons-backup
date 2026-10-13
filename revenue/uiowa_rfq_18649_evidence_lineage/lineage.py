"""Offline evidence lineage review. No network, source mutations, or assessment scores."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from copy import deepcopy
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from typing import Any

SCHEMA = "uiowa.evidence-lineage.v1"
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
MAX_BYTES = 16 * 1024 * 1024


class InvalidInput(ValueError):
    """A supplied record cannot be interpreted without guessing."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise InvalidInput(message)


def text(value: Any, where: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{where}: nonempty text required")
    return value


def digest(value: Any, where: str) -> str:
    require(isinstance(value, str) and DIGEST.fullmatch(value) is not None,
            f"{where}: lowercase SHA-256 required")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise InvalidInput(f"non-finite JSON constant: {value}")


def load(path: Path) -> dict:
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    require(len(data) <= MAX_BYTES, f"{path}: JSON exceeds {MAX_BYTES} bytes")
    return json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                      parse_constant=_constant)


def encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def ref_key(record: dict) -> tuple[str, str]:
    return record["record_id"], record["sha256"]


def reference(record: dict) -> dict:
    return {key: record[key] for key in ("record_id", "sha256")}


def validate_manifest(value: Any) -> dict:
    require(isinstance(value, dict), "manifest: object required")
    require(value.get("schema") == SCHEMA, f"manifest.schema must be {SCHEMA}")
    text(value.get("collection_id"), "manifest.collection_id")
    require(type(value.get("synthetic")) is bool, "manifest.synthetic: boolean required")
    require(isinstance(value.get("records"), list), "manifest.records: list required")
    seen = set()
    for index, row in enumerate(value["records"]):
        where = f"records[{index}]"
        require(isinstance(row, dict), f"{where}: object required")
        for key in ("record_id", "document_id", "version", "title", "location"):
            text(row.get(key), f"{where}.{key}")
        digest(row.get("sha256"), f"{where}.sha256")
        require(row["record_id"] not in seen, f"duplicate record_id: {row['record_id']}")
        seen.add(row["record_id"])
        require(isinstance(row.get("metadata", {}), dict), f"{where}.metadata: object required")
        predecessors = row.get("supersedes", [])
        require(isinstance(predecessors, list), f"{where}.supersedes: list required")
        for predecessor in predecessors:
            require(isinstance(predecessor, dict), f"{where}.supersedes: reference object required")
            text(predecessor.get("record_id"), f"{where}.supersedes.record_id")
            digest(predecessor.get("sha256"), f"{where}.supersedes.sha256")
        require(len({ref_key(p) for p in predecessors}) == len(predecessors),
                f"{where}: duplicate predecessor")
    # Check JSON compatibility even for direct library callers; preserve all metadata.
    encoded(value)
    return deepcopy(value)


def snapshot(catalog: Any, root: Path) -> dict:
    """Hash explicit regular files under root; no discovery, downloads, or writes."""
    require(isinstance(catalog, dict) and isinstance(catalog.get("records"), list),
            "catalog: object with records required")
    root = root.resolve(strict=True)
    require(root.is_dir(), "catalog root must be a directory")
    output = deepcopy(catalog)
    for index, row in enumerate(output["records"]):
        require(isinstance(row, dict), f"catalog.records[{index}]: object required")
        location = text(row.get("location"), "catalog.location")
        relative = Path(location)
        require(not relative.is_absolute() and ".." not in relative.parts,
                f"catalog location must be root-relative: {location}")
        path = root / relative
        current = root
        for part in relative.parts:
            current = current / part
            require(not current.is_symlink(), f"catalog symlink not supported: {location}")
        require(path.resolve(strict=True).is_relative_to(root), "catalog path escapes root")
        require(path.is_file(), f"catalog input is not a regular file: {location}")
        with path.open("rb") as stream:
            import os
            before = os.fstat(stream.fileno())
            data = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
        fingerprint = lambda stat: (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        require(fingerprint(before) == fingerprint(after) == fingerprint(path.stat()),
                f"catalog file changed during snapshot: {location}")
        require(len(data) <= MAX_BYTES, f"catalog file exceeds {MAX_BYTES} bytes: {location}")
        calculated = hashlib.sha256(data).hexdigest()
        require("sha256" not in row or row["sha256"] == calculated,
                f"catalog declared digest differs from bytes: {location}")
        row["sha256"] = calculated
    output["hash_basis"] = "FILES_READ_AT_SNAPSHOT_NOT_AUTHENTICATED"
    return validate_manifest(output)


def from_authority(bundle: Any, *, synthetic: bool) -> dict:
    """Adapt parent v2 source metadata, never its maturity, confidence, or authority."""
    require(isinstance(bundle, dict), "authority bundle: object required")
    require(bundle.get("schema") == "uiowa-rfq18649-evidence-authority/v2",
            "only the parent evidence-authority/v2 schema is supported")
    generation = text(bundle.get("generation"), "authority.generation")
    require(isinstance(bundle.get("sources"), list), "authority.sources: list required")
    rows = []
    for source in bundle["sources"]:
        require(isinstance(source, dict), "authority source: object required")
        sid = text(source.get("source_id"), "authority.source_id")
        metadata = {key: text(source.get(key), "authority." + key) for key in
                    ("solicitation_id", "prime_candidate", "group", "dimension",
                     "authority_generation", "observed_at", "evidence_kind")}
        require(metadata["authority_generation"] == generation, "source/bundle generation mismatch")
        for key in ("solicitation_id", "prime_candidate"):
            require(metadata[key] == bundle.get(key), f"source/bundle {key} mismatch")
        # A compound identity keeps equal source IDs in different scopes distinct.
        identity = json.dumps([metadata[k] for k in ("solicitation_id", "prime_candidate", "group", "dimension")]
                              + [sid], ensure_ascii=False, separators=(",", ":"))
        rows.append({"record_id": sid, "document_id": identity, "version": generation,
                     "title": sid, "location": text(source.get("source_ref"), "authority.source_ref"),
                     "sha256": digest(source.get("source_content_sha256"), "authority.source_content_sha256"),
                     "metadata": metadata})
    return validate_manifest({"schema": SCHEMA, "collection_id": generation, "synthetic": synthetic,
                              "hash_basis": "IMPORTED_SOURCE_ASSERTIONS_NOT_AUTHENTICATED",
                              "adapter": "parent-authority-v2-metadata-only",
                              "source_bundle_sha256": hashlib.sha256(encoded(bundle).encode()).hexdigest(),
                              "records": rows})


def _index(rows: list[dict], field: str) -> dict[Any, list[dict]]:
    result = defaultdict(list)
    for row in rows:
        result[row[field]].append(row)
    return result


def _title(value: str) -> str:
    return " ".join(value.casefold().split())


def _lineage(before: list[dict], after: list[dict]) -> tuple[dict, dict, list[dict]]:
    nodes = {}
    anomalies = []
    for row in before + after:
        key = ref_key(row)
        if key in nodes:
            require(nodes[key]["document_id"] == row["document_id"],
                    f"record/hash identity reused across documents: {key[0]}")
        nodes[key] = row
    edges = defaultdict(set)
    # Retain prior declared chains; do not infer edges from dates or labels.
    for row in before + after:
        for predecessor in row.get("supersedes", []):
            key = ref_key(predecessor)
            if key not in nodes:
                anomalies.append({"kind": "DANGLING_PREDECESSOR", "record_id": row["record_id"],
                                  "predecessor": deepcopy(predecessor)})
            elif nodes[key]["document_id"] != row["document_id"]:
                anomalies.append({"kind": "CROSS_DOCUMENT_PREDECESSOR", "record_id": row["record_id"],
                                  "predecessor": deepcopy(predecessor)})
            else:
                edges[key].add(ref_key(row))
    indegree = dict.fromkeys(nodes, 0)
    for targets in edges.values():
        for target in targets:
            indegree[target] += 1
    queue = deque(key for key, count in indegree.items() if count == 0)
    visited = 0
    while queue:
        visited += 1
        for target in edges.get(queue.popleft(), ()):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    require(visited == len(nodes), "declared predecessor graph contains a cycle")
    return nodes, edges, anomalies


def _descendants(start: tuple, edges: dict) -> set:
    reached = set()
    pending = list(edges.get(start, ()))
    while pending:
        key = pending.pop()
        if key not in reached:
            reached.add(key)
            pending.extend(edges.get(key, ()))
    return reached


def compare(before_value: Any, after_value: Any, findings_value: Any = None) -> dict:
    """Return a review aid; hash equality is not provenance or semantic equivalence."""
    before = validate_manifest(before_value)
    after = validate_manifest(after_value)
    old, new = before["records"], after["records"]
    old_ids = {row["record_id"]: row for row in old}
    old_hash = _index(old, "sha256")
    old_docs = _index(old, "document_id")
    old_titles = defaultdict(list)
    for row in old:
        old_titles[_title(row["title"])].append(row)
    new_docs = _index(new, "document_id")
    nodes, edges, anomalies = _lineage(old, new)
    all_versions = defaultdict(list)
    for row in old + new:
        all_versions[(row["document_id"], row["version"])].append(row)
    conflicts = set()
    for (document, version), rows in sorted(all_versions.items()):
        if len({row["sha256"] for row in rows}) > 1:
            conflicts.add((document, version))
            anomalies.append({"kind": "VERSION_LABEL_CONFLICT", "document_id": document,
                              "version": version, "references": sorted(
                                  {ref_key(row) for row in rows})})
    changes = []
    for row in sorted(new, key=lambda r: r["record_id"]):
        same_id = old_ids.get(row["record_id"])
        same_hash = old_hash.get(row["sha256"], [])
        same_doc = old_docs.get(row["document_id"], [])
        exact_doc = [r for r in same_hash if r["document_id"] == row["document_id"]]
        candidates = []
        if same_id and same_id["document_id"] != row["document_id"]:
            kind, candidates = "RECORD_ID_REUSED", [same_id]
        elif (row["document_id"], row["version"]) in conflicts:
            kind, candidates = "VERSION_LABEL_CONFLICT", same_doc
        elif same_id and same_id["sha256"] == row["sha256"]:
            kind = ("UNCHANGED" if same_id == row else
                    "RENAMED_EXACT_CONTENT" if same_id["location"] != row["location"] else "METADATA_CHANGED")
            candidates = [same_id]
        elif exact_doc:
            kind, candidates = "EXACT_CONTENT_COPY", exact_doc
        elif same_doc:
            kind, candidates = "CONTENT_CHANGED_REVIEW", same_doc
        elif same_hash:
            kind, candidates = "SAME_BYTES_DIFFERENT_DOCUMENT", same_hash
        else:
            candidates = old_titles.get(_title(row["title"]), [])
            kind = "TITLE_MATCH_DIFFERENT_CONTENT" if candidates else "ADDED"
        changes.append({"record_id": row["record_id"], "kind": kind,
                        "before_candidates": [reference(r) for r in sorted(candidates, key=ref_key)]})
    new_ids = {row["record_id"] for row in new}
    departures = [{"record_id": row["record_id"], "sha256": row["sha256"],
                   "status": "RECORD_ABSENT_FROM_AFTER"}
                  for row in sorted(old, key=lambda r: r["record_id"]) if row["record_id"] not in new_ids]
    duplicate_groups = []
    for sha, rows in sorted(_index(new, "sha256").items()):
        if len(rows) > 1:
            duplicate_groups.append({"sha256": sha, "record_ids": sorted(r["record_id"] for r in rows),
                                     "document_ids": sorted({r["document_id"] for r in rows})})
    findings = {"findings": []} if findings_value is None else deepcopy(findings_value)
    require(isinstance(findings, dict) and isinstance(findings.get("findings"), list),
            "findings: object with findings list required")
    new_keys = {ref_key(row) for row in new}
    impacts = []
    seen_findings = set()
    for finding in findings["findings"]:
        require(isinstance(finding, dict), "finding: object required")
        fid = text(finding.get("finding_id"), "finding.finding_id")
        require(fid not in seen_findings, f"duplicate finding_id: {fid}")
        seen_findings.add(fid)
        require(isinstance(finding.get("citations"), list), f"{fid}.citations: list required")
        if not finding["citations"]:
            impacts.append({"finding_id": fid, "status": "NO_CITATIONS_SUPPLIED"})
        for citation in finding["citations"]:
            require(isinstance(citation, dict), f"{fid}: citation object required")
            text(citation.get("record_id"), f"{fid}.record_id")
            digest(citation.get("sha256"), f"{fid}.sha256")
            text(citation.get("locator"), f"{fid}.locator")
            key = ref_key(citation)
            origin = nodes.get(key)
            retained, successors, terminal_keys, missing_terminals = [], [], [], []
            if origin is None:
                status = ("CITATION_DIGEST_MISMATCH" if any(r["record_id"] == citation["record_id"] for r in old + new)
                          else "UNKNOWN_CITATION")
            else:
                retained = [reference(r) for r in new_docs.get(origin["document_id"], [])
                            if r["sha256"] == origin["sha256"]]
                reached = _descendants(key, edges)
                # A declaration does not cease to exist because its terminal
                # record is omitted from the new export. Keep the entire known
                # frontier, then distinguish presence from lineage.
                terminal_keys = sorted(k for k in reached if not edges.get(k))
                present_terminals = [k for k in terminal_keys if k in new_keys]
                missing_terminals = [k for k in terminal_keys if k not in new_keys]
                successors = [reference(nodes[k]) for k in present_terminals]
                if len(terminal_keys) > 1:
                    status = "BRANCHED_SUCCESSION_REVIEW"
                elif missing_terminals:
                    status = "DECLARED_SUCCESSOR_MISSING_REVIEW"
                elif present_terminals:
                    status = "DECLARED_SUPERSEDED_REVIEW"
                elif retained:
                    status = "EXACT_CONTENT_RETAINED"
                elif new_docs.get(origin["document_id"]):
                    status = "CONTENT_CHANGED_REVIEW"
                else:
                    status = "MISSING_FROM_AFTER"
            impacts.append({"finding_id": fid, "citation": deepcopy(citation), "status": status,
                            "retained_exact_copies": sorted(retained, key=ref_key),
                            "declared_successors": successors, "locator_validation": "NOT_PERFORMED"})
            if missing_terminals:
                # Existing consumers keep the supplied-after subset in
                # declared_successors. Additional fields expose omitted tips,
                # without relabeling absent records as present or deleted.
                impacts[-1]["missing_declared_successors"] = [reference(nodes[k]) for k in missing_terminals]
                impacts[-1]["declared_terminal_successors"] = [
                    {**reference(nodes[k]), "present_in_after": k in new_keys} for k in terminal_keys]
    return {"schema": SCHEMA, "status": "DRAFT_NON_AUTHORITATIVE", "synthetic": before["synthetic"] and after["synthetic"],
            "limitations": ["Hashes are supplied manifest assertions unless separately checked against source bytes.",
                            "Version strings and titles never establish ordering or semantic equivalence.",
                            "Supersession is a supplied declaration, not an authenticated approval.",
                            "No maturity, compliance, approval, submission or payment conclusion is produced."],
            "before": before, "after": after, "input_findings": findings, "changes": changes,
            "duplicates_after": duplicate_groups, "departures": departures, "anomalies": anomalies,
            "input_sha256": {"before": hashlib.sha256(encoded(before).encode()).hexdigest(),
                             "after": hashlib.sha256(encoded(after).encode()).hexdigest(),
                             "findings": hashlib.sha256(encoded(findings).encode()).hexdigest()},
            "finding_impacts": sorted(impacts, key=lambda r: (r["finding_id"], encoded(r))),
            "summary": {"before_records": len(old), "after_records": len(new),
                        "change_counts": dict(sorted(Counter(r["kind"] for r in changes).items())),
                        "finding_status_counts": dict(sorted(Counter(r["status"] for r in impacts).items()))}}


def markdown(report: dict) -> str:
    def cell(value: Any) -> str:
        return html.escape(str(value)).replace("|", "&#124;").replace("\n", " ").replace("\r", " ")
    lines = ["# Evidence lineage review", "", "**DRAFT_NON_AUTHORITATIVE**", "",
             "Synthetic collections: " + str(report["synthetic"]).lower(), "",
             "## Collection changes", "", "| Record | Classification | Prior records |",
             "| --- | --- | --- |"]
    for row in report["changes"]:
        prior = ", ".join(r["record_id"] for r in row["before_candidates"]) or "None"
        lines.append(f"| {cell(row['record_id'])} | {cell(row['kind'])} | {cell(prior)} |")
    lines += ["", "## Records absent from after collection", ""]
    lines += ["- " + cell(r["record_id"]) for r in report["departures"]] or ["None."]
    lines += ["", "## Finding follow-up queue", "", "| Finding | Cited record / locator | Status | Declared successors |",
              "| --- | --- | --- | --- |"]
    for row in report["finding_impacts"]:
        citation = row.get("citation", {})
        cited = f"{citation.get('record_id', 'None')} / {citation.get('locator', 'None')}"
        successors = ", ".join(r["record_id"] for r in row.get("declared_successors", [])) or "None"
        lines.append(f"| {cell(row['finding_id'])} | {cell(cited)} | {cell(row['status'])} | {cell(successors)} |")
    missing_rows = [r for r in report["finding_impacts"] if r.get("missing_declared_successors")]
    if missing_rows:
        lines += ["", "## Declared successor records absent from after collection", "",
                  "Omission is not deletion or approval. The full known branch remains unresolved.", "",
                  "| Finding / cited record | Declared terminal record | SHA-256 | In after collection |",
                  "| --- | --- | --- | --- |"]
        for impact in missing_rows:
            for terminal in impact["declared_terminal_successors"]:
                source = impact["finding_id"] + " / " + impact["citation"]["record_id"]
                present = "Yes" if terminal["present_in_after"] else "No - request the record or reconcile its omission"
                lines.append(f"| {cell(source)} | {cell(terminal['record_id'])} | {cell(terminal['sha256'])} | {present} |")
    lines += ["", "## Duplicate byte groups", ""]
    for row in report["duplicates_after"]:
        lines.append(f"- `{row['sha256']}`: " + cell(", ".join(row["record_ids"])))
    if not report["duplicates_after"]:
        lines.append("None observed in the supplied after manifest.")
    lines += ["", "## Record anomalies", ""]
    lines += ["- " + cell(encoded(row).strip()) for row in report["anomalies"]] or ["None observed."]
    lines += ["", "## Interpretation limits", ""] + ["- " + line for line in report["limitations"]]
    lines += ["", "The JSON report retains both complete manifests and the original citation records.",
              "Locators are retained verbatim, not revalidated against changed documents.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    snap = commands.add_parser("snapshot", help="hash catalog files; emit manifest to stdout")
    snap.add_argument("catalog", type=Path)
    snap.add_argument("root", type=Path)
    native = commands.add_parser("from-authority", help="adapt parent v2 source metadata only")
    native.add_argument("bundle", type=Path)
    native.add_argument("--data-kind", required=True, choices=("synthetic", "private"))
    diff = commands.add_parser("compare", help="compare manifests; emit review report to stdout")
    diff.add_argument("before", type=Path)
    diff.add_argument("after", type=Path)
    diff.add_argument("--findings", type=Path)
    diff.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        if args.command == "snapshot":
            output = encoded(snapshot(load(args.catalog), args.root))
        elif args.command == "from-authority":
            output = encoded(from_authority(load(args.bundle), synthetic=args.data_kind == "synthetic"))
        else:
            report = compare(load(args.before), load(args.after), load(args.findings) if args.findings else None)
            output = markdown(report) if args.format == "markdown" else encoded(report)
        sys.stdout.write(output)
        return 0
    except (ValueError, OSError, UnicodeError, TypeError) as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
