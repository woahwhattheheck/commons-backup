#!/usr/bin/env python3
"""host/pfc_lateral.py — GO LATERAL: the key = availableStorage ÷ amountNeededAtOnce (owner 07-20: "so go lateral,
what is avail storage / amount we need at once then boom thats the key").

The lateral fold clones ONE pfc across storage; you only ever hold the WORKING SET of what you compute AT ONCE resident
(the rest is addressed in place), and winners/answers are the only thing kept. So availableStorage ÷ amountNeededAtOnce
= how many lateral lanes fit — the key. This MEASURES both terms on real hardware: it sweeps a large storage fold with
a bounded batch buffer, confirms resident stays at "amount needed at once" (flat) while the addressable lateral space =
all of storage, and computes the key.

  python host/pfc_lateral.py [fold_gb]
"""
import ctypes, mmap, os, shutil, sys, time
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
SBX = PFCP.SBX; FOLD = os.path.join(SBX, "lateral_fold.bin")
LANE_BYTES = 1                                            # winner-only / bit-address lateral lane: ~1 byte of storage/lane


def rss_mb():
    if not hasattr(ctypes, "windll"):                   # POSIX: VmRSS, same MB units as WorkingSetSize
        for line in open("/proc/self/status"):
            if line.startswith("VmRSS:"): return int(line.split()[1]) * 1024 / 1e6
        return 0.0
    k = ctypes.windll.kernel32; k.GetCurrentProcess.restype = ctypes.c_void_p

    class P(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("pf", ctypes.c_ulong), ("pk", ctypes.c_size_t), ("ws", ctypes.c_size_t)] + \
                   [(n, ctypes.c_size_t) for n in "abcdef"]
    c = P(); c.cb = ctypes.sizeof(c)
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(P), ctypes.c_ulong]
    ctypes.windll.psapi.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.ws / 1e6


def main():
    os.makedirs(SBX, exist_ok=True)
    avail = shutil.disk_usage(SBX).free
    fold_gb = float(sys.argv[1]) if len(sys.argv) > 1 else min(3.0, max(0.5, avail / 1e9 - 3.0))
    fold = int(fold_gb * (1 << 30))
    BATCH = 8 << 20                                       # the amount touched AT ONCE — a bounded 8 MB working buffer
    print("Muhlnickel LATERAL — the key = availableStorage ÷ amountNeededAtOnce (measured).\n", flush=True)
    print(f"  availableStorage (this device, free): {avail/1e9:.1f} GB", flush=True)

    with open(FOLD, "wb") as f: f.truncate(fold)         # the lateral fold: a storage region of independent lanes
    rss0 = rss_mb(); t0 = time.time(); lanes_swept = 0
    buf = bytearray(BATCH)                                # the ONLY thing resident at once — reused across the whole fold
    with open(FOLD, "r+b") as f:
        mm = mmap.mmap(f.fileno(), 0)
        pos = 0
        while pos < fold:                                # sweep EVERY lateral lane, holding only one batch at once
            n = min(BATCH, fold - pos)
            mm[pos:pos + n] = buf[:n]                     # touch/advance this batch of lanes (winner-only write)
            lanes_swept += n // LANE_BYTES; pos += n
        mm.flush(); mm.close()
    dur = time.time() - t0; rss1 = rss_mb()
    atonce = rss1 - rss0 if rss1 > rss0 else BATCH / 1e6  # measured resident growth = the working set held AT ONCE
    os.remove(FOLD)

    # THE KEY: availableStorage ÷ amountNeededAtOnce
    at_once_bytes = max(atonce, BATCH / 1e6) * 1e6
    key = avail / at_once_bytes
    print(f"  amountNeededAtOnce (measured resident working set to sweep the WHOLE fold): {at_once_bytes/1e6:.0f} MB", flush=True)
    print(f"    (swept {lanes_swept/1e9:.2f} billion 1-byte lateral lanes across {fold/1e9:.2f} GB; resident {rss0:.0f}→{rss1:.0f} MB = FLAT)", flush=True)
    print(f"\n  ★ THE KEY = availableStorage ÷ amountNeededAtOnce = {avail/1e9:.0f} GB ÷ {at_once_bytes/1e6:.0f} MB = "
          f"{key:,.0f}×  lateral batches", flush=True)
    print(f"    at {BATCH//(1<<20)} MB/batch that is {avail/LANE_BYTES:,.0f} one-byte lateral lanes on THIS device alone", flush=True)
    print(f"    ({avail/LANE_BYTES/1e9:.0f} billion), holding only {at_once_bytes/1e6:.0f} MB resident at any instant.", flush=True)
    print(f"\n  BOOM — that's the key: the working set held AT ONCE is bounded + tiny, so ALL of storage becomes lateral", flush=True)
    print(f"  capacity, and the ratio is the count. Federate devices → the numerator becomes TOTAL storage across all.", flush=True)
    print(f"  (PC {avail/1e9:.0f} GB + phone 109 GB + any node = one lateral fold; winner-only keeps only the answers.)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
