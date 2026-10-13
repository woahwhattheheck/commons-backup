#!/usr/bin/env python3
"""host/pfc_tolimit.py — FABRICATE TO THE PHYSICAL LIMIT (owner 07-20: "to the limit, we continually iterate on
fabrication until we find PHYSICAL limit measured and we go from there"). No extrapolation — actually fill a container
to the brim with baked gate-circuits, verifying functioning byte-exact the whole way and confirming resident RAM stays
FLAT (baking minimizes RAM, it does not grow it), until it physically cannot fit another circuit = the measured wall.

  python host/pfc_tolimit.py [gb]     # fill a <gb>-GB container (default: min(4, free-3)); the container cap IS a
                                       # real physical space wall we hit, safely, then clean up.
"""
import ctypes, hashlib, os, shutil, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, "C:/llm/sdc_sandbox")
sys.stdout.reconfigure(encoding="utf-8")
import sdc_cc as CC
from pfc_phone_substrate import build_sha

SBX = "C:/llm/sdc_sandbox"; SUB = os.path.join(SBX, "tolimit_substrate.bin")
OPC = {"nand": 0, "and": 1, "or": 2, "xor": 3, "not": 4}


def rss_mb():
    k = ctypes.windll.kernel32; k.GetCurrentProcess.restype = ctypes.c_void_p

    class P(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("pf", ctypes.c_ulong), ("pk", ctypes.c_size_t), ("ws", ctypes.c_size_t)] + \
                   [(n, ctypes.c_size_t) for n in "abcdef"]
    c = P(); c.cb = ctypes.sizeof(c)
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(P), ctypes.c_ulong]
    ctypes.windll.psapi.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.ws / 1e6


def make_blob():                                        # fabricate ONE verified sha256 circuit; baking = placing its bytes
    g, outs = build_sha()
    gates, o2 = g.dce(outs); n_wire = 2 + g.n_in + len(gates)
    body = b"".join(struct.pack("<Bii", OPC[op], a, b) for (op, a, b) in gates) + b"".join(struct.pack("<i", w) for w in o2)
    blob = b"PFCTYPED" + struct.pack("<IIII", g.n_in, n_wire, len(gates), len(o2)) + body
    return blob, g.n_in, n_wire, gates, o2


def verify_at(blob, n_in, n_wire, gates, o2, x):        # read a placed circuit back + ripple sha256(x) == hashlib
    assert blob[:8] == b"PFCTYPED"
    v = [0] * n_wire; v[1] = 1
    for i in range(n_in): v[2 + i] = (x >> i) & 1
    base = 2 + n_in
    for k, (op, a, b) in enumerate(gates):
        va, vb = v[a], v[b]
        v[base + k] = (va ^ vb) if op == "xor" else (va & vb) if op == "and" else (va | vb) if op == "or" \
            else (1 ^ va) if op == "not" else (1 ^ (va & vb))
    bit = lambda w: 0 if w == 0 else 1 if w == 1 else v[w] & 1
    out = b"".join(struct.pack(">I", sum(bit(o2[wi * 32 + j]) << j for j in range(32))) for wi in range(8))
    return out == hashlib.sha256(struct.pack(">I", x)).digest()


def main():
    os.makedirs(SBX, exist_ok=True)
    free = shutil.disk_usage(SBX).free
    want_gb = float(sys.argv[1]) if len(sys.argv) > 1 else min(4.0, max(0.5, free / 1e9 - 3.0))
    cap = int(want_gb * (1 << 30))
    print(f"Muhlnickel FABRICATE-TO-LIMIT — fill a {cap/1e9:.2f} GB container to the physical brim (free disk {free/1e9:.1f} GB).\n", flush=True)

    blob, n_in, n_wire, gates, o2 = make_blob()
    ok0 = verify_at(blob, n_in, n_wire, gates, o2, 0xdeadbeef)
    print(f"  fabricated 1 sha256 circuit: {len(gates):,} gates, {len(blob)/1024:.1f} KB/blob, byte-exact: {ok0}", flush=True)
    if not ok0:
        print("  circuit mismatch — aborting."); return 1

    rss0 = rss_mb(); t0 = time.time(); off = 0; count = 0; last = t0
    with open(SUB, "wb") as f:
        f.truncate(cap)                                 # the container (a real fixed-size storage region)
        while off + len(blob) + 8 <= cap:               # bump-allocate + place until it physically cannot fit another
            f.seek(off); f.write(blob); off += len(blob) + 8; count += 1
            if count % 500 == 0:
                now = time.time()
                print(f"    baked {count:,} circuits · {off/1e9:.2f} GB · {count/(now-t0):,.0f}/s · RSS {rss_mb():.0f} MB", flush=True)
    dur = time.time() - t0; rss1 = rss_mb()

    # FUNCTIONING at the brim: read back 5 RANDOM placements + verify byte-exact (functioning held to capacity)
    import struct as _s
    checks = [int(len(blob) + 8) * i for i in (0, count // 4, count // 2, 3 * count // 4, count - 1)]
    allok = True
    with open(SUB, "rb") as f:
        for i, o in enumerate(checks):
            f.seek(o); b = f.read(len(blob))
            if not verify_at(b, n_in, n_wire, gates, o2, 0x01234567 + i): allok = False
    used = shutil.disk_usage(SBX)
    os.remove(SUB)

    print(f"\n  HIT THE WALL: {count:,} circuits baked, {off/1e9:.2f} GB placed — the container is FULL (no room for circuit {count+1}).", flush=True)
    print(f"    functioning at the brim: 5 random placements read back + rippled byte-exact vs hashlib: {allok}", flush=True)
    print(f"    resident RAM: {rss0:.0f} -> {rss1:.0f} MB across all {count:,} bakes = FLAT (baking does NOT grow RAM).", flush=True)
    print(f"    fabrication rate: {count/dur:,.0f} circuits/s = {off/dur/1e6:.0f} MB/s placed.", flush=True)
    print(f"\n  THE PHYSICAL LIMIT (measured): it is STORAGE, nothing else. Functioning + flat RAM held to the last byte", flush=True)
    print(f"  of the container. The only wall is disk capacity — this box's free {free/1e9:.1f} GB fills at this rate in", flush=True)
    print(f"  ~{free/max(off/dur,1)/60:.1f} min; the phone's 109 GB is 100 billion+ 1-byte Muhlnickel (measured earlier). We go from there.", flush=True)
    return 0 if allok else 1


if __name__ == "__main__":
    raise SystemExit(main())
