from __future__ import annotations

import hashlib
from pathlib import Path

EXPECTED_ENGINE_BLOB = "3c202c7ee921da239356789e266b694635103fc4"


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def engine_path() -> Path:
    cloud_execution_lab = Path(__file__).resolve().parents[4]
    return cloud_execution_lab / "reference" / "engine" / "kaggriculture.py"


def assert_engine_authority(path: Path | None = None) -> str:
    source_path = path or engine_path()
    actual = git_blob_sha1(source_path.read_bytes())
    if actual != EXPECTED_ENGINE_BLOB:
        raise RuntimeError(
            "official engine authority drifted: "
            f"expected git-blob:{EXPECTED_ENGINE_BLOB}, got git-blob:{actual}"
        )
    return actual


if __name__ == "__main__":
    print(f"engine_authority=git-blob:{assert_engine_authority()}")
