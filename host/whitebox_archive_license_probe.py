#!/usr/bin/env python3
"""Read exact GGUF license metadata without loading or hashing model tensors."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import mmap
import os
from pathlib import Path
import re
import struct
import sys


SCHEMA_VERSION = "commons-whitebox-archive-license-probe/v1"
INVENTORY_BLOB_SHA = "dfc9923c290837151454b086df1af25aed724330"
INVENTORY_TREE_SHA256 = "d67234a1e0d69dba621f4073ecfbaf77db298134d3bd516fba30fc2062467bc9"
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
MODEL_NAMES = [
    "Llama-3.3-70B-Instruct-Q4_K_M.gguf",
    "SmolLM2-360M-Instruct-Q8_0.gguf",
    "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf",
    "gemma-4-31B-it-qat-UD-Q4_K_XL.gguf",
    "google_gemma-3-27b-it-Q4_K_M.gguf",
    "mistralai_Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf",
    "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf",
    "phi-4-Q4_K_M.gguf",
]
SCALAR = {
    0: ("<B", 1),
    1: ("<b", 1),
    2: ("<H", 2),
    3: ("<h", 2),
    4: ("<I", 4),
    5: ("<i", 4),
    6: ("<f", 4),
    7: ("<?", 1),
    10: ("<Q", 8),
    11: ("<q", 8),
    12: ("<d", 8),
}
MIXTRAL_PRIMARY_EVIDENCE = {
    "provider": "HUGGING_FACE_MODEL_API",
    "repository_id": "mistralai/Mixtral-8x7B-Instruct-v0.1",
    "revision": "eba92302a2861cdc0098cc54bc9f17cb2c47eb61",
    "license_id": "apache-2.0",
    "retrieved_date": "2026-08-26",
    "url": "https://huggingface.co/mistralai/Mixtral-8x7B-Instruct-v0.1/tree/eba92302a2861cdc0098cc54bc9f17cb2c47eb61",
    "scope": "BASE_MODEL_PRIMARY_SOURCE_ONLY",
}


class ProbeError(AssertionError):
    """The measured GGUF license probe violates its public contract."""


def _read_string(mm: mmap.mmap, offset: int) -> tuple[bytes, int]:
    length = struct.unpack_from("<Q", mm, offset)[0]
    offset += 8
    return bytes(mm[offset : offset + length]), offset + length


def _read_value(mm: mmap.mmap, offset: int, value_type: int, keep: bool):
    if value_type == 8:
        raw, offset = _read_string(mm, offset)
        return (raw.decode("utf-8", "replace") if keep else None), offset
    if value_type == 9:
        element_type = struct.unpack_from("<I", mm, offset)[0]
        count = struct.unpack_from("<Q", mm, offset + 4)[0]
        offset += 12
        values = [] if keep else None
        for _ in range(count):
            value, offset = _read_value(mm, offset, element_type, keep)
            if keep:
                values.append(value)
        return values, offset
    if value_type not in SCALAR:
        raise ProbeError("unsupported GGUF metadata type %d" % value_type)
    fmt, size = SCALAR[value_type]
    value = struct.unpack_from(fmt, mm, offset)[0]
    return (value if keep else None), offset + size


def _wanted_key(key: str) -> bool:
    return key in {
        "general.name",
        "general.basename",
        "general.license",
        "general.license.link",
    } or (
        key.startswith("general.base_model.")
        and (key.endswith(".name") or key.endswith(".repo_url"))
    )


def read_gguf_prefix(path: Path) -> dict:
    with path.open("rb") as handle:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            if mm[:4] != b"GGUF":
                raise ProbeError("source is not GGUF")
            version = struct.unpack_from("<I", mm, 4)[0]
            tensor_count = struct.unpack_from("<Q", mm, 8)[0]
            metadata_count = struct.unpack_from("<Q", mm, 16)[0]
            offset = 24
            alignment = 32
            fields = {}
            for _ in range(metadata_count):
                raw_key, offset = _read_string(mm, offset)
                key = raw_key.decode("utf-8", "replace")
                value_type = struct.unpack_from("<I", mm, offset)[0]
                offset += 4
                keep = (_wanted_key(key) or key == "general.alignment") and value_type != 9
                value, offset = _read_value(mm, offset, value_type, keep)
                if keep and _wanted_key(key):
                    fields[key] = value
                if key == "general.alignment" and value_type != 9:
                    alignment = int(value)
            for _ in range(tensor_count):
                _, offset = _read_string(mm, offset)
                dimensions = struct.unpack_from("<I", mm, offset)[0]
                offset += 4 + (8 * dimensions) + 4 + 8
            prefix_bytes = ((offset + alignment - 1) // alignment) * alignment
            return {
                "gguf_version": version,
                "file_size_bytes": len(mm),
                "metadata_prefix_bytes": prefix_bytes,
                "metadata_prefix_sha256": hashlib.sha256(mm[:prefix_bytes]).hexdigest(),
                "fields": fields,
            }


def _resolve_model(models_root: Path, filename: str) -> tuple[Path, str]:
    direct = models_root / filename
    if direct.is_file():
        return direct, "MODELS_ROOT"
    removed = models_root / "_removed" / filename
    if removed.is_file():
        return removed, "MODELS_ROOT_REMOVED_BY_ROUTE"
    raise ProbeError("model source is missing: %s" % filename)


def scan_models(models_root: Path) -> dict:
    records = []
    for filename in MODEL_NAMES:
        path, route = _resolve_model(models_root, filename)
        measured = read_gguf_prefix(path)
        fields = measured.pop("fields")
        embedded_id = fields.get("general.license")
        external = []
        if filename == "mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf":
            external.append(dict(MIXTRAL_PRIMARY_EVIDENCE))
        records.append(
            {
                "archive_group": filename[:-5],
                "source_filename": filename,
                "source_relative_route": route,
                **measured,
                "general_name": fields.get("general.name"),
                "general_basename": fields.get("general.basename"),
                "embedded_license": {
                    "status": "PRESENT" if embedded_id else "NOT_EMBEDDED",
                    "license_id": embedded_id,
                    "license_link": fields.get("general.license.link"),
                },
                "embedded_base_model_repositories": sorted(
                    value
                    for key, value in fields.items()
                    if key.endswith(".repo_url") and isinstance(value, str)
                ),
                "external_base_model_evidence": external,
                "quantized_copy_source_verified": False,
                "transfer_cleared": False,
            }
        )

    license_counts = Counter(
        row["embedded_license"]["license_id"]
        for row in records
        if row["embedded_license"]["license_id"]
    )
    probe = {
        "schema_version": SCHEMA_VERSION,
        "probe_date": "2026-08-26",
        "inventory_binding": {
            "inventory_path": "revenue/ip/whitebox_archive_inventory.json",
            "inventory_blob_sha": INVENTORY_BLOB_SHA,
            "archive_tree_sha256": INVENTORY_TREE_SHA256,
        },
        "scope": {
            "source_location_class": "OWNER_LOCAL_GGUF_MODELS",
            "source_absolute_paths_published": False,
            "model_tensor_bytes_loaded": False,
            "full_model_sha256_computed": False,
            "measured_region": "GGUF_HEADER_METADATA_TENSOR_INDEX_PREFIX",
        },
        "summary": {
            "expected_models": len(MODEL_NAMES),
            "located_models": len(records),
            "embedded_license_present": sum(
                row["embedded_license"]["status"] == "PRESENT" for row in records
            ),
            "embedded_license_missing": sum(
                row["embedded_license"]["status"] == "NOT_EMBEDDED" for row in records
            ),
            "embedded_license_counts": [
                {"license_id": key, "models": license_counts[key]}
                for key in sorted(license_counts)
            ],
            "metadata_prefix_total_bytes": sum(
                row["metadata_prefix_bytes"] for row in records
            ),
        },
        "records": records,
        "commercial_readiness": {
            "transfer_cleared": False,
            "archive_license_offer_ready": False,
            "pricing_ready": False,
            "remaining_evidence": [
                "EXACT_QUANTIZED_COPY_SOURCE_PROVENANCE",
                "UPSTREAM_TERMS_AND_NOTICE_REVIEW",
                "ARCHIVE_REDACTION_AND_MANUAL_SAMPLE_REVIEW",
            ],
        },
    }
    validate_probe(probe)
    return probe


def validate_probe(probe: dict) -> dict:
    if probe.get("schema_version") != SCHEMA_VERSION:
        raise ProbeError("unexpected schema version")
    binding = probe["inventory_binding"]
    if binding["inventory_blob_sha"] != INVENTORY_BLOB_SHA:
        raise ProbeError("inventory blob binding drift")
    if binding["archive_tree_sha256"] != INVENTORY_TREE_SHA256:
        raise ProbeError("archive tree binding drift")
    if not HEX_40.fullmatch(binding["inventory_blob_sha"]):
        raise ProbeError("invalid inventory blob")
    if not HEX_64.fullmatch(binding["archive_tree_sha256"]):
        raise ProbeError("invalid archive tree digest")

    records = probe["records"]
    names = [row["source_filename"] for row in records]
    if names != MODEL_NAMES:
        raise ProbeError("model records must be exact and ordered")
    if len({row["archive_group"] for row in records}) != len(MODEL_NAMES):
        raise ProbeError("archive groups must be unique")
    for row in records:
        if row["archive_group"] != row["source_filename"][:-5]:
            raise ProbeError("archive group/source filename drift")
        if row["source_relative_route"] not in {
            "MODELS_ROOT",
            "MODELS_ROOT_REMOVED_BY_ROUTE",
        }:
            raise ProbeError("source route publishes an unsupported location")
        if row["file_size_bytes"] <= row["metadata_prefix_bytes"] or row[
            "metadata_prefix_bytes"
        ] <= 0:
            raise ProbeError("invalid measured prefix extent")
        if not HEX_64.fullmatch(row["metadata_prefix_sha256"]):
            raise ProbeError("invalid metadata prefix digest")
        embedded = row["embedded_license"]
        expected_status = "PRESENT" if embedded["license_id"] else "NOT_EMBEDDED"
        if embedded["status"] != expected_status:
            raise ProbeError("embedded license status drift")
        if row["quantized_copy_source_verified"] or row["transfer_cleared"]:
            raise ProbeError("metadata probe cannot clear quantized-copy transfer")
        external = row["external_base_model_evidence"]
        if row["source_filename"].startswith("mixtral-"):
            if external != [MIXTRAL_PRIMARY_EVIDENCE]:
                raise ProbeError("Mixtral primary-source evidence drift")
            if embedded["status"] != "NOT_EMBEDDED":
                raise ProbeError("Mixtral frozen reading must remain not embedded")
        elif external:
            raise ProbeError("unexpected external base-model evidence")

    summary = probe["summary"]
    embedded_ids = [
        row["embedded_license"]["license_id"]
        for row in records
        if row["embedded_license"]["license_id"]
    ]
    counts = Counter(embedded_ids)
    expected_counts = [
        {"license_id": key, "models": counts[key]} for key in sorted(counts)
    ]
    if summary["expected_models"] != 8 or summary["located_models"] != 8:
        raise ProbeError("model coverage drift")
    if summary["embedded_license_present"] != len(embedded_ids):
        raise ProbeError("embedded-license present count drift")
    if summary["embedded_license_missing"] != 8 - len(embedded_ids):
        raise ProbeError("embedded-license missing count drift")
    if summary["embedded_license_counts"] != expected_counts:
        raise ProbeError("embedded-license summary drift")
    if summary["metadata_prefix_total_bytes"] != sum(
        row["metadata_prefix_bytes"] for row in records
    ):
        raise ProbeError("metadata-prefix byte summary drift")

    scope = probe["scope"]
    if scope["source_absolute_paths_published"]:
        raise ProbeError("absolute source paths may not be published")
    if scope["model_tensor_bytes_loaded"] or scope["full_model_sha256_computed"]:
        raise ProbeError("probe scope exceeds measured behavior")
    rendered = json.dumps(probe, ensure_ascii=False).lower()
    if "c:\\\\" in rendered or "c:/llm/" in rendered or "c:/users/" in rendered:
        raise ProbeError("probe leaks an absolute local path")

    readiness = probe["commercial_readiness"]
    if any(
        readiness[key]
        for key in ("transfer_cleared", "archive_license_offer_ready", "pricing_ready")
    ):
        raise ProbeError("commercial readiness exceeds metadata evidence")
    expected_remaining = {
        "EXACT_QUANTIZED_COPY_SOURCE_PROVENANCE",
        "UPSTREAM_TERMS_AND_NOTICE_REVIEW",
        "ARCHIVE_REDACTION_AND_MANUAL_SAMPLE_REVIEW",
    }
    if set(readiness["remaining_evidence"]) != expected_remaining:
        raise ProbeError("remaining evidence contract drift")

    return {
        "status": "VALID",
        "models": 8,
        "embedded_license_present": len(embedded_ids),
        "embedded_license_missing": 8 - len(embedded_ids),
        "metadata_prefix_total_bytes": summary["metadata_prefix_total_bytes"],
        "transfer_cleared": False,
    }


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProbeError("probe must be a JSON object")
    return value


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan")
    scan.add_argument("models_root", type=Path)
    scan.add_argument("--output", type=Path, required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("probe", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "scan":
        probe = scan_models(args.models_root)
        write_json(args.output, probe)
        result = validate_probe(probe)
    else:
        result = validate_probe(read_json(args.probe))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProbeError as exc:
        print("INVALID: %s" % exc, file=sys.stderr)
        raise SystemExit(2)
