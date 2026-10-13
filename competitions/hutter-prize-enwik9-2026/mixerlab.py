#!/usr/bin/env python3
"""Bounded-memory reversible compression laboratory for the Hutter enwik9 prize.

This module is intentionally self-contained and standard-library only. It is a
research carrier, not a claim that the current implementation beats the Hutter
record. Archives bind their payload and uncompressed bytes with SHA-256 so
truncation/corruption fails closed.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import os
from pathlib import Path
import resource
import struct
import time
from typing import Iterable, Sequence

MAGIC = b"HML1"
VERSION = 1
ESC = 0xFF
MAX_CODE = 0xFE
PROB_TOTAL = 65536
HALF = 1 << 31
FIRST_QTR = 1 << 30
THIRD_QTR = 3 << 30
MAX_RANGE = (1 << 32) - 1

# Fixed, submission-visible dictionary. Longest-match encoding is deterministic.
# Codes start at 1; 0 is reserved for a literal ESC byte.
WIKI_TOKENS: tuple[bytes, ...] = (
    b"</text>", b"<text", b"</page>", b"<page>", b"</revision>", b"<revision>",
    b"</title>", b"<title>", b"<timestamp>", b"</timestamp>", b"<contributor>",
    b"</contributor>", b"<username>", b"</username>", b"<comment>", b"</comment>",
    b"<minor />", b"<id>", b"</id>", b"<sha1>", b"</sha1>", b"<model>", b"</model>",
    b"<format>", b"</format>", b"<redirect title=\"", b"http://", b"https://", b"&quot;",
    b"&amp;", b"&lt;", b"&gt;", b"[[", b"]]", b"{{", b"}}", b"==", b"\n    ",
    b"\n  ", b"\n",
)
if len(WIKI_TOKENS) > MAX_CODE:
    raise RuntimeError("token dictionary exceeds one-byte code space")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_token_trie(tokens: Sequence[bytes]) -> dict:
    root: dict = {}
    for code, token in enumerate(tokens, start=1):
        node = root
        for value in token:
            node = node.setdefault(value, {})
        node[None] = code
    return root


_TOKEN_TRIE = _build_token_trie(WIKI_TOKENS)


def wiki_transform_encode(data: bytes) -> bytes:
    """Reversibly tokenise common enwik XML/text seams.

    Literal 0xff becomes ``ff 00``. A matched token becomes ``ff CODE``.
    All other bytes pass through unchanged. Longest token wins.
    """
    out = bytearray()
    i = 0
    n = len(data)
    while i < n:
        node = _TOKEN_TRIE
        j = i
        best_code = None
        best_end = i
        while j < n:
            child = node.get(data[j])
            if child is None:
                break
            node = child
            j += 1
            code = node.get(None)
            if code is not None:
                best_code = code
                best_end = j
        if best_code is not None:
            out.extend((ESC, best_code))
            i = best_end
            continue
        value = data[i]
        if value == ESC:
            out.extend((ESC, 0))
        else:
            out.append(value)
        i += 1
    return bytes(out)


def wiki_transform_decode(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        value = data[i]
        if value != ESC:
            out.append(value)
            i += 1
            continue
        if i + 1 >= len(data):
            raise ValueError("malformed transform: trailing escape")
        code = data[i + 1]
        if code == 0:
            out.append(ESC)
        elif 1 <= code <= len(WIKI_TOKENS):
            out.extend(WIKI_TOKENS[code - 1])
        else:
            raise ValueError(f"malformed transform: unknown token code {code}")
        i += 2
    return bytes(out)


class BitWriter:
    def __init__(self) -> None:
        self._buffer = bytearray()
        self._current = 0
        self._used = 0
        self.nbits = 0

    def write(self, bit: int) -> None:
        if bit not in (0, 1):
            raise ValueError("bit must be 0 or 1")
        self._current = (self._current << 1) | bit
        self._used += 1
        self.nbits += 1
        if self._used == 8:
            self._buffer.append(self._current)
            self._current = 0
            self._used = 0

    def finish(self) -> bytes:
        if self._used:
            self._buffer.append(self._current << (8 - self._used))
            self._current = 0
            self._used = 0
        return bytes(self._buffer)


class BitReader:
    def __init__(self, data: bytes, bit_length: int) -> None:
        if bit_length < 0 or bit_length > len(data) * 8:
            raise ValueError("invalid bit length")
        self.data = data
        self.bit_length = bit_length
        self.pos = 0

    def read_or_zero(self) -> int:
        # Arithmetic decoders conventionally consume implicit zero padding after
        # the final coded bit. Payload SHA + explicit bit_length prevent this
        # from masking archive truncation.
        if self.pos >= self.bit_length:
            self.pos += 1
            return 0
        byte = self.data[self.pos >> 3]
        bit = (byte >> (7 - (self.pos & 7))) & 1
        self.pos += 1
        return bit


def _mix64(value: int) -> int:
    value &= 0xFFFFFFFFFFFFFFFF
    value ^= value >> 30
    value = (value * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
    value ^= value >> 27
    value = (value * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
    value ^= value >> 31
    return value & 0xFFFFFFFFFFFFFFFF


def _byte_class(value: int) -> int:
    if 65 <= value <= 90 or 97 <= value <= 122:
        return 1
    if 48 <= value <= 57:
        return 2
    if value in (9, 10, 13, 32):
        return 3
    if value in b"<>{}[]=/|:'\"&;_-":
        return 4
    if value >= 128:
        return 5
    return 0


class BoundedContextMixer:
    """Fixed-size hashed adaptive bit model.

    Context collisions are intentional and deterministic. Memory does not grow
    with corpus length: two uint16 arrays of 2**table_bits entries are allocated
    once. Each update uses five views of byte history/current bit prefix.
    """

    def __init__(self, table_bits: int = 16) -> None:
        if table_bits < 10 or table_bits > 20:
            raise ValueError("table_bits must be in [10, 20]")
        self.table_bits = table_bits
        self.size = 1 << table_bits
        self.mask = self.size - 1
        self.c0 = array("H", [1]) * self.size
        self.c1 = array("H", [1]) * self.size
        self.h1 = 0
        self.h2 = 0
        self.h3 = 0

    @property
    def table_bytes(self) -> int:
        return len(self.c0) * self.c0.itemsize + len(self.c1) * self.c1.itemsize

    def _indices(self, bitpos: int, prefix: int) -> tuple[int, ...]:
        # Type salts make the different semantic contexts independent before
        # hashing; prefix separates current-byte partial symbols.
        common = (bitpos << 8) | prefix
        raw = (
            0x11_000000 | common,
            0x22_000000 | (self.h1 << 11) | common,
            0x33_000000 | (self.h2 << 19) | (self.h1 << 11) | common,
            0x44_000000 | (self.h3 << 27) | (self.h2 << 19) | (self.h1 << 11) | common,
            0x55_000000 | (_byte_class(self.h1) << 16) | common,
        )
        return tuple(_mix64(value) & self.mask for value in raw)

    def probability_one(self, bitpos: int, prefix: int) -> tuple[int, tuple[int, ...]]:
        indices = self._indices(bitpos, prefix)
        # Higher-order history gets more vote while lower orders provide robust
        # fallbacks for unseen/collided contexts.
        weights = (1, 2, 3, 4, 2)
        weighted = 0
        weight_total = 0
        for idx, weight in zip(indices, weights):
            zero = self.c0[idx]
            one = self.c1[idx]
            p1 = ((one + 1) * PROB_TOTAL) // (zero + one + 2)
            if p1 <= 0:
                p1 = 1
            elif p1 >= PROB_TOTAL:
                p1 = PROB_TOTAL - 1
            weighted += p1 * weight
            weight_total += weight
        mixed = weighted // weight_total
        if mixed <= 0:
            mixed = 1
        elif mixed >= PROB_TOTAL:
            mixed = PROB_TOTAL - 1
        return mixed, indices

    def update(self, indices: Iterable[int], bit: int) -> None:
        for idx in indices:
            if bit:
                one = self.c1[idx]
                zero = self.c0[idx]
                if one + zero >= 4096:
                    self.c0[idx] = max(1, (zero + 1) >> 1)
                    self.c1[idx] = max(1, (one + 1) >> 1)
                self.c1[idx] += 1
            else:
                one = self.c1[idx]
                zero = self.c0[idx]
                if one + zero >= 4096:
                    self.c0[idx] = max(1, (zero + 1) >> 1)
                    self.c1[idx] = max(1, (one + 1) >> 1)
                self.c0[idx] += 1

    def push_byte(self, value: int) -> None:
        self.h3, self.h2, self.h1 = self.h2, self.h1, value


class ArithmeticEncoder:
    def __init__(self) -> None:
        self.low = 0
        self.high = MAX_RANGE
        self.pending = 0
        self.bits = BitWriter()

    def _emit(self, bit: int) -> None:
        self.bits.write(bit)
        follow = 1 - bit
        while self.pending:
            self.bits.write(follow)
            self.pending -= 1

    def encode(self, bit: int, p1: int) -> None:
        if not (1 <= p1 < PROB_TOTAL):
            raise ValueError("probability out of range")
        freq0 = PROB_TOTAL - p1
        span = self.high - self.low + 1
        cut = self.low + (span * freq0 // PROB_TOTAL)
        if cut <= self.low or cut > self.high:
            raise RuntimeError("arithmetic interval collapsed")
        if bit == 0:
            self.high = cut - 1
        else:
            self.low = cut
        while True:
            if self.high < HALF:
                self._emit(0)
            elif self.low >= HALF:
                self._emit(1)
                self.low -= HALF
                self.high -= HALF
            elif self.low >= FIRST_QTR and self.high < THIRD_QTR:
                self.pending += 1
                self.low -= FIRST_QTR
                self.high -= FIRST_QTR
            else:
                break
            self.low = (self.low << 1) & MAX_RANGE
            self.high = ((self.high << 1) | 1) & MAX_RANGE

    def finish(self) -> tuple[bytes, int]:
        self.pending += 1
        if self.low < FIRST_QTR:
            self._emit(0)
        else:
            self._emit(1)
        payload = self.bits.finish()
        return payload, self.bits.nbits


class ArithmeticDecoder:
    def __init__(self, payload: bytes, bit_length: int) -> None:
        self.low = 0
        self.high = MAX_RANGE
        self.reader = BitReader(payload, bit_length)
        self.code = 0
        for _ in range(32):
            self.code = ((self.code << 1) | self.reader.read_or_zero()) & MAX_RANGE

    def decode(self, p1: int) -> int:
        if not (1 <= p1 < PROB_TOTAL):
            raise ValueError("probability out of range")
        freq0 = PROB_TOTAL - p1
        span = self.high - self.low + 1
        cut = self.low + (span * freq0 // PROB_TOTAL)
        if cut <= self.low or cut > self.high:
            raise RuntimeError("arithmetic interval collapsed")
        if self.code < cut:
            bit = 0
            self.high = cut - 1
        else:
            bit = 1
            self.low = cut
        while True:
            if self.high < HALF:
                pass
            elif self.low >= HALF:
                self.low -= HALF
                self.high -= HALF
                self.code -= HALF
            elif self.low >= FIRST_QTR and self.high < THIRD_QTR:
                self.low -= FIRST_QTR
                self.high -= FIRST_QTR
                self.code -= FIRST_QTR
            else:
                break
            self.low = (self.low << 1) & MAX_RANGE
            self.high = ((self.high << 1) | 1) & MAX_RANGE
            self.code = ((self.code << 1) | self.reader.read_or_zero()) & MAX_RANGE
        return bit


# magic, version, flags, table_bits, original_len, transformed_len, bit_length,
# original_sha256, transformed_sha256, payload_len
_HEADER = struct.Struct(">4sBBBBQQQ32s32sQ")
FLAG_WIKI_TRANSFORM = 0x01


def _encode_stream(data: bytes, table_bits: int) -> tuple[bytes, int]:
    mixer = BoundedContextMixer(table_bits)
    coder = ArithmeticEncoder()
    for value in data:
        prefix = 0
        for bitpos in range(8):
            bit = (value >> (7 - bitpos)) & 1
            p1, indices = mixer.probability_one(bitpos, prefix)
            coder.encode(bit, p1)
            mixer.update(indices, bit)
            prefix = (prefix << 1) | bit
        mixer.push_byte(value)
    return coder.finish()


def _decode_stream(payload: bytes, bit_length: int, output_len: int, table_bits: int) -> bytes:
    if output_len < 0:
        raise ValueError("negative output length")
    mixer = BoundedContextMixer(table_bits)
    coder = ArithmeticDecoder(payload, bit_length)
    out = bytearray()
    for _ in range(output_len):
        value = 0
        prefix = 0
        for bitpos in range(8):
            p1, indices = mixer.probability_one(bitpos, prefix)
            bit = coder.decode(p1)
            mixer.update(indices, bit)
            value = (value << 1) | bit
            prefix = (prefix << 1) | bit
        out.append(value)
        mixer.push_byte(value)
    return bytes(out)


def compress_bytes(data: bytes, *, use_transform: bool = True, table_bits: int = 16) -> bytes:
    transformed = wiki_transform_encode(data) if use_transform else data
    payload, bit_length = _encode_stream(transformed, table_bits)
    flags = FLAG_WIKI_TRANSFORM if use_transform else 0
    header = _HEADER.pack(
        MAGIC,
        VERSION,
        flags,
        table_bits,
        0,
        len(data),
        len(transformed),
        bit_length,
        hashlib.sha256(data).digest(),
        hashlib.sha256(transformed).digest(),
        len(payload),
    )
    return header + payload + hashlib.sha256(payload).digest()


def _parse_archive(archive: bytes) -> tuple[dict, bytes]:
    minimum = _HEADER.size + 32
    if len(archive) < minimum:
        raise ValueError("archive truncated before header/footer")
    fields = _HEADER.unpack_from(archive, 0)
    magic, version, flags, table_bits, reserved, original_len, transformed_len, bit_length, orig_hash, trans_hash, payload_len = fields
    if magic != MAGIC:
        raise ValueError("bad archive magic")
    if version != VERSION:
        raise ValueError(f"unsupported archive version {version}")
    if reserved != 0:
        raise ValueError("reserved header byte must be zero")
    if flags & ~FLAG_WIKI_TRANSFORM:
        raise ValueError("unknown archive flags")
    if table_bits < 10 or table_bits > 20:
        raise ValueError("invalid model table_bits")
    expected = _HEADER.size + payload_len + 32
    if len(archive) != expected:
        raise ValueError("archive length does not match header")
    payload = archive[_HEADER.size:_HEADER.size + payload_len]
    payload_hash = archive[-32:]
    if hashlib.sha256(payload).digest() != payload_hash:
        raise ValueError("archive payload SHA-256 mismatch")
    if bit_length > payload_len * 8:
        raise ValueError("bit length exceeds payload")
    meta = {
        "flags": flags,
        "table_bits": table_bits,
        "original_len": original_len,
        "transformed_len": transformed_len,
        "bit_length": bit_length,
        "original_sha256": orig_hash,
        "transformed_sha256": trans_hash,
        "payload_len": payload_len,
    }
    return meta, payload


def decompress_bytes(archive: bytes) -> bytes:
    meta, payload = _parse_archive(archive)
    transformed = _decode_stream(payload, meta["bit_length"], meta["transformed_len"], meta["table_bits"])
    if hashlib.sha256(transformed).digest() != meta["transformed_sha256"]:
        raise ValueError("decoded transformed SHA-256 mismatch")
    if meta["flags"] & FLAG_WIKI_TRANSFORM:
        original = wiki_transform_decode(transformed)
    else:
        original = transformed
    if len(original) != meta["original_len"]:
        raise ValueError("decoded original length mismatch")
    if hashlib.sha256(original).digest() != meta["original_sha256"]:
        raise ValueError("decoded original SHA-256 mismatch")
    return original


def canonical_json_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8")


def program_accounted_bytes(archive_bytes: int, *, combined_program_bytes: int | None = None,
                            compressor_bytes: int | None = None, decompressor_bytes: int | None = None) -> int:
    """Apply the Hutter size-accounting shapes documented in the current rules.

    A combined compressor/decompressor artifact is counted once. For distinct
    programs the published alternative-program rule counts compressor + twice
    decompressor, because decompression is used in both directions of judging.
    """
    if archive_bytes < 0:
        raise ValueError("negative archive size")
    if combined_program_bytes is not None:
        if compressor_bytes is not None or decompressor_bytes is not None:
            raise ValueError("combined and split program accounting are mutually exclusive")
        if combined_program_bytes < 0:
            raise ValueError("negative program size")
        return archive_bytes + combined_program_bytes
    if compressor_bytes is None or decompressor_bytes is None:
        raise ValueError("split accounting requires compressor and decompressor sizes")
    if compressor_bytes < 0 or decompressor_bytes < 0:
        raise ValueError("negative program size")
    return archive_bytes + compressor_bytes + (2 * decompressor_bytes)


def benchmark(data: bytes, *, use_transform: bool = True, table_bits: int = 16,
              program_bytes: int = 0, evidence_class: str = "fixture") -> tuple[dict, bytes]:
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    started = time.perf_counter()
    archive = compress_bytes(data, use_transform=use_transform, table_bits=table_bits)
    decoded = decompress_bytes(archive)
    elapsed = time.perf_counter() - started
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KiB; macOS reports bytes. The cloud/runtime path for this
    # repository is Linux, but the raw field is preserved so the receipt is not
    # pretending cross-platform equivalence.
    peak_rss_raw = max(rss_before, rss_after)
    peak_rss_bytes_linux = int(peak_rss_raw) * 1024
    roundtrip = decoded == data
    body = {
        "schema": "hutter-mixerlab-benchmark-v1",
        "evidence_class": evidence_class,
        "input_bytes": len(data),
        "input_sha256": sha256_hex(data),
        "archive_bytes": len(archive),
        "archive_sha256": sha256_hex(archive),
        "program_bytes": int(program_bytes),
        "total_accounted_bytes": program_accounted_bytes(len(archive), combined_program_bytes=int(program_bytes)),
        "ratio_archive_only": (len(archive) / len(data)) if data else None,
        "elapsed_seconds": round(elapsed, 6),
        "peak_rss_raw": int(peak_rss_raw),
        "peak_rss_bytes_linux_interpretation": peak_rss_bytes_linux,
        "table_bits": table_bits,
        "model_table_bytes": BoundedContextMixer(table_bits).table_bytes,
        "wiki_transform": bool(use_transform),
        "roundtrip": roundtrip,
        "output_sha256": sha256_hex(decoded),
        "network_used": False,
        "gpu_used": False,
    }
    body["receipt_sha256"] = sha256_hex(canonical_json_bytes(body))
    return body, archive


def verify_receipt(receipt: dict) -> None:
    clone = dict(receipt)
    claimed = clone.pop("receipt_sha256", None)
    if not isinstance(claimed, str):
        raise ValueError("receipt missing receipt_sha256")
    actual = sha256_hex(canonical_json_bytes(clone))
    if claimed != actual:
        raise ValueError("receipt SHA-256 mismatch")
    if clone.get("schema") != "hutter-mixerlab-benchmark-v1":
        raise ValueError("unsupported receipt schema")
    if clone.get("roundtrip") is not True:
        raise ValueError("receipt does not prove roundtrip")
    if clone.get("input_sha256") != clone.get("output_sha256"):
        raise ValueError("input/output hashes differ")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        with temp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except FileNotFoundError:
            pass


def cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_compress = sub.add_parser("compress")
    p_compress.add_argument("input", type=Path)
    p_compress.add_argument("output", type=Path)
    p_compress.add_argument("--no-transform", action="store_true")
    p_compress.add_argument("--table-bits", type=int, default=16)

    p_decompress = sub.add_parser("decompress")
    p_decompress.add_argument("archive", type=Path)
    p_decompress.add_argument("output", type=Path)

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("input", type=Path)
    p_verify.add_argument("archive", type=Path)

    p_bench = sub.add_parser("benchmark")
    p_bench.add_argument("input", type=Path)
    p_bench.add_argument("--archive", type=Path)
    p_bench.add_argument("--receipt", type=Path)
    p_bench.add_argument("--program", type=Path, help="combined compressor/decompressor artifact counted in total")
    p_bench.add_argument("--evidence-class", default="fixture")
    p_bench.add_argument("--no-transform", action="store_true")
    p_bench.add_argument("--table-bits", type=int, default=16)

    p_receipt = sub.add_parser("verify-receipt")
    p_receipt.add_argument("receipt", type=Path)

    args = parser.parse_args(argv)
    if args.command == "compress":
        data = args.input.read_bytes()
        _atomic_write(args.output, compress_bytes(data, use_transform=not args.no_transform, table_bits=args.table_bits))
        return 0
    if args.command == "decompress":
        _atomic_write(args.output, decompress_bytes(args.archive.read_bytes()))
        return 0
    if args.command == "verify":
        expected = args.input.read_bytes()
        actual = decompress_bytes(args.archive.read_bytes())
        if actual != expected:
            raise SystemExit("roundtrip mismatch")
        print(json.dumps({"ok": True, "sha256": sha256_hex(actual), "bytes": len(actual)}, sort_keys=True))
        return 0
    if args.command == "benchmark":
        data = args.input.read_bytes()
        program_bytes = args.program.stat().st_size if args.program else 0
        receipt, archive = benchmark(
            data,
            use_transform=not args.no_transform,
            table_bits=args.table_bits,
            program_bytes=program_bytes,
            evidence_class=args.evidence_class,
        )
        if args.archive:
            _atomic_write(args.archive, archive)
        rendered = canonical_json_bytes(receipt)
        if args.receipt:
            _atomic_write(args.receipt, rendered)
        print(rendered.decode("utf-8"), end="")
        return 0
    if args.command == "verify-receipt":
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        verify_receipt(receipt)
        print(json.dumps({"ok": True, "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True))
        return 0
    raise RuntimeError("unreachable command")


if __name__ == "__main__":
    raise SystemExit(cli())
