#!/usr/bin/env python3
"""Measure and verify an opaque cloud generation by reconstructing its page bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def measure(manifest_path: Path, source_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    source = source_path.read_bytes()
    source_spec = manifest["source"]
    pages = sorted(manifest["pages"], key=lambda item: item["index"])

    chunks: list[bytes] = []
    measured_pages: list[dict[str, Any]] = []
    cursor = 0
    for page in pages:
        payload = (root / page["path"]).read_bytes()
        measured = {
            "index": page["index"],
            "declared_byte_start": page["byte_start"],
            "declared_byte_end_exclusive": page["byte_end_exclusive"],
            "measured_bytes": len(payload),
            "measured_sha256": sha256(payload),
            "starts_at_running_cursor": page["byte_start"] == cursor,
            "ends_at_running_cursor": page["byte_end_exclusive"] == cursor + len(payload),
            "matches_declared_bytes": len(payload) == page["bytes"],
            "matches_declared_sha256": sha256(payload) == page["sha256"],
        }
        measured_pages.append(measured)
        chunks.append(payload)
        cursor += len(payload)

    reconstructed = b"".join(chunks)
    source_digest = sha256(source)
    record_stride = int(manifest["record"]["stride_bytes"])
    page_indices_contiguous = [page["index"] for page in pages] == list(range(len(pages)))
    source_declaration_matches = (
        len(source) == int(source_spec["bytes"])
        and source_digest == source_spec["sha256"]
    )
    generation_id_matches_source = (
        manifest["generation_id"] == f"muhlcloud1-{source_digest}"
    )
    coverage_starts_at_zero = bool(pages) and pages[0]["byte_start"] == 0
    coverage_ends_at_source_bytes = cursor == len(source)
    all_page_boundaries_on_record_stride = all(
        page["byte_start"] % record_stride == 0
        and page["byte_end_exclusive"] % record_stride == 0
        for page in pages
    )
    pages_match_declarations = all(
        page["starts_at_running_cursor"]
        and page["ends_at_running_cursor"]
        and page["matches_declared_bytes"]
        and page["matches_declared_sha256"]
        for page in measured_pages
    )
    byte_equal_measured = reconstructed == source
    verification_passed = all(
        (
            manifest.get("format") == "MUHLCLOUD1_GENERATION",
            source_declaration_matches,
            generation_id_matches_source,
            page_indices_contiguous,
            coverage_starts_at_zero,
            coverage_ends_at_source_bytes,
            all_page_boundaries_on_record_stride,
            pages_match_declarations,
            byte_equal_measured,
        )
    )
    receipt = {
        "format": "MUHLCLOUD1_MEASUREMENT",
        "generation_id": manifest["generation_id"],
        "source_bytes_measured": len(source),
        "source_sha256_measured": source_digest,
        "source_declaration_matches": source_declaration_matches,
        "generation_id_matches_source": generation_id_matches_source,
        "reconstructed_bytes_measured": len(reconstructed),
        "reconstructed_sha256_measured": sha256(reconstructed),
        "byte_equal_measured": byte_equal_measured,
        "page_count_measured": len(pages),
        "page_indices_contiguous": page_indices_contiguous,
        "page_bytes_measured": [item["measured_bytes"] for item in measured_pages],
        "coverage_starts_at_zero": coverage_starts_at_zero,
        "coverage_ends_at_source_bytes": coverage_ends_at_source_bytes,
        "all_page_boundaries_on_record_stride": all_page_boundaries_on_record_stride,
        "pages_match_declarations": pages_match_declarations,
        "verification_passed": verification_passed,
        "pages": measured_pages,
    }
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    receipt = measure(args.manifest.resolve(), args.source.resolve())
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
