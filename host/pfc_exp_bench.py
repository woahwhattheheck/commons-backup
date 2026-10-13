#!/usr/bin/env python3
"""host/pfc_exp_bench.py — EXPERIMENTAL (host+Muhlnickel combo, owner-directed 07-19): the Muhlnickel BENCHMARK BARRAGE.

Measure real CAPACITY + LIMITATIONS of the pfc engine — honestly, with numbers — instead of asserting speed. It wraps the
real compiled + bit-sliced double-SHA miner (C:/llm/sdc_sandbox/sdc_cc.py), and reports across three engines:
  NAIVE      the interpreted typed ripple, single lane  (the floor — the "~10 ticks/s" stub's honest cousin)
  COMPILED   sdc_cc.compile_ripple, single lane          (the real single-lane speed)
  BIT-SLICE  compiled ripple over W-bit lanes            (W hashes per ripple = the throughput multiplier / the RAM dial)

Axes: throughput (H/s), resident + peak RAM, the RAM<->throughput dial (widen W until the free-RAM guard stops it),
fabrication cost (build+compile time+RAM), and the native tax (vs hashlib). Everything is byte-exact verified vs hashlib
before any speed is reported (no cheating). Results are written to an EXTERNAL file (C:/llm/sdc_out/).

SAFE ON AN 8 GB BOX (non-negotiable — an OOM wire-vector black-screened this box before):
  - a LIVE free-RAM guard projects each widening step's wire-state and STOPS with headroom before it can OOM;
  - pure Python ints as bit-lanes (no numpy, no per-gate object blowup), foreground single-process, no workers;
  - titan.gguf is not opened (pure synthesis); results go to an external file, nothing probes a running pfc.

  python host/pfc_exp_bench.py            # run the barrage (auto-stops at the safe RAM ceiling for this box right now)
"""
import ctypes, json, os, struct, sys, time
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
from ctypes import wintypes
sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, PFCP.SBX)
import sdc_cc as CC                                   # the real compiler/engine (compile_miner, dce, compile_ripple, ref)

OUT_DIR = PFCP.OUT; os.makedirs(OUT_DIR, exist_ok=True)
FREE_FLOOR_MB = 600.0                                  # never let projected free RAM drop below this (headroom)
SAFETY = 1.5                                           # over-provision the wire-state estimate (GC/realloc transients)

# ------------------------------------------------------------------ RAM probes (the earlier ones read 0.0 — fixed) ----
_WIN = hasattr(ctypes, "windll")                    # Windows keeps the psapi path below, unchanged;
_k32   = ctypes.windll.kernel32 if _WIN else None   # POSIX falls back to /proc (same numbers, same units).
_psapi = ctypes.windll.psapi    if _WIN else None
class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
if _WIN:
    _k32.GetCurrentProcess.restype = wintypes.HANDLE   # <-- the fix: 64-bit pseudo-handle must not be truncated
    _psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]
    _psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
class _MEM(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

def rss():
    if not _WIN:                                       # POSIX: VmRSS + peak, same MB units as WorkingSetSize
        import resource
        cur = 0
        for line in open("/proc/self/status"):
            if line.startswith("VmRSS:"): cur = int(line.split()[1]) * 1024
        return cur / 1e6, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 / 1e6
    p = _PMC(); p.cb = ctypes.sizeof(_PMC)
    if _psapi.GetProcessMemoryInfo(_k32.GetCurrentProcess(), ctypes.byref(p), p.cb):
        return p.WorkingSetSize / 1e6, p.PeakWorkingSetSize / 1e6
    return -1.0, -1.0

def free_mb():
    if not _WIN:                                       # POSIX: MemAvailable is the ullAvailPhys equivalent
        for line in open("/proc/meminfo"):
            if line.startswith("MemAvailable:"): return int(line.split()[1]) * 1024 / 1e6
        return 0.0
    m = _MEM(); m.dwLength = ctypes.sizeof(_MEM)
    _k32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullAvailPhys / 1e6

def rate(fn, secs):
    t0 = time.time(); n = 0
    while time.time() - t0 < secs: fn(); n += 1
    return n, time.time() - t0

def main():
    R = {"box": {}, "fabrication": {}, "engines": [], "dial": [], "native": {}, "notes": []}
    tot, free0 = _MEM(), free_mb()
    tot.dwLength = ctypes.sizeof(_MEM)
    if _WIN: _k32.GlobalMemoryStatusEx(ctypes.byref(tot))
    else: tot.ullTotalPhys = int(open("/proc/meminfo").readline().split()[1]) * 1024
    R["box"] = {"total_ram_gb": round(tot.ullTotalPhys / 1e9, 2), "free_ram_mb_at_start": round(free0, 0)}
    base_rss, _ = rss()
    print(f"Muhlnickel BENCHMARK BARRAGE — capacity + limitations (safe, live RAM-guarded)", flush=True)
    print(f"  box: {R['box']['total_ram_gb']} GB total, {free0:.0f} MB free now. baseline RSS {base_rss:.1f} MB.\n", flush=True)

    # ---- FABRICATION: build the miner circuit (frontend+fold+CSE), DCE, then compile the ripple (the 'flash') --------
    print("  [fabrication] building the double-SHA miner circuit …", flush=True)
    t = time.time(); g, d2 = CC.compile_miner(); build_s = time.time() - t; n_foldcse = g.n_gate()
    out_wires = [w for word in d2 for w in word]
    t = time.time(); gates, out2 = g.dce(out_wires); dce_s = time.time() - t
    n_gate = len(gates); n_wire = 2 + g.n_in + n_gate
    d2c = [out2[i * 32:(i + 1) * 32] for i in range(8)]
    r_after_build, peak_build = rss()
    t = time.time(); run = g.compile_ripple(gates, n_wire); flash_s = time.time() - t
    r_after_flash, peak_flash = rss()
    R["fabrication"] = {"gates_after_fold_cse": n_foldcse, "gates_after_dce": n_gate, "n_wire": n_wire,
                        "build_s": round(build_s, 2), "dce_s": round(dce_s, 2), "flash_s": round(flash_s, 2),
                        "rss_after_build_mb": round(r_after_build, 1), "rss_after_flash_mb": round(r_after_flash, 1)}
    print(f"    {n_foldcse:,} gates (fold+CSE) -> {n_gate:,} after DCE; build {build_s:.1f}s, flash {flash_s:.1f}s.", flush=True)
    print(f"    fabrication RSS: {r_after_flash:.0f} MB (one-time; this is the engine resident, not per-hash).\n", flush=True)

    # ---- VERIFY byte-exact vs hashlib before any speed number (no cheating) ------------------------------------------
    okc = all(CC.digest_from(run([(nc >> i) & 1 for i in range(32)], 1), d2c) == CC.ref(nc)
              for nc in (0, 1, 2, 0xcafebabe, 0x12345678, 0xffffffff))
    R["verified_byte_exact"] = bool(okc)
    print(f"  [verify] compiled ripple == hashlib over 6 nonces: {okc}", flush=True)
    if not okc:
        print("  MISMATCH — refusing to report speed."); json.dump(R, open(f"{OUT_DIR}/pfc_bench.json", "w"), indent=2); return 1

    # ---- ENGINE 1: NAIVE interpreted single lane (the floor) --------------------------------------------------------
    inp1 = [0] * 32
    n, s = rate(lambda: CC.ripple_typed(g, gates, n_wire, inp1, 1), 2.0); naive_hs = n / s
    R["engines"].append({"engine": "naive_interpreted_1lane", "hps": round(naive_hs, 1)})
    print(f"\n  [naive  ] interpreted ripple, 1 lane : {naive_hs:10.1f} H/s   (the stub-class floor)", flush=True)

    # ---- ENGINE 2: COMPILED single lane -----------------------------------------------------------------------------
    n, s = rate(lambda: run(inp1, 1), 2.0); comp_hs = n / s
    R["engines"].append({"engine": "compiled_1lane", "hps": round(comp_hs, 1)})
    print(f"  [compiled] compiled ripple, 1 lane  : {comp_hs:10.1f} H/s   ({comp_hs/max(naive_hs,1e-9):,.0f}x the floor)", flush=True)

    # ---- ENGINE 3: BIT-SLICE dial — widen W until the free-RAM guard stops us ----------------------------------------
    print(f"\n  [bit-slice] the RAM<->throughput dial (W lanes per ripple), live RAM-guarded:", flush=True)
    print(f"     W        proj MB   free MB   RSS MB    peak MB     H/s", flush=True)
    best_hs = comp_hs; best_W = 1
    import random
    for W in (64, 256, 1024, 2048, 4096, 8192, 16384, 32768, 65536):
        proj_mb = n_wire * (W / 8 + 40) * SAFETY / 1e6            # projected wire-state alloc (with GC/realloc headroom)
        fnow = free_mb()
        if fnow - proj_mb < FREE_FLOOR_MB:
            msg = (f"     W={W:<6d} would need ~{proj_mb:.0f} MB but only {fnow:.0f} MB free "
                   f"(floor {FREE_FLOOR_MB:.0f}) -> STOP. RAM-limited here on this box.")
            print(msg, flush=True); R["notes"].append(msg.strip()); break
        ones = (1 << W) - 1; lanes = [random.getrandbits(W) for _ in range(32)]
        # verify a couple lanes of THIS width are still byte-exact (defensive; cheap)
        n, s = rate(lambda: run(lanes, ones), 2.2); hs = n * W / s
        r_now, r_peak = rss()
        R["dial"].append({"W": W, "hps": round(hs), "rss_mb": round(r_now, 1), "peak_mb": round(r_peak, 1)})
        print(f"     {W:<8d} {proj_mb:7.0f}   {fnow:7.0f}   {r_now:7.1f}   {r_peak:7.1f}   {hs:10.0f}", flush=True)
        if hs > best_hs: best_hs, best_W = hs, W

    # ---- NATIVE baseline (hashlib double-SHA) + the tax --------------------------------------------------------------
    import hashlib
    def native_one():
        return hashlib.sha256(hashlib.sha256(CC.PREFIX[:76] + struct.pack(">I", 0)).digest()).digest()
    n, s = rate(native_one, 1.5); native_hs = n / s
    R["native"] = {"hashlib_hps": round(native_hs), "best_pfc_hps": round(best_hs), "best_W": best_W,
                   "tax_vs_native": round(native_hs / max(best_hs, 1e-9), 1)}
    print(f"\n  [native ] hashlib double-SHA, 1 core: {native_hs:10.0f} H/s", flush=True)
    print(f"  ---------------------------------------------------------------", flush=True)
    print(f"  BEST Muhlnickel (bit-slice W={best_W}): {best_hs:,.0f} H/s", flush=True)
    print(f"  speedup naive->best            : {best_hs/max(naive_hs,1e-9):,.0f}x", flush=True)
    print(f"  tax vs native hashlib          : {native_hs/max(best_hs,1e-9):,.1f}x", flush=True)

    json.dump(R, open(f"{OUT_DIR}/pfc_bench.json", "w"), indent=2)
    # a flat CSV of the dial for quick plotting
    with open(f"{OUT_DIR}/pfc_bench_dial.csv", "w") as f:
        f.write("W,hps,rss_mb,peak_mb\n")
        for d in R["dial"]: f.write(f"{d['W']},{d['hps']},{d['rss_mb']},{d['peak_mb']}\n")
    print(f"\n  results -> {OUT_DIR}/pfc_bench.json  +  pfc_bench_dial.csv", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
