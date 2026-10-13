#!/usr/bin/env python3
"""Pack opaque Muhlnickel bytes into record-aligned cloud carrier pages.

This program never decodes a gate record and never evaluates container logic.
It performs byte transport, content addressing, and placement-manifest creation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build(genome_path: Path, repo_root: Path, output: Path) -> dict[str, Any]:
    genome = read_json(genome_path)
    if genome.get("format") != "MUHLCLOUD1":
        raise ValueError("unsupported cloud genome format")

    source_spec = genome["source"]
    record_spec = genome["record"]
    geometry = genome["carrier_geometry"]
    source_path = (repo_root / source_spec["path"]).resolve()
    source = source_path.read_bytes()

    measured_sha = sha256(source)
    measured_bytes = len(source)
    stride = int(record_spec["stride_bytes"])
    record_count = int(record_spec["count"])
    page_records = int(geometry["page_records"])
    page_bytes = page_records * stride

    if measured_sha != source_spec["sha256"]:
        raise ValueError(f"source sha256 differs: measured={measured_sha}")
    if measured_bytes != int(source_spec["bytes"]):
        raise ValueError(f"source byte count differs: measured={measured_bytes}")
    if measured_bytes != stride * record_count:
        raise ValueError("source byte count is not record_stride * record_count")
    if page_bytes != int(geometry["page_bytes"]):
        raise ValueError("page_bytes differs from page_records * record_stride")

    output.mkdir(parents=True, exist_ok=True)
    pages_dir = output / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    pages: list[dict[str, Any]] = []
    for index, byte_start in enumerate(range(0, measured_bytes, page_bytes)):
        payload = source[byte_start : byte_start + page_bytes]
        byte_end = byte_start + len(payload)
        page_name = f"page-{index:04d}.mno.page"
        (pages_dir / page_name).write_bytes(payload)
        pages.append(
            {
                "index": index,
                "path": f"pages/{page_name}",
                "byte_start": byte_start,
                "byte_end_exclusive": byte_end,
                "bytes": len(payload),
                "record_start": byte_start // stride,
                "record_end_exclusive": byte_end // stride,
                "sha256": sha256(payload),
                "provider": None,
            }
        )

    if len(pages) != int(geometry["page_count"]):
        raise ValueError(f"page count differs: measured={len(pages)}")

    generation_id = f"muhlcloud1-{measured_sha}"
    manifest = {
        "format": "MUHLCLOUD1_GENERATION",
        "generation_id": generation_id,
        "source": {
            "repo_path": source_spec["path"],
            "layout_repo_path": source_spec["layout_path"],
            "bytes": measured_bytes,
            "sha256": measured_sha,
        },
        "record": record_spec,
        "carrier_geometry": geometry,
        "roles": genome["roles"],
        "pages": pages,
    }
    head = {
        "format": "MUHLCLOUD1_HEAD",
        "active_generation": generation_id,
        "generation_manifest_provider": None,
        "page_providers": [None for _ in pages],
    }
    write_json(output / "generation.json", manifest)
    write_json(output / "HEAD.json", head)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--genome", required=True, type=Path)
    parser.add_argument("--repo-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = build(args.genome.resolve(), args.repo_root.resolve(), args.output.resolve())
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
