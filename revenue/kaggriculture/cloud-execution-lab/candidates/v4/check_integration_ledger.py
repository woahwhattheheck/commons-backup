#!/usr/bin/env python3
"""Trusted-anchor composition for the TITAN V4 integration-ledger checker.

This carrier preserves the reviewed descriptor-relative child/leaf implementation
from #14748 byte-for-byte in ``check_integration_ledger_core.py`` and replaces
only its root acquisition seam.  The canonical executable path remains this
module; there is no runtime/gameplay/default/archive/Kaggle authority here.
"""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import check_integration_ledger_core as _core


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | os.O_DIRECTORY
        | os.O_NOFOLLOW
    )


def _open_custody_root(custody_dir: Path) -> int:
    """Open one custody root from a trusted anchor, component by component.

    Absolute roots are walked from ``/``; relative roots are walked from the
    already-open current working directory.  Every untrusted component is
    inspected without following symlinks, opened relative to the retained
    parent descriptor, and re-inspected before the parent descriptor is
    released.  ``..`` is never admissible.
    """

    path = Path(custody_dir)
    parts = path.parts
    if any(part == ".." for part in parts):
        raise _core.LedgerError(f"custody root contains forbidden '..': {custody_dir}")

    flags = _directory_flags()
    absolute = path.is_absolute()
    anchor = "/" if absolute else "."
    components = parts[1:] if absolute else parts

    try:
        current_fd = os.open(anchor, flags)
    except OSError as exc:
        raise _core.LedgerError(
            f"cannot open trusted custody anchor {anchor!r}: {exc}"
        ) from exc

    try:
        anchor_stat = os.fstat(current_fd)
        if not stat.S_ISDIR(anchor_stat.st_mode):
            raise _core.LedgerError(
                f"trusted custody anchor is not a directory: {anchor!r}"
            )

        for component in components:
            if component in ("", "."):
                continue
            if component == "..":
                raise _core.LedgerError(
                    f"custody root contains forbidden '..': {custody_dir}"
                )

            try:
                before = os.stat(
                    component,
                    dir_fd=current_fd,
                    follow_symlinks=False,
                )
            except OSError as exc:
                raise _core.LedgerError(
                    f"cannot inspect custody root component {component!r} in {custody_dir}: {exc}"
                ) from exc
            if not stat.S_ISDIR(before.st_mode):
                raise _core.LedgerError(
                    f"custody root component is not a directory: {component!r} in {custody_dir}"
                )

            try:
                child_fd = os.open(component, flags, dir_fd=current_fd)
            except OSError as exc:
                raise _core.LedgerError(
                    f"cannot open custody root component {component!r} in {custody_dir}: {exc}"
                ) from exc

            keep_child = False
            try:
                opened = os.fstat(child_fd)
                if not stat.S_ISDIR(opened.st_mode):
                    raise _core.LedgerError(
                        f"custody root component is no longer a directory: {component!r} in {custody_dir}"
                    )
                try:
                    after = os.stat(
                        component,
                        dir_fd=current_fd,
                        follow_symlinks=False,
                    )
                except OSError as exc:
                    raise _core.LedgerError(
                        f"cannot re-inspect custody root component {component!r} in {custody_dir}: {exc}"
                    ) from exc

                if (
                    not _core._same_stat_generation(
                        before,
                        opened,
                        _core._DIR_STABLE_FIELDS,
                    )
                    or not _core._same_stat_generation(
                        opened,
                        after,
                        _core._DIR_STABLE_FIELDS,
                    )
                ):
                    raise _core.LedgerError(
                        f"custody root component changed during acquisition: {component!r} in {custody_dir}"
                    )
                keep_child = True
            finally:
                if not keep_child:
                    os.close(child_fd)

            old_fd = current_fd
            current_fd = child_fd
            os.close(old_fd)

        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def _secure_custody_blob_ids(custody_dir: Path, wanted: set[str]) -> set[str]:
    """Resolve custody blobs beneath a trusted-anchor root descriptor."""

    _core._require_descriptor_relative_custody()
    root_fd = _open_custody_root(Path(custody_dir))
    found: set[str] = set()
    try:
        opened = os.fstat(root_fd)
        if not stat.S_ISDIR(opened.st_mode):
            raise _core.LedgerError(
                f"custody path is no longer a directory: {custody_dir}"
            )

        _core._walk_custody_dir(root_fd, Path(custody_dir), wanted, found)

        descriptor_after = os.fstat(root_fd)
        if not _core._same_stat_generation(
            opened,
            descriptor_after,
            _core._DIR_STABLE_FIELDS,
        ):
            raise _core.LedgerError(
                f"custody directory changed while traversing: {custody_dir}"
            )
    except OSError as exc:
        raise _core.LedgerError(
            f"cannot inspect retained custody root {custody_dir}: {exc}"
        ) from exc
    finally:
        os.close(root_fd)
    return found


# Install the narrow successor semantic into the exact reviewed #14748 core.
_core._open_custody_root = _open_custody_root
_core._custody_blob_ids = _secure_custody_blob_ids

if __name__ == "__main__":
    raise SystemExit(_core.main())

# Imports of check_integration_ledger should receive the patched core module so
# existing focused/inherited tests keep their original private-name surface.
sys.modules[__name__] = _core
