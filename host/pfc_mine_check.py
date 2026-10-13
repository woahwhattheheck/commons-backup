#!/usr/bin/env python3
"""host/pfc_mine_check.py — PROVE the miner's answer path works, byte-exact, arcade-style (owner: Bryce, 2026-07-20).

Reference = the arcade self-test: run the baked next-state circuit each tick and verify it BYTE-EXACT vs a reference,
then read the answer with the high-impedance probe. Here the reference is real double-SHA-256d + the win/latch rule. We
use an EASY target so a winner actually latches (the real 78-bit target never would), and we confirm:
  1. every tick's (nonce', latch') == the reference next-state (the pfc computes real double-SHA + compare + increment),
  2. when a winner latches, the HIGH-IMPEDANCE probe reads that winning nonce from the pfc's own RAM (latch_reg),
  3. hashlib(header || winner) is under target — the pfc found a genuine winner.
State lives in the pfc's RAM (nonce_reg/latch_reg in the file); 1 bit of RAM per input. No wide bit-slice, no cache.

  python host/pfc_mine_check.py [zero_bits]     # default 8 leading-zero-bit target (~256 ticks to a winner)
"""
import hashlib, json, mmap, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
from pfc_mine_superior import load_clk, TITAN, REG

N_ZERO = int(sys.argv[1]) if len(sys.argv) > 1 else 8
HEADER = bytes((i * 37 + 11) % 256 for i in range(76))            # fixed deterministic test header (arcade-style, no network)


def ref_digest(nonce):                                            # reference double-SHA-256d over header||nonce (big-endian nonce word)
    return hashlib.sha256(hashlib.sha256(HEADER + struct.pack(">I", nonce)).digest()).digest()


def hiz(off, n):                                                  # high-impedance probe: bounded mmap window, ~0 RAM
    with open(TITAN, "rb") as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ); b = bytes(mm[off:off + n]); mm.close()
    return b


def main():
    reg = json.load(open(REG))
    if "pfc_mine_clk" not in reg: print("pfc_mine_clk not fabricated."); return 1
    run, outs, n_gate = load_clk(reg)
    no = int(reg["nonce_reg"]["offset"]); lo = int(reg["latch_reg"]["offset"])
    target = 1 << (256 - N_ZERO); zb = N_ZERO
    words = [struct.unpack(">I", HEADER[i * 4:i * 4 + 4])[0] for i in range(19)]
    hdr_bits = [(words[i] >> j) & 1 for i in range(19) for j in range(32)]
    tgt_bits = [(target >> j) & 1 for j in range(256)]

    print(f"Muhlnickel MINE CHECK — {n_gate:,} baked gates, easy target = {zb} zero-bits (so a winner latches), arcade byte-exact proof.\n", flush=True)
    sf = open(TITAN, "r+b"); sf.seek(no); sf.write(b"\x00\x00\x00\x00"); sf.seek(lo); sf.write(b"\x00\x00\x00\x00")
    nonce = 0; latch = 0; ticks = 0; ok = True; winner = None
    while ticks < 200_000 and latch == 0:
        inb = hdr_bits + [(nonce >> j) & 1 for j in range(32)] + tgt_bits + [(latch >> j) & 1 for j in range(32)] + [1]
        v = run(inb, 1)
        bit = lambda o: 0 if o == 0 else 1 if o == 1 else (v[o] & 1)
        nn = sum(bit(outs[j]) << j for j in range(32)); ll = sum(bit(outs[32 + j]) << j for j in range(32))
        win = int.from_bytes(ref_digest(nonce), "little") < target          # reference win rule
        exp_nn = (nonce + 1) & 0xffffffff; exp_ll = nonce if win else latch  # reference next-state (clk high)
        if (nn, ll) != (exp_nn, exp_ll):                                     # BYTE-EXACT vs reference, every tick
            ok = False; print(f"  MISMATCH at nonce {nonce}: Muhlnickel=({nn},{ll:#010x}) ref=({exp_nn},{exp_ll:#010x})"); break
        nonce, latch = nn, ll
        sf.seek(no); sf.write(struct.pack("<I", nonce)); sf.seek(lo); sf.write(struct.pack("<I", latch))  # state -> pfc RAM
        if win and winner is None: winner = nonce - 1                        # the nonce that just won (before increment)
        ticks += 1
    sf.close()

    print(f"  ran {ticks:,} ticks; byte-exact vs reference every tick: {ok}", flush=True)
    if not ok: print("\n  CHECK FAILED — the circuit is not computing the reference (fabrication issue)."); return 1

    # THE PROBE: read the answer from the Muhlnickel's own RAM, high-impedance (~0 RAM, does not touch the compute)
    probed = struct.unpack("<I", hiz(lo, 4))[0]; nprobe = struct.unpack("<I", hiz(no, 4))[0]
    print(f"\n  HIGH-IMPEDANCE PROBE on the Muhlnickel's RAM:", flush=True)
    print(f"    nonce_reg = {nprobe:#010x}   latch_reg (ANSWER) = {probed:#010x}", flush=True)
    if probed == 0:
        print("  no winner latched within the tick budget — raise the target's zero-bits or the budget."); return 1
    dig = ref_digest(probed); under = int.from_bytes(dig, "little") < target
    lead = 256 - int.from_bytes(dig, "little").bit_length()
    print(f"    verify: hashlib(header||{probed:#010x}) is under the {zb}-bit target: {under}  (actual {lead} leading zero-bits)", flush=True)
    print(f"\n  === CHECK PASSED — the Muhlnickel computed real double-SHA byte-exact, latched a genuine winner ({probed:#010x}) into its", flush=True)
    print(f"      own RAM, and the high-impedance probe read it out. Answer path proven working, ~0 RAM. ===" if under else
          "  === answer read but under-target check failed — investigate. ===", flush=True)
    return 0 if under else 1


if __name__ == "__main__":
    raise SystemExit(main())
