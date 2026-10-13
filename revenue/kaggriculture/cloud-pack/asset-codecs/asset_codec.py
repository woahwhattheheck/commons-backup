"""Optional bounded, streaming asset frames for Commons MUHC/RINGDELTA.

KAC1 framing is new; inner MUHC and RDV1 containers are unchanged. Every
transform sees at most 16 KiB. This module also ships with each decoder bundle.
"""
from __future__ import annotations

import argparse
import bz2
from functools import lru_cache
import hashlib
import importlib.util
import json
import lzma
import os
from pathlib import Path
import resource
import struct
import sys
import tempfile
import time
import zlib

HERE = Path(__file__).resolve().parent
MAX_FRAME = 16384
MAX_PAYLOAD = 1024 * 1024
DEFAULT_BUDGET = 256 * 1024
HEADER = struct.Struct("<8sB3xIQ32s")
FRAME = struct.Struct("<II32s")
MAGIC = b"KAGAST1\0"
CODECS = ("raw", "zlib", "bz2", "xz", "rdv1", "rdv1-zlib",
          "muhc-raw", "muhc-stack", "muhc-fold", "muhc-evolve")


def sha_file(path):
    with Path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


@lru_cache(maxsize=2)
def vendor(name):
    names = ["evolve", "foldpack", "muhc"] if name == "muhc" else ["ringdelta"]
    manifest = json.loads((HERE / "vendor/manifest.json").read_text())
    saved = {key: sys.modules.get(key) for key in names}
    loaded = {}
    try:
        for key in names:
            path = HERE / "vendor" / (key + ".py")
            if sha_file(path) != manifest["files"][path.name]["sha256"]:
                raise ValueError("Codec source differs from its manifest: " + key)
            spec = importlib.util.spec_from_file_location(key, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[key] = module
            spec.loader.exec_module(module)
            loaded[key] = module
    finally:
        for key, previous in saved.items():
            if previous is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = previous
    return loaded[name]


def encode_block(data, codec):
    if not 0 < len(data) <= MAX_FRAME:
        raise ValueError("A transform receives 1..16384 bytes")
    if codec == "raw": return data
    if codec == "zlib": return zlib.compress(data, 9)
    if codec == "bz2": return bz2.compress(data, 9)
    if codec == "xz": return lzma.compress(data, preset=6)
    if codec.startswith("rdv1"):
        blob = vendor("ringdelta").encode_rdv1(data, width=25)
        return zlib.compress(blob, 9) if codec == "rdv1-zlib" else blob
    mode = codec.removeprefix("muhc-")
    return vendor("muhc").encode_bytes(data, 200, codec=mode,
        tile_w=25, tile_h=1, folds=4, mode="adjacent", program=["XOR_ROW"], entropy="zlib")


def inflate_zlib(blob, limit):
    decoder = zlib.decompressobj()
    data = decoder.decompress(blob, limit + 1)
    if len(data) > limit or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("Invalid or oversized compressed frame")
    return data


def decode_block(blob, codec, expected):
    if codec == "raw": return blob
    if codec == "zlib": return inflate_zlib(blob, expected)
    if codec in ("bz2", "xz"):
        dec = bz2.BZ2Decompressor() if codec == "bz2" else lzma.LZMADecompressor(memlimit=128*1024**2)
        data = dec.decompress(blob, max_length=expected + 1)
        if len(data) > expected or not dec.eof or dec.unused_data:
            raise ValueError("Invalid or oversized compressed frame")
        return data
    if codec.startswith("rdv1"):
        if codec == "rdv1-zlib": blob = inflate_zlib(blob, MAX_PAYLOAD)
        if len(blob) < 48:
            raise ValueError("Truncated RDV1 frame")
        version, size, width = struct.unpack_from("<III", blob, 4)
        if (version, size, width) != (1, expected, 25):
            raise ValueError("RDV1 frame dimensions differ from KAC1")
        return vendor("ringdelta").decode_rdv1(blob)
    module = vendor("muhc")
    header, _ = module.parse_header(blob)
    if (header["width"] != 200 or header["height"] != (expected*8+199)//200 or
            header["bit_len"] != expected*8 or
            header["codec"] != module.CODEC_NAMES[codec.removeprefix("muhc-")]):
        raise ValueError("MUHC frame dimensions/codec differ from KAC1")
    data, _ = module.decode_bytes(blob)
    return data


def encode_file(source, destination, codec, max_bytes=DEFAULT_BUDGET, frame_bytes=MAX_FRAME):
    source, destination = Path(source), Path(destination)
    if codec not in CODECS or not 1 <= frame_bytes <= MAX_FRAME:
        raise ValueError("Unknown codec or frame size outside 1..16384")
    size = source.stat().st_size
    if max_bytes < 0 or size > max_bytes:
        raise ValueError("Input exceeds explicit byte budget; use sample for a large model")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest, frames, payload_bytes, inner_overhead = hashlib.sha256(), 0, 0, 0
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as out:
        tmp = Path(out.name)
        try:
            out.write(HEADER.pack(MAGIC, CODECS.index(codec), frame_bytes, size, bytes(32)))
            actual = 0
            with source.open("rb") as inp:
                while data := inp.read(frame_bytes):
                    actual += len(data)
                    if actual > size: raise ValueError("Input grew during encoding")
                    blob = encode_block(data, codec)
                    if len(blob) > MAX_PAYLOAD: raise ValueError("Encoded frame exceeds bounded payload size")
                    out.write(FRAME.pack(len(data), len(blob), hashlib.sha256(data).digest()))
                    out.write(blob)
                    digest.update(data)
                    frames += 1
                    payload_bytes += len(blob)
                    if codec.startswith("muhc-"): inner_overhead += vendor("muhc").HEADER_SIZE + 4
                    elif codec.startswith("rdv1"): inner_overhead += 48
            if actual != size: raise ValueError("Input shrank during encoding")
            out.seek(0)
            out.write(HEADER.pack(MAGIC, CODECS.index(codec), frame_bytes, size, digest.digest()))
            out.flush()
            os.fsync(out.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        # Exclusive publication preserves an existing asset file.
        os.link(tmp, destination)
    finally:
        tmp.unlink(missing_ok=True)
    return {"codec": codec, "source_bytes": size, "source_sha256": digest.hexdigest(),
            "frame_bytes": frame_bytes, "frames": frames, "container_bytes": destination.stat().st_size,
            "container_sha256": sha_file(destination), "payload_bytes": payload_bytes,
            "outer_framing_bytes": HEADER.size + FRAME.size*frames,
            "inner_header_bytes_before_optional_zlib": inner_overhead}


def decode_file(source, destination, max_bytes=DEFAULT_BUDGET):
    """Restore to disk one bounded frame at a time; return an exact-byte receipt."""
    source, destination = Path(source), Path(destination)
    with source.open("rb") as inp:
        raw = inp.read(HEADER.size)
        if len(raw) != HEADER.size: raise ValueError("Truncated KAC1 header")
        magic, codec_id, frame_bytes, size, expected_sha = HEADER.unpack(raw)
        if magic != MAGIC or codec_id >= len(CODECS) or not 1 <= frame_bytes <= MAX_FRAME:
            raise ValueError("Unsupported KAC1 header")
        if max_bytes < 0 or size > max_bytes: raise ValueError("Decoded asset exceeds explicit byte budget")
        codec = CODECS[codec_id]
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as out:
            tmp = Path(out.name)
            digest, written, frames = hashlib.sha256(), 0, 0
            try:
                while written < size:
                    raw = inp.read(FRAME.size)
                    if len(raw) != FRAME.size: raise ValueError("Truncated frame header")
                    length, encoded_length, expected = FRAME.unpack(raw)
                    if length != min(frame_bytes, size-written) or not 0 < encoded_length <= MAX_PAYLOAD:
                        raise ValueError("Invalid frame length")
                    blob = inp.read(encoded_length)
                    if len(blob) != encoded_length: raise ValueError("Truncated frame payload")
                    data = decode_block(blob, codec, length)
                    if len(data) != length or hashlib.sha256(data).digest() != expected:
                        raise ValueError("Decoded frame differs from its original bytes")
                    out.write(data)
                    digest.update(data)
                    written += length
                    frames += 1
                if inp.read(1) or digest.digest() != expected_sha:
                    raise ValueError("Trailing bytes or whole-asset hash mismatch")
                out.flush()
                os.fsync(out.fileno())
            except BaseException:
                tmp.unlink(missing_ok=True)
                raise
        try:
            os.link(tmp, destination)
        finally:
            tmp.unlink(missing_ok=True)
    return {"codec": codec, "restored_bytes": written, "sha256": digest.hexdigest(), "frames": frames}


def sample(source, destination, offset, length):
    if offset < 0 or not 0 < length <= 65536:
        raise ValueError("Sample requires a nonnegative offset and 1..65536 bytes")
    source, destination = Path(source), Path(destination)
    before = source.stat()
    with source.open("rb") as inp:
        inp.seek(offset)
        data = inp.read(length)
    if len(data) != length: raise ValueError("Requested sample crosses EOF")
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed during sampling")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as out: out.write(data)
    return {"source_name": source.name, "source_bytes": before.st_size,
            "offset": offset, "sample_bytes": length, "sample_sha256": hashlib.sha256(data).hexdigest(),
            "whole_source_sha256": None, "whole_source_read": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for command in ("encode", "decode", "sample"):
        sub = subs.add_parser(command)
        sub.add_argument("source", type=Path)
        sub.add_argument("destination", type=Path)
        if command == "sample":
            sub.add_argument("--offset", type=int, required=True)
            sub.add_argument("--length", type=int, default=65536)
        else:
            sub.add_argument("--max-bytes", type=int, default=DEFAULT_BUDGET)
        if command == "encode":
            sub.add_argument("--codec", choices=CODECS, required=True)
            sub.add_argument("--frame-bytes", type=int, default=MAX_FRAME)
    args = parser.parse_args()
    started = time.perf_counter()
    if args.command == "encode":
        result = encode_file(args.source, args.destination, args.codec, args.max_bytes, args.frame_bytes)
    elif args.command == "decode":
        result = decode_file(args.source, args.destination, args.max_bytes)
    else:
        result = sample(args.source, args.destination, args.offset, args.length)
    use = resource.getrusage(resource.RUSAGE_SELF)
    result.update(operation_seconds=time.perf_counter()-started,
                  process_cpu_seconds=use.ru_utime+use.ru_stime,
                  peak_rss_kib=use.ru_maxrss/(1024 if sys.platform=="darwin" else 1))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
