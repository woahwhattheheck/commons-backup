#!/usr/bin/env python3
"""Independently decodable .muhc container (v1).

foldpack.py / stackpack.py / evolve.py stay untouched. Those CLIs still
rebuild from in-memory grids and can print OK after dropping tails.
This file is the productization leftover: one encode/decode API, a
versioned artifact, exact-SHA round trips, tail coverage, and
corruption refusal.

  python3 muhc.py encode --codec stack SEED0.mno out.muhc --width 200
  python3 muhc.py decode out.muhc out.bin
  python3 muhc.py bench SEED0.mno --width 200
"""
from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import lzma
import math
import struct
import sys
import time
import zlib

import evolve
import foldpack

MAGIC = b"MUHC"
VERSION = 1
HEADER_FMT = "<4sHHI IQ32sII"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

CODEC_RAW = 1
CODEC_STACK = 2
CODEC_FOLD = 3
CODEC_EVOLVE = 4
CODEC_NAMES = {
    "raw": CODEC_RAW,
    "raw_zlib": CODEC_RAW,
    "stack": CODEC_STACK,
    "stack_v1": CODEC_STACK,
    "fold": CODEC_FOLD,
    "fold_v1": CODEC_FOLD,
    "evolve": CODEC_EVOLVE,
    "evolve_v1": CODEC_EVOLVE,
}
CODEC_LABEL = {
    CODEC_RAW: "raw_zlib",
    CODEC_STACK: "stack_v1",
    CODEC_FOLD: "fold_v1",
    CODEC_EVOLVE: "evolve_v1",
}
FOLD_MODES = {"translate": 0, "mirror": 1, "adjacent": 2}
FOLD_MODE_NAME = {v: k for k, v in FOLD_MODES.items()}
OP_IDS = {name: idx + 1 for idx, name in enumerate(evolve.NAMES)}
ID_OPS = {idx: name for name, idx in OP_IDS.items()}


class MuhcError(Exception):
    """Container or codec failure."""


class MuhcCorrupt(MuhcError):
    """Artifact failed integrity or decode checks."""


class MuhcVersion(MuhcError):
    """Unsupported container version."""


def bitpack(vals, bits):
    out = bytearray()
    acc = 0
    nacc = 0
    for val in vals:
        acc = (acc << bits) | int(val)
        nacc += bits
        while nacc >= 8:
            nacc -= 8
            out.append((acc >> nacc) & 0xFF)
            acc &= (1 << nacc) - 1
    if nacc:
        out.append((acc << (8 - nacc)) & 0xFF)
    return bytes(out)


def unpack_vals(data, bits, count):
    vals = []
    acc = 0
    nacc = 0
    mask = (1 << bits) - 1
    for byte in data:
        acc = (acc << 8) | byte
        nacc += 8
        while nacc >= bits and len(vals) < count:
            nacc -= bits
            vals.append((acc >> nacc) & mask)
            acc &= (1 << nacc) - 1
    if len(vals) != count:
        raise MuhcCorrupt("short bit stream: got %d need %d" % (len(vals), count))
    return vals


def grid_from_bytes(data, width):
    bit_len = len(data) * 8
    height = (bit_len + width - 1) // width
    grid = []
    for y in range(height):
        row = bytearray(width)
        for x in range(width):
            idx = y * width + x
            if idx < bit_len:
                row[x] = (data[idx >> 3] >> (7 - (idx & 7))) & 1
        grid.append(row)
    return width, height, grid, bit_len


def bytes_from_grid(grid, bit_len):
    out = bytearray((bit_len + 7) // 8)
    idx = 0
    for row in grid:
        for bit in row:
            if idx >= bit_len:
                return bytes(out)
            if bit:
                out[idx >> 3] |= 1 << (7 - (idx & 7))
            idx += 1
    return bytes(out)


def grid_sha(grid, bit_len):
    return hashlib.sha256(bytes_from_grid(grid, bit_len)).digest()


def flatten_bits(grid, width, height):
    return [int(grid[y][x]) & 1 for y in range(height) for x in range(width)]


def _header(codec, width, height, bit_len, digest, flags, payload_len):
    return struct.pack(
        HEADER_FMT,
        MAGIC,
        VERSION,
        codec,
        width,
        height,
        bit_len,
        digest,
        flags,
        payload_len,
    )


def _wrap(codec, width, height, bit_len, digest, payload, flags=0):
    header = _header(codec, width, height, bit_len, digest, flags, len(payload))
    body = header + payload
    return body + struct.pack("<I", zlib.crc32(body) & 0xFFFFFFFF)


def parse_header(blob):
    if len(blob) < HEADER_SIZE + 4:
        raise MuhcCorrupt("artifact shorter than header")
    body, crc_bytes = blob[:-4], blob[-4:]
    expect = struct.unpack("<I", crc_bytes)[0]
    got = zlib.crc32(body) & 0xFFFFFFFF
    if got != expect:
        raise MuhcCorrupt("crc32 mismatch")
    magic, version, codec, width, height, bit_len, digest, flags, payload_len = (
        struct.unpack(HEADER_FMT, body[:HEADER_SIZE])
    )
    if magic != MAGIC:
        raise MuhcCorrupt("bad magic")
    if version != VERSION:
        raise MuhcVersion("unsupported version %d" % version)
    payload = body[HEADER_SIZE:]
    if len(payload) != payload_len:
        raise MuhcCorrupt("payload length mismatch")
    if codec not in CODEC_LABEL:
        raise MuhcCorrupt("unknown codec %d" % codec)
    return {
        "version": version,
        "codec": codec,
        "codec_name": CODEC_LABEL[codec],
        "width": width,
        "height": height,
        "bit_len": bit_len,
        "sha256": digest.hex(),
        "flags": flags,
        "payload_len": payload_len,
        "overhead": HEADER_SIZE + 4,
        "total": len(blob),
    }, payload


def _stack_encode(grid, width, height, tile_w, tile_h):
    across, down = width // tile_w, height // tile_h
    tiles = across * down
    if tiles < 2:
        raise MuhcError("stack tile does not cover at least two tiles")
    cover_w, cover_h = across * tile_w, down * tile_h
    cols = []
    for y in range(tile_h):
        for x in range(tile_w):
            val = 0
            for ty in range(down):
                row = grid[ty * tile_h + y]
                for tx in range(across):
                    val = (val << 1) | (row[tx * tile_w + x] & 1)
            cols.append(val)
    table = {}
    order = []
    for val in cols:
        if val not in table:
            table[val] = len(order)
            order.append(val)
    entries = len(order)
    sym_bits = max(1, (entries - 1).bit_length())
    stream = bitpack([table[val] for val in cols], sym_bits)
    tbl = bitpack(order, tiles)
    z_stream = zlib.compress(stream, 9)
    z_tbl = zlib.compress(tbl, 9)
    tail_bits = []
    for y in range(cover_h):
        tail_bits.extend(int(grid[y][x]) & 1 for x in range(cover_w, width))
    for y in range(cover_h, height):
        tail_bits.extend(int(grid[y][x]) & 1 for x in range(width))
    z_tail = zlib.compress(bitpack(tail_bits, 1), 9) if tail_bits else b""
    return (
        struct.pack("<HHIIII", tile_w, tile_h, tiles, entries, len(z_tbl), len(z_stream))
        + z_tbl
        + z_stream
        + struct.pack("<I", len(z_tail))
        + z_tail
    )


def _stack_decode(payload, width, height):
    if len(payload) < 16:
        raise MuhcCorrupt("stack payload truncated")
    tile_w, tile_h, tiles, entries, z_tbl_len, z_stream_len = struct.unpack_from(
        "<HHIIII", payload, 0
    )
    offset = struct.calcsize("<HHIIII")
    z_tbl = payload[offset : offset + z_tbl_len]
    offset += z_tbl_len
    z_stream = payload[offset : offset + z_stream_len]
    offset += z_stream_len
    if len(payload) < offset + 4:
        raise MuhcCorrupt("stack tail header truncated")
    (z_tail_len,) = struct.unpack_from("<I", payload, offset)
    offset += 4
    z_tail = payload[offset : offset + z_tail_len]
    if len(z_tbl) != z_tbl_len or len(z_stream) != z_stream_len or len(z_tail) != z_tail_len:
        raise MuhcCorrupt("stack section truncated")
    try:
        tbl = zlib.decompress(z_tbl)
        stream = zlib.decompress(z_stream)
    except zlib.error as exc:
        raise MuhcCorrupt("stack zlib failed: %s" % exc) from exc
    across, down = width // tile_w, height // tile_h
    if across * down != tiles:
        raise MuhcCorrupt("stack K mismatch")
    order = unpack_vals(tbl, tiles, entries)
    sym_bits = max(1, (entries - 1).bit_length())
    symbols = unpack_vals(stream, sym_bits, tile_w * tile_h)
    rec = [bytearray(width) for _ in range(height)]
    for idx, sid in enumerate(symbols):
        if sid >= len(order):
            raise MuhcCorrupt("stack symbol out of range")
        y, x = divmod(idx, tile_w)
        val = order[sid]
        for ty in range(down - 1, -1, -1):
            for tx in range(across - 1, -1, -1):
                rec[ty * tile_h + y][tx * tile_w + x] = val & 1
                val >>= 1
    cover_w, cover_h = across * tile_w, down * tile_h
    need = cover_h * (width - cover_w) + (height - cover_h) * width
    if need:
        try:
            tail = zlib.decompress(z_tail)
        except zlib.error as exc:
            raise MuhcCorrupt("stack tail zlib failed: %s" % exc) from exc
        bits = unpack_vals(tail, 1, need)
        pos = 0
        for y in range(cover_h):
            for x in range(cover_w, width):
                rec[y][x] = bits[pos]
                pos += 1
        for y in range(cover_h, height):
            for x in range(width):
                rec[y][x] = bits[pos]
                pos += 1
    return rec


def _fold_encode(grid, width, height, folds, mode):
    if mode not in FOLD_MODES:
        raise MuhcError("unknown fold mode %s" % mode)
    states = 2
    current = [list(row) for row in grid]
    cur_h = height
    odds = []
    used = 0
    for _ in range(folds):
        if cur_h < 2:
            break
        current, cur_h, states, odd = foldpack.fold_once(current, cur_h, width, states, mode)
        odds.append([[idx, list(row)] for idx, row in odd])
        used += 1
    raw, _wid = foldpack.pack(current, cur_h, width, states)
    z_raw = zlib.compress(raw, 9)
    z_odds = zlib.compress(
        json.dumps(odds, separators=(",", ":")).encode("ascii"), 9
    )
    return struct.pack("<BBIIII", FOLD_MODES[mode], used, cur_h, states, len(z_raw), len(z_odds)) + z_raw + z_odds


def _fold_decode(payload, width, height):
    if len(payload) < 18:
        raise MuhcCorrupt("fold payload truncated")
    mode_id, _folds, cur_h, states, z_raw_len, z_odds_len = struct.unpack_from(
        "<BBIIII", payload, 0
    )
    offset = 18
    z_raw = payload[offset : offset + z_raw_len]
    offset += z_raw_len
    z_odds = payload[offset : offset + z_odds_len]
    if mode_id not in FOLD_MODE_NAME:
        raise MuhcCorrupt("bad fold mode")
    try:
        raw = zlib.decompress(z_raw)
        odds = json.loads(zlib.decompress(z_odds).decode("ascii"))
    except (zlib.error, ValueError, UnicodeDecodeError) as exc:
        raise MuhcCorrupt("fold payload decode failed: %s" % exc) from exc
    bits = max(1, (max(1, states - 1)).bit_length())
    vals = unpack_vals(raw, bits, cur_h * width)
    rec = [vals[y * width : (y + 1) * width] for y in range(cur_h)]
    rec_h, rec_s = cur_h, states
    mode = FOLD_MODE_NAME[mode_id]
    for level in range(len(odds) - 1, -1, -1):
        odd = [(int(idx), list(row)) for idx, row in odds[level]]
        rec = foldpack.unfold_once(rec, rec_h, width, rec_s, mode, odd)
        rec_h = len(rec)
        rec_s = math.isqrt(rec_s)
    if rec_h != height:
        raise MuhcCorrupt("fold height %d != %d" % (rec_h, height))
    return [bytearray(int(v) & 1 for v in row) for row in rec]


def _evolve_encode(grid, width, height, program, entropy="zlib"):
    seq = list(program)
    for name in seq:
        if name not in OP_IDS:
            raise MuhcError("unknown evolve op %s" % name)
    transformed = evolve.apply_seq(grid, seq)
    inverted = evolve.invert_seq(transformed, seq)
    if [list(row) for row in inverted] != [list(row) for row in grid]:
        raise MuhcError("evolve program is not lossless on this grid")
    packed = evolve.pack(transformed)
    if entropy == "zlib":
        entropy_id = 0
        blob = zlib.compress(packed, 9)
    elif entropy == "bz2":
        entropy_id = 1
        blob = bz2.compress(packed, 9)
    elif entropy == "lzma":
        entropy_id = 2
        blob = lzma.compress(packed, preset=9)
    else:
        raise MuhcError("unknown entropy %s" % entropy)
    tw = len(transformed[0])
    th = len(transformed)
    return (
        bytes([len(seq)])
        + bytes(OP_IDS[name] for name in seq)
        + struct.pack("<BIII", entropy_id, tw, th, len(blob))
        + blob
    )


def _evolve_decode(payload, width, height):
    if not payload:
        raise MuhcCorrupt("empty evolve payload")
    n_ops = payload[0]
    offset = 1
    if len(payload) < offset + n_ops + 13:
        raise MuhcCorrupt("evolve header truncated")
    seq = []
    for raw_id in payload[offset : offset + n_ops]:
        if raw_id not in ID_OPS:
            raise MuhcCorrupt("bad evolve op %d" % raw_id)
        seq.append(ID_OPS[raw_id])
    offset += n_ops
    entropy_id, tw, th, blob_len = struct.unpack_from("<BIII", payload, offset)
    offset += 13
    blob = payload[offset : offset + blob_len]
    if len(blob) != blob_len:
        raise MuhcCorrupt("evolve blob truncated")
    try:
        if entropy_id == 0:
            packed = zlib.decompress(blob)
        elif entropy_id == 1:
            packed = bz2.decompress(blob)
        elif entropy_id == 2:
            packed = lzma.decompress(blob)
        else:
            raise MuhcCorrupt("bad evolve entropy %d" % entropy_id)
    except Exception as exc:
        raise MuhcCorrupt("evolve decompress failed: %s" % exc) from exc
    bits = unpack_vals(packed, 1, tw * th)
    transformed = [bytearray(bits[y * tw : (y + 1) * tw]) for y in range(th)]
    rec = evolve.invert_seq(transformed, seq)
    if len(rec) < height or (rec and len(rec[0]) < width):
        raise MuhcCorrupt("evolve invert undersized")
    return [bytearray(row[:width]) for row in rec[:height]]


def encode(grid, codec="stack", bit_len=None, **opts):
    height = len(grid)
    width = len(grid[0]) if height else 0
    if bit_len is None:
        bit_len = width * height
    digest = grid_sha(grid, bit_len)
    name = codec.lower()
    if name not in CODEC_NAMES:
        raise MuhcError("unknown codec %s" % codec)
    codec_id = CODEC_NAMES[name]
    if codec_id == CODEC_RAW:
        payload = zlib.compress(bitpack(flatten_bits(grid, width, height), 1), 9)
    elif codec_id == CODEC_STACK:
        payload = _stack_encode(
            grid, width, height, int(opts.get("tile_w") or width), int(opts.get("tile_h") or 1)
        )
    elif codec_id == CODEC_FOLD:
        payload = _fold_encode(
            grid,
            width,
            height,
            int(opts.get("folds") or 4),
            str(opts.get("mode") or "translate"),
        )
    else:
        payload = _evolve_encode(
            grid,
            width,
            height,
            list(opts.get("program") or []),
            str(opts.get("entropy") or "zlib"),
        )
    return _wrap(codec_id, width, height, bit_len, digest, payload)


def decode(blob):
    header, payload = parse_header(blob)
    codec = header["codec"]
    width, height, bit_len = header["width"], header["height"], header["bit_len"]
    if codec == CODEC_RAW:
        try:
            raw = zlib.decompress(payload)
        except zlib.error as exc:
            raise MuhcCorrupt("raw zlib failed: %s" % exc) from exc
        bits = unpack_vals(raw, 1, width * height)
        grid = [bytearray(bits[y * width : (y + 1) * width]) for y in range(height)]
    elif codec == CODEC_STACK:
        grid = _stack_decode(payload, width, height)
    elif codec == CODEC_FOLD:
        grid = _fold_decode(payload, width, height)
    else:
        grid = _evolve_decode(payload, width, height)
    digest = grid_sha(grid, bit_len)
    if digest.hex() != header["sha256"]:
        raise MuhcCorrupt("sha256 mismatch after decode")
    header["grid"] = grid
    return header


def encode_bytes(data, width, codec="stack", **opts):
    width, height, grid, bit_len = grid_from_bytes(data, width)
    return encode(grid, codec=codec, bit_len=bit_len, **opts)


def decode_bytes(blob):
    header = decode(blob)
    return bytes_from_grid(header["grid"], header["bit_len"]), header


def ratio_report(src_len, blob, raw_zlib_len=None):
    header, payload = parse_header(blob)
    payload_len = header["payload_len"]
    total = header["total"]
    report = {
        "source_b": src_len,
        "payload_b": payload_len,
        "overhead_b": header["overhead"],
        "container_b": total,
        "payload_pct": 100.0 * payload_len / max(src_len, 1),
        "container_pct": 100.0 * total / max(src_len, 1),
        "codec": header["codec_name"],
    }
    if raw_zlib_len is not None:
        report["entropy_only_b"] = raw_zlib_len
        report["transform_delta_b"] = raw_zlib_len - payload_len
    return report


def bench_bytes(data, width=200, program=None):
    program = list(program or [])
    raw_blob = encode_bytes(data, width, codec="raw")
    t0 = time.perf_counter()
    stack_blob = encode_bytes(data, width, codec="stack", tile_w=width, tile_h=1)
    stack_e = time.perf_counter() - t0
    t0 = time.perf_counter()
    decode_bytes(stack_blob)
    stack_d = time.perf_counter() - t0
    t0 = time.perf_counter()
    fold_blob = encode_bytes(data, width, codec="fold", folds=4, mode="adjacent")
    fold_e = time.perf_counter() - t0
    t0 = time.perf_counter()
    decode_bytes(fold_blob)
    fold_d = time.perf_counter() - t0
    rows = {
        "raw_zlib": ratio_report(len(data), raw_blob),
        "stack_v1": ratio_report(len(data), stack_blob, parse_header(raw_blob)[0]["payload_len"]),
        "fold_v1": ratio_report(len(data), fold_blob, parse_header(raw_blob)[0]["payload_len"]),
    }
    rows["stack_v1"]["encode_s"] = stack_e
    rows["stack_v1"]["decode_s"] = stack_d
    rows["fold_v1"]["encode_s"] = fold_e
    rows["fold_v1"]["decode_s"] = fold_d
    if program:
        t0 = time.perf_counter()
        ev_blob = encode_bytes(data, width, codec="evolve", program=program, entropy="lzma")
        ev_e = time.perf_counter() - t0
        t0 = time.perf_counter()
        decode_bytes(ev_blob)
        ev_d = time.perf_counter() - t0
        rows["evolve_v1"] = ratio_report(
            len(data), ev_blob, parse_header(raw_blob)[0]["payload_len"]
        )
        rows["evolve_v1"]["encode_s"] = ev_e
        rows["evolve_v1"]["decode_s"] = ev_d
        rows["evolve_v1"]["program"] = program
    t0 = time.perf_counter()
    z = zlib.compress(data, 9)
    z_e = time.perf_counter() - t0
    t0 = time.perf_counter()
    zlib.decompress(z)
    z_d = time.perf_counter() - t0
    rows["zlib_file"] = {
        "source_b": len(data),
        "payload_b": len(z),
        "overhead_b": 0,
        "container_b": len(z),
        "payload_pct": 100.0 * len(z) / max(len(data), 1),
        "container_pct": 100.0 * len(z) / max(len(data), 1),
        "encode_s": z_e,
        "decode_s": z_d,
        "note": "file-bytes zlib, not a .muhc",
    }
    return rows


def _cmd_encode(args):
    data = open(args.src, "rb").read()
    blob = encode_bytes(
        data,
        args.width,
        codec=args.codec,
        tile_w=args.tile_w or args.width,
        tile_h=args.tile_h,
        folds=args.folds,
        mode=args.mode,
        program=list(args.program or []),
        entropy=args.entropy,
    )
    open(args.dst, "wb").write(blob)
    header, _payload = parse_header(blob)
    print(json.dumps({"wrote": args.dst, **header}, indent=2))
    return 0


def _cmd_decode(args):
    data, header = decode_bytes(open(args.src, "rb").read())
    open(args.dst, "wb").write(data)
    print(json.dumps({"wrote": args.dst, "bytes": len(data), "sha256": header["sha256"]}, indent=2))
    return 0


def _cmd_info(args):
    header, _payload = parse_header(open(args.src, "rb").read())
    print(json.dumps(header, indent=2))
    return 0


def _cmd_bench(args):
    data = open(args.src, "rb").read()
    print(json.dumps(bench_bytes(data, args.width, args.program), indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Independently decodable .muhc container")
    sub = parser.add_subparsers(dest="cmd", required=True)
    enc = sub.add_parser("encode")
    enc.add_argument("src")
    enc.add_argument("dst")
    enc.add_argument("--width", type=int, default=200)
    enc.add_argument("--codec", default="stack")
    enc.add_argument("--tile-w", type=int, default=0)
    enc.add_argument("--tile-h", type=int, default=1)
    enc.add_argument("--folds", type=int, default=4)
    enc.add_argument("--mode", default="translate")
    enc.add_argument("--program", nargs="*", default=[])
    enc.add_argument("--entropy", default="zlib")
    dec = sub.add_parser("decode")
    dec.add_argument("src")
    dec.add_argument("dst")
    info = sub.add_parser("info")
    info.add_argument("src")
    bench = sub.add_parser("bench")
    bench.add_argument("src")
    bench.add_argument("--width", type=int, default=200)
    bench.add_argument("--program", nargs="*", default=[])
    args = parser.parse_args(argv)
    if args.cmd == "encode":
        return _cmd_encode(args)
    if args.cmd == "decode":
        return _cmd_decode(args)
    if args.cmd == "info":
        return _cmd_info(args)
    if args.cmd == "bench":
        return _cmd_bench(args)
    raise MuhcError("unknown command")


if __name__ == "__main__":
    sys.exit(main() or 0)
