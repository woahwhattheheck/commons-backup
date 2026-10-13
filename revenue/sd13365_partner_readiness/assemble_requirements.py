#!/usr/bin/env python3
"""Materialize and validate the canonical SD13365 evidence matrix payload."""
from __future__ import annotations

import argparse
import base64
import binascii
import gzip
import hashlib
from pathlib import Path

import matrix
import safe_output

EXPECTED_SHA256 = "e6e857e1df33a6b6d486252fd1e0f1f243fdf0818b48ebfe6a80525e5dc19f42"
MAX_COMPRESSED_BYTES = 16_384
MAX_MATRIX_BYTES = 65_536


class AssemblyError(ValueError):
    """Raised when the source payload cannot be trusted or materialized."""


def decode_payload(payload_path: Path) -> bytes:
    if payload_path.is_symlink():
        raise AssemblyError("payload must not be a symlink")
    try:
        encoded = payload_path.read_bytes().strip()
    except OSError as exc:
        raise AssemblyError(f"cannot read payload: {exc}") from exc
    if len(encoded) > MAX_COMPRESSED_BYTES * 2:
        raise AssemblyError("encoded payload exceeds the bounded source size")
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AssemblyError("payload is not canonical base64") from exc
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise AssemblyError("compressed payload exceeds the bounded source size")
    try:
        data = gzip.decompress(compressed)
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise AssemblyError("payload is not a valid gzip stream") from exc
    if len(data) > MAX_MATRIX_BYTES:
        raise AssemblyError("decoded matrix exceeds the bounded output size")
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED_SHA256:
        raise AssemblyError(f"matrix SHA-256 mismatch: {digest}")
    try:
        parsed = matrix.loads_strict(data.decode("utf-8"))
        matrix.validate_matrix(parsed)
    except (UnicodeDecodeError, matrix.MatrixError) as exc:
        raise AssemblyError(f"decoded matrix validation failed: {exc}") from exc
    return data


def write_atomic(output_path: Path, data: bytes) -> None:
    try:
        safe_output.atomic_write_bytes(output_path, data)
    except safe_output.OutputCustodyError as exc:
        raise AssemblyError(f"unsafe output custody: {exc}") from exc


def assemble(payload_path: Path, output_path: Path) -> str:
    data = decode_payload(payload_path)
    write_atomic(output_path, data)
    return hashlib.sha256(data).hexdigest()


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--payload",
        type=Path,
        default=here / "requirements.json.gz.b64",
        help="bounded canonical source payload",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=here / "requirements.json",
        help="materialized strict JSON matrix",
    )
    args = parser.parse_args(argv)
    try:
        digest = assemble(args.payload, args.output)
    except AssemblyError as exc:
        parser.exit(2, f"assembly error: {exc}\n")
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
