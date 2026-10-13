#!/usr/bin/env python3
"""Import the published 023 evidence register without inventing findings.

Reads an explicitly supplied UTF-8 CSV; no network access. A source node denotes
an imported evidence-register row, not verified contents of its source_ref.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

if __package__:
    from .identity_map import SCHEMA, MappingError, IdentityMap, reconcile
else:
    from identity_map import SCHEMA, MappingError, IdentityMap, reconcile

REQUIRED = ("evidence_id", "observation_id", "finding_id", "group", "area", "source_ref")


def git_blob_sha(raw: bytes) -> str:
    """Git SHA-1 blob ID of the exact input bytes; not a source-authenticity claim."""
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()


def import_register(raw: bytes, *, namespace: str, source_path: str,
                    synthetic: bool, expected_blob: str | None = None) -> dict:
    if type(synthetic) is not bool:
        raise MappingError("synthetic must be an explicit boolean")
    blob = git_blob_sha(raw)
    if expected_blob is not None and blob != expected_blob:
        raise MappingError(f"register bytes differ: expected {expected_blob}, received {blob}")
    try:
        text = raw.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = next(reader)
        if not header or any(not name for name in header) or len(header) != len(set(header)):
            raise MappingError("CSV headers must be nonempty and unique")
        if not set(REQUIRED).issubset(header):
            raise MappingError("missing required CSV columns: " + ", ".join(sorted(set(REQUIRED) - set(header))))
        rows = []
        for ordinal, values in enumerate(reader, 2):
            if len(values) != len(header):
                raise MappingError(f"CSV record {ordinal}: expected {len(header)} fields, got {len(values)}")
            row = dict(zip(header, values))
            if any(not row[name].strip() for name in REQUIRED):
                raise MappingError(f"CSV record {ordinal}: an identity/context/source_ref field is empty")
            rows.append((ordinal, row))
    except (StopIteration, UnicodeError, csv.Error) as exc:
        raise MappingError(f"unreadable CSV: {exc}") from exc
    revision = "git-blob:" + blob
    def ref(kind: str, local_id: str) -> dict:
        return {"namespace": namespace, "kind": kind, "id": local_id, "revision": revision}
    def locator(ordinal: int) -> str:
        return f"{source_path}#csv-record={ordinal}"
    buckets: dict[tuple[str, str], list] = defaultdict(list)
    evidence_ids = set()
    links = []
    for ordinal, row in rows:
        if row["evidence_id"] in evidence_ids:
            raise MappingError(f"CSV record {ordinal}: duplicate evidence_id {row['evidence_id']}")
        evidence_ids.add(row["evidence_id"])
        member = {"csv_record": ordinal, "row": deepcopy(row)}
        for kind, column in (("source", "evidence_id"), ("observation", "observation_id"), ("finding", "finding_id")):
            buckets[kind, row[column]].append(member)
        for relation, left, right in (
            ("supported_by", ref("observation", row["observation_id"]), ref("source", row["evidence_id"])),
            ("has_observation", ref("finding", row["finding_id"]), ref("observation", row["observation_id"])),
        ):
            links.append({"link_id": f"csv-record-{ordinal}:{relation}", "relation": relation,
                          "from": left, "to": right, "source_locator": locator(ordinal),
                          "evidence_state": row.get("evidence_state"), "synthetic": synthetic})
    records = []
    for (kind, local_id), members in sorted(buckets.items()):
        contexts = {(m["row"]["group"], m["row"]["area"]) for m in members}
        if len(contexts) != 1:
            raise MappingError(f"{kind} {local_id}: conflicting group/area contexts require explicit reconciliation")
        records.append({**ref(kind, local_id), "synthetic": synthetic,
                        "source_locators": [locator(m["csv_record"]) for m in members],
                        "payload": {"memberships": deepcopy(members),
                                    "representation": "imported evidence-register records",
                                    "underlying_source_content_read": False}})
    document = {"schema": SCHEMA, "records": records, "equivalences": [], "links": links,
                "adapter": {"name": "023-register-v1", "input_path": source_path,
                            "input_git_blob": blob, "input_sha256": hashlib.sha256(raw).hexdigest(),
                            "input_columns": header, "input_records": len(rows), "synthetic": synthetic,
                            "locator_semantics": "one-based logical CSV record including header; not physical line",
                            "limits": "Group labels are not service IDs; shared finding IDs preserve memberships; no maturity or evidence-state reinterpretation."}}
    # Exercise the actual core contract before exporting an input packet.
    IdentityMap(records).report(links)
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--source-path", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--synthetic", action="store_true")
    mode.add_argument("--non-synthetic", action="store_true")
    parser.add_argument("--expected-blob")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    try:
        paths = [p.resolve() for p in (args.input, args.output, args.report) if p]
        if len(paths) != len(set(paths)):
            raise MappingError("input and output paths must be distinct")
        document = import_register(args.input.read_bytes(), namespace=args.namespace,
                                   source_path=args.source_path, synthetic=args.synthetic,
                                   expected_blob=args.expected_blob)
        args.output.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                               encoding="utf-8", newline="\n")
        if args.report:
            args.report.write_text(json.dumps(reconcile(document), ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                                   encoding="utf-8", newline="\n")
        return 0
    except (MappingError, OSError, UnicodeError) as exc:
        print(f"register-adapter: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
