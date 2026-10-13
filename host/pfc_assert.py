#!/usr/bin/env python3
"""host/pfc_assert.py — the Muhlnickel ASSERTION CHECKER: verify the miner's live state vs a hashlib reference (owner 07-19).

High-impedance, READ-ONLY. Reads the miner's small registers (input_window, nonce_reg, latch_reg) with bounded mmap-free
reads, then computes the reference double-SHA in Python and reports whether the state is self-consistent: is the latched
nonce actually a winner (hash < target)? what does the current nonce hash to? This is how we CONFIRM a real answer the
moment latch_reg moves — no black-hole, no writes.

  python host/pfc_assert.py
"""
import hashlib, json, struct, sys
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"


def rd(off, n):
    with open(TITAN, "rb") as f: f.seek(off); return f.read(n)


def sha256d(b): return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def header80(hwords, nonce):
    return b"".join(struct.pack(">I", w & 0xffffffff) for w in (list(hwords) + [nonce]))   # 80-byte BE header


def main():
    reg = json.load(open(REG))
    for k in ("input_window", "nonce_reg", "latch_reg"):
        if k not in reg: print(f"{k} absent — run host/pfc_miner.py first."); return 1
    iw = int(reg["input_window"]["offset"]); no = int(reg["nonce_reg"]["offset"]); lo = int(reg["latch_reg"]["offset"])
    win_bytes = rd(iw, 108)                                            # header:76 | target:32
    hwords = [struct.unpack_from("<I", win_bytes, w * 4)[0] for w in range(19)]   # 19 header words (as the miner reads them)
    target = int.from_bytes(win_bytes[76:108], "little")
    nonce = struct.unpack("<I", rd(no, 4))[0]
    latch = struct.unpack("<I", rd(lo, 4))[0]

    print("Muhlnickel ASSERTION CHECKER — live state vs hashlib (high-impedance, read-only):", flush=True)
    print(f"  target        = {'FF*32 (test: everything wins)' if target == (1<<256)-1 else hex(target)}", flush=True)
    tz = 256 - target.bit_length() if target else 256
    print(f"  target zbits  = {tz}", flush=True)

    dn = sha256d(header80(hwords, nonce)); wn = int.from_bytes(dn, "little") < target
    print(f"  nonce_reg     = {nonce}  ->  hash {dn[::-1].hex()[:24]}…  win={wn}", flush=True)

    dl = sha256d(header80(hwords, latch)); wl = int.from_bytes(dl, "little") < target
    print(f"  latch_reg     = {latch}  ->  hash {dl[::-1].hex()[:24]}…  win={wl}", flush=True)
    if latch == 0:
        print("  => latch_reg is 0 (no answer latched yet).", flush=True)
    elif wl:
        print(f"  => ✔ latch_reg holds a VALID winning nonce ({latch}) for this target. Submittable.", flush=True)
    else:
        print(f"  => latch_reg = {latch} does NOT clear this target (not a win for the current header/target).", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
