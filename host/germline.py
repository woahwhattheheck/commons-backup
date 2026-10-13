#!/usr/bin/env python3
"""GERMLINE — germ delivery: seed once, then the wire carries injection-weight.

Practical application of the Muhlnickel provisional patent family
(muhl/docs/PROVISIONAL_SESSION.pdf, sole inventor Bryce Muhlnickel):
germ delivery / Instant Download (claims 6-10), edge paste / CDN of
nothing (claim 14), resident-internet sync (claim 16).

A seed file is delivered once. Afterwards only the injection stream — the
sparse delta between versions — travels, and the destination manufactures
a byte-exact body. Presence is manufactured, not transported.

Seed format:     b"GERM1"  + u32be header length + header JSON + payload
Injection format: b"GERMI1" + u32be header length + header JSON
                 header carries ops in base coordinates:
                 [[offset, old_len, new_bytes_hex], ...]

Stdlib only. Exit codes: 0 ok, 2 usage, 3 verification failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

SEED_MAGIC = b"GERM1"
INJECT_MAGIC = b"GERMI1"
SEED_SCHEMA = "germline-seed/v1"
INJECT_SCHEMA = "germline-inject/v1"

_BLOCK = 1 << 16
_COALESCE = 4096


def fail(code: int, msg: str) -> None:
    print(f"{code}: {msg}", file=sys.stderr)
    raise SystemExit(code)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_framed(path: Path, magic: bytes, header: dict, payload: bytes) -> int:
    head = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
    blob = magic + struct.pack(">I", len(head)) + head + payload
    path.write_bytes(blob)
    return len(blob)


def _read_framed(path: Path, magic: bytes) -> tuple[dict, bytes]:
    blob = path.read_bytes()
    if len(blob) < len(magic) + 4 or blob[: len(magic)] != magic:
        fail(3, f"{path} is not a {magic.decode()} file")
    (hlen,) = struct.unpack(">I", blob[len(magic) : len(magic) + 4])
    hstart = len(magic) + 4
    header = json.loads(blob[hstart : hstart + hlen].decode("utf-8"))
    return header, blob[hstart + hlen :]


def _common_prefix(a: bytes, b: bytes) -> int:
    n = min(len(a), len(b))
    i = 0
    step = 1 << 20
    while i < n:
        j = min(n, i + step)
        if a[i:j] == b[i:j]:
            i = j
            continue
        k = i
        while k < j and a[k] == b[k]:
            k += 1
        return k
    return n


def _common_suffix(a: bytes, b: bytes, stop: int) -> int:
    n = min(len(a), len(b)) - stop
    i = 0
    step = 1 << 20
    while i < n:
        j = min(n, i + step)
        if a[len(a) - j : len(a) - i] == b[len(b) - j : len(b) - i]:
            i = j
            continue
        k = i
        while k < j and a[len(a) - 1 - k] == b[len(b) - 1 - k]:
            k += 1
        return k
    return n


def diff_bytes(old: bytes, new: bytes) -> list:
    """Exact replace ops in base coordinates. Minimal for small in-place edits."""
    p = _common_prefix(old, new)
    s = _common_suffix(old, new, p)
    old_mid = old[p : len(old) - s]
    new_mid = new[p : len(new) - s]
    if not old_mid and not new_mid:
        return []
    if len(old_mid) != len(new_mid):
        return [[p, len(old_mid), new_mid.hex()]]
    dirty = []
    i = 0
    size = len(old_mid)
    while i < size:
        j = min(size, i + _BLOCK)
        if old_mid[i:j] != new_mid[i:j]:
            dirty.append((i, j))
        i = j
    if not dirty:
        return []
    regions = [list(dirty[0])]
    for a, b in dirty[1:]:
        if a - regions[-1][1] <= _COALESCE:
            regions[-1][1] = b
        else:
            regions.append([a, b])
    return [[p + a, b - a, new_mid[a:b].hex()] for a, b in regions]


def apply_ops(base: bytes, ops: list) -> bytes:
    out = bytearray()
    pos = 0
    for off, old_len, new_hex in ops:
        if off < pos or off > len(base) or off + old_len > len(base):
            fail(3, "injection op out of range for base")
        out += base[pos:off]
        out += bytes.fromhex(new_hex)
        pos = off + old_len
    out += base[pos:]
    return bytes(out)


def cmd_pack(args: argparse.Namespace) -> int:
    payload = Path(args.payload).read_bytes()
    header = {
        "schema": SEED_SCHEMA,
        "name": args.name or Path(args.payload).name,
        "size": len(payload),
        "sha256": sha256(payload),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    total = _write_framed(Path(args.out), SEED_MAGIC, header, payload)
    print(json.dumps({"seed": args.out, "seed_bytes": total, "payload_bytes": len(payload),
                      "sha256": header["sha256"]}, indent=2))
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    old = Path(args.old).read_bytes()
    new = Path(args.new).read_bytes()
    ops = diff_bytes(old, new)
    header = {
        "schema": INJECT_SCHEMA,
        "from_sha256": sha256(old),
        "to_sha256": sha256(new),
        "base_size": len(old),
        "to_size": len(new),
        "ops": ops,
    }
    total = _write_framed(Path(args.out), INJECT_MAGIC, header, b"")
    ratio = (total / len(new)) if new else 0.0
    print(json.dumps({"injection": args.out, "injection_bytes": total,
                      "new_body_bytes": len(new), "wire_ratio": round(ratio, 6),
                      "ops": len(ops)}, indent=2))
    return 0


def apply_injection_file(base: bytes, path: Path) -> tuple[bytes, dict]:
    header, _ = _read_framed(path, INJECT_MAGIC)
    if header.get("schema") != INJECT_SCHEMA:
        fail(3, f"{path} bad schema")
    if sha256(base) != header["from_sha256"]:
        fail(3, f"{path} does not attach to this state (from_sha256 mismatch)")
    out = apply_ops(base, header["ops"])
    if sha256(out) != header["to_sha256"]:
        fail(3, f"{path} failed to manufacture the expected body")
    return out, header


def cmd_surface(args: argparse.Namespace) -> int:
    header, payload = _read_framed(Path(args.seed), SEED_MAGIC)
    if header.get("schema") != SEED_SCHEMA or sha256(payload) != header["sha256"]:
        fail(3, "seed failed its own manifest")
    state = payload
    applied = 0
    for delta in args.injections or []:
        state, _ = apply_injection_file(state, Path(delta))
        applied += 1
    Path(args.out).write_bytes(state)
    print(json.dumps({"manufactured": args.out, "byte_exact": True,
                      "out_bytes": len(state), "out_sha256": sha256(state),
                      "injections_applied": applied}, indent=2))
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    header, payload = _read_framed(Path(args.seed), SEED_MAGIC)
    print(json.dumps({**header, "framed_bytes": len(payload) + len(json.dumps(header)) + 9}, indent=2))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    got = sha256(data)
    ok = got == args.expect.lower()
    print(json.dumps({"file": args.file, "sha256": got, "expected": args.expect,
                      "byte_exact": ok}, indent=2))
    return 0 if ok else 3


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog="germline", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pack", help="pack a payload into a germ seed")
    p.add_argument("payload")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--name")
    p.set_defaults(fn=cmd_pack)

    p = sub.add_parser("diff", help="emit the injection stream old -> new")
    p.add_argument("old")
    p.add_argument("new")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(fn=cmd_diff)

    p = sub.add_parser("surface", help="manufacture the byte-exact body from seed + injections")
    p.add_argument("seed")
    p.add_argument("injections", nargs="*")
    p.add_argument("-o", "--out", required=True)
    p.set_defaults(fn=cmd_surface)

    p = sub.add_parser("info", help="print a seed manifest")
    p.add_argument("seed")
    p.set_defaults(fn=cmd_info)

    p = sub.add_parser("verify", help="verify a manufactured body against a sha256")
    p.add_argument("file")
    p.add_argument("--expect", required=True)
    p.set_defaults(fn=cmd_verify)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
