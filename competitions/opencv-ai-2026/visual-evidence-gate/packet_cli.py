#!/usr/bin/env python3
"""Local file interface for the canonical multi-photo quality extension.

Image paths are explicit local inputs, resolved relative to the image-map file.
No image URL, provider operation, or business decision is performed.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

from packet_quality import (
    MAX_IMAGE_BYTES, ProofCamError, canonical_bytes, compile_triage,
    strict_json_bytes, verify_triage,
)

MAX_JSON_BYTES = 1_048_576


def read_json(path: Path) -> Any:
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    return strict_json_bytes(raw, max_bytes=MAX_JSON_BYTES)


def local_inputs(packet_path: Path, map_path: Path, *, receipt_path: Path | None = None):
    packet = read_json(packet_path)
    image_map = read_json(map_path)
    if type(image_map) is not dict or any(
        type(key) is not str or type(value) is not str or not value
        for key, value in image_map.items()
    ):
        raise ProofCamError("image map must map image ids to nonempty local path strings")
    captured: dict[str, bytes] = {}

    def load(image_id: str) -> bytes:
        if image_id not in image_map:
            raise ProofCamError(f"image map is missing {image_id}")
        if image_id not in captured:
            image_path = Path(image_map[image_id])
            if not image_path.is_absolute():
                image_path = map_path.parent / image_path
            with image_path.open("rb") as stream:
                raw = stream.read(MAX_IMAGE_BYTES + 1)
            if len(raw) > MAX_IMAGE_BYTES:
                raise ProofCamError(f"image exceeds local byte limit: {image_id}")
            captured[image_id] = raw
        return captured[image_id]

    # Validation precedes calls to the local loader. The resulting set also
    # rejects unused map entries so the published receipt has one input set.
    if receipt_path is None:
        result = compile_triage(packet, load)
    else:
        result = read_json(receipt_path)
        # The verifier performs the full deterministic recompile itself.
        # Do not decode and measure every image once before calling it.
        verify_triage(packet, load, result)
    if set(image_map) != {item["image_id"] for item in packet["images"]}:
        raise ProofCamError("image map keys must exactly match packet image ids")
    return packet, load, result


def write_new_json(path: Path, value: Any) -> None:
    data = canonical_bytes(value) + b"\n"
    # Exclusive creation protects existing artifacts, including symlink targets.
    with path.open("xb") as stream:
        stream.write(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "verify"):
        child = commands.add_parser(name)
        child.add_argument("--packet", type=Path, required=True)
        child.add_argument("--image-map", type=Path, required=True)
        if name == "inspect":
            child.add_argument("--output", type=Path)
        else:
            child.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        packet, load, result = local_inputs(
            args.packet, args.image_map,
            receipt_path=args.receipt if args.command == "verify" else None,
        )
        if args.command == "verify":
            result = {"verified": True, "receipt_sha256": result["receipt_sha256"]}
        elif args.output is not None:
            write_new_json(args.output, result)
            result = {"written": str(args.output), "receipt_sha256": result["receipt_sha256"]}
        sys.stdout.buffer.write(canonical_bytes(result) + b"\n")
        return 0
    except (ProofCamError, OSError, ValueError) as exc:
        print(f"packet input/output error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
