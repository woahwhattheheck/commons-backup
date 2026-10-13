#!/usr/bin/env python3
"""Compare two supplied 023 register versions through the existing impact engine."""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from revenue.uiowa_rfq_18649_source_impact import source_impact as engine
from revenue.uiowa_rfq_18649_source_impact_023.register_index import build_index, NAMESPACE

INTERPRETATION = {"claim", "scope_limit", "confidence", "evidence_state", "directness",
                  "recency", "representativeness", "corroboration", "follow_up"}


def adapt(raw: bytes, *, revision: str, snapshot_id: str, captured_at: str,
          scope: str, input_path: str) -> tuple[dict, dict]:
    # These are caller-supplied file bytes and an explicit source revision. The
    # original adapter's default historical-blob check remains unchanged.
    index = build_index(raw, revision=revision, expected_blob=None)
    sources = []
    for record in index["register_records"]:
        fields = deepcopy(record["fields"])
        row_digest = hashlib.sha256(engine.canonical(fields).encode("utf-8")).hexdigest()
        sources.append({
            "id": record["source_id"], "revision": "register-row-sha256:" + row_digest,
            "content": {"representation": "uiowa-023-register-record/v1", "sha256": row_digest},
            "metadata": {key: value for key, value in fields.items() if key not in INTERPRETATION},
            "interpretation": {key: value for key, value in fields.items() if key in INTERPRETATION},
        })
    manifest = {
        "schema": engine.MANIFEST, "snapshot_id": snapshot_id, "captured_at": captured_at,
        "namespace": NAMESPACE, "scope": {"engagement": scope, "source_family": "UIOWA-023 register"},
        "coverage": "complete", "sources": sorted(sources, key=lambda row: row["id"]),
        "provenance": {
            "adapter": "uiowa-023-register-impact/v1", "input_path": input_path,
            "register_revision": revision, "register_git_blob": index["provenance"]["register_blob"],
            "register_sha256": hashlib.sha256(raw).hexdigest(),
            "register_bytes_base64": base64.b64encode(raw).decode("ascii"),
            "record_locators": {row["source_id"]: row["locator"] for row in index["register_records"]},
            "inventory_scope": "All records in this supplied register only; not all institutional evidence.",
            "notice": "Content digests describe register records, not original PDFs or source exports. Underlying documents were not fetched.",
        },
    }
    engine.validate_manifest(manifest)
    return manifest, index


def dependencies(before_index: dict, after_index: dict, scope: dict) -> dict:
    nodes = {}
    for index in (before_index, after_index):
        for source_node in index["artifacts"]:
            ident = source_node["id"]
            node = nodes.setdefault(ident, {
                "id": ident, "kind": source_node["kind"], "locator": source_node["locator"],
                "depends_on": [], "notes": source_node["dependency_basis"],
            })
            node["locator"] = source_node["locator"]
            if node["kind"] != source_node["kind"]:
                raise engine.InputError("artifact kind changed: " + ident)
            refs = {(next(iter(ref)), next(iter(ref.values()))) for ref in node["depends_on"]}
            refs.update((next(iter(ref)), next(iter(ref.values()))) for ref in source_node["depends_on"])
            node["depends_on"] = [{key: value} for key, value in sorted(refs)]
    graph = {
        "schema": engine.GRAPH, "namespace": NAMESPACE, "scope": deepcopy(scope),
        "coverage": "partial", "artifacts": [nodes[key] for key in sorted(nodes)],
        "provenance": {
            "before": deepcopy(before_index["provenance"]), "after": deepcopy(after_index["provenance"]),
            "edge_policy": "Union of both register generations; removed memberships remain reviewable.",
            "narrative_linkage": "Retained analyst declaration from the original 023 adapter, not a new full-document dependency survey.",
        },
    }
    engine.validate_graph(graph, NAMESPACE)
    return graph


def compare(before: dict, after: dict, before_index: dict, after_index: dict) -> tuple[dict, dict]:
    graph = dependencies(before_index, after_index, after["scope"])
    return engine.analyze(before, after, graph), graph


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--before-revision", required=True)
    parser.add_argument("--after-revision", required=True)
    parser.add_argument("--before-captured-at", required=True)
    parser.add_argument("--after-captured-at", required=True)
    parser.add_argument("--scope", required=True, help="Same explicit engagement scope for both register versions")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if not args.scope.strip():
            raise engine.InputError("scope must be nonempty")
        before, before_index = adapt(args.before.read_bytes(), revision=args.before_revision,
            snapshot_id="register-before", captured_at=args.before_captured_at,
            scope=args.scope, input_path=args.before.as_posix())
        after, after_index = adapt(args.after.read_bytes(), revision=args.after_revision,
            snapshot_id="register-after", captured_at=args.after_captured_at,
            scope=args.scope, input_path=args.after.as_posix())
        report, graph = compare(before, after, before_index, after_index)
        engine.write_report(report, args.out_dir)
        for filename, document in (("before-manifest.json", before), ("after-manifest.json", after),
                                   ("dependencies.json", graph), ("before-index.json", before_index),
                                   ("after-index.json", after_index)):
            (args.out_dir / filename).write_text(json.dumps(document, ensure_ascii=False, sort_keys=True,
                                                           indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "counts": report["counts"],
                          "artifacts": len(report["artifacts"]), "out_dir": str(args.out_dir)}, sort_keys=True))
        return 2 if report["status"] == "INCOMPLETE" else 0
    except (ValueError, OSError, UnicodeError, csv.Error) as exc:
        print(f"register-impact: INPUT_OR_OUTPUT_ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
