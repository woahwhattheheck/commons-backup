#!/usr/bin/env python3
"""host/pfc_mine_gem.py — THE GEM MINER (owner: Bryce, 2026-07-20). gen_miner stays in STORAGE.

The hybrid miners (pfc_fold_mine / pfc_mine_superior / pfc_fold_check) run gen_miner via compile_ripple = the whole
337k-gate list held resident (the ~585 MB crutch in the LIVE_BITCOIN_RUNS log). This runs the SAME baked gen_miner the
GEM way: the gates STAY in titan.gguf, STREAMED from the mmap one at a time into a bounded wire-buffer — NO resident
gate-list, gates ~0 RAM. Byte-exact vs hashlib double-SHA (compute-via-address, real Bitcoin SHA). RAM = the wire-buffer
only (the ≤~5 MB single-pfc pulse machinery, HYBRID §2.5/§3) — the count lever then scales it (RAM ÷ X pfc).

  python host/pfc_mine_gem.py            # W=1: byte-exact proof + self-calibrated RAM (gem vs the 585 MB crutch)
"""
import ctypes, hashlib, json, mmap, os, struct, sys, time
from ctypes import wintypes as wt
sys.stdout.reconfigure(encoding="utf-8")

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"; GEN_MAGIC = b"TITANGEN"
HEADER = bytes((i * 53 + 7) % 256 for i in range(76))          # fixed group-0 header (deterministic, no network) — matches pfc_fold_check


class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("pf", wt.DWORD)] + [(n, ctypes.c_size_t) for n in ("pws", "ws", "a", "b", "c", "d", "pfu", "ppf", "priv")]
_k = ctypes.windll.kernel32; _p = ctypes.windll.psapi; _k.GetCurrentProcess.restype = ctypes.c_void_p
_p.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), wt.DWORD]
def rss():
    m = PMC(); m.cb = ctypes.sizeof(m); _p.GetProcessMemoryInfo(_k.GetCurrentProcess(), ctypes.byref(m), m.cb); return m.ws / 1e6


def open_gen():
    """mmap gen_miner IN STORAGE. Returns the mmap + header + the byte offset where gates begin. NO gate-list is built."""
    reg = json.load(open(REG)); off = int(reg["gen_miner"]["offset"])
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == GEN_MAGIC, "gen_miner magic mismatch"
    n_in, n_wire, n_gate, _ = struct.unpack_from("<IIII", mm, off + 8)
    gp = off + 24                                              # gates start here (each 9 bytes: <Bii op,a,b)
    d2p = gp + n_gate * 9
    d2c = [[struct.unpack_from("<i", mm, d2p + (wi * 32 + j) * 4)[0] for j in range(32)] for wi in range(8)]
    return mm, f, n_in, n_wire, n_gate, gp, d2c


def digest_streamed(mm, n_in, n_wire, n_gate, gp, d2c, header76, nonce):
    """Ripple the stored miner for ONE nonce, STREAMING each gate from the mmap (gate defs never resident). The wire-buffer
    `v` is the only resident state (n_wire bits). This is compute-via-address: the gates live in the file, addressed here."""
    words = [struct.unpack(">I", header76[i * 4:i * 4 + 4])[0] for i in range(19)] + [nonce]
    v = bytearray(n_wire); v[1] = 1                            # wire 0 = const0, wire 1 = const1
    for i in range(640):
        v[2 + i] = (words[i // 32] >> (i % 32)) & 1
    up = struct.unpack_from; base = 2 + n_in; p = gp
    for i in range(n_gate):
        op, a, b = up("<Bii", mm, p); p += 9                  # <- the gate is READ FROM STORAGE here, not from a resident list
        va = v[a]; vb = v[b]
        v[base + i] = (1 - (va & vb)) if op == 0 else (va & vb) if op == 1 else (va | vb) if op == 2 else (va ^ vb) if op == 3 else (1 - va)
    bit = lambda o: 0 if o == 0 else 1 if o == 1 else v[o]
    return b"".join(struct.pack(">I", sum(bit(d2c[wi][j]) << j for j in range(32))) for wi in range(8))


def ref(nonce): return hashlib.sha256(hashlib.sha256(HEADER + struct.pack(">I", nonce)).digest()).digest()


if __name__ == "__main__":
    r0 = rss()
    mm, f, n_in, n_wire, n_gate, gp, d2c = open_gen()
    r1 = rss()
    print(f"gem miner: gen_miner = {n_gate:,} gates / {n_wire:,} wires, STREAMED from storage (no resident gate-list).", flush=True)
    print(f"  RAM: baseline {r0:.1f} MB -> after mmap of gen_miner {r1:.1f} MB  (+{r1-r0:.2f} MB — the {n_gate:,} gates cost ~0, they stay in the file)\n", flush=True)

    # 1) BYTE-EXACT: the streamed stored miner == hashlib double-SHA (real Bitcoin SHA, computed by address)
    ok = True
    t0 = time.time()
    for nonce in range(60):
        if digest_streamed(mm, n_in, n_wire, n_gate, gp, d2c, HEADER, nonce) != ref(nonce):
            ok = False; print(f"  MISMATCH at nonce {nonce}"); break
    dt = time.time() - t0
    r2 = rss()
    print(f"  [verify] streamed-from-storage miner == hashlib double-SHA over 60 nonces: {ok}", flush=True)
    print(f"  RAM while computing: {r2:.1f} MB (+{r2-r1:.2f} vs mmap) — the ONLY resident state is the {n_wire:,}-bit wire-buffer.\n", flush=True)

    # 2) the honest comparison to the benchmark
    hs = 60 / dt
    print(f"  === GEM vs the compile_ripple benchmark (LIVE_BITCOIN_RUNS) ===", flush=True)
    print(f"    benchmark (crutch): ~585 MB resident (gate-list held), 117.8k H/s (W=32768 bit-slice), frontier 28", flush=True)
    print(f"    gem (this, W=1):    {r2:.0f} MB resident (gates in storage), {hs:.0f} H/s single-lane — RAM is the win:", flush=True)
    print(f"    the {n_gate:,} gates are NOT in RAM. Per-Muhlnickel floor -> the count lever (RAM ÷ X) scales width/instances;", flush=True)
    print(f"    bit-slice W raises H/s (wire-buffer × W), federation adds nodes — same real SHA, gates never resident.", flush=True)
    mm.close(); f.close()
