from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import secrets
import stat

from .core import (
    ContractError,
    _file_generation,
    _open_parent_nofollow,
    _reopen_same_parent,
    _same_inode,
)

_SUPPORTS_UNLINK_DIRFD = os.unlink in os.supports_dir_fd
_SUPPORTS_LINK_DIRFD = os.link in os.supports_dir_fd


class PairPublicationError(ContractError):
    def __init__(self, message: str, *, status: str):
        super().__init__(message)
        self.status = status


@dataclass
class _Stage:
    path: Path
    name: str
    data: bytes
    parent_fd: int
    parent_state: os.stat_result
    parent_path: str
    fd: int
    stage_name: str | None
    prepared: os.stat_result
    committed: bool = False
    committed_state: os.stat_result | None = None


def _require_publication_support() -> None:
    if not _SUPPORTS_UNLINK_DIRFD or not _SUPPORTS_LINK_DIRFD or not hasattr(os, "O_NOFOLLOW"):
        raise ContractError("platform lacks descriptor-relative publication support")


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise ContractError("short write while staging output")
        view = view[written:]


def _read_all(fd: int, *, maximum: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = os.read(fd, min(1024 * 1024, maximum + 1 - total))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > maximum:
            raise ContractError("published output grew during verification")
    return b"".join(chunks)


def _require_absent(stage: _Stage) -> None:
    check_fd = _reopen_same_parent(stage.parent_path, stage.parent_state)
    os.close(check_fd)
    try:
        os.stat(stage.name, dir_fd=stage.parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ContractError(f"cannot preflight output safely: {exc}") from exc
    raise ContractError(f"refusing to overwrite {stage.path}")


def _stage(path: Path, data: bytes) -> _Stage:
    _require_publication_support()
    if type(data) is not bytes:
        raise ContractError("publication payload must be exact bytes")
    parent_fd, parent_state, parent_path, name = _open_parent_nofollow(path)
    fd: int | None = None
    stage_name: str | None = None
    try:
        try:
            os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise ContractError(f"cannot preflight output safely: {exc}") from exc
        else:
            raise ContractError(f"refusing to overwrite {path}")

        for _ in range(8):
            candidate = f".spark-stage-{secrets.token_hex(16)}"
            try:
                fd = os.open(
                    candidate,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                    0o600,
                    dir_fd=parent_fd,
                )
                stage_name = candidate
                break
            except FileExistsError:
                continue
            except OSError as exc:
                raise ContractError(f"cannot create private output stage: {exc}") from exc
        if fd is None or stage_name is None:
            raise ContractError("cannot allocate private output stage")

        created = os.fstat(fd)
        if not stat.S_ISREG(created.st_mode) or created.st_nlink != 1:
            raise ContractError("output stage is not private regular storage")
        _write_all(fd, data)
        os.fsync(fd)
        prepared = os.fstat(fd)
        if (
            not _same_inode(created, prepared)
            or prepared.st_size != len(data)
            or prepared.st_nlink != 1
        ):
            raise ContractError("output stage changed while preparing")
        check_fd = _reopen_same_parent(parent_path, parent_state)
        os.close(check_fd)
        return _Stage(path, name, data, parent_fd, parent_state, parent_path, fd, stage_name, prepared)
    except Exception:
        if fd is not None:
            if stage_name is not None:
                try:
                    visible = os.stat(stage_name, dir_fd=parent_fd, follow_symlinks=False)
                    if _same_inode(visible, os.fstat(fd)):
                        os.unlink(stage_name, dir_fd=parent_fd)
                except Exception:
                    pass
            os.close(fd)
        os.close(parent_fd)
        raise


def _commit(stage: _Stage) -> None:
    _require_absent(stage)
    current = os.fstat(stage.fd)
    if stage.stage_name is None:
        raise ContractError("output stage name missing before commit")
    try:
        visible_stage = os.stat(stage.stage_name, dir_fd=stage.parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise ContractError(f"cannot verify output stage: {exc}") from exc
    if (
        _file_generation(current) != _file_generation(stage.prepared)
        or not _same_inode(visible_stage, current)
        or current.st_nlink != 1
    ):
        raise ContractError("output stage generation changed before commit")

    try:
        os.link(
            stage.stage_name,
            stage.name,
            src_dir_fd=stage.parent_fd,
            dst_dir_fd=stage.parent_fd,
            follow_symlinks=False,
        )
        stage.committed = True
    except FileExistsError as exc:
        raise ContractError(f"refusing to overwrite {stage.path}") from exc
    except OSError as exc:
        raise ContractError(f"cannot create-exclusive commit {stage.path}: {exc}") from exc

    linked = os.fstat(stage.fd)
    if not _same_inode(linked, current) or linked.st_nlink != 2 or linked.st_size != len(stage.data):
        raise ContractError("published output link state is not exclusively owned")
    try:
        visible_stage = os.stat(stage.stage_name, dir_fd=stage.parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise ContractError(f"cannot verify output stage cleanup: {exc}") from exc
    if not _same_inode(visible_stage, linked):
        raise ContractError("output stage pathname changed before cleanup")
    os.unlink(stage.stage_name, dir_fd=stage.parent_fd)
    stage.stage_name = None

    committed = os.fstat(stage.fd)
    if committed.st_nlink != 1 or committed.st_size != len(stage.data):
        raise ContractError("published output is not uniquely linked")
    stage.committed_state = committed


def _verify(stage: _Stage) -> None:
    if stage.committed_state is None:
        raise ContractError("published output lacks committed generation")
    os.fsync(stage.parent_fd)
    check_fd = _reopen_same_parent(stage.parent_path, stage.parent_state)
    try:
        try:
            visible = os.stat(stage.name, dir_fd=check_fd, follow_symlinks=False)
        except OSError as exc:
            raise ContractError(f"cannot verify published output: {exc}") from exc
        if _file_generation(visible) != _file_generation(stage.committed_state):
            raise ContractError("published output path generation changed")
    finally:
        os.close(check_fd)

    if _read_all(stage.fd, maximum=len(stage.data)) != stage.data:
        raise ContractError("published output byte verification failed")
    final = os.fstat(stage.fd)
    if _file_generation(final) != _file_generation(stage.committed_state):
        raise ContractError("published output generation changed after byte verification")


def _rollback(stage: _Stage) -> bool:
    clean = True
    try:
        visible = os.stat(stage.name, dir_fd=stage.parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        visible = None
    except OSError:
        return False

    if stage.committed:
        if visible is not None:
            retained = os.fstat(stage.fd)
            if not _same_inode(visible, retained):
                clean = False
            else:
                try:
                    os.unlink(stage.name, dir_fd=stage.parent_fd)
                    os.fsync(stage.parent_fd)
                except OSError:
                    clean = False
    elif visible is not None:
        clean = False

    if stage.stage_name is not None:
        try:
            visible_stage = os.stat(stage.stage_name, dir_fd=stage.parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            stage.stage_name = None
        except OSError:
            clean = False
        else:
            retained = os.fstat(stage.fd)
            if _same_inode(visible_stage, retained):
                try:
                    os.unlink(stage.stage_name, dir_fd=stage.parent_fd)
                    stage.stage_name = None
                except OSError:
                    clean = False
            else:
                clean = False

    if clean and os.fstat(stage.fd).st_nlink != 0:
        clean = False
    try:
        check_fd = _reopen_same_parent(stage.parent_path, stage.parent_state)
        try:
            try:
                os.stat(stage.name, dir_fd=check_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            except OSError:
                clean = False
            else:
                clean = False
        finally:
            os.close(check_fd)
    except ContractError:
        clean = False
    return clean


def _close(stage: _Stage) -> None:
    if stage.stage_name is not None:
        try:
            visible_stage = os.stat(stage.stage_name, dir_fd=stage.parent_fd, follow_symlinks=False)
            retained = os.fstat(stage.fd)
            if _same_inode(visible_stage, retained):
                os.unlink(stage.stage_name, dir_fd=stage.parent_fd)
        except Exception:
            pass
    os.close(stage.fd)
    os.close(stage.parent_fd)


def publish_pair(output_path: Path, output_data: bytes, receipt_path: Path, receipt_data: bytes) -> dict[str, str]:
    """Publish output+receipt as one fail-closed in-process transaction.

    Two filesystem names cannot become visible in one portable namespace operation, so
    a process crash can still interrupt the pair. In-process failures are rolled back
    only when exact retained inode ownership proves that cleanup is safe; otherwise the
    error status is explicitly ambiguous and foreign bytes are preserved.
    """
    states: list[_Stage] = []
    try:
        states.append(_stage(Path(output_path), output_data))
        states.append(_stage(Path(receipt_path), receipt_data))
        destinations = {
            (stage.parent_state.st_dev, stage.parent_state.st_ino, stage.name)
            for stage in states
        }
        if len(destinations) != 2:
            raise ContractError("output and receipt must be distinct destinations")
        for stage in states:
            _require_absent(stage)
        try:
            for stage in states:
                _commit(stage)
            for stage in states:
                _verify(stage)
        except Exception as exc:
            clean = True
            for stage in reversed(states):
                try:
                    clean = _rollback(stage) and clean
                except Exception:
                    clean = False
            if clean:
                raise PairPublicationError(
                    f"pair publication failed; selected outputs rolled back: {exc}",
                    status="ROLLED_BACK_NO_SELECTED_OUTPUTS",
                ) from exc
            raise PairPublicationError(
                f"pair publication failed; output state ambiguous, inspect destinations: {exc}",
                status="AMBIGUOUS_INSPECT_OUTPUTS",
            ) from exc
        return {
            "status": "COMMITTED",
            "output_bytes_sha256": hashlib.sha256(output_data).hexdigest(),
            "receipt_bytes_sha256": hashlib.sha256(receipt_data).hexdigest(),
        }
    finally:
        for stage in states:
            _close(stage)
