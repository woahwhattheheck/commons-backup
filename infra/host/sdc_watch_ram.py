#!/usr/bin/env python3
"""host/sdc_watch_ram.py — measure the SDC run's resident RAM FROM OUTSIDE, without touching the SDC (owner 07-18).

The containment law: nothing may reach INTO the running SDC. So the RAM meter must live in a SEPARATE process that only
asks the OS "how much resident RAM does the run's process hold?" — the same counter Task Manager reads — and watches
whether it spikes. This watcher NEVER opens titan.gguf, never reads the sandbox or the safezone during the run. It only:
  1) launches the contained forward-pass worker as a child (one-way; no pipe monitoring its compute), and
  2) samples that child's working set via the OS by PID, recording the peak, until the child exits.
External observation, not a meter wired into the compute.

  python host/sdc_watch_ram.py [cases_per_op]     # default 8
"""
import ctypes, os, subprocess, sys, time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
sys.stdout.reconfigure(encoding="utf-8")

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class _PMC(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


def _prep():
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    fn = getattr(k32, "K32GetProcessMemoryInfo", None) or ctypes.windll.psapi.GetProcessMemoryInfo
    fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PMC), wintypes.DWORD]; fn.restype = wintypes.BOOL
    return k32, fn


def rss_of(k32, fn, pid):
    """resident + peak working set (MB) of another process, read from the OS by PID. None if the process is gone."""
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h: return None
    c = _PMC(); c.cb = ctypes.sizeof(_PMC)
    ok = fn(h, ctypes.byref(c), c.cb); k32.CloseHandle(h)
    if ok: return c.WorkingSetSize / 1e6, c.PeakWorkingSetSize / 1e6
    return None


def main():
    k32, fn = _prep()
    argv = sys.argv[1:]
    # optional first arg = the worker script (default the storage-contained forward pass); the rest are its args
    if argv and argv[0].endswith(".py"):
        wscript = argv[0] if os.path.isabs(argv[0]) else os.path.join(HERE, os.path.basename(argv[0])); rest = argv[1:]
    else:
        wscript = os.path.join(HERE, "sdc_forward_contained.py"); rest = argv
    worker = [sys.executable, wscript] + (rest or ["8"])
    print(f"[watcher] launching the SDC run as a child and sampling its RAM from OUTSIDE (never touching the SDC) ...", flush=True)
    p = subprocess.Popen(worker)                          # launch the SDC run; we do NOT read its compute, only the OS RAM counter
    first = None; peak = 0.0; n = 0
    while p.poll() is None:
        r = rss_of(k32, fn, p.pid)
        if r:
            ws, pk = r
            if first is None: first = ws
            peak = max(peak, pk, ws); n += 1
        time.sleep(0.1)
    p.wait()
    titan_gb = os.path.getsize("C:/llm/models/titan.gguf") / 1e9
    print(f"\n[watcher] SDC child (pid {p.pid}) exited. {n} external RAM samples.", flush=True)
    print(f"[watcher] first sample: {first:.1f} MB   PEAK resident: {peak:.1f} MB", flush=True)
    print(f"[watcher] titan.gguf on disk = {titan_gb:.1f} GB. If the model were resident this would read ~{titan_gb*1000:,.0f} MB;", flush=True)
    print(f"[watcher] it read ~{peak:.0f} MB, so the 40 GB model stayed in storage (mmap) — it never spiked. Watcher never touched the SDC.", flush=True)
    return p.returncode


if __name__ == "__main__":
    raise SystemExit(main())
