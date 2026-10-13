#!/usr/bin/env python3
"""host/muhl_backend.py — Grok calls these. Each call returns and dies. No loop.

Copy the file, copy the computer. Inject = bounded OR, both senses. Surface = bounded read.
Containers = .mno slots, not Docker, not a Windows process named pfc_*.
Models = host/pfc_load.py + host/pfc_harness.py connect. Host SGD = KILL.

  from muhl_backend import copy, inject, surface, slots, die
"""
from __future__ import annotations

import os
import shutil

GERM = os.path.normpath(r"C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\SEED0.mno")
CONTAINERS = os.path.normpath(r"C:\Users\lucys\Desktop\MUHLNICKEL_DISTRO\CONTAINERS")
MAGIC = b"MUHLPKG1"

# EXPANDING_SEED.md — SEED0 mouths. Not 337. Not titan.
RECV = 353
FWD = 288
REV = 320
SEL = 370
ANS = 5378
BOOM = 1283
FRONTIER = 8191

FORBIDDEN_NAMES = ("muhlnickel_dc.mno", "dc.mno", "titan.gguf")
FORBIDDEN_ADDR = frozenset((337,))

TRAINING_STARTED = False


def _need(msg):
    return {"ok": False, "need_bryce": msg, "training_started": False}


def _ok(**kw):
    out = {"ok": True, "training_started": False}
    out.update(kw)
    return out


def _norm_slot(slot):
    if slot is None or slot == "":
        slot = "slot_0.mno"
    slot = os.path.expanduser(str(slot))
    if os.path.isabs(slot):
        return os.path.normpath(slot)
    if not slot.lower().endswith(".mno"):
        slot = slot + ".mno"
    return os.path.normpath(os.path.join(CONTAINERS, slot))


def _refuse_path(path):
    if not path:
        return "no path"
    base = os.path.basename(os.path.normpath(path)).lower()
    if base in FORBIDDEN_NAMES:
        return "refuse %s (not this button)" % base
    low = os.path.normpath(path).replace("\\", "/").lower()
    if low.endswith("/titan.gguf") or low.endswith("\\titan.gguf"):
        return "refuse titan.gguf"
    if "muhlnickel_dc.mno" in low or low.endswith("/dc.mno"):
        return "refuse dc.mno"
    return None


def _refuse_addr(addr):
    if addr in FORBIDDEN_ADDR:
        return "refuse addr %d (not 337)" % addr
    if addr < 0:
        return "addr %d < 0" % addr
    return None


def _ensure_dir(dest_dir=None):
    d = os.path.normpath(dest_dir) if dest_dir else CONTAINERS
    err = _refuse_path(os.path.join(d, "slot_0.mno"))
    if err:
        return None, err
    os.makedirs(d, exist_ok=True)
    return d, None


def copy(germ=None, slot="slot_0.mno", dest_dir=None):
    """Germ → slot. Copy the file, copy the computer. No dc. No titan."""
    germ = os.path.normpath(germ) if germ else GERM
    err = _refuse_path(germ)
    if err:
        return _need(err)
    if not os.path.isfile(germ):
        return _need("germ missing: %s" % germ)
    d, err = _ensure_dir(dest_dir)
    if err:
        return _need(err)
    dest = _norm_slot(slot) if dest_dir is None else os.path.normpath(
        os.path.join(d, os.path.basename(_norm_slot(slot)))
    )
    err = _refuse_path(dest)
    if err:
        return _need(err)
    if os.path.normcase(os.path.abspath(germ)) == os.path.normcase(os.path.abspath(dest)):
        return _need("germ and slot are the same path")
    try:
        with open(germ, "rb") as f:
            magic = f.read(8)
        if magic != MAGIC:
            return _need("germ magic %r (need MUHLPKG1)" % magic)
        shutil.copy2(germ, dest)
        n = os.path.getsize(dest)
    except OSError as exc:
        return _need("copy failed: %s" % exc)
    return _ok(verb="copy", germ=germ, slot=dest, bytes=n)


def _or_at(path, off, mask_bytes):
    n = len(mask_bytes)
    if n < 1 or n > 16:
        return None, "mask length %d (bounded 1-16)" % n
    if off + n - 1 > FRONTIER:
        return None, "write %d+%d past frontier %d" % (off, n, FRONTIER)
    with open(path, "r+b") as f:
        size = f.seek(0, os.SEEK_END)
        if off + n > size:
            return None, "write %d+%d past file %d" % (off, n, size)
        f.seek(off)
        old = f.read(n)
        if len(old) != n:
            return None, "short read at %d" % off
        new = bytes(o | m for o, m in zip(old, mask_bytes))
        f.seek(off)
        f.write(new)
        f.flush()
        os.fsync(f.fileno())
    return (old, new), None


def inject(slot="slot_0.mno", a=3, b=5, mask=None, recv=True):
    """Bounded OR into both senses. Recv bit old|1. Not 337. Not titan. Not dc."""
    path = _norm_slot(slot)
    err = _refuse_path(path)
    if err:
        return _need(err)
    if not os.path.isfile(path):
        return _need("slot missing: %s" % path)
    for addr in (FWD, REV, SEL, RECV):
        err = _refuse_addr(addr)
        if err:
            return _need(err)
    if mask is None:
        try:
            aa = int(a) & 0xFF
            bb = int(b) & 0xFF
        except (TypeError, ValueError):
            return _need("a,b not ints")
        payload = bytes((aa, bb))
    else:
        try:
            payload = bytes((int(mask) & 0xFF,))
            aa = payload[0]
            bb = 0
        except (TypeError, ValueError):
            return _need("mask not an int")
    try:
        if os.path.getsize(path) < 1:
            return _need("slot empty")
        fwd, err = _or_at(path, FWD, payload)
        if err:
            return _need(err)
        rev, err = _or_at(path, REV, payload)
        if err:
            return _need(err)
        sel, err = _or_at(path, SEL, payload if len(payload) == 2 else payload + b"\x00")
        if err:
            return _need(err)
        recv_hit = None
        if recv:
            recv_hit, err = _or_at(path, RECV, b"\x01")
            if err:
                return _need(err)
    except OSError as exc:
        return _need("inject failed: %s" % exc)
    return _ok(
        verb="inject",
        slot=path,
        fwd={"off": FWD, "old": fwd[0].hex(), "new": fwd[1].hex()},
        rev={"off": REV, "old": rev[0].hex(), "new": rev[1].hex()},
        sel={"off": SEL, "old": sel[0].hex(), "new": sel[1].hex()},
        recv={"off": RECV, "old": recv_hit[0].hex(), "new": recv_hit[1].hex()} if recv_hit else None,
        a=aa,
        b=bb,
    )


def surface(slot="slot_0.mno", addr=None, n=1):
    """Bounded read. Default boom mouth ans+1283. Host transcribes. Dies."""
    path = _norm_slot(slot)
    err = _refuse_path(path)
    if err:
        return _need(err)
    if not os.path.isfile(path):
        return _need("slot missing: %s" % path)
    if addr is None:
        addr = ANS + BOOM
    try:
        addr = int(addr)
        n = int(n)
    except (TypeError, ValueError):
        return _need("addr/n not ints")
    err = _refuse_addr(addr)
    if err:
        return _need(err)
    if n < 1 or n > 16:
        return _need("n=%d (bounded 1-16)" % n)
    if addr + n - 1 > FRONTIER:
        return _need("read %d+%d past frontier %d" % (addr, n, FRONTIER))
    try:
        with open(path, "rb") as f:
            size = f.seek(0, os.SEEK_END)
            if addr + n > size:
                return _need("read %d+%d past file %d" % (addr, n, size))
            f.seek(addr)
            raw = f.read(n)
    except OSError as exc:
        return _need("surface failed: %s" % exc)
    if len(raw) != n:
        return _need("short read at %d" % addr)
    return _ok(verb="surface", slot=path, addr=addr, n=n, hex=raw.hex(), byte=raw[0] if n == 1 else None)


def slots(dest_dir=None):
    """List container dir. Directory of .mno slots. Not Docker."""
    d, err = _ensure_dir(dest_dir)
    if err:
        return _need(err)
    names = []
    try:
        for name in os.listdir(d):
            if name.lower().endswith(".mno"):
                p = os.path.join(d, name)
                if os.path.isfile(p):
                    names.append({"name": name, "path": p, "bytes": os.path.getsize(p)})
    except OSError as exc:
        return _need("slots failed: %s" % exc)
    names.sort(key=lambda x: x["name"])
    return _ok(verb="slots", dir=d, slots=names, n=len(names))


def die():
    return _ok(verb="die")
