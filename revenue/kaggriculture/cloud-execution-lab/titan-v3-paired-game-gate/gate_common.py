# SPDX-License-Identifier: Apache-2.0
"""Strict primitives shared by the Titan paired-game evidence gate."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
MAX_JSON_BYTES = 1_048_576
MAX_JSONL_BYTES = 536_870_912


class GateError(ValueError):
    """Evidence cannot be interpreted safely."""


@dataclass(frozen=True, order=True)
class CellKey:
    opponent: str
    seed: int
    seat: int

    def as_list(self) -> list[Any]:
        return [self.opponent, self.seed, self.seat]


@dataclass(frozen=True)
class Game:
    key: CellKey
    scores: tuple[float, float]
    line: int

    @property
    def own(self) -> float:
        return self.scores[self.key.seat]

    @property
    def rival(self) -> float:
        return self.scores[1 - self.key.seat]

    @property
    def margin(self) -> float:
        return finite_number(
            self.own - self.rival,
            label=f"cell {self.key.as_list()} margin",
        )

    @property
    def result(self) -> str:
        margin = self.margin
        return "W" if margin > 0 else ("T" if margin == 0 else "L")


@dataclass(frozen=True)
class FileSnapshot:
    """Private immutable copy whose digest covers exactly the bytes later parsed."""

    path: Path
    sha256: str
    bytes: int


def is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def finite_number(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GateError(f"{label}: expected a number")
    try:
        result = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise GateError(f"{label}: expected a finite number") from exc
    if not math.isfinite(result):
        raise GateError(f"{label}: expected a finite number")
    return result


def _reject_constant(value: str) -> None:
    raise GateError(f"non-finite JSON constant {value!r}")


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise GateError(f"duplicate JSON object key {key!r}")
        out[key] = value
    return out


def strict_loads(text: str, *, label: str) -> Any:
    try:
        return json.loads(
            text,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except GateError:
        raise
    except json.JSONDecodeError as exc:
        raise GateError(
            f"{label}: malformed JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except (RecursionError, ValueError) as exc:
        raise GateError(f"{label}: malformed JSON value: {exc}") from exc


def regular_file(path: Path, *, max_bytes: int, label: str) -> Path:
    raw = Path(path)
    if raw.is_symlink():
        raise GateError(f"{label}: symbolic links are not accepted")
    try:
        path = raw.resolve(strict=True)
    except OSError as exc:
        raise GateError(f"{label}: cannot resolve regular file: {exc}") from exc
    if not path.is_file():
        raise GateError(f"{label}: expected a regular file")
    size = path.stat().st_size
    if size > max_bytes:
        raise GateError(f"{label}: {size} bytes exceeds limit {max_bytes}")
    return path


def snapshot_regular_file(
    path: Path, *, directory: Path, max_bytes: int, label: str
) -> FileSnapshot:
    """Open an input once and hash the exact bytes copied to a private snapshot."""

    raw = Path(path)
    if raw.is_symlink():
        raise GateError(f"{label}: symbolic links are not accepted")

    flags = os.O_RDONLY
    flags |= getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    source_fd: int | None = None
    destination_fd: int | None = None
    destination_name: str | None = None
    try:
        try:
            source_fd = os.open(raw, flags)
        except OSError as exc:
            raise GateError(f"{label}: cannot open regular file: {exc}") from exc

        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode):
            raise GateError(f"{label}: expected a regular file")
        if before.st_size > max_bytes:
            raise GateError(f"{label}: {before.st_size} bytes exceeds limit {max_bytes}")

        directory.mkdir(parents=True, exist_ok=True)
        destination_fd, destination_name = tempfile.mkstemp(
            prefix=".input-", suffix=".snapshot", dir=directory
        )
        digest = hashlib.sha256()
        total = 0
        with os.fdopen(source_fd, "rb", closefd=True) as source:
            source_fd = None
            with os.fdopen(destination_fd, "wb", closefd=True) as destination:
                destination_fd = None
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    total += len(chunk)
                    if total > max_bytes:
                        raise GateError(
                            f"{label}: input grew beyond limit {max_bytes} while reading"
                        )
                    digest.update(chunk)
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())

            after = os.fstat(source.fileno())
            before_identity = (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
            after_identity = (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            if before_identity != after_identity or total != after.st_size:
                raise GateError(f"{label}: changed while being snapshotted")

        snapshot_path = Path(destination_name)
        return FileSnapshot(snapshot_path, digest.hexdigest(), total)
    except Exception:
        if source_fd is not None:
            os.close(source_fd)
        if destination_fd is not None:
            os.close(destination_fd)
        if destination_name is not None:
            try:
                os.unlink(destination_name)
            except FileNotFoundError:
                pass
        raise


def read_json(path: Path, *, label: str) -> Mapping[str, Any]:
    path = regular_file(path, max_bytes=MAX_JSON_BYTES, label=label)
    obj = strict_loads(path.read_text(encoding="utf-8"), label=label)
    if not isinstance(obj, dict):
        raise GateError(f"{label}: top level must be an object")
    return obj


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
