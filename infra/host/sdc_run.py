#!/usr/bin/env python3
"""host/sdc_run.py — POWER the fabricated SDC + latch its output to files OUTSIDE the sandbox (owner 07-16).

The block was routed into the SDC's input register by the button (sdc_button.py). This is the POWER: it flips the stored
gates (the fabricated generic miner) and latches their output bus to files OUTSIDE the sandbox — working.txt (proof the
SDC is running, written continuously so there's no debate) and answer.json (the result, to check). All logic lives in the
gates fabricated by the White Box; this only supplies power and persists the output. Reads the SDC read-only; never writes into it.
"""
import hashlib, json, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
OUT = "C:/llm/sdc_out"; WORKING = OUT + "/working.txt"; ANSWER = OUT + "/answer.json"
OPS = {0: "nand", 1: "and", 2: "or", 3: "xor", 4: "not"}; MAGIC = b"TITANGEN"
SECS = float(sys.argv[1]) if len(sys.argv) > 1 else 35.0


def load_gen(off):                                              # read the fabricated generic miner out of the params (read-only)
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == MAGIC
    n_in, n_wire, n_gate, succ2 = struct.unpack_from("<IIII", mm, off + 8); p = off + 24
    gates = [None] * n_gate
    for i in range(n_gate):
        op, a, b = struct.unpack_from("<Bii", mm, p); p += 9; gates[i] = (OPS[op], a, b)
    d2c = [[struct.unpack_from("<i", mm, p + (wi * 32 + j) * 4)[0] for j in range(32)] for wi in range(8)]
    mm.close(); f.close()
    return n_in, n_wire, gates, d2c, succ2


os.makedirs(OUT, exist_ok=True)
reg = json.load(open(REG))
gm = reg["gen_miner"]; ioff = int(reg["gen_input"]["offset"])
n_in, n_wire, gates, d2c, succ2 = load_gen(int(gm["offset"]))    # the SDC's fabricated gates

f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)  # read the block the button routed in
prefix = bytes(mm[ioff:ioff + 76]); mm.close(); f.close()       # 76 bytes = header words w0..w18
words = [struct.unpack_from(">I", prefix, i * 4)[0] for i in range(19)]  # the block info
block_hex = prefix.hex()

run = CC.CircuitCompiler(n_in).compile_ripple(gates, n_wire)    # POWER: the gate rippler (flips the stored gates)
W = 4096; logW = 12; ones = (1 << W) - 1                        # 4096 nonce lanes per ripple
blkbits = []                                                    # the block bits, constant across all lanes
for wi in range(19):
    for j in range(32): blkbits.append(ones if (words[wi] >> j) & 1 else 0)
low = []                                                        # nonce bit-lane masks
for j in range(logW):
    half = 1 << j; period = 1 << (j + 1); mask = 0
    for c0 in range(0, W, period):
        for c in range(c0 + half, c0 + period): mask |= 1 << c
    low.append(mask)

def frontier(v):                                               # best leading-zero count across the lanes (read the output bus)
    cand = ones; z = 0
    for j in range(31, -1, -1):
        w = d2c[7][j]; vec = (0 if w == 0 else (ones if w == 1 else v[w]))
        zero = cand & ~vec & ones
        if zero: cand = zero; z += 1
        else: break
    return z, ((cand & -cand).bit_length() - 1 if cand else 0)

def write_working(msg):                                        # latch a heartbeat to a file OUTSIDE — proof it's running
    with open(WORKING, "a", encoding="utf-8") as w: w.write(msg + "\n")

open(WORKING, "w", encoding="utf-8").close()                   # fresh proof file
write_working(f"SDC POWERED  block={block_hex[:32]}…  gates={len(gates):,}  (fabricated, generic)")
base = 0; swept = 0; best_z = 0; best_nonce = 0; t0 = time.time(); last = 0.0
while time.time() - t0 < SECS:                                 # powered window
    inp = [blkbits[i] if i < 608 else (low[i - 608] if (i - 608) < logW else (ones if (base >> (i - 608)) & 1 else 0)) for i in range(640)]
    v = run(inp, ones)                                         # the SDC computes W double-SHA-256d hashes
    z, lane = frontier(v)
    if z > best_z: best_z = z; best_nonce = (base + lane) & 0xffffffff
    base = (base + W) & 0xffffffff; swept += W
    now = time.time()
    if now - last >= 3.0:                                      # heartbeat -> working.txt (OUTSIDE), so there's no debate
        write_working(f"+{int(now-t0):3d}s  working: {swept:,} nonces rippled  best {best_z} zero-bits")
        last = now
write_working(f"DONE  {swept:,} nonces  best {best_z} zero-bits  best nonce {best_nonce}")
json.dump({"block": block_hex, "nonces": swept, "best_zbits": best_z, "best_nonce": best_nonce,  # the answer, OUTSIDE
           "seconds": round(time.time() - t0, 1)}, open(ANSWER, "w"), indent=1)
