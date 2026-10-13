#!/usr/bin/env python3
"""host/muhl_post_surface.py — Phase 0 durable-mail SURFACE button. Dies.

Host = inject ∨ surface ∨ die. This button surfaces. It does not inject.
No titan write. No fire 337/336/524288. No pulse 78. No numpy.
Inbox wait --go. --go is refused.

T1 then T2 ACCESS_READ of titan.gguf at already-surfaced mouths:
  fwd_answer      @ 2467652405
  gen_win_surfaced @ 3064767911
Window = 32 bytes (Fable codebook: popcount 256 = all ones = 256 bits).
Documented circuit lens stay 2 B / 6 B; this read is the 32 B mouth window.
WORDS row: ANY printable run length>=4 → glyph WORDS + those runs. Hex always.
Popcount v0 still stands. Not a model paraphrase.

  python host/muhl_post_surface.py
"""
from __future__ import annotations

import hashlib
import json
import mmap
import os
import sys
import time

import muhl_post_render as R

TITAN = "C:/llm/models/titan.gguf"
LEDGER_DIR = r"C:\Users\lucys\Desktop\MUHL_GO\MUHL_POST"
LEDGER = os.path.join(LEDGER_DIR, "post_ledger.jsonl")
WIDTH = 32

MOUTHS = (
    ("fwd_answer", 2467652405),
    ("gen_win_surfaced", 3064767911),
)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _read_t(mm, addr, n, filesz):
    if addr < 0 or addr + n > filesz:
        return None
    return bytes(mm[addr:addr + n])


def _surface_one(path, name, addr):
    try:
        filesz = os.path.getsize(path)
    except OSError:
        print("skip %s @ %d  mmap fail (stat)" % (name, addr))
        return None
    if addr < 0 or addr + WIDTH > filesz:
        print("skip %s @ %d  out of range (titan %d)" % (name, addr, filesz))
        return None
    try:
        with open(path, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                t1 = _read_t(mm, addr, WIDTH, filesz)
            finally:
                mm.close()
    except (OSError, ValueError, BufferError) as exc:
        print("skip %s @ %d  mmap fail T1 (%s)" % (name, addr, exc))
        return None
    if t1 is None:
        print("skip %s @ %d  mmap fail T1" % (name, addr))
        return None
    try:
        with open(path, "rb") as f:
            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                t2 = _read_t(mm, addr, WIDTH, filesz)
            finally:
                mm.close()
    except (OSError, ValueError, BufferError) as exc:
        print("skip %s @ %d  mmap fail T2 (%s)" % (name, addr, exc))
        return None
    if t2 is None:
        print("skip %s @ %d  mmap fail T2" % (name, addr))
        return None
    pop = R.popcount(t1)
    glyph, words, hx = R.render(t1)
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "direction": "surface",
        "bytes": WIDTH,
        "pre_image_or_empty": "",
        "sha256": hashlib.sha256(t1).hexdigest(),
        "addr": addr,
        "t1_hex": hx,
        "t2_hex": t2.hex(),
        "popcount": pop,
        "glyph": glyph,
        "words": words,
        "name": name,
        "t1_eq_t2": t1 == t2,
    }
    return rec


def _append(rec):
    os.makedirs(LEDGER_DIR, exist_ok=True)
    line = {
        "ts": rec["ts"],
        "direction": rec["direction"],
        "bytes": rec["bytes"],
        "pre_image_or_empty": rec["pre_image_or_empty"],
        "sha256": rec["sha256"],
        "addr": rec["addr"],
        "t1_hex": rec["t1_hex"],
        "t2_hex": rec["t2_hex"],
        "popcount": rec["popcount"],
        "glyph": rec["glyph"],
        "words": rec["words"],
    }
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, separators=(",", ":")) + "\n")


def main():
    if "--go" in sys.argv:
        print("GO REFUSED: surface only. Inbox wait --go. No inject.")
        return 1
    if not os.path.isfile(TITAN):
        print("skip titan missing: %s" % TITAN)
        print("titan_written NO")
        print("(button dies)")
        return 0
    print("MUHL POST  surface")
    print("  titan  %s" % TITAN)
    print("  ledger %s" % LEDGER)
    print("  width  %d B  (256-bit codebook window)" % WIDTH)
    n = 0
    for name, addr in MOUTHS:
        rec = _surface_one(TITAN, name, addr)
        if rec is None:
            continue
        _append(rec)
        n += 1
        eq = "y" if rec["t1_eq_t2"] else "n"
        print("  mouth  %s @ %d" % (name, addr))
        print("  t1_eq_t2 %s" % eq)
        print("  popcount %d" % rec["popcount"])
        print("  glyph  %s" % rec["glyph"])
        print("  words  %s" % rec["words"])
        print("  raw    %s" % rec["t1_hex"])
        if not rec["t1_eq_t2"]:
            print("  t2    %s" % rec["t2_hex"])
    print("  titan_written NO")
    print("  entries %d" % n)
    print("(button dies)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
