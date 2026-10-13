#!/usr/bin/env python3
"""RINGDELTA — Muhlnickel-native lossless XOR-delta codec.

Additive. Does not remint foldpack.py, stackpack.py, evolve.py, muhc.py,
titan/engines/muhl_compress.py, the eight compress.html doors, or SEED0.
Titan not written. No auth.

Organ law: excerpts/20260828/ringdelta_xor8.mno
  magic MUHLRD01, 8 XOR gates (opcode 0 on this organ), stride 25
  inject 40..55, surface 56..63
  colony-aligned: 28-byte header + 72-byte zero wire plane + 200-byte gates = 300 B
  page 1 (bytes 150..299) is the last six gate records and matches the
  original PR 4898 colony page-1 sha256.

Compression: each tick XORs one previous-column byte with one current-column
byte. Width 25 is the Muhlnickel gate-record stride. Native RDV1 stores a
48-byte header, a presence bitmask, and the nonzero delta bytes. zlib numbers
are weather and live in a separate room.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORGAN_PATH = ROOT / "excerpts" / "20260828" / "ringdelta_xor8.mno"
SEED0_PATH = ROOT / "muhl" / "containers" / "MUHLNICKEL_DISTRO" / "SEED0.mno"

MAGIC_MNO = b"MUHLRD01"
MAGIC_RDV1 = b"RDV1"
WIDTH = 25
N_GATE = 8
N_WIRES = 72
N_IN = 16
N_OUT = 8
DEPTH = 1
OP_XOR = 0  # RINGDELTA opcode map: XOR=0
INJECT0 = 40
SURFACE0 = 56
ORGAN_BYTES = 300
RDV1_HEADER_BYTES = 48
PAGE_BYTES = 150
PAGE1_SHA256 = "ba209df3e3ca41d60ed71b4c46f5b8834d3d5a7ed04b0cbef14ecba4d4ca1e6d"
SEED0_SHA256 = "faa70efc328e9b596eb27d6c1b2e2c4d76a863d8a81380f0d22ec7a8e4d85071"
PR4898_CLAIMED_ORGAN_SHA256 = (
    "a06d90086949e6073d077ffd0ed4c593091414b7053daf9340efaf389b245da9"
)
PR4898_CLAIMED_PAGE0_SHA256 = (
    "659fff137b8c1c58599e3257d7ff79e27517c0effe2b249dfe7b656ff96d14d0"
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rec(op: int, a: int, b: int, out: int) -> bytes:
    return struct.pack("<BQQQ", op, a, b, out)


def fabricate_organ() -> bytes:
    header = MAGIC_MNO + struct.pack("<5I", N_GATE, N_WIRES, N_IN, N_OUT, DEPTH)
    wires = bytes(N_WIRES)
    gates = b"".join(
        rec(OP_XOR, INJECT0 + i, INJECT0 + 8 + i, SURFACE0 + i) for i in range(N_GATE)
    )
    blob = header + wires + gates
    if len(blob) != ORGAN_BYTES:
        raise RuntimeError("organ size %d != %d" % (len(blob), ORGAN_BYTES))
    return blob


def parse_organ(blob: bytes) -> dict:
    if len(blob) != ORGAN_BYTES:
        raise ValueError("organ must be %d bytes, got %d" % (ORGAN_BYTES, len(blob)))
    if blob[:8] != MAGIC_MNO:
        raise ValueError("bad magic %r" % (blob[:8],))
    n_gate, n_wires, n_in, n_out, depth = struct.unpack_from("<5I", blob, 8)
    gates = []
    off = 28 + n_wires
    for i in range(n_gate):
        gates.append(struct.unpack_from("<BQQQ", blob, off))
        off += WIDTH
    return {
        "n_gate": n_gate,
        "n_wires": n_wires,
        "n_in": n_in,
        "n_out": n_out,
        "depth": depth,
        "gates": gates,
        "page0_sha256": sha256(blob[:PAGE_BYTES]),
        "page1_sha256": sha256(blob[PAGE_BYTES:]),
        "sha256": sha256(blob),
    }


def xor_delta(src: bytes, width: int = WIDTH) -> bytes:
    out = bytearray(len(src))
    for i, b in enumerate(src):
        prev = src[i - width] if i >= width else 0
        out[i] = b ^ prev
    return bytes(out)


def xor_undelta(delta: bytes, width: int = WIDTH) -> bytes:
    out = bytearray(len(delta))
    for i, b in enumerate(delta):
        prev = out[i - width] if i >= width else 0
        out[i] = b ^ prev
    return bytes(out)


def encode_rdv1(src: bytes, width: int = WIDTH) -> bytes:
    delta = xor_delta(src, width)
    n_zero = delta.count(0)
    n_nz = len(delta) - n_zero
    header = bytearray(RDV1_HEADER_BYTES)
    header[0:4] = MAGIC_RDV1
    struct.pack_into("<5I", header, 4, 1, len(src), width, n_zero, n_nz)
    bitmask = bytearray((len(src) + 7) // 8)
    values = bytearray()
    for i, b in enumerate(delta):
        if b:
            bitmask[i >> 3] |= 1 << (i & 7)
            values.append(b)
    if len(values) != n_nz:
        raise RuntimeError("nonzero count drifted")
    return bytes(header) + bytes(bitmask) + bytes(values)


def decode_rdv1(blob: bytes) -> bytes:
    if len(blob) < RDV1_HEADER_BYTES or blob[:4] != MAGIC_RDV1:
        raise ValueError("not an RDV1 container")
    version, src_len, width, n_zero, n_nz = struct.unpack_from("<5I", blob, 4)
    if version != 1:
        raise ValueError("unsupported RDV1 version %d" % version)
    if width != WIDTH:
        raise ValueError("RDV1 width %d != %d" % (width, WIDTH))
    mask_len = (src_len + 7) // 8
    need = RDV1_HEADER_BYTES + mask_len + n_nz
    if len(blob) != need:
        raise ValueError("RDV1 size %d != %d" % (len(blob), need))
    bitmask = blob[RDV1_HEADER_BYTES : RDV1_HEADER_BYTES + mask_len]
    values = blob[RDV1_HEADER_BYTES + mask_len :]
    delta = bytearray(src_len)
    vi = 0
    for i in range(src_len):
        if bitmask[i >> 3] & (1 << (i & 7)):
            delta[i] = values[vi]
            vi += 1
    if vi != n_nz:
        raise ValueError("RDV1 bitmask/value mismatch")
    if delta.count(0) != n_zero:
        raise ValueError("RDV1 zero count mismatch")
    return xor_undelta(bytes(delta), width)


def measure(src: bytes, label: str = "source") -> dict:
    delta = xor_delta(src)
    container = encode_rdv1(src)
    back = decode_rdv1(container)
    organ = fabricate_organ()
    parsed = parse_organ(organ)
    return {
        "label": label,
        "source_b": len(src),
        "source_sha256": sha256(src),
        "delta_zeros": delta.count(0),
        "delta_zero_pct": round(100.0 * delta.count(0) / len(src), 2) if src else 0.0,
        "native_container_b": len(container),
        "native_vs_source_pct": round(100.0 * len(container) / len(src), 2) if src else 0.0,
        "zlib_source_b": len(zlib.compress(src, 9)),
        "zlib_delta_b": len(zlib.compress(delta, 9)),
        "roundtrip": "EXACT" if back == src else "FAIL",
        "roundtrip_sha256": sha256(back),
        "organ_bytes": len(organ),
        "organ_sha256": parsed["sha256"],
        "page0_sha256": parsed["page0_sha256"],
        "page1_sha256": parsed["page1_sha256"],
        "page1_matches_pr4898": parsed["page1_sha256"] == PAGE1_SHA256,
    }


def write_organ(path: Path = ORGAN_PATH) -> bytes:
    blob = fabricate_organ()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return blob


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--write-organ", action="store_true")
    parser.add_argument("--encode", type=Path)
    parser.add_argument("--decode", type=Path)
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--seed0", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        organ = fabricate_organ()
        parsed = parse_organ(organ)
        assert parsed["page1_sha256"] == PAGE1_SHA256, parsed["page1_sha256"]
        assert organ[:8] == MAGIC_MNO
        seed = SEED0_PATH.read_bytes()
        assert sha256(seed) == SEED0_SHA256
        stats = measure(seed, "SEED0")
        assert stats["roundtrip"] == "EXACT"
        assert stats["delta_zeros"] == 6145
        assert stats["native_container_b"] == 3119
        assert stats["zlib_source_b"] == 1391
        assert stats["zlib_delta_b"] == 1025
        noise = bytes(range(256)) * 3 + b"RINGDELTA"
        assert decode_rdv1(encode_rdv1(noise)) == noise
        print(json.dumps({"ok": True, **stats}, indent=2, sort_keys=True))
        return 0

    if args.write_organ:
        blob = write_organ()
        parsed = parse_organ(blob)
        print(json.dumps(parsed, indent=2, sort_keys=True))
        return 0

    if args.encode or args.seed0:
        src = SEED0_PATH.read_bytes() if args.seed0 else args.encode.read_bytes()
        out = encode_rdv1(src)
        if args.output:
            args.output.write_bytes(out)
        else:
            sys.stdout.buffer.write(out)
        return 0

    if args.decode:
        src = decode_rdv1(args.decode.read_bytes())
        if args.output:
            args.output.write_bytes(src)
        else:
            sys.stdout.buffer.write(src)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
