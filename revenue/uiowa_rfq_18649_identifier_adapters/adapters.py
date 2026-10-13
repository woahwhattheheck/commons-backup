#!/usr/bin/env python3
"""Preserve supplied Handoff/Outcome bytes and compose the canonical identity map."""
from __future__ import annotations

import argparse
import base64
from collections import defaultdict
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from revenue.uiowa_rfq_18649_identity_map.identity_map import (
    SCHEMA, MappingError, load_json, reconcile,
)


def _text(value, label):
    if type(value) is not str or not value.strip():
        raise MappingError(f"{label} must be a nonempty string")
    return value


class Extraction:
    def __init__(self, raw: bytes, namespace: str, source_path: str, format_name: str):
        self.namespace = _text(namespace, "namespace")
        self.path = _text(source_path, "source_path")
        digest = hashlib.sha256(raw).hexdigest()
        self.revision = "sha256:" + digest
        self.packet = {
            "schema": SCHEMA, "records": [], "equivalences": [], "links": [],
            "adapter": {
                "schema": "uiowa.identifier-adapters.v1", "format": format_name,
                "source_path": self.path, "input_sha256": digest,
                "input_bytes": len(raw),
                "input_git_blob": hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest(),
                "source_base64": base64.b64encode(raw).decode("ascii"),
                "diagnostics": [], "unclassified": [],
                "assessment_authority": False,
            },
        }

    def selector(self, section, kind, ident):
        return {"namespace": self.namespace + ":" + section, "kind": kind,
                "id": ident, "revision": self.revision}

    def diagnostic(self, code, locator, detail):
        self.packet["adapter"]["diagnostics"].append(
            {"code": code, "locator": locator, "detail": detail})

    def record(self, section, kind, ident, synthetic, payload, locator):
        if type(ident) is not str or not ident.strip():
            code = "MISSING_ID"
        elif type(synthetic) is not bool:
            code = "UNKNOWN_SYNTHETIC_CLASSIFICATION"
        else:
            self.packet["records"].append({
                **self.selector(section, kind, ident), "synthetic": synthetic,
                "source_locators": [locator], "payload": deepcopy(payload),
            })
            return
        self.diagnostic(code, locator, "Original record retained without inventing its identity or synthetic label.")
        self.packet["adapter"]["unclassified"].append({
            "section": section, "kind": kind, "id": ident,
            "synthetic": synthetic, "source_locator": locator,
            "original": deepcopy(payload), "reason": code,
        })

    def link(self, ident, relation, left, right, locator, **extensions):
        self.packet["links"].append({
            "link_id": self.namespace + ":" + self.revision + ":" + ident,
            "relation": relation, "from": left, "to": right,
            "source_locator": locator, **extensions,
        })

    def finish(self):
        # Use the existing mapper for validation and identity resolution.
        reconcile(self.packet)
        return self.packet


def handoff(raw: bytes, *, namespace: str, source_path: str) -> dict:
    try:
        document = load_json(raw.decode("utf-8-sig"))
    except UnicodeError as exc:
        raise MappingError("handoff input must be UTF-8") from exc
    if type(document) is not dict or type(document.get("metadata")) is not dict:
        raise MappingError("handoff requires an object with metadata")
    extraction = Extraction(raw, namespace, source_path, "handoff-json")
    label = document["metadata"].get("synthetic")
    root = extraction.selector("document", "source", "document")
    extraction.record("document", "source", "document", label, document, source_path + "#")
    if document["metadata"].get("service") and not document["metadata"].get("service_id"):
        extraction.diagnostic("SERVICE_LABEL_WITHOUT_ID", source_path + "#/metadata/service",
                              "Service display text is preserved, not converted into a service identity.")
    support = defaultdict(set)
    for section in ("acceptance_evidence", "support_readiness", "operational_needs"):
        entries = document.get(section, [])
        if type(entries) is not list:
            raise MappingError(f"handoff {section} must be an array")
        for index, item in enumerate(entries):
            if type(item) is not dict:
                raise MappingError(f"handoff {section}/{index} must be an object")
            ident = item.get("id")
            extraction.record(section, "source", ident, item.get("synthetic", label), item,
                              f"{source_path}#/{section}/{index}")
            if section != "acceptance_evidence" and type(ident) is str:
                support[ident].add(section)
    requirements = document.get("requirements", [])
    if type(requirements) is not list:
        raise MappingError("handoff requirements must be an array")
    for index, requirement in enumerate(requirements):
        if type(requirement) is not dict:
            raise MappingError(f"handoff requirements/{index} must be an object")
        for field in ("acceptance_evidence", "support_readiness"):
            references = requirement.get(field, [])
            if type(references) is not list:
                raise MappingError(f"requirement {field} must be an array")
            for ordinal, ident in enumerate(references):
                _text(ident, f"requirement {field} reference")
                locator = f"{source_path}#/requirements/{index}/{field}/{ordinal}"
                if field == "acceptance_evidence":
                    target = extraction.selector(field, "source", ident)
                else:
                    candidates = sorted(support.get(ident, set()))
                    if len(candidates) == 1:
                        target = extraction.selector(candidates[0], "source", ident)
                    elif not candidates:
                        target = extraction.selector("unresolved_support_reference", "source", ident)
                        extraction.diagnostic("DANGLING_SUPPORT_REFERENCE", locator, ident)
                    else:
                        target = {"kind": "source", "id": ident, "revision": extraction.revision}
                        extraction.diagnostic("AMBIGUOUS_SUPPORT_REFERENCE", locator, ident)
                extraction.link(f"requirement-{index}-{field}-{ordinal}", "requirement_" + field,
                                root, target, locator, requirement=deepcopy(requirement))
    return extraction.finish()


def outcome(raw: bytes, *, namespace: str, source_path: str) -> dict:
    try:
        reader = csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        columns = next(reader)
        if not columns or any(not name for name in columns) or len(set(columns)) != len(columns):
            raise MappingError("outcome CSV columns must be nonempty and unique")
        if not {"recommendation_id", "synthetic"}.issubset(columns):
            raise MappingError("outcome CSV requires recommendation_id and synthetic")
        rows = []
        for ordinal, values in enumerate(reader, 2):
            if len(values) != len(columns):
                raise MappingError(f"CSV record {ordinal}: expected {len(columns)} fields, got {len(values)}")
            rows.append((ordinal, dict(zip(columns, values))))
    except (StopIteration, UnicodeError, csv.Error) as exc:
        raise MappingError(f"unreadable outcome CSV: {exc}") from exc
    extraction = Extraction(raw, namespace, source_path, "outcome-recommendations-csv")
    labels = {row["synthetic"] for _, row in rows}
    root_label = {"true": True, "false": False}.get(next(iter(labels))) if len(labels) == 1 else None
    root = extraction.selector("document", "source", "document")
    extraction.record("document", "source", "document", root_label,
                      {"columns": columns, "rows": [row for _, row in rows]}, source_path)
    for ordinal, row in rows:
        ident = row["recommendation_id"]
        label = {"true": True, "false": False}.get(row["synthetic"])
        locator = f"{source_path}#csv-record={ordinal}"
        extraction.record("recommendations", "recommendation", ident, label, row, locator)
        if type(ident) is str and ident.strip():
            extraction.link(f"csv-record-{ordinal}", "imported_from",
                            extraction.selector("recommendations", "recommendation", ident), root, locator)
    return extraction.finish()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("format", choices=("handoff", "outcome"))
    parser.add_argument("input", type=Path)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--source-path", help="Original retained path used in source locators")
    parser.add_argument("--report", action="store_true", help="Emit the canonical mapper report instead of its input packet")
    args = parser.parse_args(argv)
    try:
        adapter = handoff if args.format == "handoff" else outcome
        packet = adapter(args.input.read_bytes(), namespace=args.namespace,
                         source_path=args.source_path or args.input.as_posix())
        report = reconcile(packet)
        result = report if args.report else packet
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
        return 1 if report["summary"]["unresolved_links"] or packet["adapter"]["unclassified"] else 0
    except (MappingError, OSError, UnicodeError, RecursionError) as exc:
        print(f"identifier-adapters: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
