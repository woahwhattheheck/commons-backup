"""Prepare native UIOWA-039 review cycles without deciding or rewriting comments.

Consumes the published review-document/v1 and review-cycle/v1 contracts. Native
verification/application remain in review_cycle.review; this is only an adapter.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys

try:
    from .comment_import import ImportFormatError, canonical, digest, stage_comments
except ImportError:
    from comment_import import ImportFormatError, canonical, digest, stage_comments

DOC_SCHEMA = "uiowa-rfq18649-review-document/v1"
CYCLE_SCHEMA = "uiowa-rfq18649-review-cycle/v1"
NAMESPACE = "uiowa-review-document"
KINDS = {"factual", "evidence", "wording", "interpretation", "priority"}
IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}\Z")


def native_digest(value: dict) -> str:
    # Native review.py canonical() includes a trailing LF; core staging does not.
    return hashlib.sha256(canonical(value) + b"\n").hexdigest()


def catalog_from_document(document: dict, source_name: str, namespace: str = NAMESPACE) -> dict:
    if not isinstance(document, dict) or document.get("schema") != DOC_SCHEMA:
        raise ImportFormatError("expected actual review-document/v1")
    if not isinstance(namespace, str) or not namespace.strip() or not source_name:
        raise ImportFormatError("explicit document namespace and source label required")
    version = document.get("version")
    if not isinstance(version, str) or not IDENT.fullmatch(version):
        raise ImportFormatError("invalid native document version")
    findings = document.get("findings")
    if not isinstance(findings, list):
        raise ImportFormatError("native document requires findings array")
    result, seen = [], set()
    for index, finding in enumerate(findings):
        fid = finding.get("id") if isinstance(finding, dict) else None
        if not isinstance(fid, str) or not IDENT.fullmatch(fid) or fid in seen:
            raise ImportFormatError("invalid or duplicate native finding ID")
        seen.add(fid)
        result.append({"finding_id": fid, "namespace": namespace, "report_version": version,
                       "locator": f"{source_name}#/findings/{index}",
                       "native_document_sha256": native_digest(document),
                       "native_target_type": "findings", "synthetic": document.get("synthetic")})
    return {"schema": "uiowa-review-import-native-catalog/v1", "findings": result,
            "native_document_sha256": native_digest(document), "namespace": namespace}


def prepare_cycle(raw: bytes, source_id: str, source_name: str, document: dict,
                  report: dict, cycle_id: str, new_version: str, *,
                  document_name: str = "original-draft.json", namespace: str = NAMESPACE,
                  prior: dict | None = None, validate_text=None) -> dict:
    """Return OPEN comments plus a lossless sidecar; never apply an edit.

    validate_text is the actual native review.text callable when running the CLI.
    Structural preparation alone does not verify the compiler's report integrity.
    """
    for label, value in (("cycle_id", cycle_id), ("new_version", new_version)):
        if not isinstance(value, str) or not IDENT.fullmatch(value):
            raise ImportFormatError(f"invalid native {label}")
    if new_version == document.get("version"):
        raise ImportFormatError("native review needs a distinct new draft version")
    if cycle_id in document.get("applied_cycles", []):
        raise ImportFormatError("cycle already applied; retain its receipt rather than applying twice")
    receipt = report.get("receipt_sha256") if isinstance(report, dict) else None
    if not isinstance(receipt, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt):
        raise ImportFormatError("missing native compiler receipt")
    if document.get("report_receipt_sha256") != receipt:
        raise ImportFormatError("native document/report receipt mismatch")
    catalog = catalog_from_document(document, document_name, namespace)
    staged = stage_comments(raw, source_id, source_name, catalog, prior)
    comments, mapped, native_unresolved, already_present = [], [], [], []
    existing = {}
    for item in document.get("unresolved", []):
        existing.setdefault(item.get("comment_id"), []).append(item)
    for item in staged["ready"]:
        values = item["values"]
        kind = values.get("comment_kind", "")
        issues = []
        if kind not in KINDS:
            issues.append({"code": "NATIVE_KIND_REQUIRED", "supplied": kind,
                           "supported": sorted(KINDS)})
        native_id = "IMP-" + item["import_key"]
        owner = values.get("owner_role", "").strip() or "UNASSIGNED"
        # Reviewer role is not automatically a disposition ownership assignment.
        if validate_text is not None:
            for field, value in (("comment", values["comment_text"]), ("owner_role", owner)):
                try:
                    validate_text(value, field)
                except (TypeError, ValueError) as exc:
                    issues.append({"code": "NATIVE_TEXT_REJECTED", "field": field, "reason": str(exc)})
        # Re-import identity is not an exemption from current native validation.
        # Preserve a collision alongside other diagnostics rather than erasing them.
        if native_id in existing and not all(
                e.get("target_id") == values["finding_id"] and e.get("comment") == values["comment_text"]
                for e in existing[native_id]):
            issues.append({"code": "NATIVE_ID_CONFLICT"})
        if issues:
            native_unresolved.append({"record": deepcopy(item), "diagnostics": issues})
            continue
        if native_id in existing:
            already_present.append({"native_comment_id": native_id, "record": deepcopy(item),
                                    "code": "ALREADY_IN_REVIEW"})
            continue
        native = {"id": native_id, "kind": kind, "target_type": "findings",
                  "target_id": values["finding_id"], "comment": values["comment_text"],
                  "proposed_changes": [], "source_ids": [], "decision": "OPEN",
                  "rationale": "Imported for consolidated review; no disposition has been recorded.",
                  "owner_role": owner}
        comments.append(native)
        mapped.append({"native_comment_id": native_id, "record": deepcopy(item),
                       "reviewer_role": values["reviewer_role"],
                       "notes": ["Source proposed_edit and other extension columns are preserved in record.values; no native patch or decision was inferred."]})
    cycle = {"schema": CYCLE_SCHEMA, "id": cycle_id,
             "base_document_sha256": native_digest(document),
             "base_report_receipt_sha256": receipt, "target_report_receipt_sha256": receipt,
             "new_version": new_version, "comments": sorted(comments, key=lambda c: c["id"])}
    return {"schema": "uiowa-review-import-native-preparation/v1", "status": "PREPARED_NOT_APPLIED",
            "cycle": cycle, "staged": staged, "mapped": mapped,
            "native_unresolved": native_unresolved, "already_present": already_present,
            "summary": {**staged["summary"], "native_open_comments": len(comments),
                        "native_unresolved": len(native_unresolved), "already_present": len(already_present)},
            "cycle_sha256": native_digest(cycle)}


def load_native():
    root = Path(__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from revenue.uiowa_rfq_18649_review_cycle import review
    except ImportError as exc:
        raise ImportFormatError("published UIOWA-039 review_cycle and parent compiler must exist in this checkout") from exc
    return review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path)
    parser.add_argument("document", type=Path)
    parser.add_argument("report", type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--cycle-id", required=True)
    parser.add_argument("--new-version", required=True)
    parser.add_argument("--namespace", default=NAMESPACE)
    parser.add_argument("--prior", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="New preparation directory")
    parser.add_argument("--apply-open", action="store_true", help="Apply only OPEN comments through native build_bundle; no approvals or proposed edits")
    args = parser.parse_args()
    try:
        native = load_native()
        document, report = native.load(args.document), native.load(args.report)
        native.verify_inspection(report)
        native.validate_document(document, report)
        prior = native.load(args.prior) if args.prior else None
        prepared = prepare_cycle(args.csv.read_bytes(), args.source_id, args.csv.name, document, report,
                                 args.cycle_id, args.new_version, namespace=args.namespace,
                                 document_name=args.document.name, prior=prior, validate_text=native.text)
        # Native validation and bundle generation happen before writing any output.
        bundle = None
        # An entirely unresolved import still has valuable source diagnostics.
        # A duplicate-only or empty import is a no-op, not another draft revision.
        # In all three cases retain the preparation without claiming application.
        if args.apply_open and prepared["cycle"]["comments"]:
            bundle = native.build_bundle(report, report, document, prepared["cycle"])
        args.out.mkdir(parents=True, exist_ok=False)
        (args.out / "preparation.json").write_bytes(canonical(prepared) + b"\n")
        (args.out / "native-comments.json").write_bytes(native.canonical(prepared["cycle"]))
        if bundle is not None:
            native.write_bundle(args.out / "native-bundle", bundle)
            native.verify_bundle(args.out / "native-bundle")
            receipt = {"status": "APPLIED_OPEN_COMMENTS", "cycle_sha256": prepared["cycle_sha256"],
                       "native_manifest_sha256": hashlib.sha256(bundle["manifest.json"]).hexdigest(),
                       "summary": prepared["summary"]}
            (args.out / "application-receipt.json").write_bytes(canonical(receipt) + b"\n")
        print(json.dumps(prepared["summary"], sort_keys=True))
        return 1 if prepared["staged"]["unresolved"] or prepared["staged"]["unkeyed_rows"] or prepared["native_unresolved"] else 0
    except (OSError, TypeError, ValueError, KeyError) as exc:
        parser.exit(2, f"native import error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
