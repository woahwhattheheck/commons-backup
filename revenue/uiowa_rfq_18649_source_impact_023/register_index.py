"""Build the UIOWA-023 documentary dependency index; no source comparison or scoring."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

REVISION = "809ff46d4a828b2fdb0ea72dd135b1dd5301b926"
REGISTER = "revenue/uiowa_rfq_18649_workshare/methodology/23-synthetic-evidence-register.csv"
REGISTER_BLOB = "fc2ef567e3f9b3f5a5031c74994e62c62b1d9c7e"
METHOD = "revenue/uiowa_rfq_18649_workshare/methodology/23-evidence-confidence.md"
METHOD_BLOB = "864bd6ed9a99d2ed9e0df0ec3e62fca8e77c3e79"
NAMESPACE = "uiowa-023-register/v1"
REQUIRED = {"evidence_id", "observation_id", "finding_id", "claim", "scope_limit", "source_ref", "captured_at"}


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def build_index(data: bytes, *, revision: str = REVISION, expected_blob: str | None = REGISTER_BLOB) -> dict:
    """Read a synthetic CSV without collapsing rows; unknown columns remain documentary payload."""
    require(isinstance(revision, str) and bool(revision.strip()), "revision must be explicit")
    observed = git_blob(data)
    if expected_blob is not None:
        require(observed == expected_blob, f"register drift: expected {expected_blob}; observed {observed}")
    reader = csv.reader(io.StringIO(data.decode("utf-8"), newline=""), strict=True)
    headers = next(reader, None)
    require(headers is not None and REQUIRED <= set(headers), "register: required headers missing")
    require(len(headers) == len(set(headers)), "register: duplicate header")
    prefix = f"https://github.com/woahwhattheheck/commons/blob/{revision}/"
    sources, observations, findings, records = {}, {}, {}, []
    previous_line = reader.line_num
    for values in reader:
        first_line, last_line = previous_line + 1, reader.line_num
        previous_line = last_line
        if not values:
            continue
        require(len(values) == len(headers), "register: malformed row width")
        row = dict(zip(headers, values))
        require(all(isinstance(row[k], str) and bool(row[k].strip()) for k in REQUIRED), "register: required value missing")
        sid, oid, fid = row["evidence_id"], row["observation_id"], row["finding_id"]
        require(sid.startswith("EV-SYN-") and oid.startswith("OBS-SYN-") and fid.startswith("FND-SYN-"),
                "adapter accepts explicit EV-SYN/OBS-SYN/FND-SYN identifiers only")
        require(sid not in sources, f"duplicate evidence ID: {sid}")
        locator = prefix + REGISTER + f"#L{first_line}-L{last_line}"
        sources[sid] = {"source_id": sid, "locator": locator, "source_ref": row["source_ref"],
                        "source_captured_at": row["captured_at"], "representation": "register_record",
                        "underlying_content": "NOT_FETCHED", "register_blob": observed}
        records.append({"source_id": sid, "locator": locator, "fields": dict(row)})
        observations.setdefault(oid, []).append(sid)
        findings.setdefault(fid, set()).add(oid)
    artifacts = []
    for oid, ids in sorted(observations.items()):
        artifacts.append({"id": oid, "kind": "mapping", "locator": prefix + REGISTER,
                          "depends_on": [{"source_id": sid} for sid in sorted(ids)],
                          "dependency_basis": "Exact observation_id memberships in the published register; no evidence rows dropped"})
    for fid, ids in sorted(findings.items()):
        artifacts.append({"id": fid, "kind": "mapping", "locator": prefix + REGISTER,
                          "depends_on": [{"artifact_id": oid} for oid in sorted(ids)],
                          "dependency_basis": "Exact finding_id memberships in the published register; shared findings retain all observations"})
    artifacts.append({"id": "UIOWA-023-REGISTER", "kind": "worksheet", "locator": prefix + REGISTER,
                      "depends_on": [{"source_id": sid} for sid in sorted(sources)],
                      "dependency_basis": "The worksheet physically contains these evidence records"})
    # This linkage is a disclosed analyst declaration, not inferred document lineage.
    if "FND-SYN-IAM-DEP-001" in findings:
        artifacts.append({"id": "UIOWA-023-CASE-D", "kind": "narrative",
                          "locator": prefix + METHOD + "#case-d--conflicting-records",
                          "depends_on": [{"artifact_id": "FND-SYN-IAM-DEP-001"}],
                          "dependency_basis": "Analyst-declared rehearsal linkage to published section 8 Case D, which describes this IAM conflict; not exhaustive narrative dependency discovery"})
    return {"schema": "uiowa-source-dependencies/v1", "namespace": NAMESPACE, "coverage": "partial",
            "artifacts": sorted(artifacts, key=lambda a: a["id"]),
            "provenance": {"synthetic": True, "revision": revision, "register_path": REGISTER,
                           "register_blob": observed, "method_path": METHOD,
                           "method_blob_at_pinned_revision": METHOD_BLOB if revision == REVISION else None,
                           "scope": "023 register, its explicit OBS/FND memberships, and one declared narrative linkage only",
                           "not_surveyed": "Other preparation assets, external documents and authority-v2 source identities",
                           "notice": "Records contain documented interpretation, not original PDF/export content. No conclusions or ratings are changed."},
            "source_inventory": [sources[sid] for sid in sorted(sources)], "register_records": records}


def inventory_markdown(index: dict) -> str:
    def cell(value: object) -> str:
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|").replace("\r", "").replace("\n", "<br>")
    lines = ["# UIOWA-023 source-linked dependency inventory", "", "SYNTHETIC PREPARATION MATERIAL / PARTIAL DEPENDENCY SURVEY", "",
             index["provenance"]["notice"], "", f"Pinned revision: `{index['provenance']['revision']}`", "",
             f"{len(index['source_inventory'])} evidence records; {len(index['artifacts'])} worksheet/mapping/narrative nodes.", "",
             "## Source records", "", "| ID | Register locator | Original reference (not fetched) |", "|---|---|---|"]
    for source in index["source_inventory"]:
        lines.append("| " + " | ".join(cell(source[k]) for k in ("source_id", "locator", "source_ref")) + " |")
    lines += ["", "## Declared consumers", "", "| Artifact | Kind | Dependencies | Locator | Basis |", "|---|---|---|---|---|"]
    for artifact in index["artifacts"]:
        deps = ", ".join(("source:" + d["source_id"]) if "source_id" in d else "artifact:" + d["artifact_id"] for d in artifact["depends_on"])
        lines.append("| " + " | ".join(cell(v) for v in (artifact["id"], artifact["kind"], deps, artifact["locator"], artifact["dependency_basis"])) + " |")
    lines += ["", "## Boundaries", "", index["provenance"]["scope"], "", "Not surveyed: " + index["provenance"]["not_surveyed"], "",
              "Dependency coverage is partial even though all seven records in the pinned register are retained. No consumer hit means no declared link was found, not that no dependency exists.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--input", type=Path, help="Explicit register copy; defaults to the repository path")
    parser.add_argument("--revision", default=REVISION, help="Revision used in original-source locators")
    parser.add_argument("--expected-blob", default=REGISTER_BLOB, help="Expected Git blob of the supplied register")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        result = build_index((args.input or args.repo_root / REGISTER).read_bytes(),
                             revision=args.revision, expected_blob=args.expected_blob)
        sys.stdout.write(canonical(result) + "\n" if args.format == "json" else inventory_markdown(result))
    except (ValueError, OSError, csv.Error) as error:
        print(f"uiowa-023-index: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
