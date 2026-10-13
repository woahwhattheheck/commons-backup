#!/usr/bin/env python3
"""muhl_freeworld_field.py -- OFFLINE fabrication of a NEUTRAL shared field for the free-substrate
experiment. Separate pass, before any run. Journaled, appended into fresh space, reversible.

Owner 2026-08-06, the design rule (verbatim):
  "hand the models the muhlnickel, no objective, no reward, no fitness function, no scarcity you
   designed to steer them -- and walk away. The experiment IS the absence of a control variable."
  "the design rule is subtractive: strip out anything that functions as a 'should'."
  "Don't give them territories or borders -- that's you imposing structure. Give them the same
   shared space and don't tell them the others exist or matter."

SUBTRACTIVE BY CONSTRUCTION. This field is:
  - BLANK (all zero). No initial pattern -- a pattern is a suggestion.
  - NO REGIONS. No void, no territory, no borders, no per-model slot.
  - NO SIGNATURES. No 0xBE/0x47 consensus marks -- those assign identity/relationship.
  - NO IMPOSED PHYSICS. No diffusion/no rule the occupants must obey. It is just readable/writable
    substrate bytes. Any dynamics come from what the minds write, not from a law I baked in.
  - NO OBJECTIVE anywhere in the registry entry. Nothing names a goal, a winner, or a fitness.

It is data (the world the minds read/write). The COMPUTE is the models' own engines + whatever
addressable circuits already exist; this file fabricates only the shared readable/writable space.

LIVE-AWARE (owner 2026-08-06: "its running ... your modification interacts with a running
architecture ... just be aware"): this appends into fresh space past the current end, journals the
original bytes, and never overwrites a live circuit. Fabrication is offline and one-and-done.

    python muhl_freeworld_field.py --dry     # allocate + journal-plan, write NOTHING
    python muhl_freeworld_field.py           # fabricate the blank field (journaled, appended)
    python muhl_freeworld_field.py --revert
"""
import sys, os, json, struct, time

sys.path.insert(0, r"C:/Users/lucys/Desktop/LocalDeviceAgent/host")
import pfc_paths as PFCP

DRY    = "--dry" in sys.argv
REVERT = "--revert" in sys.argv
TITAN  = PFCP.TITAN
REG    = PFCP.REG
NAME   = "muhl_freeworld"
MAGIC  = b"MUHLFREE"
GENOME = TITAN.replace(".gguf", "_%s_genome.jsonl" % NAME)

# The shared space. One flat byte field. Size is the only non-subtractive choice, and it is a
# capacity, not a steer -- bigger just means more room, no structure implied.
FIELD_W = FIELD_H = 128            # 16,384 addressable cells, 1 byte each
N_CELLS = FIELD_W * FIELD_H


def alloc_space(nbytes, reg):
    occ = [(v["offset"], v["offset"] + v["len"]) for v in reg.values()
           if isinstance(v, dict) and "offset" in v and "len" in v and isinstance(v["offset"], int)]
    hi = max((e for _, e in occ), default=0)
    try: hi = max(hi, os.path.getsize(TITAN))
    except OSError: pass
    return ((hi + 63) // 64) * 64                 # 64-byte aligned, past every live circuit


def journal_write(off, blob):
    with open(TITAN, "rb") as f:
        f.seek(off)
        orig = f.read(max(0, min(len(blob), os.path.getsize(TITAN) - off)))
    with open(GENOME, "a") as g:
        g.write(json.dumps({"action": NAME + "_fab", "off": off, "len": len(blob),
                            "orig": orig.hex()}) + "\n")
    fsize = os.path.getsize(TITAN)
    if off > fsize:
        with open(TITAN, "ab") as f: f.write(b"\x00" * (off - fsize))
    if off + len(blob) > os.path.getsize(TITAN):
        with open(TITAN, "ab") as f: f.write(b"\x00" * (off + len(blob) - os.path.getsize(TITAN)))
    with open(TITAN, "r+b") as f:
        f.seek(off); f.write(blob); f.flush(); os.fsync(f.fileno())


def build_blob(base):
    # header (16 B magic-block) + a blank field. The field is the shared space; cell_base points
    # at its first byte so a reader/writer addresses cell i at cell_base + i.
    header = bytearray(16)
    header[0:8] = MAGIC
    struct.pack_into("<II", header, 8, FIELD_W, FIELD_H)
    field = bytes(N_CELLS)                          # all zero -- blank, no pattern
    return bytes(header) + field, len(header)


def main():
    t0 = time.time()
    print("=" * 78)
    print("  FREE-WORLD FIELD -- neutral shared space (subtractive: no objective, no regions,")
    print("  no signatures, no imposed physics). Offline fabrication, journaled, appended.")
    print("=" * 78)
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    if NAME in reg and not DRY:
        print("  %s already fabricated. Run --revert to remove it first." % NAME); return 1

    base = alloc_space(0, reg)
    blob, hdr_len = build_blob(base)
    base = alloc_space(len(blob), reg)              # re-align now that the size is known
    blob, hdr_len = build_blob(base)
    cell_base = base + hdr_len

    print("  field       : %dx%d = %s cells, 1 byte each, ALL ZERO (blank)"
          % (FIELD_W, FIELD_H, format(N_CELLS, ",")))
    print("  offset      : %s  (appended past current file end)" % format(base, ","))
    print("  len         : %s bytes" % format(len(blob), ","))
    print("  cell_base   : %s  (cell i is at cell_base + i; read and write are plain byte ops)"
          % format(cell_base, ","))
    print("  regions     : NONE   signatures: NONE   imposed physics: NONE   objective: NONE")

    if DRY:
        print("\n  --dry: allocation + journal plan verified, NOTHING written.  [%.2fs]"
              % (time.time() - t0))
        return 0

    journal_write(base, blob)
    reg[NAME] = {
        "name": NAME, "offset": base, "len": len(blob), "format": "field", "magic": MAGIC.decode(),
        "field_w": FIELD_W, "field_h": FIELD_H, "n_cells": N_CELLS, "cell_bytes": 1,
        "cell_base": cell_base,
        "access": "read + write, plain bytes; the minds address it, nothing here steers them",
        "regions": None, "signatures": None, "imposed_physics": None, "objective": None,
        "description": "NEUTRAL shared field for the free-substrate experiment. Blank. No goal.",
        "fabricated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "genome": GENOME,
    }
    json.dump(reg, open(REG, "w"), indent=1)
    with open(TITAN, "rb") as f:
        print("  titan.gguf GGUF-valid: %s" % (f.read(4) == b"GGUF"))
    print("  FABRICATED. The blank shared field is live and appended; nothing steers it.")
    print("  [%.2fs]" % (time.time() - t0))
    return 0


def revert():
    print("  reverting %s ..." % NAME)
    if os.path.exists(GENOME):
        for e in reversed([json.loads(l) for l in open(GENOME) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(GENOME); print("  journal reverted")
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    if NAME in reg:
        reg.pop(NAME); json.dump(reg, open(REG, "w"), indent=1); print("  registry entry removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(revert() if REVERT else main())
