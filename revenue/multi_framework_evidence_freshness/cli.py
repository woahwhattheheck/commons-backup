from __future__ import annotations
import argparse, json, os, stat
from pathlib import Path
from .gate import GateError, compile_packet, load_strict_json, render_markdown, verify_packet


def _open_parent(path: Path) -> tuple[int, os.stat_result]:
    parent = path.parent if str(path.parent) else Path(".")
    dflags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"): dflags |= os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"): dflags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"): dflags |= os.O_NOFOLLOW
    dfd = os.open(parent, dflags)
    try:
        before = os.fstat(dfd)
        if not stat.S_ISDIR(before.st_mode):
            raise GateError("output_parent_not_directory")
        return dfd, before
    except Exception:
        os.close(dfd)
        raise


def _target_exists_at(dfd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=dfd, follow_symlinks=False)
        return True
    except FileNotFoundError:
        return False


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    sent = 0
    while sent < len(view):
        n = os.write(fd, view[sent:])
        if n <= 0:
            raise OSError("short_write")
        sent += n


def _final_key(path: Path) -> tuple[str, str]:
    parent = path.parent if str(path.parent) else Path(".")
    return (os.path.normpath(str(parent)), path.name)


def _require_visible_final(path: Path, data: bytes, dfd: int, fd: int) -> None:
    written = os.fstat(fd)
    if not stat.S_ISREG(written.st_mode) or written.st_size != len(data):
        raise GateError("output_write_identity_changed")
    try:
        visible = os.stat(path.name, dir_fd=dfd, follow_symlinks=False)
    except FileNotFoundError as exc:
        raise GateError("output_final_missing") from exc
    if (
        not stat.S_ISREG(visible.st_mode)
        or (visible.st_dev, visible.st_ino, visible.st_size)
        != (written.st_dev, written.st_ino, written.st_size)
    ):
        raise GateError("output_final_replaced")


def _write_new_set(items: list[tuple[Path, bytes]]) -> None:
    """Publish an artifact set under retained parent/file descriptor custody.

    All targets are preflighted before any create. Every created file descriptor
    remains open through the complete set write, fsync, and visible-name identity
    verification. Failures never pathname-delete a partially published artifact.
    """
    if not items:
        return
    seen: set[tuple[str, str]] = set()
    for path, _data in items:
        key = _final_key(path)
        if key in seen:
            raise GateError("output_duplicate_target")
        seen.add(key)

    retained: list[tuple[Path, bytes, int, os.stat_result]] = []
    opened: list[tuple[Path, bytes, int, os.stat_result, int]] = []
    try:
        # Retain every parent generation before checking or creating any target.
        for path, data in items:
            dfd, parent_before = _open_parent(path)
            retained.append((path, data, dfd, parent_before))

        # Whole-set preflight preserves the no-partial-publication behavior for
        # already occupied or dangling-symlink targets.
        for path, _data, dfd, _parent_before in retained:
            if _target_exists_at(dfd, path.name):
                raise GateError("output_exists")

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"): flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"): flags |= os.O_NOFOLLOW

        # Create every final name relative to its retained parent, then retain
        # the exact file descriptor until the entire artifact set is verified.
        for path, data, dfd, parent_before in retained:
            fd = os.open(path.name, flags, 0o600, dir_fd=dfd)
            opened.append((path, data, dfd, parent_before, fd))

        for _path, data, _dfd, _parent_before, fd in opened:
            _write_all(fd, data)
            os.fsync(fd)

        # The visible final basename must still identify the inode/size written
        # through the retained descriptor. A rename/substitution is fail-closed.
        for path, data, dfd, _parent_before, fd in opened:
            _require_visible_final(path, data, dfd, fd)

        # Flush directory entries only after every file passes visible identity.
        synced: set[int] = set()
        for _path, _data, dfd, _parent_before, _fd in opened:
            if dfd not in synced:
                os.fsync(dfd)
                synced.add(dfd)

        # Recheck after directory durability. A substitution on the fsync
        # boundary must not produce a success receipt.
        for path, data, dfd, _parent_before, fd in opened:
            _require_visible_final(path, data, dfd, fd)

        # Preserve the original parent-path generation fence, but perform it
        # only after the whole artifact set is complete.
        for path, _data, _dfd, parent_before, _fd in opened:
            parent = path.parent if str(path.parent) else Path(".")
            try:
                current = os.stat(parent, follow_symlinks=False)
            except FileNotFoundError as exc:
                raise GateError("output_parent_changed") from exc
            if (parent_before.st_dev, parent_before.st_ino) != (current.st_dev, current.st_ino):
                raise GateError("output_parent_changed")

        # Success is emitted only after every retained descriptor closes cleanly.
        # A close error is therefore a publication failure, never a green receipt.
        while opened:
            _path, _data, _dfd, _parent_before, fd = opened.pop()
            os.close(fd)
        while retained:
            _path, _data, dfd, _parent_before = retained.pop()
            os.close(dfd)
    finally:
        # Failure cleanup is descriptor-only and best-effort. Never delete by
        # pathname: partially published truth remains visible for reconciliation.
        for _path, _data, _dfd, _parent_before, fd in reversed(opened):
            try:
                os.close(fd)
            except OSError:
                pass
        for _path, _data, dfd, _parent_before in reversed(retained):
            try:
                os.close(dfd)
            except OSError:
                pass


def _write_new(path: Path, data: bytes) -> None:
    # Preserve the landed single-output helper contract: an already occupied
    # path raises OSError/FileExistsError even though the multi-output compile
    # transaction uses GateError for preflight classification.
    try:
        _write_new_set([(path, data)])
    except GateError as exc:
        if str(exc) == "output_exists":
            raise FileExistsError("output_exists") from exc
        raise


def _target_exists(path: Path) -> bool:
    try:
        os.lstat(path)
        return True
    except FileNotFoundError:
        return False


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description="Compile/verify multi-framework evidence freshness packets")
    sub=parser.add_subparsers(dest="cmd",required=True)
    c=sub.add_parser("compile"); c.add_argument("input"); c.add_argument("packet"); c.add_argument("markdown")
    v=sub.add_parser("verify"); v.add_argument("packet")
    ns=parser.parse_args(argv)
    try:
        if ns.cmd=="compile":
            raw=load_strict_json(ns.input); packet=compile_packet(raw)
            packet_bytes=json.dumps(packet,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")+b"\n"; md_bytes=render_markdown(packet).encode("utf-8")
            packet_path=Path(ns.packet); md_path=Path(ns.markdown)
            _write_new_set([(packet_path,packet_bytes),(md_path,md_bytes)])
            print(packet["receipt_sha256"]); return 0
        packet=load_strict_json(ns.packet); verify_packet(packet); print(packet["receipt_sha256"]); return 0
    except (GateError,OSError) as exc:
        print(f"ERROR:{exc}"); return 2
if __name__=="__main__": raise SystemExit(main())
