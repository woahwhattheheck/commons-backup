#!/usr/bin/env python3
"""Offline preflight for FrontierOR Main-track solver archives.

This intentionally checks only the public submission contract. It does not
evaluate optimization quality, feasibility, or private-instance behavior.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import resource
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from dataclasses import dataclass, asdict
from typing import Iterable, Sequence


MIB = 1024 * 1024


@dataclass(frozen=True)
class Policy:
    max_archive_bytes: int = 10 * MIB
    max_entries: int = 10_000
    max_unpacked_bytes: int = 256 * MIB
    max_output_bytes: int = 16 * MIB


@dataclass(frozen=True)
class Member:
    name: str
    size: int
    is_dir: bool
    is_link: bool


@dataclass
class Report:
    ok: bool
    format: str | None
    wrapper: str | None
    solver_folders: list[str]
    missing_expected: list[str]
    errors: list[str]
    warnings: list[str]
    entry_count: int
    unpacked_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


def _safe_name(name: str) -> bool:
    if "\\" in name:
        return False
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts


def _zip_members(zf: zipfile.ZipFile) -> list[Member]:
    out: list[Member] = []
    for info in zf.infolist():
        mode = (info.external_attr >> 16) & 0xFFFF
        is_link = stat.S_ISLNK(mode)
        out.append(Member(info.filename, info.file_size, info.is_dir(), is_link))
    return out


def _tar_members(tf: tarfile.TarFile) -> list[Member]:
    return [
        Member(m.name, m.size, m.isdir(), m.issym() or m.islnk())
        for m in tf.getmembers()
    ]


def _load_members(path: Path) -> tuple[str, list[Member]]:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            return "zip", _zip_members(zf)
    if tarfile.is_tarfile(path):
        with tarfile.open(path, "r:*") as tf:
            return "tar", _tar_members(tf)
    raise ValueError("archive is not zip, tar, or tar.gz")


def _normalized_files(members: Iterable[Member]) -> list[PurePosixPath]:
    result: list[PurePosixPath] = []
    for member in members:
        if member.is_dir:
            continue
        p = PurePosixPath(member.name)
        if not p.parts:
            continue
        if p.parts[0] == "__MACOSX" or p.name == ".DS_Store":
            continue
        result.append(p)
    return result


def _layout(files: Sequence[PurePosixPath]) -> tuple[str | None, dict[str, set[str]]]:
    """Return optional wrapper and direct files for each problem directory."""
    if not files:
        return None, {}

    first_parts = {p.parts[0] for p in files if p.parts}
    wrapper: str | None = None

    if len(first_parts) == 1:
        candidate = next(iter(first_parts))
        direct = {
            p.name for p in files
            if len(p.parts) == 2 and p.parts[0] == candidate
        }
        if not ({"solve.py", "solve"} & direct):
            wrapper = candidate

    folders: dict[str, set[str]] = {}
    for p in files:
        parts = p.parts[1:] if wrapper and p.parts[0] == wrapper else p.parts
        if len(parts) < 2:
            continue
        slug, rest = parts[0], parts[1:]
        if len(rest) == 1:
            folders.setdefault(slug, set()).add(rest[0])
        else:
            folders.setdefault(slug, set())
    return wrapper, folders


def validate_archive(
    archive: Path,
    *,
    expected_slugs: Sequence[str] = (),
    require_all: bool = False,
    policy: Policy = Policy(),
) -> Report:
    errors: list[str] = []
    warnings: list[str] = []
    fmt: str | None = None
    members: list[Member] = []

    if not archive.is_file():
        return Report(False, None, None, [], list(expected_slugs),
                      ["archive does not exist"], [], 0, 0)

    size = archive.stat().st_size
    if size > policy.max_archive_bytes:
        errors.append(
            f"archive is {size} bytes; limit is {policy.max_archive_bytes}"
        )

    try:
        fmt, members = _load_members(archive)
    except (ValueError, OSError, tarfile.TarError, zipfile.BadZipFile) as exc:
        errors.append(str(exc))
        return Report(False, fmt, None, [], list(expected_slugs),
                      errors, warnings, 0, 0)

    if len(members) > policy.max_entries:
        errors.append(
            f"archive has {len(members)} entries; limit is {policy.max_entries}"
        )

    unpacked = sum(max(0, m.size) for m in members if not m.is_dir)
    if unpacked > policy.max_unpacked_bytes:
        errors.append(
            f"unpacked size is {unpacked} bytes; limit is "
            f"{policy.max_unpacked_bytes}"
        )

    bad_paths = sorted({m.name for m in members if not _safe_name(m.name)})
    if bad_paths:
        errors.append("unsafe archive paths: " + ", ".join(bad_paths[:8]))

    links = sorted({m.name for m in members if m.is_link})
    if links:
        errors.append("links are not allowed: " + ", ".join(links[:8]))

    files = _normalized_files(members)
    wrapper, folders = _layout(files)

    solver_folders: list[str] = []
    for slug, names in sorted(folders.items()):
        has_py = "solve.py" in names
        has_bin = "solve" in names
        if has_py and has_bin:
            errors.append(f"{slug}: contains both solve.py and solve")
        elif has_py or has_bin:
            solver_folders.append(slug)

    if not solver_folders:
        errors.append("archive has no problem folder with solve.py or solve")

    expected = sorted(set(expected_slugs))
    missing = sorted(set(expected) - set(solver_folders))
    if missing:
        msg = "missing expected problem solvers: " + ", ".join(missing)
        if require_all:
            errors.append(msg)
        else:
            warnings.append(msg + " (allowed by FrontierOR with acknowledgement)")

    return Report(
        ok=not errors,
        format=fmt,
        wrapper=wrapper,
        solver_folders=solver_folders,
        missing_expected=missing,
        errors=errors,
        warnings=warnings,
        entry_count=len(members),
        unpacked_bytes=unpacked,
    )


def _extract_archive(archive: Path, dest: Path) -> None:
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
        return
    with tarfile.open(archive, "r:*") as tf:
        tf.extractall(dest)


def _solver_dir(root: Path, wrapper: str | None, slug: str) -> Path:
    return root / wrapper / slug if wrapper else root / slug


def _limit_child(cpu_count: int, memory_bytes: int, nofile: int) -> None:
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_NOFILE, (nofile, nofile))
    if hasattr(resource, "RLIMIT_NPROC"):
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
        except (ValueError, OSError):
            pass
    if hasattr(os, "sched_getaffinity") and hasattr(os, "sched_setaffinity"):
        try:
            allowed = sorted(os.sched_getaffinity(0))
            os.sched_setaffinity(0, set(allowed[: max(1, cpu_count)]))
        except OSError:
            pass


def probe_solver(
    archive: Path,
    slug: str,
    instance: Path,
    *,
    time_limit: int,
    policy: Policy = Policy(),
) -> dict:
    report = validate_archive(archive, expected_slugs=[slug], require_all=True,
                              policy=policy)
    if not report.ok:
        return {"ok": False, "phase": "archive", "report": report.to_dict()}

    if not instance.is_file():
        return {"ok": False, "phase": "probe", "error": "instance does not exist"}

    with tempfile.TemporaryDirectory(prefix="frontieror-preflight-") as td:
        root = Path(td)
        _extract_archive(archive, root)
        solver_dir = _solver_dir(root, report.wrapper, slug)
        py = solver_dir / "solve.py"
        exe = solver_dir / "solve"
        if py.is_file():
            command = [
                sys.executable, "solve.py",
                "--problem", slug,
                "--instance", str(instance.resolve()),
                "--output", str((root / "solution.json").resolve()),
                "--time-limit", str(time_limit),
            ]
        elif exe.is_file():
            exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
            command = [
                "./solve",
                "--problem", slug,
                "--instance", str(instance.resolve()),
                "--output", str((root / "solution.json").resolve()),
                "--time-limit", str(time_limit),
            ]
        else:
            return {"ok": False, "phase": "probe", "error": "entry point vanished"}

        output = root / "solution.json"
        started = time.monotonic()
        try:
            cp = subprocess.run(
                command,
                cwd=solver_dir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=time_limit,
                preexec_fn=lambda: _limit_child(2, 4 * 1024 * MIB, 1024),
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "phase": "probe",
                "error": f"solver exceeded local {time_limit}s wall timeout",
                "elapsed_s": round(time.monotonic() - started, 6),
            }

        elapsed = time.monotonic() - started
        errors: list[str] = []
        if cp.returncode != 0:
            errors.append(f"solver exited {cp.returncode}")
        if not output.is_file():
            errors.append("solver did not write the requested output file")
        else:
            if output.stat().st_size > policy.max_output_bytes:
                errors.append(
                    f"solution is {output.stat().st_size} bytes; "
                    f"limit is {policy.max_output_bytes}"
                )
            try:
                obj = json.loads(output.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"solution is not one JSON object: {exc}")
            else:
                if not isinstance(obj, dict):
                    errors.append("solution JSON must be an object")
                elif not isinstance(obj.get("objective_value"), (int, float)):
                    errors.append("solution JSON lacks numeric objective_value")

        return {
            "ok": not errors,
            "phase": "probe",
            "elapsed_s": round(elapsed, 6),
            "returncode": cp.returncode,
            "errors": errors,
            "stdout_tail": cp.stdout[-1000:],
            "stderr_tail": cp.stderr[-1000:],
            "notes": [
                "CPU affinity, address-space, fd and wall-time limits are "
                "best-effort local approximations.",
                "This probe does not enforce FrontierOR network isolation, "
                "read-only /work/solver, feasibility, or objective correctness.",
            ],
        }


def _write_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)


def self_test() -> dict:
    cases: list[tuple[str, bool]] = []
    with tempfile.TemporaryDirectory(prefix="frontieror-selftest-") as td:
        root = Path(td)

        valid = root / "valid.zip"
        _write_zip(valid, {"p1/solve.py": b"print('x')\n"})
        cases.append(("valid-single-problem", validate_archive(valid).ok))

        wrapped = root / "wrapped.zip"
        _write_zip(wrapped, {
            "submission/p1/solve.py": b"x\n",
            "submission/p2/model.py": b"x\n",
            "submission/p2/solve.py": b"x\n",
        })
        r = validate_archive(wrapped)
        cases.append(("valid-wrapper", r.ok and r.wrapper == "submission"))

        traversal = root / "traversal.zip"
        _write_zip(traversal, {"../p1/solve.py": b"x\n"})
        cases.append(("reject-parent-traversal", not validate_archive(traversal).ok))

        dual = root / "dual.zip"
        _write_zip(dual, {"p1/solve.py": b"x\n", "p1/solve": b"x\n"})
        cases.append(("reject-dual-entrypoint", not validate_archive(dual).ok))

        empty = root / "empty.zip"
        _write_zip(empty, {"README.md": b"x\n"})
        cases.append(("reject-no-solver", not validate_archive(empty).ok))

        entries = root / "entries.zip"
        _write_zip(entries, {
            "p1/solve.py": b"x\n",
            "p1/a": b"x",
            "p1/b": b"x",
        })
        cases.append((
            "reject-entry-count",
            not validate_archive(entries, policy=Policy(max_entries=2)).ok,
        ))

        unpacked = root / "unpacked.zip"
        _write_zip(unpacked, {"p1/solve.py": b"12345"})
        cases.append((
            "reject-unpacked-budget",
            not validate_archive(
                unpacked, policy=Policy(max_unpacked_bytes=4)
            ).ok,
        ))

        with tempfile.TemporaryDirectory(prefix="frontieror-tar-") as sd:
            source = Path(sd)
            (source / "p1").mkdir()
            (source / "p1" / "solve.py").write_text("x\n")
            os.symlink("solve.py", source / "p1" / "link")
            linked = root / "linked.tar"
            with tarfile.open(linked, "w") as tf:
                tf.add(source / "p1", arcname="p1")
        cases.append(("reject-link", not validate_archive(linked).ok))

    passed = sum(int(ok) for _, ok in cases)
    return {
        "ok": passed == len(cases),
        "passed": passed,
        "total": len(cases),
        "cases": [{"name": name, "ok": ok} for name, ok in cases],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preflight FrontierOR Main-track solver archives."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="validate archive structure and safety")
    check.add_argument("archive", type=Path)
    check.add_argument("--expected-slug", action="append", default=[])
    check.add_argument("--require-all", action="store_true")

    probe = sub.add_parser(
        "probe",
        help="run one solver under best-effort local CPU/memory/time limits",
    )
    probe.add_argument("archive", type=Path)
    probe.add_argument("--slug", required=True)
    probe.add_argument("--instance", required=True, type=Path)
    probe.add_argument("--time-limit", type=int, default=60)

    sub.add_parser("self-test", help="run eight bounded synthetic checks")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "check":
        result = validate_archive(
            args.archive,
            expected_slugs=args.expected_slug,
            require_all=args.require_all,
        ).to_dict()
    elif args.command == "probe":
        if args.time_limit <= 0:
            raise SystemExit("--time-limit must be positive")
        result = probe_solver(
            args.archive,
            args.slug,
            args.instance,
            time_limit=args.time_limit,
        )
    else:
        result = self_test()

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
