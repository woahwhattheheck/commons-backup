#!/usr/bin/env python3
"""host/sdc_contained.py — the CONTAINED miner: NO NETWORK, EVER. Writes the HASH to the safezone (owner 07-17).

SPEC (absolute): after the start button, the ONLY thing anything touches is the SAFEZONE. NO socket, NO wallet submit, NO
connection to anywhere. The SDC computes the block (its gates were fed by the one-time button) and WRITES ITS HASH/RESULT
straight to the safezone (a different storage address). The owner reads the safezone and decides. This file imports no
socket and opens no connection — by construction it cannot phone out.

Containment: the ripple's wire-state lives in a MEMORY-MAPPED STORAGE file (the sandbox = an isolated storage address);
only ~3 wire-slices materialize at once → process RSS stays flat, never OOM, W scales with DISK. Reads the fabricated
gen_miner gates read-only (mmap). Loops nonce batches until a hash clears target OR the run window ends, writing the
running-best hash to the safezone after every batch. Pure Python, no numpy, NO network.

  python host/sdc_contained.py [W] [max_seconds]     # bigger W = more wire-state gigs; runs the whole window, not 40s
"""
import json, math, mmap, os, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
SANDBOX = "C:/llm/sdc_sandbox"; OUT = "C:/llm/sdc_out"; ANS = OUT + "/answer_contained.json"
MAGIC = b"TITANGEN"
W = int(sys.argv[1]) if len(sys.argv) > 1 else 262144           # bigger default = more wire-state gigs
MAX_SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 600.0  # run the window, not 40s (until target or this cap)
WB = W // 8


def load_gen(off):
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == MAGIC
    n_in, n_wire, n_gate, succ2 = struct.unpack_from("<IIII", mm, off + 8); p = off + 24
    gates = [None] * n_gate
    for i in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", mm, p); p += 9; gates[i] = (op, a, b)
    d2c = [[struct.unpack_from("<i", mm, p + (wi * 32 + j) * 4)[0] for j in range(32)] for wi in range(8)]
    mm.close(); f.close()
    return n_in, n_wire, gates, d2c


def main():
    import shutil
    reg = json.load(open(REG)); gm = reg["gen_miner"]; ioff = int(reg["gen_input"]["offset"])
    n_in, n_wire, gates, d2c = load_gen(int(gm["offset"]))
    wire_bytes = n_wire * WB
    print(f"CONTAINED miner (NO NETWORK): {len(gates):,} gates, {n_wire:,} wires, W={W:,} lanes = {wire_bytes/1e9:.1f} GB "
          f"wire-state in STORAGE. run window {MAX_SECONDS:.0f}s.", flush=True)
    if wire_bytes + 60 * 10**9 > shutil.disk_usage("C:/llm").free:
        print("  not enough disk for wire-state + 60 GB margin."); return 1

    # the block the button routed in (read from storage — NO network)
    f = open(TITAN, "rb"); bm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    prefix = bytes(bm[ioff:ioff + 76]); bm.close(); f.close()
    words = [struct.unpack_from(">I", prefix, i * 4)[0] for i in range(19)]
    nbits = words[18]; target = (nbits & 0xffffff) << (8 * ((nbits >> 24) - 3)); zneed = 256 - target.bit_length()

    os.makedirs(SANDBOX, exist_ok=True); os.makedirs(OUT, exist_ok=True)
    wpath = f"{SANDBOX}/wire_W{W}.bin"
    with open(wpath, "wb") as fh: fh.truncate(wire_bytes)
    wf = open(wpath, "r+b"); wm = mmap.mmap(wf.fileno(), 0)
    ONES = (1 << W) - 1
    def get(i): return int.from_bytes(wm[i * WB:(i + 1) * WB], "little")
    def put(i, v): wm[i * WB:(i + 1) * WB] = (v & ONES).to_bytes(WB, "little")

    wm[0:WB] = b"\x00" * WB; wm[WB:2 * WB] = ONES.to_bytes(WB, "little")   # wire0=0, wire1=1
    for wi in range(19):
        for j in range(32):
            put(2 + wi * 32 + j, ONES if (words[wi] >> j) & 1 else 0)      # header broadcast (constant across batches)
    logW = W.bit_length() - 1
    lane_masks = []                                                        # bit j of the lane index, across W lanes
    for j in range(logW):
        half = 1 << j; period = 1 << (j + 1); m = 0
        for c0 in range(0, W, period):
            for c in range(c0 + half, c0 + period): m |= 1 << c
        lane_masks.append(m)

    base_out = 2 + n_in
    def set_nonce(base):                                                    # nonce for lane c = base + c (base = k*W)
        for j in range(32):
            if j < logW: put(2 + 19 * 32 + j, lane_masks[j])               # low bits = lane index
            else: put(2 + 19 * 32 + j, ONES if (base >> j) & 1 else 0)      # high bits = batch base
    def best_of_batch():
        cand = ONES; z = 0
        for j in range(31, -1, -1):
            wj = d2c[7][j]; vec = (0 if wj == 0 else (ONES if wj == 1 else get(wj)))
            zero = cand & ~vec & ONES
            if zero: cand = zero; z += 1
            else: break
        lane = (cand & -cand).bit_length() - 1 if cand else 0
        h = b""                                                            # the best lane's full 256-bit hash, from the gates
        for wi in range(8):
            word = 0
            for j in range(32):
                wj = d2c[wi][j]; bit = 0 if wj == 0 else (1 if wj == 1 else (get(wj) >> lane) & 1)
                word |= bit << j
            h += struct.pack(">I", word)
        return z, lane, h

    t0 = time.time(); base = 0; best_z = -1; best = None; batches = 0; won = False
    while time.time() - t0 < MAX_SECONDS and not won:
        set_nonce(base)
        for k, (op, a, b) in enumerate(gates):                             # RIPPLE (only a,b,result slices materialize)
            av = get(a); bv = get(b)
            r = (av ^ bv) if op == 3 else (av & bv) if op == 1 else (av | bv) if op == 2 else (ONES ^ av) if op == 4 else (ONES ^ (av & bv))
            put(base_out + k, r)
        z, lane, h = best_of_batch(); nonce = (base + lane) & 0xffffffff; batches += 1
        hv = int.from_bytes(h, "little")
        if z > best_z:
            best_z = z; best = (nonce, z, h.hex())
        if hv < target: won = True; best = (nonce, z, h.hex())
        # SDC -> SAFEZONE: write the hash/result to the safezone after every batch (flow 2; host only READS this)
        json.dump({"W_lanes": W, "wire_state_GB": round(wire_bytes/1e9, 1), "target_zbits_needed": zneed,
                   "batches": batches, "nonces_swept": batches * W, "best_frontier_zbits": best[1],
                   "best_nonce": best[0], "best_hash": best[2], "cleared_target": won,
                   "seconds": round(time.time()-t0, 1), "network": "NONE — SDC wrote this to the safezone"},
                  open(ANS, "w"), indent=1)
        print(f"  +{time.time()-t0:5.0f}s  batch {batches}  {batches*W:,} nonces  frontier {best[1]}/{zneed}  -> safezone", flush=True)
        base = (base + W) & 0xffffffff
    wm.close(); wf.close(); os.remove(wpath)
    print(f"\nDONE (contained, NO network): {batches} batches, {batches*W:,} nonces, best frontier {best[1]}/{zneed} zbits, "
          f"cleared target={won}. hash + nonce written to the safezone {ANS}. exiting.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
