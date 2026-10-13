#!/usr/bin/env python3
"""Reproducible, offline packaging of RFQ 18649 non-authoritative handoffs.

No extraction, networking, scoring, compiler receipt recomputation, or approval.
An independently supplied archive digest detects whole-bundle replacement;
self-contained checksums alone do not establish provenance or authenticity.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import stat
import sys
import zipfile
from pathlib import Path

SCHEMA = "uiowa-rfq18649-delivery-bundle/v1"
HANDOFF_SCHEMA = "uiowa-rfq18649-analyst-handoff-draft/v1"
DEMO_SCHEMA = "SYNTHETIC_UI_DEMO_NOT_COMPILER_OUTPUT"
COMPILER_REPORT_SCHEMA = "uiowa-rfq18649-workshare-report/v2"
SCOPE = "BYTE_INTEGRITY_AND_HANDOFF_CROSS_REFERENCES_ONLY"
AUTHORITY_KEYS = (
    "buyer_approved", "prime_approved", "current_evidence_review_authority",
    "submission_authorized", "signature_authorized",
    "invoice_or_payment_authorized", "recognized_revenue",
)
CELLS = frozenset((g, d) for g in ("ESS", "RIS", "IAM") for d in (
    "software_development", "security", "deployment", "ai_readiness"))
# The parent compiler v2 uses "software"; the existing UI demo uses the long key.
# Keep CELLS as the legacy/demo public constant and preserve the input bytes.
COMPILER_CELLS = frozenset((g, d) for g in ("ESS", "RIS", "IAM") for d in (
    "software", "security", "deployment", "ai_readiness"))
DISPOSITIONS = frozenset(("UNREVIEWED", "NEEDS_EVIDENCE", "DISCUSS_WITH_PRIME",
                          "TECHNICAL_DRAFT_NOTE"))
MEMBERS = frozenset(("report.json", "handoff.json", "README.txt", "manifest.json"))
MAX_JSON_BYTES = 1024 * 1024
MAX_ARCHIVE_BYTES = 2 * MAX_JSON_BYTES + 65536
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class BundleError(ValueError):
    """A format, consistency, or integrity failure with a stable diagnostic code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise BundleError(code, message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, allow_nan=False,
                       sort_keys=True, indent=2) + "\n").encode("utf-8")


def parse_object(data: bytes, label: str) -> dict:
    require(isinstance(data, bytes) and len(data) <= MAX_JSON_BYTES,
            "JSON_SIZE", f"{label} must be at most 1 MiB of UTF-8 JSON bytes")

    def unique(pairs):
        obj = {}
        for key, value in pairs:
            require(key not in obj, "JSON_DUPLICATE_KEY", f"{label}: duplicate JSON key")
            obj[key] = value
        return obj

    def finite(_):
        raise BundleError("JSON_NONFINITE", f"{label}: non-finite JSON number")

    def finite_float(value):
        number = float(value)
        require(math.isfinite(number), "JSON_NONFINITE", f"{label}: non-finite JSON number")
        return number

    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=unique,
                         parse_constant=finite, parse_float=finite_float)
        # JSON escapes can decode into unpaired surrogates. Validate all text
        # before any manifest binding is serialized; fail with a stable error
        # rather than an uncaught UnicodeEncodeError. Walk iteratively.
        pending = [obj]
        while pending:
            value = pending.pop()
            if isinstance(value, str):
                value.encode("utf-8")
            elif isinstance(value, dict):
                pending.extend(value.keys())
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
    except BundleError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise BundleError("JSON_INVALID", f"{label}: invalid UTF-8 JSON") from exc
    require(isinstance(obj, dict), "JSON_OBJECT", f"{label} must be an object")
    return obj


def matrix(rows, label: str, *, expected_cells: frozenset = CELLS) -> dict:
    require(isinstance(rows, list) and len(rows) == len(expected_cells),
            "CELL_COVERAGE", f"{label} must contain all 12 assessment cells")
    result = {}
    for row in rows:
        require(isinstance(row, dict), "CELL_SHAPE", f"{label}: cell must be an object")
        group, dimension = row.get("group"), row.get("dimension")
        require(isinstance(group, str) and isinstance(dimension, str),
                "CELL_SHAPE", f"{label}: group and dimension must be strings")
        key = (group, dimension)
        require(key in expected_cells and key not in result, "CELL_COVERAGE",
                f"{label}: unknown or duplicate assessment cell")
        result[key] = row
    return result


def validate_pair(report_bytes: bytes, handoff_bytes: bytes) -> dict:
    """Validate the v1 handoff contract, not the truth of assessment findings."""
    report = parse_object(report_bytes, "report")
    handoff = parse_object(handoff_bytes, "handoff")
    require(report.get("mode") == "UNTRUSTED_INSPECTION", "REPORT_MODE",
            "Only untrusted inspection reports belong in this draft bundle")
    trust = report.get("trust")
    require(isinstance(trust, dict)
            and trust.get("current_evidence_review_authority") is False
            and trust.get("authority_root_supplied_out_of_band") is False,
            "REPORT_AUTHORITY", "Report must explicitly carry no rooted/current authority")
    receipt = report.get("receipt_sha256")
    require(isinstance(receipt, str) and HEX64.fullmatch(receipt) is not None,
            "REPORT_RECEIPT", "Report receipt must be a lowercase SHA-256 string")
    aggregate = report.get("aggregate_state")
    require(isinstance(aggregate, str) and bool(aggregate), "REPORT_AGGREGATE",
            "Report aggregate state is required")
    synthetic = report.get("synthetic_demo", False)
    require(type(synthetic) is bool, "SYNTHETIC_LABEL", "Synthetic flag must be a boolean")
    require((report.get("schema") == DEMO_SCHEMA) == synthetic,
            "SYNTHETIC_LABEL", "UI demo schema and synthetic flag must agree")
    require(isinstance(report.get("schema"), str) and bool(report["schema"]),
            "REPORT_SCHEMA", "Report schema is required")
    require(handoff.get("schema") == HANDOFF_SCHEMA
            and handoff.get("status") == "DRAFT_NON_AUTHORITATIVE",
            "HANDOFF_SCHEMA", "Expected the v1 non-authoritative draft handoff")
    authority = handoff.get("authority")
    require(isinstance(authority, dict) and set(authority) == set(AUTHORITY_KEYS)
            and all(authority[k] is False for k in AUTHORITY_KEYS),
            "HANDOFF_AUTHORITY", "Every v1 handoff authority flag must be explicitly false")
    require(handoff.get("report_receipt_sha256") == receipt
            and handoff.get("report_mode") == report["mode"]
            and handoff.get("aggregate_state") == aggregate,
            "REPORT_BINDING", "Handoff receipt, mode, and aggregate must match this report")
    require(handoff.get("synthetic_demo") is synthetic, "SYNTHETIC_LABEL",
            "Handoff must preserve the report's synthetic classification")
    # Named schemas have exact cell vocabularies. Unknown non-demo schemas
    # retain the legacy external-report road, while also accepting one complete
    # canonical grid. Neither a union of vocabularies nor key rewriting is used.
    # This is shape compatibility only, never compiler semantic verification.
    rows = report.get("assessment_matrix")
    if report["schema"] == COMPILER_REPORT_SCHEMA:
        expected_cells = COMPILER_CELLS
    elif synthetic:
        expected_cells = CELLS
    elif isinstance(rows, list) and any(
            isinstance(row, dict) and row.get("dimension") == "software" for row in rows):
        expected_cells = COMPILER_CELLS
    else:
        expected_cells = CELLS
    cells = matrix(rows, "report", expected_cells=expected_cells)
    notes = matrix(handoff.get("cell_notes"), "handoff", expected_cells=expected_cells)
    for key in expected_cells:
        status = cells[key].get("status")
        require(isinstance(status, str) and bool(status)
                and notes[key].get("compiler_status") == status,
                "CELL_BINDING", "Each note must preserve its report cell status")
        disposition = notes[key].get("disposition")
        require(isinstance(disposition, str) and disposition in DISPOSITIONS,
                "NOTE_DISPOSITION", "Unsupported v1 analyst disposition")
        require(isinstance(notes[key].get("analyst_note"), str),
                "NOTE_SHAPE", "Analyst notes must be strings")
    return {"report_receipt_sha256": receipt, "synthetic_demo": synthetic,
            "report_mode": report["mode"], "aggregate_state": aggregate}


def bundle_notes(synthetic: bool) -> bytes:
    label = ("SYNTHETIC DEMONSTRATION - NOT UNIVERSITY FINDINGS" if synthetic
             else "DRAFT ANALYST MATERIAL - NOT AN APPROVED ASSESSMENT")
    return (label + "\n\n"
            "This archive preserves report.json and handoff.json as exact input bytes.\n"
            "manifest.json describes packaging integrity and handoff cross-references only.\n"
            "The synthetic_demo flag identifies UI demo mode only; false does not prove real data.\n"
            "No compiler receipt is recomputed. No evidence truth, source authenticity,\n"
            "maturity score, confidentiality clearance, approval, signature, submission,\n"
            "payment, or recognized revenue is established.\n"
            "Self-contained hashes are not signatures. Compare the entire archive SHA-256\n"
            "with a digest received through an independent trusted channel.\n"
            "Do not place private evidence in the public repository or public demo.\n"
            "The bundle tool makes no network requests and does not extract archives.\n").encode("utf-8")


def payloads(report: bytes, handoff: bytes) -> dict[str, bytes]:
    binding = validate_pair(report, handoff)
    files = {"report.json": report, "handoff.json": handoff,
             "README.txt": bundle_notes(binding["synthetic_demo"])}
    manifest = {
        "schema": SCHEMA, "status": "DRAFT_NON_AUTHORITATIVE",
        "verification_scope": SCOPE, "binding": binding,
        "parent_compiler_receipt_recomputed": False,
        "authority": {key: False for key in AUTHORITY_KEYS},
        "entries": [{"path": name, "bytes": len(data), "sha256": sha256(data)}
                    for name, data in sorted(files.items())],
    }
    files["manifest.json"] = canonical(manifest)
    return files


def encode_archive(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED,
                         allowZip64=False) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, data)
    return buffer.getvalue()


def build_bundle(report: bytes, handoff: bytes) -> bytes:
    """Return deterministic ZIP bytes; caller chooses where to write them."""
    return encode_archive(payloads(report, handoff))


def verify_bundle(data: bytes, expected_sha256: str | None = None) -> dict:
    require(isinstance(data, bytes) and 0 < len(data) <= MAX_ARCHIVE_BYTES,
            "ARCHIVE_SIZE", "Archive is empty or exceeds the supported size")
    digest = sha256(data)
    if expected_sha256 is not None:
        require(isinstance(expected_sha256, str)
                and HEX64.fullmatch(expected_sha256) is not None,
                "EXPECTED_DIGEST", "Expected digest must be a lowercase SHA-256 string")
        require(digest == expected_sha256, "ARCHIVE_DIGEST", "Independent archive digest mismatch")
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            infos = archive.infolist()
            require(len(infos) == len(MEMBERS) and {i.filename for i in infos} == MEMBERS,
                    "ARCHIVE_MEMBERS", "Expected exactly the four unique v1 bundle members")
            for info in infos:
                cap = MAX_JSON_BYTES if info.filename in ("report.json", "handoff.json") else 16384
                require(0 <= info.file_size <= cap and info.compress_type == zipfile.ZIP_STORED
                        and not info.flag_bits & 1,
                        "ARCHIVE_FORMAT", "Member exceeds limits or uses unsupported ZIP encoding")
            files = {info.filename: archive.read(info) for info in infos}
    except BundleError:
        raise
    except (zipfile.BadZipFile, ValueError, RuntimeError, NotImplementedError, EOFError) as exc:
        raise BundleError("ARCHIVE_INVALID", "Malformed or damaged ZIP archive") from exc
    parse_object(files["manifest.json"], "manifest")
    expected = payloads(files["report.json"], files["handoff.json"])
    require(files == expected, "MANIFEST_MISMATCH", "Manifest or bundle labels do not match payloads")
    require(data == encode_archive(expected), "ARCHIVE_NONCANONICAL",
            "Archive metadata, order, or trailing bytes differ from the canonical v1 format")
    binding = validate_pair(files["report.json"], files["handoff.json"])
    return {"status": "PACKAGING_INTEGRITY_VERIFIED", "verification_scope": SCOPE,
            "archive_sha256": digest, "independent_digest_match":
            True if expected_sha256 is not None else None,
            "parent_compiler_receipt_recomputed": False, "binding": binding,
            "authority": {key: False for key in AUTHORITY_KEYS},
            "member_sha256": {name: sha256(raw) for name, raw in sorted(files.items())}}


def read_bounded(path: Path, maximum: int) -> bytes:
    require(path.is_file(), "INPUT_FILE", "Input must be an existing regular file")
    with path.open("rb") as handle:
        data = handle.read(maximum + 1)
    require(len(data) <= maximum, "INPUT_SIZE", "Input exceeds its supported size")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("pack", help="Create a new draft ZIP; never overwrite a file")
    pack.add_argument("--report", required=True, type=Path)
    pack.add_argument("--handoff", required=True, type=Path)
    pack.add_argument("--output", required=True, type=Path)
    verify = commands.add_parser("verify", help="Inspect bytes without extracting them")
    verify.add_argument("archive", type=Path)
    verify.add_argument("--expected-sha256")
    args = parser.parse_args(argv)
    try:
        if args.command == "pack":
            data = build_bundle(read_bounded(args.report, MAX_JSON_BYTES),
                                read_bounded(args.handoff, MAX_JSON_BYTES))
            receipt = verify_bundle(data)
            with args.output.open("xb") as handle:
                handle.write(data)
        else:
            receipt = verify_bundle(read_bounded(args.archive, MAX_ARCHIVE_BYTES),
                                    args.expected_sha256)
        print(canonical(receipt).decode("utf-8"), end="")
        return 0
    except (BundleError, OSError) as exc:
        code = exc.code if isinstance(exc, BundleError) else "FILE_IO"
        print(json.dumps({"error": code, "message": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
