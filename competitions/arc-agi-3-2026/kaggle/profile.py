"""Subprocess wall-time/RSS profiler with deterministic receipt fields."""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import json
import math
from pathlib import Path
import resource
import subprocess
import time
from typing import Sequence


@dataclass(frozen=True)
class ProfileReceipt:
    command: tuple[str, ...]
    cwd: str
    returncode: int
    wall_seconds: float
    peak_rss_mib: float
    stdout_sha256: str
    stderr_sha256: str
    timed_out: bool

    def __post_init__(self) -> None:
        if not self.command or any(not isinstance(x, str) or not x for x in self.command):
            raise ValueError("command must be non-empty argv")
        if not math.isfinite(self.wall_seconds) or self.wall_seconds < 0:
            raise ValueError("wall_seconds invalid")
        if not math.isfinite(self.peak_rss_mib) or self.peak_rss_mib < 0:
            raise ValueError("peak_rss_mib invalid")


def run_profile(argv: Sequence[str], *, cwd: Path, timeout_seconds: float) -> ProfileReceipt:
    if not argv or any(not isinstance(x, str) or not x for x in argv):
        raise ValueError("argv must contain non-empty strings")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be finite positive")
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(tuple(argv), cwd=str(cwd), stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=timeout_seconds, check=False)
        rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        rc = 124
        out = exc.stdout or b""
        err = exc.stderr or b""
    elapsed = time.monotonic() - start
    after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # Linux reports KiB, macOS bytes. Commons/Kaggle Linux is primary; guard absurd byte-like values.
    raw = max(before, after)
    rss_mib = raw / 1024.0
    if rss_mib > 1_000_000:
        rss_mib = raw / (1024.0 * 1024.0)
    return ProfileReceipt(tuple(argv), str(cwd.resolve()), rc, elapsed, rss_mib,
                          sha256(out).hexdigest(), sha256(err).hexdigest(), timed_out)


def receipt_json(receipt: ProfileReceipt) -> str:
    return json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":"), allow_nan=False)
