# SPDX-License-Identifier: Apache-2.0
"""Runtime identity guard for the canonical TITAN carrier."""
from __future__ import annotations

import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
EXPECTED_GIT_BLOBS = {
    "main.py": "4a8cf7bcda1f0fea231a144692cb84a779a9e73e",
    "titan_runtime.py": "b952c9c228ecbde592bf3d2df01638677abb0d24",
    "TITAN-CONFIG.json": "3a3bef83899d3010fad623b628d9e95d9978111b",
}


def git_blob_sha1(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def verify_canonical_carrier() -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in EXPECTED_GIT_BLOBS.items():
        path = LAB / relative
        actual = git_blob_sha1(path)
        observed[relative] = actual
        if actual != expected:
            raise RuntimeError(
                f"canonical TITAN carrier drift at {relative}: expected {expected}, got {actual}"
            )
    return observed
