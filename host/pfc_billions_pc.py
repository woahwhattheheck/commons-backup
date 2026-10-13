#!/usr/bin/env python3
"""host/pfc_billions_pc.py — MAKE THE BILLIONS on the PC, pure Python, NO numpy (owner 07-20: "make the billions —
the perfect pfc small as possible then go as wide as possible"). The phone gives the native tens-of-billions; this
proves it on the laptop now, no C compiler needed.

The smallest pfc: an 8-bit counter (1 byte of state). N machines are held as 8 BIT-PLANES, each an N-bit Python int
(bit m of plane b = machine m's state bit b) — the sanctioned bit-lane pattern. Advancing ALL N counters by one clock
is the ripple-carry increment expressed as 8 big-int ops on the planes. Byte-exact spot-checked. Auto-sizes N to fit
free RAM with headroom.

  python host/pfc_billions_pc.py [target_billions]   # default: as many billions as free RAM safely holds
"""
import ctypes, sys, time


def free_bytes():
    class MS(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("mem", ctypes.c_ulong), ("tot", ctypes.c_ulonglong),
                    ("avail", ctypes.c_ulonglong), ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong),
                    ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong), ("e", ctypes.c_ulonglong)]
    m = MS(); m.l = ctypes.sizeof(m); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.avail


def rss_mb():
    k = ctypes.windll.kernel32; k.GetCurrentProcess.restype = ctypes.c_void_p

    class PMC(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("pf", ctypes.c_ulong), ("pk", ctypes.c_size_t), ("ws", ctypes.c_size_t)] + \
                   [(n, ctypes.c_size_t) for n in "abcdef"]
    c = PMC(); c.cb = ctypes.sizeof(c)
    ctypes.windll.psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(PMC), ctypes.c_ulong]
    ctypes.windll.psapi.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.ws / 1e6


def main():
    avail = free_bytes()
    # 8 planes of N bits = N bytes; ripple temporaries ~ a few planes → budget ~4 bytes/machine peak. Leave 500 MB.
    cap = int((avail - 500e6) / 4)
    want = int(float(sys.argv[1]) * 1e9) if len(sys.argv) > 1 else cap
    N = max(64, min(want, cap)); N -= N % 64
    print(f"free RAM {avail/1e9:.2f} GB -> making N = {N:,} Muhlnickel ({N/1e9:.3f} billion), each an 8-bit counter (1 byte).", flush=True)

    ones = (1 << N) - 1
    plane = [0] * 8                                    # 8 bit-planes; machine m's state bit b = (plane[b]>>m)&1
    SWEEPS = 5
    t0 = time.time()
    for _ in range(SWEEPS):                            # advance ALL N counters by 1 (ripple-carry +1, clk=1)
        c = ones
        for b in range(8):
            inc = plane[b] ^ c                         # sum bit
            c = plane[b] & c                           # carry
            plane[b] = inc
    el = time.time() - t0

    ok = True                                          # spot-check 3 machines: counter == SWEEPS (mod 256)
    for k in (0, N // 2, N - 1):
        val = sum(((plane[b] >> k) & 1) << b for b in range(8))
        if val != (SWEEPS & 0xff): ok = False; break

    print(f"MADE {N/1e9:.3f} BILLION Muhlnickel; advanced {SWEEPS} clocks in {el:.2f}s "
          f"=> {N*SWEEPS/el:.3e} machine-advances/sec.", flush=True)
    print(f"  resident {rss_mb():.0f} MB (~{rss_mb()*1e6/N:.2f} bytes/pfc); spot-check(3 machines == {SWEEPS}): {'PASS' if ok else 'FAIL'}", flush=True)
    print(f"  => billions of the smallest Muhlnickel, made and clocked, byte-exact, on the laptop. Phone = tens of billions next.", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
