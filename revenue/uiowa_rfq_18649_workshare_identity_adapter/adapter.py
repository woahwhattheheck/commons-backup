#!/usr/bin/env python3
"""Native workshare/workbench records for the canonical UIOWA-103 identity mapper.

Imports record identity and retained provenance only. No source-truth, receipt
integrity, maturity, approval, or equivalence judgment is performed here.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

SCHEMA = "uiowa.identity-map.v1"
AUTHORITY_SCHEMA = "uiowa-rfq18649-evidence-authority/v2"
HANDOFF_SCHEMA = "uiowa-rfq18649-analyst-handoff-draft/v1"
DEFAULT_MAPPER = Path(__file__).resolve().parent.parent / "uiowa_rfq_18649_identity_map/identity_map.py"
FLAGS = {"buyer_approved", "prime_approved", "current_evidence_review_authority", "submission_authorized",
         "signature_authorized", "invoice_or_payment_authorized", "recognized_revenue"}


class AdapterError(ValueError):
    """Input cannot be imported under its declared native format."""


def canonical(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, UnicodeError) as exc:
        raise AdapterError(f"Not finite JSON: {exc}") from exc


def sha256(value: Any) -> str:
    try:
        return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()
    except UnicodeError as exc:
        raise AdapterError("Input contains an unpaired Unicode surrogate") from exc


def text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise AdapterError(f"{label}: expected nonempty text without control characters")
    return value


def object_value(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise AdapterError(f"{label}: expected an object")
    return value


def load_json(raw: str) -> dict:
    def pairs(items: list) -> dict:
        value: dict = {}
        for key, item in items:
            if key in value:
                raise AdapterError(f"Duplicate JSON key: {key}")
            value[key] = item
        return value
    def reject(value: str) -> None:
        raise AdapterError(f"Non-finite JSON constant: {value}")
    try:
        return object_value(json.loads(raw, object_pairs_hook=pairs, parse_constant=reject), "input")
    except json.JSONDecodeError as exc:
        raise AdapterError(f"Invalid JSON at line {exc.lineno}, column {exc.colno}") from exc


def load_mapper(path: Path = DEFAULT_MAPPER) -> ModuleType:
    """Load the selected local canonical implementation without generic imports."""
    path = Path(path).resolve()
    module_name = "_uiowa_identity_mapper_" + hashlib.sha256(path.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise AdapterError(f"Cannot load canonical mapper from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if getattr(module, "SCHEMA", None) != SCHEMA or not callable(getattr(module, "reconcile", None)):
        raise AdapterError("Selected module does not implement uiowa.identity-map.v1")
    return module


def _envelope(document: dict, namespace: str, locator: str, synthetic: bool) -> dict:
    object_value(document, "document")
    text(namespace, "namespace")
    text(locator, "locator")
    if type(synthetic) is not bool:
        raise AdapterError("synthetic must be an explicit boolean")
    # The declared source location is part of provenance identity. JSON formatting
    # is not. A changed document at the same location is a different revision.
    revision = "sha256:" + sha256({"origin_locator": locator, "document": document})
    return {"schema": SCHEMA, "records": [], "equivalences": [], "links": [],
        "adapter": {"schema": "uiowa.workshare-identity-adapter.v1", "native_schema": document.get("schema"),
                    "namespace": namespace, "revision": revision, "synthetic": synthetic, "source_locator": locator,
                    "document_sha256": sha256(document), "original_document": deepcopy(document),
                    "verification": "IDENTITY_AND_STRUCTURE_ONLY_NOT_COMPILER_VERIFICATION"}}


def _record(packet: dict, kind: str, raw_id: str, payload: dict, pointer: str, *, container: bool = False) -> dict:
    meta = packet["adapter"]
    return {"namespace": meta["namespace"] + ("/artifact" if container else ""),
        "kind": kind, "id": raw_id, "revision": meta["revision"], "synthetic": meta["synthetic"],
        "source_locators": [meta["source_locator"] + "#" + pointer], "payload": deepcopy(payload),
        "id_origin": "DERIVED_CONTAINER_ID" if container else "NATIVE_OR_EXPLICIT_DERIVED_ID",
        "verification": "IMPORTED_RECORD_NOT_VERIFIED_FINDING"}


def select(record: dict) -> dict:
    return {key: record[key] for key in ("namespace", "kind", "id", "revision")}


def _link(label: str, left: dict, right: dict, relation: str) -> dict:
    return {"link_id": label + ":" + sha256([select(left), select(right)]), "relation": relation,
            "from": select(left), "to": select(right), "assessment_authority": False}


def adapt_authority(document: dict, *, namespace: str, locator: str, synthetic: bool) -> dict:
    """Import authority rows as source records; never validate their truth claims."""
    packet = _envelope(document, namespace, locator, synthetic)
    if document.get("schema") != AUTHORITY_SCHEMA:
        raise AdapterError(f"Expected {AUTHORITY_SCHEMA}")
    text(document.get("generation"), "authority.generation")
    sources = document.get("sources")
    if not isinstance(sources, list):
        raise AdapterError("authority.sources must be an array")
    header = {key: deepcopy(value) for key, value in document.items() if key != "sources"}
    container = _record(packet, "source", "authority-document", header, "", container=True)
    packet["records"].append(container)
    ids: set[str] = set()
    for index, row in enumerate(sources):
        object_value(row, "authority source")
        sid = text(row.get("source_id"), "source.source_id")
        text(row.get("source_ref"), "source.source_ref")
        if sid in ids:
            raise AdapterError(f"Duplicate native source_id: {sid}")
        ids.add(sid)
        imported = _record(packet, "source", sid, row, f"/sources/{index}")
        imported["id_origin"] = "NATIVE_SOURCE_ID"
        imported["source_semantics"] = "AUTHORITY_BUNDLE_ROW_NOT_FETCHED_UNDERLYING_DOCUMENT"
        packet["records"].append(imported)
        packet["links"].append(_link("authority-row", imported, container, "recorded_in_authority_bundle"))
    return packet


def cell_id(group: str, dimension: str) -> str:
    return canonical([text(group, "group"), text(dimension, "dimension")])


def adapt_handoff(document: dict, *, namespace: str, locator: str) -> dict:
    """Retain draft notes with content-bound revisions, not receipt-only revisions."""
    object_value(document, "handoff")
    if document.get("schema") != HANDOFF_SCHEMA:
        raise AdapterError(f"Expected {HANDOFF_SCHEMA}")
    if document.get("status") != "DRAFT_NON_AUTHORITATIVE" or document.get("report_mode") != "UNTRUSTED_INSPECTION":
        raise AdapterError("Handoff must retain draft status and untrusted report mode")
    flags = object_value(document.get("authority"), "handoff.authority")
    if not FLAGS.issubset(flags) or any(value is not False for value in flags.values()):
        raise AdapterError("Handoff must retain its false authority flags")
    receipt = text(document.get("report_receipt_sha256"), "handoff.report_receipt_sha256")
    if len(receipt) != 64 or any(c not in "0123456789abcdef" for c in receipt):
        raise AdapterError("Handoff receipt must have lowercase SHA-256 syntax")
    packet = _envelope(document, namespace, locator, document.get("synthetic_demo"))
    notes = document.get("cell_notes")
    if not isinstance(notes, list):
        raise AdapterError("handoff.cell_notes must be an array")
    container = _record(packet, "source", "handoff-document",
        {key: deepcopy(value) for key, value in document.items() if key != "cell_notes"}, "", container=True)
    packet["records"].append(container)
    ids: set[str] = set()
    for index, note in enumerate(notes):
        object_value(note, "cell note")
        nid = cell_id(note.get("group"), note.get("dimension"))
        if nid in ids:
            raise AdapterError(f"Duplicate native cell: {nid}")
        ids.add(nid)
        if not isinstance(note.get("analyst_note"), str):
            raise AdapterError("analyst_note must be text; empty is permitted")
        text(note.get("disposition"), "note.disposition")
        text(note.get("compiler_status"), "note.compiler_status")
        imported = _record(packet, "observation", nid, note, f"/cell_notes/{index}")
        imported.update({"id_origin": "DERIVED_GROUP_DIMENSION_TUPLE", "evidence_class": "ANALYST_STATEMENT_NOT_VERIFIED_OBSERVATION",
                         "bound_report_receipt_sha256": receipt})
        packet["records"].append(imported)
        packet["links"].append(_link("analyst-note", imported, container, "analyst_statement_recorded_in"))
    return packet


def review_request(authority: dict, handoff: dict, *, source_id: str, group: str, dimension: str,
                   expected_receipt: str, expected_generation: str, expected_handoff_revision: str, expected_authority_revision: str,
                   request_id: str, rationale: str) -> dict:
    """An explicit request to inspect a source, never an inferred support claim.

    Consistency checks bind the caller's request to supplied artifacts, not to an
    independently trusted report. Missing source/cell IDs become mapper diagnostics.
    """
    am, hm = authority["adapter"], handoff["adapter"]
    if am["native_schema"] != AUTHORITY_SCHEMA or hm["native_schema"] != HANDOFF_SCHEMA:
        raise AdapterError("review_request needs authority and handoff adapter packets")
    if am["synthetic"] != hm["synthetic"]:
        raise AdapterError("A review request cannot silently combine synthetic and nonsynthetic inputs")
    if hm["original_document"]["report_receipt_sha256"] != expected_receipt:
        raise AdapterError("Review request report receipt mismatch")
    if am["original_document"]["generation"] != expected_generation:
        raise AdapterError("Review request authority generation mismatch")
    if am["revision"] != expected_authority_revision:
        raise AdapterError("Review request authority content revision mismatch")
    if hm["revision"] != expected_handoff_revision:
        raise AdapterError("Review request handoff content revision mismatch")
    return {"link_id": text(request_id, "request_id"), "relation": "analyst_requests_review_of",
        "from": {"namespace": hm["namespace"], "kind": "observation", "id": cell_id(group, dimension), "revision": hm["revision"]},
        "to": {"namespace": am["namespace"], "kind": "source", "id": text(source_id, "source_id"), "revision": am["revision"]},
        "request_rationale": text(rationale, "rationale"), "expected_report_receipt_sha256": expected_receipt,
        "expected_authority_generation": expected_generation, "assessment_authority": False,
        "meaning": "REVIEW_REQUEST_NOT_EVIDENCE_SUPPORT_OR_SAME_ENTITY"}


def combine(packets: list[dict], extra_links: list[dict] | None = None) -> dict:
    if not packets:
        raise AdapterError("At least one packet is required")
    result = {"schema": SCHEMA, "records": [], "equivalences": [], "links": [], "component_inputs": []}
    for packet in packets:
        if packet.get("schema") != SCHEMA:
            raise AdapterError("Component envelope schema mismatch")
        for field in ("records", "equivalences", "links"):
            result[field].extend(deepcopy(packet[field]))
        result["component_inputs"].append(deepcopy({k: v for k, v in packet.items() if k not in ("schema", "records", "equivalences", "links")}))
    result["links"].extend(deepcopy(extra_links or []))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("format", choices=("authority", "handoff"))
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, help="new JSON output file")
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--locator", required=True, help="stable source locator, preferably repository-relative")
    parser.add_argument("--synthetic", action="store_true", help="explicit source label for authority bundles")
    args = parser.parse_args(argv)
    try:
        document = load_json(args.input.read_text(encoding="utf-8"))
        if args.format == "authority":
            packet = adapt_authority(document, namespace=args.namespace, locator=args.locator, synthetic=args.synthetic)
        else:
            if args.synthetic and document.get("synthetic_demo") is not True:
                raise AdapterError("--synthetic must not relabel a nonsynthetic handoff")
            packet = adapt_handoff(document, namespace=args.namespace, locator=args.locator)
        with args.output.open("x", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(packet, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
        print(canonical({"records": len(packet["records"]), "links": len(packet["links"]), "revision": packet["adapter"]["revision"]}))
        return 0
    except (AdapterError, OSError, ValueError, UnicodeError) as exc:
        print(f"workshare-identity-adapter: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
