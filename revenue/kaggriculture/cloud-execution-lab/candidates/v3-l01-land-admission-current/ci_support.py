# SPDX-License-Identifier: Apache-2.0
"""Small fail-closed helpers for the current-LAND evidence driver."""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Sequence


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_id(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git identity.


def run(
    command: Sequence[str],
    *,
    cwd: Path,
    stdout: Path | None = None,
    stderr: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    out_handle = stdout.open("w", encoding="utf-8") if stdout else None
    err_handle = stderr.open("w", encoding="utf-8") if stderr else None
    try:
        return subprocess.run(
            list(command), cwd=cwd, text=True, stdout=out_handle,
            stderr=err_handle, check=check,
        )
    finally:
        if out_handle:
            out_handle.close()
        if err_handle:
            err_handle.close()


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url, headers={"User-Agent": "titan-land-admission-ci/1"}
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        payload = response.read()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def extract_verified(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    root = destination.resolve()
    with tarfile.open(archive, "r:gz") as handle:
        members = handle.getmembers()
        for member in members:
            if member.issym() or member.islnk():
                raise ValueError(f"archive link forbidden: {member.name!r}")
            (root / member.name).resolve().relative_to(root)
        handle.extractall(destination, members=members, filter="data")


def invoke_python(
    python: Path, script: Path, args: Sequence[object], *, cwd: Path
) -> None:
    command = [str(python), "-B", str(script), *map(str, args)]
    result = run(command, cwd=cwd, check=False)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, command)
