#!/usr/bin/env python3
"""host/pfc_exp_eval.py — EXPERIMENTAL (host+Muhlnickel combo, owner-directed 07-19): the BARE-MINIMUM contained evaluator.

Purpose: get DATA on the smallest / highest-impedance host process that advances the pfc's stored-bit state — no assertion
about whether one is "needed", just measure it. One tick = read the state (bounded), propagate the stored gates once
(the ripple), write the next state (bounded). It measures its OWN working-set RAM each step so the impedance is a number,
not a claim. NO mmap. Bounded reads/writes of the small registers; the gate list is read once (its size is reported).

  python host/pfc_exp_eval.py [ticks]        # default 8 ticks; prints nonce/latch trajectory + RAM + ticks/s
"""
import ctypes, json, struct, sys, time
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"


def rss_mb():
    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    try:
        pmc = PMC(); pmc.cb = ctypes.sizeof(PMC)
        ctypes.windll.psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
        return pmc.WorkingSetSize / 1e6
    except Exception:
        return -1.0


def rd(off, n):
    with open(TITAN, "rb") as f: f.seek(off); return f.read(n)


def wr(off, b):
    with open(TITAN, "r+b") as f: f.seek(off); f.write(b)


def main():
    ticks = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    reg = json.load(open(REG))
    pm = reg["pfc_mine"]; iw = int(reg["input_window"]["offset"])
    no = int(reg["nonce_reg"]["offset"]); lo = int(reg["latch_reg"]["offset"])
    off = int(pm["offset"]); n_in = int(pm["n_in"]); n_wire = int(pm["n_wire"]); n_gate = int(pm["n_gate"]); n_out = int(pm["n_out"])

    rss0 = rss_mb()
    blob = rd(off, int(pm["len"]))                                  # read the netlist ONCE (bounded); size is the impedance floor
    assert blob[:8] == b"PFCSMACH"
    p = 24
    ops = bytearray(n_gate); ga = [0] * n_gate; gb = [0] * n_gate
    for k in range(n_gate):
        ops[k], ga[k], gb[k] = struct.unpack_from("<Bii", blob, p); p += 9
    outs = list(struct.unpack_from("<%di" % n_out, blob, p))
    rss1 = rss_mb()
    print(f"Muhlnickel EXP EVAL — bare-minimum contained evaluator (no mmap):", flush=True)
    print(f"  netlist: {n_gate:,} gates, {n_wire:,} wires, {len(blob)/1e6:.2f} MB blob.", flush=True)
    print(f"  RAM: bare python {rss0:.1f} MB -> after loading gates {rss1:.1f} MB  (Δ {rss1-rss0:+.1f} MB = the impedance floor)", flush=True)

    def tick(v_in):
        v = bytearray(n_wire); v[1] = 1
        for i in range(n_in): v[2 + i] = v_in[i]
        base = 2 + n_in
        for k in range(n_gate):
            a = v[ga[k]]; b = v[gb[k]]; op = ops[k]
            v[base + k] = (1 - (a & b)) if op == 0 else (a & b) if op == 1 else (a | b) if op == 2 else (a ^ b) if op == 3 else (1 - a)
        return [v[o] if o >= 2 else o for o in outs]

    print(f"  running {ticks} ticks (read state -> ripple -> write state) …", flush=True)
    print("   tick   nonce_reg     latch_reg     ms/tick   RAM", flush=True)
    t_all = time.time()
    for t in range(ticks):
        win = rd(iw, 108); nb = rd(no, 4); lb = rd(lo, 4)
        v_in = [0] * n_in
        for i in range(608): v_in[i] = (win[i // 8] >> (i % 8)) & 1          # header
        for j in range(32): v_in[608 + j] = (nb[j // 8] >> (j % 8)) & 1      # nonce <- nonce_reg
        for i in range(256): v_in[640 + i] = (win[76 + i // 8] >> (i % 8)) & 1  # target
        for j in range(32): v_in[896 + j] = (lb[j // 8] >> (j % 8)) & 1      # latch <- latch_reg
        t0 = time.time(); out = tick(v_in); dt = (time.time() - t0) * 1000
        nn = sum(out[i] << i for i in range(32)); ln = sum(out[32 + i] << i for i in range(32))
        wr(no, struct.pack("<I", nn)); wr(lo, struct.pack("<I", ln))         # write next state (bounded)
        print(f"   {t:4d}   {nn:<12d}  {ln:<12d}  {dt:6.0f}   {rss_mb():.1f} MB", flush=True)
    dur = time.time() - t_all
    print(f"  => {ticks} ticks in {dur:.1f}s ({ticks/dur:.2f} ticks/s). state now: nonce_reg={struct.unpack('<I',rd(no,4))[0]}, "
          f"latch_reg={struct.unpack('<I',rd(lo,4))[0]}.", flush=True)
    print("  (verify the answer with: python host/pfc_assert.py)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
