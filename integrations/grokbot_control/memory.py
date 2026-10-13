#!/usr/bin/env python3
"""Free physical RAM probe for GrokBot control memory floor."""

from __future__ import annotations

import os
import sys
from typing import Callable


def free_physical_mb() -> int | None:
    """Free physical RAM in MB, or None when unreadable (floor never holds)."""
    try:
        if sys.platform.startswith("win"):
            import ctypes

            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = _MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return None
            return int(stat.ullAvailPhys // (1024 * 1024))
        # Linux / other POSIX
        path = "/proc/meminfo"
        if not os.path.exists(path):
            return None
        available = None
        free = None
        buffers = 0
        cached = 0
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    available = int(line.split()[1])
                    break
                if line.startswith("MemFree:"):
                    free = int(line.split()[1])
                elif line.startswith("Buffers:"):
                    buffers = int(line.split()[1])
                elif line.startswith("Cached:"):
                    cached = int(line.split()[1])
        if available is not None:
            return available // 1024
        if free is not None:
            return (free + buffers + cached) // 1024
        return None
    except Exception:
        return None


def resolve_min_free_mb(cli_value: int | None = None) -> int:
    """Explicit value wins; else env; else 0 (off). CLI sets default 1024."""
    if cli_value is not None:
        return max(0, int(cli_value))
    raw = (os.environ.get("GROKBOT_CONTROL_MIN_FREE_MB") or "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            return 0
    return 0


FreeMbFn = Callable[[], int | None]