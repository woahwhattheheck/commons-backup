#!/usr/bin/env python3
"""Fixed-memory rolling match successor for Hutter MixerLab.

This module is deliberately additive: the landed MixerLab remains the baseline.
Candidate archives use the same-size envelope with a distinct magic and serialize
both context-table and match-table sizes. The decoder reconstructs every match
prediction from already-decoded history; no side information is hidden.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
from pathlib import Path
from typing import Sequence

import mixerlab

MATCH_MAGIC = b"HMM1"
MATCH_VERSION = 1
FLAG_MATCH_MODEL = 0x02
MATCH_WINDOW_BITS = 16
MATCH_WINDOW_BYTES = 1 << MATCH_WINDOW_BITS
MATCH_SALT = 0xA5A5A5A5


class FixedMatchPredictor:
    """Fixed-memory 4-byte-context prior-position predictor.

    A direct-mapped table stores the most recent byte position following an
    exact four-byte context. Successful predictions continue at the same match
    distance, including safe overlapping runs, while misses immediately fall
    back to a fresh context lookup. History is a 64 KiB ring, so corpus length
    never grows model memory.
    """

    def __init__(self, match_bits: int = 16) -> None:
        if match_bits < 10 or match_bits > 20:
            raise ValueError("match_bits must be in [10, 20]")
        self.match_bits = match_bits
        self.size = 1 << match_bits
        self.mask = self.size - 1
        self.tags = array("I", [0]) * self.size
        self.positions = array("Q", [0]) * self.size  # absolute position + 1
        self.history = bytearray(MATCH_WINDOW_BYTES)
        self.position = 0
        self.distance: int | None = None
        self.run = 0

    @property
    def memory_bytes(self) -> int:
        return (len(self.tags) * self.tags.itemsize +
                len(self.positions) * self.positions.itemsize +
                len(self.history))

    def _key_slot(self) -> tuple[int | None, int | None]:
        i = self.position
        if i < 4:
            return None, None
        mask = MATCH_WINDOW_BYTES - 1
        key = ((self.history[(i - 4) & mask] << 24) |
               (self.history[(i - 3) & mask] << 16) |
               (self.history[(i - 2) & mask] << 8) |
               self.history[(i - 1) & mask])
        slot = mixerlab._mix64(key ^ MATCH_SALT) & self.mask
        return key, slot

    def predict(self) -> tuple[int | None, int | None, int | None]:
        key, slot = self._key_slot()
        source = None
        if self.distance is not None and 0 < self.distance <= min(self.position, MATCH_WINDOW_BYTES):
            source = self.position - self.distance
        elif key is not None and slot is not None:
            stored = self.positions[slot]
            if stored and self.tags[slot] == key:
                prior = stored - 1
                distance = self.position - prior
                if 0 < distance <= MATCH_WINDOW_BYTES:
                    self.distance = distance
                    self.run = 0
                    source = prior
        if source is None:
            return None, key, slot
        return self.history[source & (MATCH_WINDOW_BYTES - 1)], key, slot

    def push(self, value: int, predicted: int | None,
             key: int | None, slot: int | None) -> None:
        self.history[self.position & (MATCH_WINDOW_BYTES - 1)] = value
        if predicted is not None and predicted == value:
            self.run = min(self.run + 1, 255)
        else:
            self.distance = None
            self.run = 0
        if key is not None and slot is not None:
            self.tags[slot] = key
            self.positions[slot] = self.position + 1
        self.position += 1


def _blend_probability(base_p1: int, predicted_bit: int, run: int) -> int:
    # A first-byte match is only a weak hint; continuation evidence rapidly
    # increases confidence. This bounds false-match damage on noisy inputs while
    # exploiting long repeated Wiki/XML/text spans.
    if run <= 0:
        confidence, weight = 49152, 1      # 75%, 1:1 with base
    elif run == 1:
        confidence, weight = 57344, 2      # 87.5%
    elif run < 4:
        confidence, weight = 61440, 4      # 93.75%
    else:
        confidence, weight = 64512, 7      # 98.4375%
    match_p1 = confidence if predicted_bit else mixerlab.PROB_TOTAL - confidence
    mixed = (base_p1 + weight * match_p1) // (weight + 1)
    return max(1, min(mixerlab.PROB_TOTAL - 1, mixed))


def _encode_stream(data: bytes, table_bits: int, match_bits: int) -> tuple[bytes, int]:
    mixer = mixerlab.BoundedContextMixer(table_bits)
    match = FixedMatchPredictor(match_bits)
    coder = mixerlab.ArithmeticEncoder()
    for value in data:
        predicted, key, slot = match.predict()
        prefix = 0
        for bitpos in range(8):
            bit = (value >> (7 - bitpos)) & 1
            p1, indices = mixer.probability_one(bitpos, prefix)
            if predicted is not None:
                p1 = _blend_probability(p1, (predicted >> (7 - bitpos)) & 1, match.run)
            coder.encode(bit, p1)
            mixer.update(indices, bit)
            prefix = (prefix << 1) | bit
        mixer.push_byte(value)
        match.push(value, predicted, key, slot)
    return coder.finish()


def _decode_stream(payload: bytes, bit_length: int, output_len: int,
                   table_bits: int, match_bits: int) -> bytes:
    if output_len < 0:
        raise ValueError("negative output length")
    mixer = mixerlab.BoundedContextMixer(table_bits)
    match = FixedMatchPredictor(match_bits)
    coder = mixerlab.ArithmeticDecoder(payload, bit_length)
    out = bytearray()
    for _ in range(output_len):
        predicted, key, slot = match.predict()
        value = 0
        prefix = 0
        for bitpos in range(8):
            p1, indices = mixer.probability_one(bitpos, prefix)
            if predicted is not None:
                p1 = _blend_probability(p1, (predicted >> (7 - bitpos)) & 1, match.run)
            bit = coder.decode(p1)
            mixer.update(indices, bit)
            value = (value << 1) | bit
            prefix = (prefix << 1) | bit
        out.append(value)
        mixer.push_byte(value)
        match.push(value, predicted, key, slot)
    return bytes(out)


def compress_bytes(data: bytes, *, use_transform: bool = True,
                   table_bits: int = 16, match_bits: int = 16) -> bytes:
    transformed = mixerlab.wiki_transform_encode(data) if use_transform else data
    payload, bit_length = _encode_stream(transformed, table_bits, match_bits)
    flags = FLAG_MATCH_MODEL | (mixerlab.FLAG_WIKI_TRANSFORM if use_transform else 0)
    header = mixerlab._HEADER.pack(
        MATCH_MAGIC, MATCH_VERSION, flags, table_bits, match_bits,
        len(data), len(transformed), bit_length,
        hashlib.sha256(data).digest(), hashlib.sha256(transformed).digest(), len(payload),
    )
    return header + payload + hashlib.sha256(payload).digest()


def _parse_archive(archive: bytes) -> tuple[dict, bytes]:
    minimum = mixerlab._HEADER.size + 32
    if len(archive) < minimum:
        raise ValueError("archive truncated before header/footer")
    fields = mixerlab._HEADER.unpack_from(archive, 0)
    magic, version, flags, table_bits, match_bits, original_len, transformed_len, bit_length, orig_hash, trans_hash, payload_len = fields
    if magic != MATCH_MAGIC:
        raise ValueError("bad match archive magic")
    if version != MATCH_VERSION:
        raise ValueError(f"unsupported match archive version {version}")
    allowed = FLAG_MATCH_MODEL | mixerlab.FLAG_WIKI_TRANSFORM
    if flags & ~allowed or not (flags & FLAG_MATCH_MODEL):
        raise ValueError("unknown or missing match archive flags")
    if table_bits < 10 or table_bits > 20:
        raise ValueError("invalid model table_bits")
    if match_bits < 10 or match_bits > 20:
        raise ValueError("invalid match_bits")
    expected = mixerlab._HEADER.size + payload_len + 32
    if len(archive) != expected:
        raise ValueError("archive length does not match header")
    payload = archive[mixerlab._HEADER.size:mixerlab._HEADER.size + payload_len]
    if hashlib.sha256(payload).digest() != archive[-32:]:
        raise ValueError("archive payload SHA-256 mismatch")
    if bit_length > payload_len * 8:
        raise ValueError("bit length exceeds payload")
    return {
        "flags": flags, "table_bits": table_bits, "match_bits": match_bits,
        "original_len": original_len, "transformed_len": transformed_len,
        "bit_length": bit_length, "original_sha256": orig_hash,
        "transformed_sha256": trans_hash, "payload_len": payload_len,
    }, payload


def decompress_bytes(archive: bytes) -> bytes:
    meta, payload = _parse_archive(archive)
    transformed = _decode_stream(payload, meta["bit_length"], meta["transformed_len"],
                                 meta["table_bits"], meta["match_bits"])
    if hashlib.sha256(transformed).digest() != meta["transformed_sha256"]:
        raise ValueError("decoded transformed SHA-256 mismatch")
    original = (mixerlab.wiki_transform_decode(transformed)
                if meta["flags"] & mixerlab.FLAG_WIKI_TRANSFORM else transformed)
    if len(original) != meta["original_len"]:
        raise ValueError("decoded original length mismatch")
    if hashlib.sha256(original).digest() != meta["original_sha256"]:
        raise ValueError("decoded original SHA-256 mismatch")
    return original


def paired_benchmark(data: bytes, *, use_transform: bool = True,
                     table_bits: int = 12, match_bits: int = 12) -> dict:
    baseline = mixerlab.compress_bytes(data, use_transform=use_transform, table_bits=table_bits)
    candidate = compress_bytes(data, use_transform=use_transform,
                               table_bits=table_bits, match_bits=match_bits)
    if mixerlab.decompress_bytes(baseline) != data:
        raise RuntimeError("baseline round-trip failed")
    if decompress_bytes(candidate) != data:
        raise RuntimeError("candidate round-trip failed")
    baseline_program = Path(mixerlab.__file__).stat().st_size
    candidate_program = baseline_program + Path(__file__).stat().st_size
    result = {
        "schema": "hutter-mixerlab-match-ablation/v1",
        "evidence_class": "fixture_or_public_slice",
        "input_bytes": len(data),
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "table_bits": table_bits,
        "match_bits": match_bits,
        "match_memory_bytes": FixedMatchPredictor(match_bits).memory_bytes,
        "baseline_archive_bytes": len(baseline),
        "candidate_archive_bytes": len(candidate),
        "archive_delta_bytes": len(candidate) - len(baseline),
        "archive_improved": len(candidate) < len(baseline),
        "baseline_program_bytes": baseline_program,
        "candidate_program_bytes": candidate_program,
        "baseline_source_shape_total": len(baseline) + baseline_program,
        "candidate_source_shape_total": len(candidate) + candidate_program,
        "roundtrip_sha256": hashlib.sha256(decompress_bytes(candidate)).hexdigest(),
        "official_enwik9_claim": False,
    }
    return result


def cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--table-bits", type=int, default=12)
    parser.add_argument("--match-bits", type=int, default=12)
    parser.add_argument("--no-transform", action="store_true")
    args = parser.parse_args(argv)
    data = args.input.read_bytes()
    print(json.dumps(paired_benchmark(
        data, use_transform=not args.no_transform,
        table_bits=args.table_bits, match_bits=args.match_bits,
    ), sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
