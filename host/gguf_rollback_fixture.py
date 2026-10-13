#!/usr/bin/env python3
"""Synthetic GGUF v3 tensor-table rollback fixture.

Generates one tiny public GGUF v3 file inside a temporary directory, parses
the header / KV / tensor table to locate a named F32 payload, zeros that
payload, then restores the journaled bytes. This is not the generic
production-survival byte proof. No caller path. No network. No Titan write.
Not a customer GGUF, buyer signal, program submission, award, or cash.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import tempfile


MAGIC = b"GGUF"
GGUF_VERSION = 3
GGUF_TYPE_UINT8 = 0
GGUF_TYPE_INT8 = 1
GGUF_TYPE_UINT16 = 2
GGUF_TYPE_INT16 = 3
GGUF_TYPE_UINT32 = 4
GGUF_TYPE_INT32 = 5
GGUF_TYPE_FLOAT32 = 6
GGUF_TYPE_BOOL = 7
GGUF_TYPE_STRING = 8
GGUF_TYPE_ARRAY = 9
GGUF_TYPE_UINT64 = 10
GGUF_TYPE_INT64 = 11
GGUF_TYPE_FLOAT64 = 12
GGML_TYPE_F32 = 0
GGML_TYPE_F32_NAME = "F32"
DEFAULT_ALIGNMENT = 32
ARCHITECTURE = "synthrollback"
ARCHITECTURE_GRAMMAR = "abcdefghijklmnopqrstuvwxyz0123456789"
METADATA_KEY_GRAMMAR = "abcdefghijklmnopqrstuvwxyz0123456789_."
FIXTURE_NAME = "commons-gguf-rollback-fixture"
TENSOR_NAME = "synth.ffn_down.weight"
TENSOR_DIMENSIONS = (8,)
TENSOR_PAYLOAD_BYTES = 32
F32_ONES = struct.pack("<8f", 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0)
SCHEMA_VERSION = "gguf-rollback-fixture/v1"
KIND = "SYNTHETIC_GGUF_ROLLBACK_FIXTURE"
PASS_LABEL = "SYNTHETIC_FIXTURE_PASS"
FIXTURE_METADATA_TYPES = {
    "general.architecture": GGUF_TYPE_STRING,
    "general.name": GGUF_TYPE_STRING,
    "general.alignment": GGUF_TYPE_UINT32,
}
SCALAR_WIDTH = {
    GGUF_TYPE_UINT8: 1,
    GGUF_TYPE_INT8: 1,
    GGUF_TYPE_UINT16: 2,
    GGUF_TYPE_INT16: 2,
    GGUF_TYPE_UINT32: 4,
    GGUF_TYPE_INT32: 4,
    GGUF_TYPE_FLOAT32: 4,
    GGUF_TYPE_BOOL: 1,
    GGUF_TYPE_UINT64: 8,
    GGUF_TYPE_INT64: 8,
    GGUF_TYPE_FLOAT64: 8,
}
SCALAR_FORMAT = {
    GGUF_TYPE_UINT8: "<B",
    GGUF_TYPE_INT8: "<b",
    GGUF_TYPE_UINT16: "<H",
    GGUF_TYPE_INT16: "<h",
    GGUF_TYPE_UINT32: "<I",
    GGUF_TYPE_INT32: "<i",
    GGUF_TYPE_FLOAT32: "<f",
    GGUF_TYPE_BOOL: "<?",
    GGUF_TYPE_UINT64: "<Q",
    GGUF_TYPE_INT64: "<q",
    GGUF_TYPE_FLOAT64: "<d",
}


class FixtureError(Exception):
    """Fail-closed fixture or GGUF parse error."""


class ParsedTensor:
    def __init__(
        self,
        name: str,
        dimensions: tuple[int, ...],
        ggml_type: int,
        type_name: str,
        relative_offset: int,
        payload_bytes: int,
    ) -> None:
        self.name = name
        self.dimensions = dimensions
        self.ggml_type = ggml_type
        self.type_name = type_name
        self.relative_offset = relative_offset
        self.payload_bytes = payload_bytes


class ParsedGguf:
    def __init__(
        self,
        version: int,
        architecture: str | None,
        name: str | None,
        alignment: int,
        kv: dict[str, object],
        tensors: dict[str, ParsedTensor],
        tensor_info_end: int,
        data_section_start: int,
    ) -> None:
        self.version = version
        self.architecture = architecture
        self.name = name
        self.alignment = alignment
        self.kv = kv
        self.tensors = tensors
        self.tensor_info_end = tensor_info_end
        self.data_section_start = data_section_start


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def align_up(offset: int, alignment: int) -> int:
    # The written GGUF spec requires a multiple of 8 while the current
    # reference reader requires a power of two. Keep the fixture in the
    # executable intersection of both requirements.
    if alignment < 8 or alignment & (alignment - 1):
        raise FixtureError("alignment is not a supported power of two of at least 8")
    return (offset + alignment - 1) // alignment * alignment


def _gguf_string(text: str) -> bytes:
    encoded = text.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def _kv_string(key: str, value: str) -> bytes:
    return _gguf_string(key) + struct.pack("<I", GGUF_TYPE_STRING) + _gguf_string(value)


def _kv_u32(key: str, value: int) -> bytes:
    return _gguf_string(key) + struct.pack("<I", GGUF_TYPE_UINT32) + struct.pack("<I", value)


def _tensor_info(name: str, dimensions: tuple[int, ...], ggml_type: int, relative_offset: int) -> bytes:
    blob = _gguf_string(name)
    blob += struct.pack("<I", len(dimensions))
    for dim in dimensions:
        blob += struct.pack("<Q", dim)
    blob += struct.pack("<I", ggml_type)
    blob += struct.pack("<Q", relative_offset)
    return blob


def build_synthetic_gguf(
    *,
    magic: bytes = MAGIC,
    version: int = GGUF_VERSION,
    architecture: str = ARCHITECTURE,
    name: str = FIXTURE_NAME,
    alignment: int = DEFAULT_ALIGNMENT,
    extra_kv: tuple[tuple[str, str], ...] = (),
    tensor_name: str = TENSOR_NAME,
    extra_tensor_names: tuple[str, ...] = (),
    dimensions: tuple[int, ...] = TENSOR_DIMENSIONS,
    include_tensor: bool = True,
    payload: bytes = F32_ONES,
    relative_offset: int = 0,
) -> bytes:
    kv_parts = [
        _kv_string("general.architecture", architecture),
        _kv_string("general.name", name),
        _kv_u32("general.alignment", alignment),
    ]
    kv_parts.extend(_kv_string(key, value) for key, value in extra_kv)
    tensor_parts = []
    if include_tensor:
        tensor_parts.append(_tensor_info(tensor_name, dimensions, GGML_TYPE_F32, relative_offset))
        tensor_parts.extend(
            _tensor_info(extra_name, dimensions, GGML_TYPE_F32, relative_offset)
            for extra_name in extra_tensor_names
        )
    header = magic[:4].ljust(4, b"\x00")[:4]
    header += struct.pack("<I", version)
    header += struct.pack("<Q", len(tensor_parts))
    header += struct.pack("<Q", len(kv_parts))
    body = header + b"".join(kv_parts) + b"".join(tensor_parts)
    data_start = align_up(len(body), alignment)
    padding = b"\x00" * (data_start - len(body))
    tensor_blob = b""
    if include_tensor:
        tensor_blob = b"\x00" * relative_offset + payload
    return body + padding + tensor_blob


def _need(data: bytes, offset: int, size: int, what: str) -> bytes:
    if size < 0 or offset < 0 or offset + size > len(data):
        raise FixtureError("truncated %s" % what)
    return data[offset : offset + size]


def _u32(data: bytes, offset: int, what: str) -> tuple[int, int]:
    raw = _need(data, offset, 4, what)
    return struct.unpack_from("<I", raw, 0)[0], offset + 4


def _u64(data: bytes, offset: int, what: str) -> tuple[int, int]:
    raw = _need(data, offset, 8, what)
    return struct.unpack_from("<Q", raw, 0)[0], offset + 8


def _read_string(data: bytes, offset: int, what: str) -> tuple[str, int]:
    length, offset = _u64(data, offset, what + " length")
    raw = _need(data, offset, length, what)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FixtureError("invalid UTF-8 in %s" % what) from exc
    return text, offset + length


def _read_value(data: bytes, offset: int, value_type: int, what: str) -> tuple[object, int]:
    if value_type == GGUF_TYPE_STRING:
        return _read_string(data, offset, what)
    if value_type == GGUF_TYPE_ARRAY:
        elem_type, offset = _u32(data, offset, what + " array type")
        count, offset = _u64(data, offset, what + " array count")
        remaining = len(data) - offset
        if count > remaining:
            raise FixtureError("truncated %s array" % what)
        values = []
        for index in range(count):
            item, offset = _read_value(data, offset, elem_type, "%s[%d]" % (what, index))
            values.append(item)
        return values, offset
    width = SCALAR_WIDTH.get(value_type)
    fmt = SCALAR_FORMAT.get(value_type)
    if width is None or fmt is None:
        raise FixtureError("unsupported GGUF value type")
    raw = _need(data, offset, width, what)
    return struct.unpack_from(fmt, raw, 0)[0], offset + width


def _product(dimensions: tuple[int, ...]) -> int:
    total = 1
    for dim in dimensions:
        if dim <= 0:
            raise FixtureError("invalid tensor dimension")
        total *= dim
    return total


def payload_abs(parsed: ParsedGguf, tensor: ParsedTensor) -> int:
    return parsed.data_section_start + tensor.relative_offset


def parse_gguf_v3(data: bytes) -> ParsedGguf:
    if len(data) < 24:
        raise FixtureError("truncated GGUF header")
    if data[:4] != MAGIC:
        raise FixtureError("bad GGUF magic")
    version, offset = _u32(data, 4, "GGUF version")
    if version != GGUF_VERSION:
        raise FixtureError("unsupported GGUF version")
    n_tensors, offset = _u64(data, offset, "tensor count")
    n_kv, offset = _u64(data, offset, "kv count")
    if n_tensors > len(data) or n_kv > len(data):
        raise FixtureError("truncated GGUF header counts")
    kv: dict[str, object] = {}
    for _ in range(n_kv):
        key, offset = _read_string(data, offset, "kv key")
        key_bytes = key.encode("utf-8")
        if (
            not key_bytes
            or len(key_bytes) > 65535
            or key.startswith(".")
            or key.endswith(".")
            or ".." in key
            or any(ch not in METADATA_KEY_GRAMMAR for ch in key)
        ):
            raise FixtureError("invalid GGUF metadata key")
        if key in kv:
            raise FixtureError("duplicate GGUF metadata key")
        value_type, offset = _u32(data, offset, "kv type")
        expected_type = FIXTURE_METADATA_TYPES.get(key)
        if expected_type is not None and value_type != expected_type:
            raise FixtureError("invalid fixture metadata type")
        value, offset = _read_value(data, offset, value_type, "kv %s" % key)
        kv[key] = value
    tensors: dict[str, ParsedTensor] = {}
    for _ in range(n_tensors):
        name, offset = _read_string(data, offset, "tensor name")
        if name in tensors:
            raise FixtureError("duplicate tensor name")
        if len(name.encode("utf-8")) > 64:
            raise FixtureError("tensor name exceeds 64 bytes")
        n_dims, offset = _u32(data, offset, "tensor n_dims")
        if n_dims < 1 or n_dims > 4:
            raise FixtureError("invalid tensor dimension count")
        dims = []
        for _ in range(n_dims):
            dim, offset = _u64(data, offset, "tensor dim")
            dims.append(dim)
        ggml_type, offset = _u32(data, offset, "tensor type")
        relative_offset, offset = _u64(data, offset, "tensor relative offset")
        dimensions = tuple(dims)
        if ggml_type != GGML_TYPE_F32:
            raise FixtureError("unsupported tensor type")
        payload_bytes = 4 * _product(dimensions)
        tensors[name] = ParsedTensor(
            name=name,
            dimensions=dimensions,
            ggml_type=ggml_type,
            type_name=GGML_TYPE_F32_NAME,
            relative_offset=relative_offset,
            payload_bytes=payload_bytes,
        )
    alignment = kv.get("general.alignment", DEFAULT_ALIGNMENT)
    if not isinstance(alignment, int) or isinstance(alignment, bool):
        raise FixtureError("invalid alignment metadata")
    data_section_start = align_up(offset, alignment)
    if data_section_start > len(data):
        raise FixtureError("truncated aligned data section")
    if any(data[offset:data_section_start]):
        raise FixtureError("nonzero tensor-data padding")
    for tensor in tensors.values():
        if tensor.relative_offset % alignment:
            raise FixtureError("misaligned tensor offset")
        start = data_section_start + tensor.relative_offset
        if start + tensor.payload_bytes > len(data):
            raise FixtureError("truncated tensor payload")
    architecture = kv.get("general.architecture")
    if architecture is not None:
        if not isinstance(architecture, str) or not architecture or any(
            ch not in ARCHITECTURE_GRAMMAR for ch in architecture
        ):
            raise FixtureError("invalid architecture")
    name = kv.get("general.name")
    if name is not None and not isinstance(name, str):
        raise FixtureError("invalid general.name")
    return ParsedGguf(
        version=version,
        architecture=architecture if isinstance(architecture, str) else None,
        name=name if isinstance(name, str) else None,
        alignment=alignment,
        kv=kv,
        tensors=tensors,
        tensor_info_end=offset,
        data_section_start=data_section_start,
    )


def validate_fixture(parsed: ParsedGguf) -> ParsedTensor:
    if parsed.version != GGUF_VERSION:
        raise FixtureError("unsupported GGUF version")
    if parsed.architecture != ARCHITECTURE:
        raise FixtureError("invalid architecture")
    if parsed.name != FIXTURE_NAME:
        raise FixtureError("invalid fixture name")
    if TENSOR_NAME not in parsed.tensors:
        raise FixtureError("missing tensor")
    if len(parsed.tensors) != 1:
        raise FixtureError("fixture requires exactly one tensor")
    tensor = parsed.tensors[TENSOR_NAME]
    if tensor.ggml_type != GGML_TYPE_F32 or tensor.type_name != GGML_TYPE_F32_NAME:
        raise FixtureError("unsupported tensor type")
    if tensor.dimensions != TENSOR_DIMENSIONS:
        raise FixtureError("unexpected tensor dimensions")
    if tensor.payload_bytes != TENSOR_PAYLOAD_BYTES:
        raise FixtureError("unexpected tensor payload size")
    return tensor


def inspect_fixture(data: bytes) -> tuple[ParsedGguf, ParsedTensor, int]:
    parsed = parse_gguf_v3(data)
    tensor = validate_fixture(parsed)
    start = payload_abs(parsed, tensor)
    if start + tensor.payload_bytes != len(data):
        raise FixtureError("unexpected trailing fixture bytes")
    return parsed, tensor, start


def build_receipt(
    parsed: ParsedGguf,
    tensor: ParsedTensor,
    original_sha: str,
    zeroed_sha: str,
    restored_sha: str,
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "label": PASS_LABEL,
        "name": parsed.name,
        "gguf_version": parsed.version,
        "architecture": parsed.architecture,
        "tensor_name": tensor.name,
        "tensor_type": tensor.type_name,
        "tensor_dimensions": list(tensor.dimensions),
        "tensor_payload_bytes": tensor.payload_bytes,
        "fixture_original": {"sha256": original_sha},
        "fixture_zeroed": {
            "sha256": zeroed_sha,
            "differs_from_original": True,
        },
        "fixture_restored": {
            "sha256": restored_sha,
            "equals_original": True,
        },
        "fixture": "SYNTHETIC",
        "binaries_published": False,
        "network_used": False,
        "titan": "NOT_WRITTEN",
        "buyer": False,
        "demand": "UNKNOWN",
        "acceptance": False,
        "delivery": False,
        "cash_claimed": False,
        "cash_usd": 0,
        "program_submission": False,
        "eligibility": "NOT_CLAIMED",
        "nonclaims": {
            "statement": (
                "This synthetic GGUF v3 rollback fixture is not a customer GGUF, "
                "not a customer delivery, not a Titan write, not a buyer signal, "
                "not a program submission, not an award, and not cash."
            ),
            "customer_gguf": False,
            "customer_delivery": False,
            "titan_write": False,
            "buyer_signal": False,
            "program_submission": False,
            "award": False,
            "cash": False,
        },
    }


def rollback_from_bytes(data: bytes, *, corrupt_restore: bool = False) -> dict[str, object]:
    parsed, tensor, start = inspect_fixture(data)
    payload = data[start : start + tensor.payload_bytes]
    if payload != F32_ONES:
        raise FixtureError("tensor payload is not eight F32 ones")
    journal = bytes(payload)
    original_sha = sha256_hex(data)
    zeroed = bytearray(data)
    zeroed[start : start + tensor.payload_bytes] = b"\x00" * tensor.payload_bytes
    zeroed_sha = sha256_hex(zeroed)
    if zeroed_sha == original_sha:
        raise FixtureError("zeroed hash equals original")
    restored = bytearray(zeroed)
    restored[start : start + tensor.payload_bytes] = journal
    if corrupt_restore:
        restored[start] ^= 0x01
    restored_sha = sha256_hex(restored)
    if restored_sha != original_sha:
        raise FixtureError("restored hash differs from original")
    return build_receipt(parsed, tensor, original_sha, zeroed_sha, restored_sha)


def run_fixture(*, corrupt_restore: bool = False) -> dict[str, object]:
    blob = build_synthetic_gguf()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "%s.gguf" % FIXTURE_NAME)
        with open(path, "wb") as handle:
            handle.write(blob)
        with open(path, "rb") as handle:
            data = handle.read()
    return rollback_from_bytes(data, corrupt_restore=corrupt_restore)


def main() -> int:
    try:
        receipt = run_fixture()
    except FixtureError as exc:
        sys.stderr.write("%s\n" % exc)
        return 1
    sys.stdout.write(canonical_json(receipt))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
