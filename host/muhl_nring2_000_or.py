#!/usr/bin/env python3
# host/muhl_nring2_000_or.py
# Bounded OR on nring2_000 forward/reverse windows only. new=old|mask.
# Dest FROM FILE (titan_circuits.json). Journal pre-image, write, die.
# Recv, carry, gates, other rings: not this button.
#   python host/muhl_nring2_000_or.py --dry
#   python host/muhl_nring2_000_or.py --go --dose fwd-cell0
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REG = "C:/llm/models/titan_circuits.json"
TITAN = "C:/llm/models/titan.gguf"
GENOME = "C:/llm/models/titan_ringfill_add_genome.jsonl"
NAME = "nring2_000"
CELLS = 32

if "--inject" in sys.argv:
    print("REFUSE: that flag is WIPE")
    raise SystemExit(2)

DOSES = ("fwd-cell0", "fwd-zeros", "rev-zeros", "both-zeros")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fail(msg):
    print("FAIL CLOSED:", msg)
    return 1


def _ones(b):
    return sum(bin(x).count("1") for x in b)


def _read(path, off, n):
    with open(path, "rb") as f:
        f.seek(off)
        got = f.read(n)
    if len(got) != n:
        raise IOError("short read @ %s n=%s got=%s" % (off, n, len(got)))
    return got


def _write(path, off, data):
    with open(path, "r+b") as f:
        f.seek(off)
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def _windows(reg):
    e = reg.get(NAME)
    if not isinstance(e, dict):
        return None, "no %s in registry" % NAME
    ram = e.get("ram")
    if not isinstance(ram, dict):
        return None, "no ram map"
    fwd = ram.get("fwd")
    rev = ram.get("rev")
    carry = ram.get("carry")
    recv = ram.get("recv")
    if None in (fwd, rev, carry, recv):
        return None, "ram map incomplete"
    return {
        "fwd": int(fwd),
        "rev": int(rev),
        "carry": int(carry),
        "recv": int(recv),
        "cells": int(e.get("cells") or CELLS),
    }, None


def _mask(dose, n, old_fwd, old_rev):
    zf = bytes(n)
    if dose == "fwd-cell0":
        m = bytearray(n)
        m[0] = 0xFF
        return bytes(m), zf
    if dose == "fwd-zeros":
        m = bytearray(n)
        for i in range(0, n, 8):
            m[i] = 0xFF
        return bytes(m), zf
    if dose == "rev-zeros":
        m = bytearray(n)
        for i in range(0, n, 8):
            m[i] = 0xFF
        return zf, bytes(m)
    if dose == "both-zeros":
        m = bytearray(n)
        for i in range(0, n, 8):
            m[i] = 0xFF
        return bytes(m), bytes(m)
    return None, None


def _or_bytes(old, mask):
    if len(old) != len(mask):
        raise ValueError("mask length")
    out = bytes(old[i] | mask[i] for i in range(len(old)))
    if any(_ones(bytes((out[i],))) < _ones(bytes((old[i],))) for i in range(len(old))):
        raise ValueError("ones would fall")
    return out


def _journal(row):
    os.makedirs(os.path.dirname(GENOME), exist_ok=True)
    with open(GENOME, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(row, ensure_ascii=True) + "\n")
        f.flush()
        os.fsync(f.fileno())


def main():
    if "--go" not in sys.argv and "--dry" not in sys.argv:
        print("NEED --dry or --go --dose %s" % "|".join(DOSES))
        return 1
    dose = None
    if "--dose" in sys.argv:
        i = sys.argv.index("--dose")
        if i + 1 >= len(sys.argv):
            return _fail("--dose needs a name")
        dose = sys.argv[i + 1]
    if "--go" in sys.argv and dose not in DOSES:
        return _fail("--go needs --dose %s" % "|".join(DOSES))
    if dose is not None and dose not in DOSES:
        return _fail("unknown dose")
    if not os.path.isfile(REG):
        return _fail("registry missing")
    if not os.path.isfile(TITAN):
        return _fail("binary missing")
    with open(REG, encoding="utf-8") as f:
        reg = json.load(f)
    win, err = _windows(reg)
    if err:
        return _fail(err)
    n = win["cells"]
    old_fwd = _read(TITAN, win["fwd"], n)
    old_rev = _read(TITAN, win["rev"], n)
    old_carry = _read(TITAN, win["carry"], 1)
    old_recv = _read(TITAN, win["recv"], 1)
    print("NOW fwd ones=%s @ %s" % (_ones(old_fwd), win["fwd"]))
    print("NOW rev ones=%s @ %s" % (_ones(old_rev), win["rev"]))
    print("NOW carry ones=%s recv ones=%s" % (_ones(old_carry), _ones(old_recv)))
    print("fwd hex", old_fwd.hex())
    print("rev hex", old_rev.hex())
    if old_recv != b"\xff":
        print("NOTE recv is not packed")
    if old_carry != b"\x00":
        print("NOTE carry is not empty")
    if "--dry" in sys.argv and "--go" not in sys.argv:
        print("DRY. no write.")
        print("DIE")
        return 0
    mf, mr = _mask(dose, n, old_fwd, old_rev)
    new_fwd = _or_bytes(old_fwd, mf)
    new_rev = _or_bytes(old_rev, mr)
    print("PLAN dose=%s fwd %s->%s rev %s->%s" % (
        dose, _ones(old_fwd), _ones(new_fwd), _ones(old_rev), _ones(new_rev)
    ))
    row = {
        "ts": _now(),
        "name": NAME,
        "dose": dose,
        "fwd_off": win["fwd"],
        "rev_off": win["rev"],
        "old_fwd_hex": old_fwd.hex(),
        "old_rev_hex": old_rev.hex(),
        "old_carry_hex": old_carry.hex(),
        "old_recv_hex": old_recv.hex(),
        "new_fwd_hex": new_fwd.hex(),
        "new_rev_hex": new_rev.hex(),
        "law": "new=old|mask",
    }
    _journal(row)
    print("JOURNAL", GENOME)
    _write(TITAN, win["fwd"], new_fwd)
    _write(TITAN, win["rev"], new_rev)
    after_fwd = _read(TITAN, win["fwd"], n)
    after_rev = _read(TITAN, win["rev"], n)
    after_carry = _read(TITAN, win["carry"], 1)
    after_recv = _read(TITAN, win["recv"], 1)
    print("AFTER fwd ones=%s" % _ones(after_fwd))
    print("AFTER rev ones=%s" % _ones(after_rev))
    print("AFTER carry ones=%s recv ones=%s" % (_ones(after_carry), _ones(after_recv)))
    if after_carry != old_carry or after_recv != old_recv:
        return _fail("recv or carry moved")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
