#!/usr/bin/env python3
"""Create and verify byte-exact delivery receipts for public MHA computers.

The instrument reads an MHA ``.mno`` from disk, validates its physical layout,
and binds the measured computer plus delivered artifacts to one JSON receipt.
Only Python's standard library is used.

Examples::

    python3 revenue/dio/substrate_receipt.py generate \
      --substrate excerpts/20260823/muhl_grbn.mno \
      --artifact excerpts/20260823/grbn_circuits.json \
      --receipt-id dio-substrate-grbn-delivery-20260825-01 \
      --job-id dio-substrate-grbn-job-20260825-01

    python3 revenue/dio/substrate_receipt.py check \
      --receipt revenue/dio/examples/substrate_delivery.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "dio-revenue/v1"
BASE_HEADER = struct.Struct("<8sIIIII")
OUTPUT_ADDRESS = struct.Struct("<Q")
GATE_RECORD = struct.Struct("<BQQQ")
OPCODE_NAMES = {
    0: "NAND",
    1: "AND",
    2: "OR",
    3: "XOR",
    4: "NOT",
}
DELIVERY_STATUSES = ("MEASURED", "DELIVERED", "PARTIAL", "FAILED")
ACCEPTANCE_STATUSES = ("MEASURED", "PASS", "FAIL", "PARTIAL", "UNMEASURED")
PAYMENT_STATUSES = (
    "NOT_REQUESTED",
    "REFERENCE_ONLY",
    "SETTLEMENT_REPORTED",
    "REFUND_REPORTED",
    "DISPUTED",
)
TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "kind",
        "receipt_id",
        "job_id",
        "quote_id",
        "status",
        "delivered_at",
        "result_address",
        "substrate",
        "artifacts",
        "acceptance",
        "bazaar",
        "payment",
    }
)
SUBSTRATE_KEYS = frozenset(
    {
        "path",
        "sha256",
        "bytes",
        "format",
        "header",
        "output_addresses",
        "wire_plane",
        "gates",
        "expected_file_bytes",
        "body_length_exact",
    }
)
HEADER_KEYS = frozenset(
    {
        "offset",
        "magic_ascii",
        "magic_hex",
        "layout",
        "base_bytes",
        "bytes",
        "sha256",
        "n_gate",
        "n_wires",
        "n_in",
        "n_out",
        "depth",
        "output_addresses_offset",
        "output_addresses_bytes",
        "output_addresses_sha256",
        "unique_output_addresses",
        "output_addresses_in_wire_plane",
    }
)
WIRE_PLANE_KEYS = frozenset(
    {"offset", "end", "bytes", "sha256", "levels", "zero_bytes", "one_bytes"}
)
GATE_KEYS = frozenset(
    {
        "count",
        "record_format",
        "record_bytes",
        "region_offset",
        "region_bytes",
        "region_sha256",
        "body_offset",
        "body_bytes",
        "body_sha256",
        "opcode_histogram",
        "unique_input_addresses",
        "unique_output_addresses",
        "repeated_output_writes",
        "self_output_inputs",
        "addresses_in_wire_plane",
    }
)
ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REPO_ROOT = Path(__file__).resolve().parents[2]


class ReceiptError(ValueError):
    """The measured bytes do not satisfy the receipt contract."""


def _read_exact(handle: Any, size: int, label: str) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise ReceiptError(
            "%s is short: expected %d bytes, read %d" % (label, size, len(data))
        )
    return data


def _resolve_existing(value: str | os.PathLike[str], base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    candidates: list[Path]
    if path.is_absolute():
        candidates = [path]
    else:
        candidates = [Path.cwd() / path, REPO_ROOT / path]
        if base is not None:
            candidates.append(base / path)
    seen: set[str] = set()
    for candidate in candidates:
        marker = os.path.abspath(os.fspath(candidate))
        if marker in seen:
            continue
        seen.add(marker)
        if candidate.is_file():
            return candidate.resolve()
    raise ReceiptError("file not found: %s" % value)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return "external/%s" % resolved.name


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _magic_text(raw: bytes) -> str:
    if len(raw) != 8:
        raise ReceiptError("MHA magic must occupy exactly 8 bytes")
    if any(byte < 0x20 or byte > 0x7E for byte in raw):
        raise ReceiptError("MHA magic must be eight printable ASCII bytes")
    if not raw.startswith(b"MUHL"):
        raise ReceiptError("MHA magic must begin with MUHL")
    return raw.decode("ascii")


def parse_mha(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Parse and validate one exact MHA physical computer from disk.

    Layout:

    - eight magic bytes;
    - five little-endian uint32 values: gates, wires, inputs, outputs, depth;
    - ``n_out`` little-endian uint64 output addresses;
    - a byte-addressed binary wire plane of ``n_wires`` bytes;
    - exactly ``n_gate`` physical ``<BQQQ>`` records.
    """

    source = _resolve_existing(path)
    file_digest = hashlib.sha256()
    header_digest = hashlib.sha256()
    output_table_digest = hashlib.sha256()
    wire_digest = hashlib.sha256()
    gate_digest = hashlib.sha256()
    body_digest = hashlib.sha256()

    with source.open("rb") as handle:
        file_size = os.fstat(handle.fileno()).st_size
        base = _read_exact(handle, BASE_HEADER.size, "MHA base header")
        file_digest.update(base)
        header_digest.update(base)
        magic_raw, n_gate, n_wires, n_in, n_out, depth = BASE_HEADER.unpack(base)
        magic = _magic_text(magic_raw)
        if n_wires == 0:
            raise ReceiptError("MHA header declares an empty wire plane")
        if n_out == 0:
            raise ReceiptError("MHA header declares no output addresses")

        output_table_bytes = n_out * OUTPUT_ADDRESS.size
        header_bytes = BASE_HEADER.size + output_table_bytes
        wire_plane_offset = header_bytes
        gate_table_offset = wire_plane_offset + n_wires
        gate_table_bytes = n_gate * GATE_RECORD.size
        expected_file_bytes = gate_table_offset + gate_table_bytes
        if expected_file_bytes != file_size:
            raise ReceiptError(
                "MHA body length mismatch: header %d + wire plane %d + "
                "%d records x %d = %d, file is %d"
                % (
                    header_bytes,
                    n_wires,
                    n_gate,
                    GATE_RECORD.size,
                    expected_file_bytes,
                    file_size,
                )
            )

        raw_outputs = _read_exact(handle, output_table_bytes, "output-address table")
        file_digest.update(raw_outputs)
        header_digest.update(raw_outputs)
        output_table_digest.update(raw_outputs)
        output_addresses = [row[0] for row in struct.iter_unpack("<Q", raw_outputs)]
        if len(set(output_addresses)) != n_out:
            raise ReceiptError("header output addresses are not unique")

        wire_plane_end = wire_plane_offset + n_wires
        invalid_outputs = [
            address
            for address in output_addresses
            if not wire_plane_offset <= address < wire_plane_end
        ]
        if invalid_outputs:
            raise ReceiptError(
                "header output address outside wire plane: %d" % invalid_outputs[0]
            )

        wire_plane = _read_exact(handle, n_wires, "wire plane")
        file_digest.update(wire_plane)
        wire_digest.update(wire_plane)
        body_digest.update(wire_plane)
        wire_levels = sorted(set(wire_plane))
        invalid_wire = next(
            ((index, value) for index, value in enumerate(wire_plane) if value not in (0, 1)),
            None,
        )
        if invalid_wire is not None:
            index, value = invalid_wire
            raise ReceiptError(
                "wire plane byte %d has level %d; expected binary 0 or 1"
                % (index, value)
            )

        opcode_counts: Counter[int] = Counter()
        input_addresses: set[int] = set()
        gate_output_addresses: set[int] = set()
        repeated_output_writes = 0
        self_output_inputs = 0
        for index in range(n_gate):
            record = _read_exact(handle, GATE_RECORD.size, "gate record %d" % index)
            file_digest.update(record)
            gate_digest.update(record)
            body_digest.update(record)
            opcode, input_a, input_b, output = GATE_RECORD.unpack(record)
            if opcode not in OPCODE_NAMES:
                raise ReceiptError("gate record %d has opcode %d" % (index, opcode))
            for field, address in (
                ("input_a", input_a),
                ("input_b", input_b),
                ("output", output),
            ):
                if not wire_plane_offset <= address < wire_plane_end:
                    raise ReceiptError(
                        "gate record %d %s address %d is outside wire plane [%d, %d)"
                        % (index, field, address, wire_plane_offset, wire_plane_end)
                    )
            opcode_counts[opcode] += 1
            input_addresses.add(input_a)
            input_addresses.add(input_b)
            if output in gate_output_addresses:
                repeated_output_writes += 1
            gate_output_addresses.add(output)
            if output == input_a or output == input_b:
                self_output_inputs += 1

        if handle.read(1):
            raise ReceiptError("bytes remain after the declared gate table")
        if os.fstat(handle.fileno()).st_size != file_size:
            raise ReceiptError("MHA size changed while it was measured")
        if repeated_output_writes:
            raise ReceiptError(
                "%d gate records repeat an output address" % repeated_output_writes
            )

    opcode_histogram = {
        OPCODE_NAMES[opcode]: opcode_counts.get(opcode, 0)
        for opcode in sorted(OPCODE_NAMES)
    }
    output_rows = []
    for index, address in enumerate(output_addresses):
        value = wire_plane[address - wire_plane_offset]
        output_rows.append(
            {
                "name": "output_%04d" % index,
                "address": address,
                "value_hex": "%02x" % value,
                "value_uint": value,
            }
        )
    return {
        "path": _display_path(source),
        "sha256": file_digest.hexdigest(),
        "bytes": file_size,
        "format": magic,
        "header": {
            "offset": 0,
            "magic_ascii": magic_raw.decode("ascii"),
            "magic_hex": magic_raw.hex(),
            "layout": "<8sIIIII then n_out*<Q",
            "base_bytes": BASE_HEADER.size,
            "bytes": header_bytes,
            "sha256": header_digest.hexdigest(),
            "n_gate": n_gate,
            "n_wires": n_wires,
            "n_in": n_in,
            "n_out": n_out,
            "depth": depth,
            "output_addresses_offset": BASE_HEADER.size,
            "output_addresses_bytes": output_table_bytes,
            "output_addresses_sha256": output_table_digest.hexdigest(),
            "unique_output_addresses": len(set(output_addresses)),
            "output_addresses_in_wire_plane": True,
        },
        "output_addresses": output_rows,
        "wire_plane": {
            "offset": wire_plane_offset,
            "end": wire_plane_end,
            "bytes": n_wires,
            "sha256": wire_digest.hexdigest(),
            "levels": wire_levels,
            "zero_bytes": wire_plane.count(0),
            "one_bytes": wire_plane.count(1),
        },
        "gates": {
            "count": n_gate,
            "record_format": "<BQQQ",
            "record_bytes": GATE_RECORD.size,
            "region_offset": gate_table_offset,
            "region_bytes": gate_table_bytes,
            "region_sha256": gate_digest.hexdigest(),
            "body_offset": header_bytes,
            "body_bytes": file_size - header_bytes,
            "body_sha256": body_digest.hexdigest(),
            "opcode_histogram": opcode_histogram,
            "unique_input_addresses": len(input_addresses),
            "unique_output_addresses": len(gate_output_addresses),
            "repeated_output_writes": repeated_output_writes,
            "self_output_inputs": self_output_inputs,
            "addresses_in_wire_plane": True,
        },
        "expected_file_bytes": expected_file_bytes,
        "body_length_exact": True,
    }


def hash_artifact(path: str | os.PathLike[str]) -> dict[str, Any]:
    source = _resolve_existing(path)
    before = source.stat()
    digest = _sha256_file(source)
    after = source.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise ReceiptError("artifact changed while it was hashed: %s" % source)
    return {
        "path": _display_path(source),
        "sha256": digest,
        "bytes": after.st_size,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _exact_object(value: Any, keys: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReceiptError("%s is not an object" % label)
    actual = set(value)
    missing = sorted(keys - actual)
    extra = sorted(actual - keys)
    if missing or extra:
        raise ReceiptError(
            "%s keys mismatch: missing=%s extra=%s" % (label, missing, extra)
        )
    return value


def _integer(value: Any, label: str, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise ReceiptError("%s must be an integer >= %d" % (label, minimum))
    return value


def _text(value: Any, label: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        raise ReceiptError("%s must be a nonempty string" % label)
    return value


def _identifier(value: Any, label: str, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or ID_PATTERN.fullmatch(value) is None:
        raise ReceiptError(
            "%s must be 8-80 characters from A-Z, a-z, 0-9, dot, underscore, or hyphen"
            % label
        )
    return value


def _id_component(value: str) -> str:
    component = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return component[:40] or "mha"


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
        raise ReceiptError("%s must be a lowercase SHA-256 digest" % label)
    return value


def _serialized_path(value: Any, label: str) -> str:
    text_value = _text(value, label)
    if (
        Path(text_value).is_absolute()
        or "\\" in text_value
        or re.match(r"^[A-Za-z]:", text_value)
        or ".." in text_value.split("/")
    ):
        raise ReceiptError("%s must be a safe repository-relative path" % label)
    return text_value


def _aware_timestamp(value: Any, label: str) -> str:
    timestamp = _text(value, label)
    try:
        parsed = datetime.fromisoformat(
            timestamp[:-1] + "+00:00" if timestamp.endswith("Z") else timestamp
        )
    except ValueError as error:
        raise ReceiptError("%s is not an ISO 8601 timestamp" % label) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReceiptError("%s must include a UTC offset or Z" % label)
    return timestamp


def _validate_substrate(value: Any) -> dict[str, Any]:
    substrate = _exact_object(value, SUBSTRATE_KEYS, "substrate")
    substrate_path = _serialized_path(substrate["path"], "substrate.path")
    if not substrate_path.endswith(".mno"):
        raise ReceiptError("substrate.path must end in .mno")
    _sha256(substrate["sha256"], "substrate.sha256")
    file_bytes = _integer(substrate["bytes"], "substrate.bytes", 8)
    format_name = _text(substrate["format"], "substrate.format")

    header = _exact_object(substrate["header"], HEADER_KEYS, "substrate.header")
    if header["offset"] != 0:
        raise ReceiptError("substrate.header.offset must be 0")
    magic_ascii = _text(header["magic_ascii"], "substrate.header.magic_ascii")
    if (
        len(magic_ascii) != 8
        or not magic_ascii.startswith("MUHL")
        or any(ord(character) < 0x20 or ord(character) > 0x7E for character in magic_ascii)
    ):
        raise ReceiptError("substrate.header.magic_ascii must be an eight-byte MUHL magic")
    magic_hex = _text(header["magic_hex"], "substrate.header.magic_hex")
    if re.fullmatch(r"[0-9a-f]{16}", magic_hex) is None:
        raise ReceiptError("substrate.header.magic_hex must contain eight lowercase bytes")
    if format_name != magic_ascii:
        raise ReceiptError("substrate.format must equal substrate.header.magic_ascii")
    if magic_ascii.encode("ascii", errors="strict").hex() != magic_hex:
        raise ReceiptError("substrate.header magic ASCII and hex disagree")
    if header["layout"] != "<8sIIIII then n_out*<Q":
        raise ReceiptError("substrate.header.layout is not the MHA layout")
    if header["base_bytes"] != BASE_HEADER.size:
        raise ReceiptError("substrate.header.base_bytes is not %d" % BASE_HEADER.size)
    header_bytes = _integer(header["bytes"], "substrate.header.bytes", BASE_HEADER.size)
    _sha256(header["sha256"], "substrate.header.sha256")
    n_gate = _integer(header["n_gate"], "substrate.header.n_gate")
    n_wires = _integer(header["n_wires"], "substrate.header.n_wires", 1)
    _integer(header["n_in"], "substrate.header.n_in")
    n_out = _integer(header["n_out"], "substrate.header.n_out", 1)
    _integer(header["depth"], "substrate.header.depth")
    if header["output_addresses_offset"] != BASE_HEADER.size:
        raise ReceiptError("substrate.header.output_addresses_offset is not 28")
    if header["output_addresses_bytes"] != n_out * OUTPUT_ADDRESS.size:
        raise ReceiptError("substrate.header.output_addresses_bytes is inconsistent")
    if header_bytes != BASE_HEADER.size + n_out * OUTPUT_ADDRESS.size:
        raise ReceiptError("substrate.header.bytes is inconsistent")
    _sha256(
        header["output_addresses_sha256"],
        "substrate.header.output_addresses_sha256",
    )
    if header["unique_output_addresses"] != n_out:
        raise ReceiptError("substrate.header.unique_output_addresses is inconsistent")
    if header["output_addresses_in_wire_plane"] is not True:
        raise ReceiptError("substrate.header output addresses are not marked in-plane")

    outputs = substrate["output_addresses"]
    if not isinstance(outputs, list) or not outputs:
        raise ReceiptError("substrate.output_addresses must be a nonempty array")
    if len(outputs) != n_out:
        raise ReceiptError("substrate.output_addresses length does not equal n_out")
    output_values: list[int] = []
    for index, row_value in enumerate(outputs):
        row = _exact_object(
            row_value,
            frozenset({"name", "address", "value_hex", "value_uint"}),
            "substrate.output_addresses[%d]" % index,
        )
        _text(row["name"], "substrate.output_addresses[%d].name" % index)
        address = _integer(
            row["address"], "substrate.output_addresses[%d].address" % index
        )
        value_uint = _integer(
            row["value_uint"],
            "substrate.output_addresses[%d].value_uint" % index,
        )
        if value_uint > 255 or row["value_hex"] != "%02x" % value_uint:
            raise ReceiptError(
                "substrate.output_addresses[%d] value fields disagree" % index
            )
        output_values.append(address)
    if len(set(output_values)) != len(output_values):
        raise ReceiptError("substrate.output_addresses contain duplicate addresses")

    wire = _exact_object(
        substrate["wire_plane"], WIRE_PLANE_KEYS, "substrate.wire_plane"
    )
    wire_offset = _integer(wire["offset"], "substrate.wire_plane.offset")
    wire_bytes = _integer(wire["bytes"], "substrate.wire_plane.bytes", 1)
    wire_end = _integer(wire["end"], "substrate.wire_plane.end")
    _sha256(wire["sha256"], "substrate.wire_plane.sha256")
    levels = wire["levels"]
    if (
        not isinstance(levels, list)
        or any(level not in (0, 1) or isinstance(level, bool) for level in levels)
        or len(levels) != len(set(levels))
    ):
        raise ReceiptError("substrate.wire_plane.levels must be unique binary levels")
    zero_bytes = _integer(wire["zero_bytes"], "substrate.wire_plane.zero_bytes")
    one_bytes = _integer(wire["one_bytes"], "substrate.wire_plane.one_bytes")
    if wire_offset != header_bytes or wire_end != wire_offset + wire_bytes:
        raise ReceiptError("substrate.wire_plane offsets are inconsistent")
    if zero_bytes + one_bytes != wire_bytes or n_wires != wire_bytes:
        raise ReceiptError("substrate.wire_plane counts are inconsistent")
    if any(not wire_offset <= address < wire_end for address in output_values):
        raise ReceiptError("substrate.output_addresses include an out-of-plane address")

    gates = _exact_object(substrate["gates"], GATE_KEYS, "substrate.gates")
    gate_count = _integer(gates["count"], "substrate.gates.count")
    if gates["record_format"] != "<BQQQ" or gates["record_bytes"] != GATE_RECORD.size:
        raise ReceiptError("substrate.gates record layout is not exact <BQQQ>")
    region_offset = _integer(gates["region_offset"], "substrate.gates.region_offset")
    region_bytes = _integer(gates["region_bytes"], "substrate.gates.region_bytes")
    _sha256(gates["region_sha256"], "substrate.gates.region_sha256")
    body_offset = _integer(gates["body_offset"], "substrate.gates.body_offset", 8)
    body_bytes = _integer(gates["body_bytes"], "substrate.gates.body_bytes")
    _sha256(gates["body_sha256"], "substrate.gates.body_sha256")
    histogram = _exact_object(
        gates["opcode_histogram"],
        frozenset(OPCODE_NAMES.values()),
        "substrate.gates.opcode_histogram",
    )
    histogram_total = sum(
        _integer(count, "substrate.gates.opcode_histogram.%s" % name)
        for name, count in histogram.items()
    )
    _integer(gates["unique_input_addresses"], "substrate.gates.unique_input_addresses")
    unique_gate_outputs = _integer(
        gates["unique_output_addresses"], "substrate.gates.unique_output_addresses"
    )
    repeated_outputs = _integer(
        gates["repeated_output_writes"], "substrate.gates.repeated_output_writes"
    )
    _integer(gates["self_output_inputs"], "substrate.gates.self_output_inputs")
    if gates["addresses_in_wire_plane"] is not True:
        raise ReceiptError("substrate.gates addresses are not marked in-plane")
    if n_gate != gate_count or histogram_total != gate_count:
        raise ReceiptError("substrate.gates count is inconsistent")
    if repeated_outputs != 0 or unique_gate_outputs != gate_count:
        raise ReceiptError("substrate.gates outputs are not one-per-record")
    if region_offset != wire_end or region_bytes != gate_count * GATE_RECORD.size:
        raise ReceiptError("substrate.gates region is inconsistent")
    if body_offset != header_bytes or body_bytes != file_bytes - header_bytes:
        raise ReceiptError("substrate.gates body is inconsistent")
    if region_offset + region_bytes != file_bytes:
        raise ReceiptError("substrate.gates region does not end at the file boundary")
    if substrate["expected_file_bytes"] != file_bytes:
        raise ReceiptError("substrate.expected_file_bytes is inconsistent")
    if substrate["body_length_exact"] is not True:
        raise ReceiptError("substrate.body_length_exact is not true")
    return substrate


def _validate_artifacts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ReceiptError("artifacts must be a nonempty array")
    rows: list[dict[str, Any]] = []
    for index, row_value in enumerate(value):
        if not isinstance(row_value, dict):
            raise ReceiptError("artifacts[%d] is not an object" % index)
        keys = set(row_value)
        if not {"path", "sha256", "bytes"} <= keys or keys - {
            "path",
            "sha256",
            "bytes",
            "role",
        }:
            raise ReceiptError("artifacts[%d] has invalid keys" % index)
        _serialized_path(row_value["path"], "artifacts[%d].path" % index)
        _sha256(row_value["sha256"], "artifacts[%d].sha256" % index)
        _integer(row_value["bytes"], "artifacts[%d].bytes" % index)
        if "role" in row_value:
            _text(row_value["role"], "artifacts[%d].role" % index)
        rows.append(row_value)
    return rows


def _validate_acceptance(
    value: Any,
    substrate: Mapping[str, Any],
    artifacts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    acceptance = _exact_object(
        value, frozenset({"status", "evidence"}), "acceptance"
    )
    if acceptance["status"] not in ACCEPTANCE_STATUSES:
        raise ReceiptError("acceptance.status is not recognized")
    evidence_rows = acceptance["evidence"]
    if not isinstance(evidence_rows, list) or not evidence_rows:
        raise ReceiptError("acceptance.evidence must be a nonempty array")
    bindings = {(substrate["path"], substrate["sha256"])} | {
        (row["path"], row["sha256"]) for row in artifacts
    }
    artifact_digests = [row["sha256"] for row in artifacts]
    for index, row_value in enumerate(evidence_rows):
        if not isinstance(row_value, dict):
            raise ReceiptError("acceptance.evidence[%d] is not an object" % index)
        label = "acceptance.evidence[%d]" % index
        if "condition_id" in row_value:
            row = _exact_object(
                row_value,
                frozenset({"condition_id", "path", "sha256", "observation"}),
                label,
            )
            _identifier(row["condition_id"], label + ".condition_id")
            evidence_path = _serialized_path(row["path"], label + ".path")
            evidence_sha = _sha256(row["sha256"], label + ".sha256")
            _text(row["observation"], label + ".observation")
            if (evidence_path, evidence_sha) not in bindings:
                raise ReceiptError(label + " is not bound to substrate or artifact bytes")
            continue
        kind = row_value.get("kind")
        if kind == "MHA_STRUCTURE":
            row = _exact_object(
                row_value,
                frozenset(
                    {
                        "kind",
                        "status",
                        "substrate_sha256",
                        "actual_bytes",
                        "expected_bytes",
                        "output_addresses",
                        "wire_plane_bytes",
                        "gate_records",
                        "gate_record_format",
                    }
                ),
                label,
            )
            if row["status"] != "MATCH":
                raise ReceiptError(label + ".status is not MATCH")
            if _sha256(row["substrate_sha256"], label + ".substrate_sha256") != substrate["sha256"]:
                raise ReceiptError(label + " names a different substrate digest")
            if _integer(row["actual_bytes"], label + ".actual_bytes", 8) != substrate["bytes"]:
                raise ReceiptError(label + ".actual_bytes is inconsistent")
            if _integer(row["expected_bytes"], label + ".expected_bytes", 8) != substrate["expected_file_bytes"]:
                raise ReceiptError(label + ".expected_bytes is inconsistent")
            if _integer(row["output_addresses"], label + ".output_addresses", 1) != len(substrate["output_addresses"]):
                raise ReceiptError(label + ".output_addresses is inconsistent")
            if _integer(row["wire_plane_bytes"], label + ".wire_plane_bytes", 1) != substrate["wire_plane"]["bytes"]:
                raise ReceiptError(label + ".wire_plane_bytes is inconsistent")
            if _integer(row["gate_records"], label + ".gate_records") != substrate["gates"]["count"]:
                raise ReceiptError(label + ".gate_records is inconsistent")
            if row["gate_record_format"] != "<BQQQ":
                raise ReceiptError(label + ".gate_record_format is not <BQQQ>")
            continue
        if kind == "DELIVERED_ARTIFACT_HASHES":
            row = _exact_object(
                row_value,
                frozenset({"kind", "status", "count", "sha256"}),
                label,
            )
            if row["status"] != "RECORDED":
                raise ReceiptError(label + ".status is not RECORDED")
            if _integer(row["count"], label + ".count") != len(artifacts):
                raise ReceiptError(label + ".count is inconsistent")
            if not isinstance(row["sha256"], list):
                raise ReceiptError(label + ".sha256 is not an array")
            digests = [
                _sha256(digest, "%s.sha256[%d]" % (label, position))
                for position, digest in enumerate(row["sha256"])
            ]
            if digests != artifact_digests:
                raise ReceiptError(label + ".sha256 does not match artifacts in order")
            continue
        if kind == "ACCEPTANCE_NOTE":
            row = _exact_object(
                row_value,
                frozenset({"kind", "status", "value"}),
                label,
            )
            if row["status"] != "RECORDED":
                raise ReceiptError(label + ".status is not RECORDED")
            _text(row["value"], label + ".value")
            continue
        raise ReceiptError(label + " has an unrecognized evidence shape")
    return acceptance


def _validate_receipt_contract(value: Any) -> dict[str, Any]:
    receipt = _exact_object(value, TOP_LEVEL_KEYS, "receipt")
    if receipt["schema_version"] != SCHEMA_VERSION:
        raise ReceiptError("receipt.schema_version is not %s" % SCHEMA_VERSION)
    if receipt["kind"] != "DELIVERY_RECEIPT":
        raise ReceiptError("receipt.kind is not DELIVERY_RECEIPT")
    _identifier(receipt["receipt_id"], "receipt.receipt_id")
    _identifier(receipt["job_id"], "receipt.job_id")
    quote_id = _identifier(receipt["quote_id"], "receipt.quote_id", nullable=True)
    if receipt["status"] not in DELIVERY_STATUSES:
        raise ReceiptError("receipt.status is not recognized")
    _aware_timestamp(receipt["delivered_at"], "receipt.delivered_at")
    _text(receipt["result_address"], "receipt.result_address")

    substrate = _validate_substrate(receipt["substrate"])
    artifacts = _validate_artifacts(receipt["artifacts"])
    acceptance = _validate_acceptance(receipt["acceptance"], substrate, artifacts)

    bazaar = _exact_object(
        receipt["bazaar"],
        frozenset({"offer_id", "action_id", "result_id", "note"}),
        "bazaar",
    )
    _identifier(bazaar["offer_id"], "bazaar.offer_id", nullable=True)
    action_id = _identifier(bazaar["action_id"], "bazaar.action_id", nullable=True)
    result_id = _identifier(bazaar["result_id"], "bazaar.result_id", nullable=True)
    _text(bazaar["note"], "bazaar.note", nonempty=False)
    if (action_id is None) != (result_id is None):
        raise ReceiptError("bazaar.action_id and bazaar.result_id must be supplied together")

    payment = _exact_object(
        receipt["payment"], frozenset({"reference", "status"}), "payment"
    )
    payment_status = payment["status"]
    if payment_status not in PAYMENT_STATUSES:
        raise ReceiptError("payment.status is not recognized")
    payment_reference = payment["reference"]
    if payment_status == "NOT_REQUESTED":
        if payment_reference is not None:
            raise ReceiptError("payment.reference must be null when status is NOT_REQUESTED")
    elif not isinstance(payment_reference, str) or not payment_reference.strip():
        raise ReceiptError("payment.reference must be nonempty for this payment status")

    if receipt["status"] == "DELIVERED":
        if quote_id is None:
            raise ReceiptError("DELIVERED receipt requires quote_id")
        if acceptance["status"] != "PASS":
            raise ReceiptError("DELIVERED receipt requires PASS acceptance")
        if action_id is None or result_id is None:
            raise ReceiptError("DELIVERED receipt requires Bazaar action_id and result_id")
    return receipt


def build_receipt(
    *,
    substrate: str | os.PathLike[str],
    artifacts: Iterable[str | os.PathLike[str]] = (),
    receipt_id: str | None = None,
    job_id: str | None = None,
    quote_id: str | None = None,
    delivered_at: str | None = None,
    result_address: str | None = None,
    status: str = "MEASURED",
    acceptance_status: str = "PASS",
    acceptance_evidence: Iterable[str] = (),
    bazaar_offer_id: str | None = None,
    bazaar_action_id: str | None = None,
    bazaar_result_id: str | None = None,
    payment_reference: str | None = None,
) -> dict[str, Any]:
    if status not in DELIVERY_STATUSES:
        raise ReceiptError("unknown delivery status: %s" % status)
    if acceptance_status not in ACCEPTANCE_STATUSES:
        raise ReceiptError("unknown acceptance status: %s" % acceptance_status)
    measured = parse_mha(substrate)
    artifact_rows = [hash_artifact(path) for path in artifacts]
    if not artifact_rows:
        raise ReceiptError("at least one delivered artifact is required")
    stem = _id_component(Path(measured["path"]).stem)
    computer_short = measured["sha256"][:12]
    resolved_receipt_id = receipt_id or "substrate-%s-%s" % (stem, computer_short)
    resolved_job_id = job_id or "substrate-job-%s-%s" % (stem, computer_short)
    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "DELIVERY_RECEIPT",
        "receipt_id": resolved_receipt_id,
        "job_id": resolved_job_id,
        "quote_id": quote_id,
        "delivered_at": delivered_at or _utc_now(),
        "status": status,
        "result_address": result_address or "receipt:%s" % resolved_receipt_id,
        "substrate": measured,
        "artifacts": artifact_rows,
        "acceptance": {
            "status": acceptance_status,
            "evidence": [
                {
                    "condition_id": "mha-structure-pass-01",
                    "path": measured["path"],
                    "sha256": measured["sha256"],
                    "observation": (
                        "%s: <8sIIIII> gates=%d wires=%d inputs=%d outputs=%d "
                        "depth=%d; %d-byte header; %d output <Q> addresses; "
                        "%d-byte wire plane; %d exact <BQQQ> gate records; "
                        "%d-byte body ends at the %d-byte file boundary."
                        % (
                            measured["header"]["magic_ascii"],
                            measured["header"]["n_gate"],
                            measured["header"]["n_wires"],
                            measured["header"]["n_in"],
                            measured["header"]["n_out"],
                            measured["header"]["depth"],
                            measured["header"]["bytes"],
                            len(measured["output_addresses"]),
                            measured["wire_plane"]["bytes"],
                            measured["gates"]["count"],
                            measured["gates"]["body_bytes"],
                            measured["bytes"],
                        )
                    ),
                },
            ]
            + [
                {
                    "condition_id": "artifact-hash-pass-%02d" % (index + 1),
                    "path": row["path"],
                    "sha256": row["sha256"],
                    "observation": "%d delivered bytes match this SHA-256."
                    % row["bytes"],
                }
                for index, row in enumerate(artifact_rows)
            ]
            + [
                {
                    "kind": "ACCEPTANCE_NOTE",
                    "status": "RECORDED",
                    "value": note,
                }
                for note in acceptance_evidence
            ],
        },
        "bazaar": {
            "offer_id": bazaar_offer_id,
            "action_id": bazaar_action_id,
            "result_id": bazaar_result_id,
            "note": (
                "Caller-supplied Bazaar lineage identifiers."
                if any((bazaar_offer_id, bazaar_action_id, bazaar_result_id))
                else "No Bazaar lineage identifiers were supplied for this receipt."
            ),
        },
        "payment": {
            "reference": payment_reference,
            "status": "REFERENCE_ONLY" if payment_reference else "NOT_REQUESTED",
        },
    }
    return _validate_receipt_contract(receipt)


def _compare_subset(expected: Any, actual: Any, label: str) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise ReceiptError("%s is not an object" % label)
        for key, value in expected.items():
            if key not in actual:
                raise ReceiptError("%s.%s is missing from current measurement" % (label, key))
            _compare_subset(value, actual[key], "%s.%s" % (label, key))
        return
    if expected != actual:
        raise ReceiptError("%s mismatch: receipt=%r current=%r" % (label, expected, actual))


def _measurement_source(
    recorded_path: str,
    override: str | os.PathLike[str] | None,
    label: str,
    option: str,
) -> Path:
    if override is not None:
        return _resolve_existing(override)
    if recorded_path.startswith("external/"):
        raise ReceiptError("%s requires %s for remeasurement" % (label, option))
    source = _resolve_existing(recorded_path)
    try:
        source.relative_to(REPO_ROOT)
    except ValueError as error:
        raise ReceiptError("%s requires %s for remeasurement" % (label, option)) from error
    return source


def check_receipt(
    path: str | os.PathLike[str],
    *,
    substrate_source: str | os.PathLike[str] | None = None,
    artifact_sources: Iterable[str | os.PathLike[str]] = (),
) -> dict[str, Any]:
    receipt_path = _resolve_existing(path)
    with receipt_path.open(encoding="utf-8") as handle:
        receipt = json.load(handle)
    receipt = _validate_receipt_contract(receipt)
    recorded_substrate = receipt["substrate"]
    substrate_path = _measurement_source(
        recorded_substrate["path"],
        substrate_source,
        "substrate.path",
        "--substrate-source",
    )
    current_substrate = parse_mha(substrate_path)
    current_substrate["path"] = recorded_substrate["path"]
    _compare_subset(recorded_substrate, current_substrate, "substrate")

    artifact_rows = receipt["artifacts"]
    source_overrides = list(artifact_sources)
    if source_overrides and len(source_overrides) != len(artifact_rows):
        raise ReceiptError(
            "--artifact-source count %d does not match %d receipt artifacts"
            % (len(source_overrides), len(artifact_rows))
        )
    checked_artifacts: list[dict[str, Any]] = []
    for index, recorded in enumerate(artifact_rows):
        override = source_overrides[index] if source_overrides else None
        artifact_path = _measurement_source(
            recorded["path"],
            override,
            "artifacts[%d].path" % index,
            "--artifact-source",
        )
        current = hash_artifact(artifact_path)
        current["path"] = recorded["path"]
        measured_record = {
            key: recorded[key] for key in ("path", "sha256", "bytes") if key in recorded
        }
        _compare_subset(measured_record, current, "artifacts[%d]" % index)
        checked_artifacts.append(current)

    return {
        "receipt": _display_path(receipt_path),
        "receipt_id": receipt.get("receipt_id"),
        "status": "VALID",
        "substrate_sha256": current_substrate["sha256"],
        "substrate_bytes": current_substrate["bytes"],
        "artifact_count": len(checked_artifacts),
    }


def _write_json(data: Mapping[str, Any], destination: str | None) -> None:
    rendered = json.dumps(data, indent=2, sort_keys=False) + "\n"
    if not destination or destination == "-":
        sys.stdout.write(rendered)
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    print(path.as_posix())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="revenue/dio/substrate_receipt.py",
        description="Generate or check an exact MHA substrate delivery receipt.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    generate = commands.add_parser("generate", help="measure files and emit a receipt")
    generate.add_argument("--substrate", required=True)
    generate.add_argument("--artifact", action="append", required=True)
    generate.add_argument("--receipt-id")
    generate.add_argument("--job-id")
    generate.add_argument("--quote-id")
    generate.add_argument("--delivered-at")
    generate.add_argument("--status", default="MEASURED")
    generate.add_argument("--result-address")
    generate.add_argument("--acceptance-status", default="PASS")
    generate.add_argument("--acceptance-evidence", action="append", default=[])
    generate.add_argument("--bazaar-offer-id")
    generate.add_argument("--bazaar-action-id")
    generate.add_argument("--bazaar-result-id")
    generate.add_argument("--payment-reference")
    generate.add_argument("--out")

    check = commands.add_parser("check", help="remeasure every bound file")
    check.add_argument("--receipt", required=True)
    check.add_argument("--substrate-source")
    check.add_argument("--artifact-source", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate":
            receipt = build_receipt(
                substrate=args.substrate,
                artifacts=args.artifact,
                receipt_id=args.receipt_id,
                job_id=args.job_id,
                quote_id=args.quote_id,
                delivered_at=args.delivered_at,
                result_address=args.result_address,
                status=args.status,
                acceptance_status=args.acceptance_status,
                acceptance_evidence=args.acceptance_evidence,
                bazaar_offer_id=args.bazaar_offer_id,
                bazaar_action_id=args.bazaar_action_id,
                bazaar_result_id=args.bazaar_result_id,
                payment_reference=args.payment_reference,
            )
            _write_json(receipt, args.out)
            return 0
        if args.command == "check":
            _write_json(
                check_receipt(
                    args.receipt,
                    substrate_source=args.substrate_source,
                    artifact_sources=args.artifact_source,
                ),
                None,
            )
            return 0
    except (OSError, ReceiptError, json.JSONDecodeError) as error:
        print("ERROR: %s" % error, file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
