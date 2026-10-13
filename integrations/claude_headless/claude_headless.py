#!/usr/bin/env python3
"""Headless Claude control for Commons peers: start, inspect, follow up, cancel, recover.

Mechanism (reuse, not invention): the installed, already-authenticated Claude Code CLI
in print mode.

    claude -p "<prompt>" --output-format stream-json --verbose --session-id <uuid>
    claude -p "<prompt>" --output-format stream-json --verbose --resume <uuid>

Every run is an on-disk record under one runs root (default
``~/.claude/commons_headless``, override with ``CLAUDE_HEADLESS_ROOT``)::

    <root>/events.jsonl                 lifecycle journal with a global cursor
    <root>/runs/<run_id>/run.json       state: status, pid, session_id, result, headless evidence
    <root>/runs/<run_id>/prompt.txt     the exact prompt bytes
    <root>/runs/<run_id>/events.jsonl   the child's raw stream-json stdout, byte-exact
    <root>/runs/<run_id>/stderr.txt     the child's stderr

The child writes its stdout straight to ``events.jsonl`` (a file, not a pipe), so a run
outlives the process that started it. Any later process -- a replacement coordinator,
the gateway after a restart, a peer's shell -- reads the same record, finalizes it from
the bytes on disk, resumes the conversation, or cancels the run. Nothing here keeps the
truth in memory only.

Headless: on Windows the child is created with CREATE_NO_WINDOW and its own process
group, stdin is /dev/null, stdout and stderr are files. The record keeps the foreground
window handle before and after, and the count of visible windows owned by the child
tree, so "it stayed headless" is a measurement, not a promise.

Nested-session guard: the Claude Code CLI exports CLAUDECODE / CLAUDE_CODE_* into its
children, and a child that inherits them is treated as part of the caller's session.
The runner strips them (see SCRUB_EXACT / SCRUB_PREFIX) and records what it stripped.
ANTHROPIC_BASE_URL is stripped too so the child uses the CLI's own default endpoint
(measured on the owner PC it is plain https://api.anthropic.com, so this is hygiene, not
a repair); keep specific names with CLAUDE_HEADLESS_KEEP_ENV=NAME,NAME.

Sibling files: ``gateway.py`` / ``client.py`` (CLEAT's lane of build demand C1) serve
this capability over loopback HTTP on 127.0.0.1:8879. This module is the durable
spawn/record primitive and a shell-level CLI; it needs no server.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "ACTIVE",
    "TERMINAL",
    "HeadlessError",
    "Journal",
    "Runner",
    "find_claude",
    "scrub_env",
]

DEFAULT_ROOT = Path(os.environ.get("CLAUDE_HEADLESS_ROOT") or (Path.home() / ".claude" / "commons_headless"))
ACTIVE = frozenset({"queued", "running"})
TERMINAL = frozenset({"completed", "error", "cancelled", "interrupted"})
SCRUB_EXACT = frozenset(
    {"CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_AGENT_SDK_VERSION", "ANTHROPIC_BASE_URL"}
)
SCRUB_PREFIX = ("CLAUDE_CODE_", "CLAUDE_PREVIEW_")
STDIN_PROMPT_THRESHOLD = 8000  # bytes; longer prompts go through stdin, not the command line
_STILL_ACTIVE = 259
_WIN = os.name == "nt"
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200


class HeadlessError(RuntimeError):
    pass


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- windows

if _WIN:
    import ctypes
    import ctypes.wintypes as wt

    _k32 = ctypes.windll.kernel32
    _u32 = ctypes.windll.user32
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _TH32CS_SNAPPROCESS = 0x00000002
    _INVALID_HANDLE = ctypes.c_void_p(-1).value

    class _PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wt.DWORD),
            ("cntUsage", wt.DWORD),
            ("th32ProcessID", wt.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wt.DWORD),
            ("cntThreads", wt.DWORD),
            ("th32ParentProcessID", wt.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wt.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    _k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    _k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    _k32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PROCESSENTRY32W)]
    _k32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PROCESSENTRY32W)]
    _k32.OpenProcess.restype = ctypes.c_void_p
    _k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _k32.CloseHandle.argtypes = [ctypes.c_void_p]
    _k32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.DWORD)]
    _k32.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(wt.FILETIME)] * 4
    _u32.GetForegroundWindow.restype = ctypes.c_void_p
    _u32.GetWindowTextW.argtypes = [ctypes.c_void_p, wt.LPWSTR, ctypes.c_int]
    _u32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    _u32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.DWORD)]
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, ctypes.c_void_p, wt.LPARAM)
    _u32.EnumWindows.argtypes = [_WNDENUMPROC, wt.LPARAM]

    def _foreground() -> list[Any]:
        hwnd = _u32.GetForegroundWindow() or 0
        buf = ctypes.create_unicode_buffer(512)
        _u32.GetWindowTextW(hwnd, buf, 512)
        return [int(hwnd), buf.value]

    def _process_table() -> dict[int, int]:
        """pid -> parent pid for every live process."""
        table: dict[int, int] = {}
        snap = _k32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if not snap or snap == _INVALID_HANDLE:
            return table
        try:
            entry = _PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
            if _k32.Process32FirstW(snap, ctypes.byref(entry)):
                while True:
                    table[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
                    if not _k32.Process32NextW(snap, ctypes.byref(entry)):
                        break
        finally:
            _k32.CloseHandle(snap)
        return table

    def _descendants(pid: int) -> list[int]:
        table = _process_table()
        found: list[int] = []
        frontier = [pid]
        while frontier:
            parent = frontier.pop()
            for child, par in table.items():
                if par == parent and child not in found and child != pid:
                    found.append(child)
                    frontier.append(child)
        return found

    def _visible_windows(pids: set[int]) -> int:
        count = 0

        @_WNDENUMPROC
        def _each(hwnd: int, _lparam: int) -> bool:
            nonlocal count
            if _u32.IsWindowVisible(hwnd):
                owner = wt.DWORD()
                _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
                if int(owner.value) in pids:
                    count += 1
            return True

        _u32.EnumWindows(_each, 0)
        return count

    def _create_time(pid: int) -> int | None:
        handle = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            creation, exit_, kernel, user = (wt.FILETIME() for _ in range(4))
            if not _k32.GetProcessTimes(
                handle, ctypes.byref(creation), ctypes.byref(exit_), ctypes.byref(kernel), ctypes.byref(user)
            ):
                return None
            return (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
        finally:
            _k32.CloseHandle(handle)

    def _pid_alive(pid: int, create_time: int | None) -> bool:
        handle = _k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = wt.DWORD()
            if not _k32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value != _STILL_ACTIVE:
                return False
        finally:
            _k32.CloseHandle(handle)
        if create_time is not None:
            now = _create_time(pid)
            if now is not None and now != create_time:
                return False  # the pid was reused by another process
        return True

    def _kill_tree(pid: int) -> dict[str, Any]:
        before = [pid] + _descendants(pid)
        proc = subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW,
        )
        # "SUCCESS: The process with PID 332 (child process of PID 9824) has been terminated."
        # Only the first number is a killed pid; the second is its parent (possibly us).
        killed = sorted({int(tok) for tok in re.findall(r"process with PID (\d+)", proc.stdout or "")})
        return {"method": "taskkill /T /F", "returncode": proc.returncode, "tree": before, "killed_pids": killed}

else:  # POSIX
    import signal

    def _foreground() -> list[Any] | None:
        return None

    def _descendants(pid: int) -> list[int]:
        children: list[int] = []
        proc = Path("/proc")
        if not proc.exists():
            return children
        table: dict[int, int] = {}
        for entry in proc.iterdir():
            if entry.name.isdigit():
                try:
                    stat = (entry / "stat").read_text().rsplit(")", 1)[1].split()
                    table[int(entry.name)] = int(stat[1])
                except (OSError, IndexError, ValueError):
                    continue
        frontier = [pid]
        while frontier:
            parent = frontier.pop()
            for child, par in table.items():
                if par == parent and child not in children:
                    children.append(child)
                    frontier.append(child)
        return children

    def _visible_windows(_pids: set[int]) -> int | None:
        return None

    def _create_time(pid: int) -> int | None:
        try:
            return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19])
        except (OSError, IndexError, ValueError):
            return None

    def _pid_alive(pid: int, create_time: int | None) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        try:
            with open(f"/proc/{pid}/stat", encoding="utf-8") as handle:
                if handle.read().rsplit(")", 1)[1].split()[0] == "Z":
                    return False
        except (OSError, IndexError):
            pass
        if create_time is not None:
            now = _create_time(pid)
            if now is not None and now != create_time:
                return False
        return True

    def _kill_tree(pid: int) -> dict[str, Any]:
        tree = [pid] + _descendants(pid)
        killed: list[int] = []
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pid, sig)
            except ProcessLookupError:
                break
            except PermissionError:
                pass
            for _ in range(20):
                if not _pid_alive(pid, None):
                    break
                time.sleep(0.1)
            if not _pid_alive(pid, None):
                killed = [p for p in tree if not _pid_alive(p, None)]
                break
        return {"method": "killpg SIGTERM/SIGKILL", "tree": tree, "killed_pids": killed}


# ----------------------------------------------------------------------------- helpers


def find_claude() -> list[str]:
    """Return the argv prefix that runs the Claude Code CLI."""
    raw = os.environ.get("CLAUDE_HEADLESS_BIN")
    if raw:
        if Path(raw).exists():
            return [raw]
        return [tok.strip('"') for tok in shlex.split(raw, posix=False)]
    found = shutil.which("claude")
    if found:
        return [found]
    for candidate in (Path.home() / ".local" / "bin" / "claude.exe", Path.home() / ".local" / "bin" / "claude"):
        if candidate.exists():
            return [str(candidate)]
    raise HeadlessError("claude CLI not found on PATH; set CLAUDE_HEADLESS_BIN to the executable")


def scrub_env(env: dict[str, str] | None = None) -> tuple[dict[str, str], list[str]]:
    """Copy ``env`` without the nested-session variables. Returns (env, removed names)."""
    source = dict(os.environ if env is None else env)
    keep = {name.strip() for name in os.environ.get("CLAUDE_HEADLESS_KEEP_ENV", "").split(",") if name.strip()}
    removed: list[str] = []
    for name in list(source):
        if name in keep:
            continue
        if name in SCRUB_EXACT or name.startswith(SCRUB_PREFIX):
            removed.append(name)
            del source[name]
    return source, sorted(removed)


def free_physical_mb() -> int | None:
    """Free physical RAM in MB, or None when it cannot be read (then no floor ever holds)."""
    try:
        if _WIN:
            import ctypes

            class _MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_uint32),
                    ("dwMemoryLoad", ctypes.c_uint32),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]

            status = _MEMORYSTATUSEX()
            status.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return None
            return int(status.ullAvailPhys // (1024 * 1024))
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
        return None
    except (OSError, ValueError, AttributeError):
        return None


class _FileLock:
    """Cross-process lock via an O_EXCL lock file; a lock older than 30 s is treated as stale."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def __enter__(self) -> "_FileLock":
        deadline = time.monotonic() + 10.0
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 30:
                        self.path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise HeadlessError(f"could not acquire {self.path}")
                time.sleep(0.02)

    def __exit__(self, *_exc: Any) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


class Journal:
    """Append-only lifecycle journal with a global integer cursor, safe across processes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = _FileLock(path.with_suffix(".lock"))
        self._condition = threading.Condition()

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                if isinstance(value, dict) and isinstance(value.get("event_id"), int):
                    events.append(value)
        return events

    @property
    def cursor(self) -> int:
        events = self._read_all()
        return events[-1]["event_id"] if events else 0

    def append(self, **fields: Any) -> dict[str, Any]:
        with self._lock:
            event = {"event_id": self.cursor + 1, "ts": _utc_now(), **fields}
            with self.path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        with self._condition:
            self._condition.notify_all()
        return event

    def after(
        self, cursor: int, *, limit: int = 100, wait_ms: int = 0, run_id: str | None = None
    ) -> list[dict[str, Any]]:
        deadline = time.monotonic() + wait_ms / 1000
        while True:
            found = [
                e
                for e in self._read_all()
                if e["event_id"] > cursor and (run_id is None or e.get("run_id") == run_id)
            ]
            if found or time.monotonic() >= deadline:
                return found[:limit]
            with self._condition:
                self._condition.wait(min(0.5, max(0.0, deadline - time.monotonic())))


# ----------------------------------------------------------------------------- runner


class Runner:
    """Start, inspect, follow up, cancel and recover headless Claude runs from on-disk records."""

    def __init__(
        self,
        root: Path | str | None = None,
        claude: list[str] | None = None,
        min_free_mb: int | None = None,
    ) -> None:
        self.root = Path(root) if root else DEFAULT_ROOT
        self.runs_dir = self.root / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.journal = Journal(self.root / "events.jsonl")
        self._claude = list(claude) if claude else None
        self._procs: dict[str, subprocess.Popen[bytes]] = {}
        self._lock = threading.RLock()
        if min_free_mb is None:
            try:
                min_free_mb = int(os.environ.get("CLAUDE_HEADLESS_MIN_FREE_MB", "0") or 0)
            except ValueError:
                min_free_mb = 0
        self.min_free_mb = max(0, int(min_free_mb))

    def memory_floor(self) -> dict[str, Any]:
        """Free physical RAM against the floor; ``holds`` is True only when a start must refuse."""
        free = free_physical_mb()
        return {
            "min_free_mb": self.min_free_mb,
            "free_physical_mb": free,
            "holds": bool(self.min_free_mb and free is not None and free < self.min_free_mb),
        }

    # -- paths -------------------------------------------------------------------------
    @property
    def claude(self) -> list[str]:
        if self._claude is None:
            self._claude = find_claude()
        return self._claude

    def run_dir(self, run_id: str) -> Path:
        if not run_id or any(ch in run_id for ch in "/\\.") or run_id.startswith("-"):
            raise HeadlessError(f"invalid run id {run_id!r}")
        return self.runs_dir / run_id

    def load(self, run_id: str) -> dict[str, Any]:
        path = self.run_dir(run_id) / "run.json"
        if not path.exists():
            raise HeadlessError(f"run not found: {run_id}")
        return _read_json(path)

    def _save(self, record: dict[str, Any]) -> None:
        record["updated_at"] = _utc_now()
        _write_json_atomic(self.run_dir(record["run_id"]) / "run.json", record)

    def _journal(self, record: dict[str, Any], status: str, **extra: Any) -> None:
        self.journal.append(
            run_id=record["run_id"],
            session_id=record["session_id"],
            status=status,
            peer=record.get("peer"),
            **extra,
        )

    # -- start / follow-up -----------------------------------------------------------------
    def start(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        resume: bool = False,
        cwd: str | Path | None = None,
        model: str | None = None,
        tools: str | list[str] | None = None,
        permission_mode: str | None = "acceptEdits",
        allowed_tools: str | list[str] | None = None,
        disallowed_tools: str | list[str] | None = None,
        strict_mcp: bool = False,
        mcp_config: str | list[str] | None = None,
        label: str | None = None,
        peer: str | None = None,
        partial: bool = False,
        extra_args: Iterable[str] = (),
        run_id: str | None = None,
        via_stdin: bool | None = None,
    ) -> dict[str, Any]:
        """Start a run.

        ``tools`` restricts the built-in tool set; it grants nothing. In print mode no
        permission prompt can be shown, so a tool that would need one is denied and the
        child reports it in the result's ``permission_denials`` (measured 2026-09-05: three
        research runs with ``tools="WebSearch,WebFetch,..."`` and no ``allowed_tools`` were
        denied every web call). ``allowed_tools`` is the pre-approval (``--allowedTools``).
        ``strict_mcp`` drops every MCP server the child would otherwise inherit from the user
        configuration (``--strict-mcp-config``); ``mcp_config`` adds explicit ones.
        """
        if not isinstance(prompt, str) or not prompt.strip():
            raise HeadlessError("prompt must be nonempty text")
        if resume and not session_id:
            raise HeadlessError("resume requires a session_id")
        session_id = session_id or str(uuid.uuid4())
        try:
            uuid.UUID(session_id)
        except ValueError as exc:
            raise HeadlessError(f"session_id must be a UUID: {session_id}") from exc
        run_id = run_id or uuid.uuid4().hex[:16]
        run_dir = self.run_dir(run_id)
        if run_dir.exists():
            raise HeadlessError(f"run id already exists: {run_id}")
        cwd_path = Path(cwd).resolve() if cwd else Path.cwd()
        if not cwd_path.is_dir():
            raise HeadlessError(f"cwd is not a directory: {cwd_path}")
        floor = self.memory_floor()
        if floor["holds"]:
            raise HeadlessError(
                f"memory floor: free physical RAM {floor['free_physical_mb']} MB is under "
                f"--min-free-mb {self.min_free_mb}; not spawning a child (each is ~500 MB commit)"
            )
        run_dir.mkdir(parents=True)

        prompt_bytes = prompt.encode("utf-8")
        (run_dir / "prompt.txt").write_bytes(prompt_bytes)
        use_stdin = bool(via_stdin) if via_stdin is not None else len(prompt_bytes) > STDIN_PROMPT_THRESHOLD

        argv = list(self.claude) + ["-p"]
        if not use_stdin:
            argv.append(prompt)
        argv += ["--output-format", "stream-json", "--verbose"]
        argv += ["--resume", session_id] if resume else ["--session-id", session_id]
        if partial:
            argv.append("--include-partial-messages")
        if model:
            argv += ["--model", model]
        if tools is not None:
            argv += ["--tools", ",".join(tools) if isinstance(tools, list) else tools]
        if permission_mode:
            argv += ["--permission-mode", permission_mode]
        if allowed_tools:
            argv += ["--allowedTools", ",".join(allowed_tools) if isinstance(allowed_tools, list) else allowed_tools]
        if disallowed_tools:
            argv += [
                "--disallowedTools",
                ",".join(disallowed_tools) if isinstance(disallowed_tools, list) else disallowed_tools,
            ]
        for item in [mcp_config] if isinstance(mcp_config, str) else (mcp_config or []):
            argv += ["--mcp-config", item]
        if strict_mcp:
            argv.append("--strict-mcp-config")
        argv += list(extra_args)

        env, removed = scrub_env()
        record: dict[str, Any] = {
            "run_id": run_id,
            "session_id": session_id,
            "resume": resume,
            "status": "queued",
            "label": label,
            "peer": peer,
            "cwd": str(cwd_path),
            "model": model,
            "tools": tools,
            "permission_mode": permission_mode,
            "allowed_tools": allowed_tools,
            "disallowed_tools": disallowed_tools,
            "strict_mcp": strict_mcp,
            "mcp_config": mcp_config,
            "partial": partial,
            "prompt_bytes": len(prompt_bytes),
            "prompt_sha256": _sha256(prompt_bytes),
            "prompt_via": "stdin" if use_stdin else "argv",
            "argv": [a if a != prompt else "<prompt>" for a in argv],
            "env_removed": removed,
            "pid": None,
            "pid_create_time": None,
            "created_at": _utc_now(),
            "started_at": None,
            "ended_at": None,
            "exit_code": None,
            "result_text": None,
            "result_subtype": None,
            "is_error": None,
            "num_turns": None,
            "cost_usd": None,
            "duration_ms": None,
            "child_model": None,
            "child_version": None,
            "event_count": 0,
            "error": None,
            "cancel_requested_at": None,
            "controller_pid": os.getpid(),
            "headless": {
                "platform": sys.platform,
                "free_physical_mb_at_spawn": floor["free_physical_mb"],
                "min_free_mb": self.min_free_mb,
                "stdin": "prompt.txt" if use_stdin else "devnull",
                "stdout": "events.jsonl",
                "stderr": "stderr.txt",
                "creationflags": (CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP) if _WIN else None,
                "start_new_session": not _WIN,
                "foreground_before": _foreground(),
                "foreground_after_spawn": None,
                "foreground_at_finalize": None,
                "foreground_unchanged": None,
                "child_visible_windows": None,
            },
        }
        self._save(record)
        self._journal(record, "queued", label=label)

        stdout = (run_dir / "events.jsonl").open("ab")
        stderr = (run_dir / "stderr.txt").open("ab")
        stdin: Any = (run_dir / "prompt.txt").open("rb") if use_stdin else subprocess.DEVNULL
        popen_kwargs: dict[str, Any] = {
            "cwd": str(cwd_path),
            "env": env,
            "stdin": stdin,
            "stdout": stdout,
            "stderr": stderr,
            "close_fds": True,
        }
        if _WIN:
            popen_kwargs["creationflags"] = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        try:
            proc = subprocess.Popen(argv, **popen_kwargs)
        except OSError as exc:
            record["status"] = "error"
            record["error"] = f"spawn failed: {exc}"
            record["ended_at"] = _utc_now()
            self._save(record)
            self._journal(record, "error", error=record["error"])
            raise HeadlessError(record["error"]) from exc
        finally:
            stdout.close()
            stderr.close()
            if use_stdin:
                stdin.close()
        record["pid"] = proc.pid
        record["pid_create_time"] = _create_time(proc.pid)
        record["started_at"] = _utc_now()
        record["status"] = "running"
        record["headless"]["foreground_after_spawn"] = _foreground()
        self._save(record)
        self._journal(record, "running", pid=proc.pid)
        with self._lock:
            self._procs[run_id] = proc
        threading.Thread(
            target=self._watch, args=(run_id, proc), name=f"claude-headless-{run_id}", daemon=True
        ).start()
        return record

    def followup(self, run_or_session_id: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Continue the exact same conversation (``claude -p --resume``) as a new run."""
        session_id = run_or_session_id
        parent: dict[str, Any] | None = None
        try:
            parent = self.load(run_or_session_id)
            session_id = parent["session_id"]
        except HeadlessError:
            pass
        if parent is None:
            for candidate in self.list_runs(session_id=session_id, limit=1):
                parent = candidate
        if parent is not None:
            for key in (
                "cwd",
                "model",
                "tools",
                "permission_mode",
                "allowed_tools",
                "disallowed_tools",
                "strict_mcp",
                "mcp_config",
                "peer",
            ):
                if kwargs.get(key) is None:
                    kwargs[key] = parent.get(key)
        return self.start(prompt, session_id=session_id, resume=True, **kwargs)

    # -- observation -------------------------------------------------------------------------
    def _watch(self, run_id: str, proc: subprocess.Popen[bytes]) -> None:
        time.sleep(1.0)
        try:
            if proc.poll() is None:
                pids = {proc.pid, *_descendants(proc.pid)}
                with self._lock:
                    record = self.load(run_id)
                    record["headless"]["child_visible_windows"] = _visible_windows(pids)
                    record["headless"]["child_pids_t_plus_1s"] = sorted(pids)
                    self._save(record)
        except HeadlessError:
            return
        proc.wait()
        try:
            self.status(run_id)
        except HeadlessError:
            pass
        with self._lock:
            self._procs.pop(run_id, None)

    def _parse_events(self, run_id: str) -> tuple[int, dict[str, Any] | None, dict[str, Any] | None]:
        """Return (line count, system init event, result event) from the child's stdout file."""
        path = self.run_dir(run_id) / "events.jsonl"
        if not path.exists():
            return 0, None, None
        count = 0
        init: dict[str, Any] | None = None
        result: dict[str, Any] | None = None
        with path.open("rb") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                count += 1
                try:
                    value = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(value, dict):
                    continue
                if value.get("type") == "system" and value.get("subtype") == "init" and init is None:
                    init = value
                elif value.get("type") == "result":
                    result = value
        return count, init, result

    def status(self, run_id: str) -> dict[str, Any]:
        """Current record, finalized from disk if the child has finished or vanished."""
        with self._lock:
            record = self.load(run_id)
            count, init, result = self._parse_events(run_id)
            changed = record.get("event_count") != count
            record["event_count"] = count
            if init is not None and record.get("child_model") is None:
                record["child_model"] = init.get("model")
                record["child_version"] = init.get("claude_code_version")
                record["child_cwd"] = init.get("cwd")
                record["child_permission_mode"] = init.get("permissionMode")
                changed = True
            if record["status"] in ACTIVE:
                proc = self._procs.get(run_id)
                exit_code = proc.poll() if proc is not None else None
                if proc is not None:
                    alive = exit_code is None
                else:
                    alive = record.get("pid") is not None and _pid_alive(
                        int(record["pid"]), record.get("pid_create_time")
                    )
                if result is not None:
                    record["result_text"] = result.get("result")
                    record["result_subtype"] = result.get("subtype")
                    record["is_error"] = bool(result.get("is_error"))
                    record["num_turns"] = result.get("num_turns")
                    record["cost_usd"] = result.get("total_cost_usd")
                    record["duration_ms"] = result.get("duration_ms")
                    changed = True
                    if not alive:
                        if record["is_error"] or result.get("subtype") != "success":
                            record["status"] = "error"
                            record["error"] = result.get("subtype") or "result reported is_error"
                        else:
                            record["status"] = "completed"
                elif not alive:
                    record["status"] = "cancelled" if record.get("cancel_requested_at") else "interrupted"
                    if record["status"] == "interrupted":
                        record["error"] = "child exited or vanished without a result event"
                if record["status"] in TERMINAL:
                    record["exit_code"] = exit_code
                    record["ended_at"] = _utc_now()
                    head = record["headless"]
                    head["foreground_at_finalize"] = _foreground()
                    if head.get("foreground_before") is not None:
                        after_spawn = head.get("foreground_after_spawn") or head["foreground_before"]
                        head["foreground_unchanged"] = (
                            head["foreground_before"][0] == after_spawn[0] == head["foreground_at_finalize"][0]
                        )
                    self._save(record)
                    self._journal(
                        record,
                        record["status"],
                        exit_code=exit_code,
                        result_bytes=len((record.get("result_text") or "").encode("utf-8")),
                        error=record.get("error"),
                    )
                    return record
            if changed:
                self._save(record)
            return record

    def wait(self, run_id: str, timeout: float | None = None, poll: float = 0.25) -> dict[str, Any]:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            record = self.status(run_id)
            if record["status"] in TERMINAL:
                return record
            if deadline is not None and time.monotonic() >= deadline:
                return record
            proc = self._procs.get(run_id)
            if proc is not None:
                try:
                    proc.wait(timeout=poll)
                except subprocess.TimeoutExpired:
                    pass
            else:
                time.sleep(poll)

    def events(
        self, run_id: str, after: int = 0, limit: int = 200, wait_ms: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        """Raw stream-json lines after cursor ``after`` (1-based line index) with the next cursor."""
        path = self.run_dir(run_id) / "events.jsonl"
        if not (self.run_dir(run_id) / "run.json").exists():
            raise HeadlessError(f"run not found: {run_id}")
        deadline = time.monotonic() + max(0, wait_ms) / 1000
        while True:
            found: list[dict[str, Any]] = []
            seq = 0
            if path.exists():
                with path.open("rb") as handle:
                    for raw in handle:
                        if not raw.strip():
                            continue
                        seq += 1
                        if seq <= after:
                            continue
                        try:
                            value = json.loads(raw)
                        except ValueError:
                            value = {"type": "unparsed", "raw": raw.decode("utf-8", "replace")}
                        found.append({"seq": seq, "event": value})
                        if len(found) >= limit:
                            break
            if found or time.monotonic() >= deadline:
                next_cursor = found[-1]["seq"] if found else after
                return found, next_cursor
            time.sleep(0.2)

    def list_runs(
        self, limit: int = 100, session_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in self.runs_dir.glob("*/run.json"):
            try:
                record = _read_json(path)
            except (OSError, ValueError):
                continue
            if session_id and record.get("session_id") != session_id:
                continue
            if status and record.get("status") != status:
                continue
            records.append(record)
        records.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return records[:limit]

    def session(self, session_id: str) -> dict[str, Any]:
        runs = [self.status(r["run_id"]) for r in self.list_runs(session_id=session_id, limit=1000)]
        projects = Path.home() / ".claude" / "projects"
        transcripts = [str(p) for p in projects.glob(f"*/{session_id}.jsonl")] if projects.exists() else []
        latest = runs[0] if runs else None
        return {
            "session_id": session_id,
            "runs": runs,
            "run_count": len(runs),
            "latest_run_id": latest and latest["run_id"],
            "latest_status": latest and latest["status"],
            "resumable": bool(transcripts) or bool(runs),
            "transcripts": transcripts,
        }

    # -- control ------------------------------------------------------------------------------
    def cancel(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            record = self.status(run_id)
            if record["status"] in TERMINAL:
                return {
                    "ok": False,
                    "run_id": run_id,
                    "session_id": record["session_id"],
                    "status": record["status"],
                    "reason": "already terminal",
                }
            record["cancel_requested_at"] = _utc_now()
            self._save(record)
            outcome = _kill_tree(int(record["pid"]))
        proc = self._procs.get(run_id)
        if proc is not None:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        else:
            for _ in range(50):
                if not _pid_alive(int(record["pid"]), record.get("pid_create_time")):
                    break
                time.sleep(0.1)
        record = self.status(run_id)
        return {
            "ok": record["status"] == "cancelled",
            "run_id": run_id,
            "session_id": record["session_id"],
            "status": record["status"],
            **outcome,
        }

    def recover(self) -> list[dict[str, Any]]:
        """Finalize every run whose child is gone: completed from bytes on disk, else interrupted.

        Returns only the runs this call finalized. Runs whose child is still alive are left
        running and are not reported here; see :meth:`active`.
        """
        finalized: list[dict[str, Any]] = []
        for record in self.list_runs(limit=100000):
            if record["status"] in ACTIVE:
                fresh = self.status(record["run_id"])
                if fresh["status"] in TERMINAL:
                    finalized.append(
                        {
                            "run_id": fresh["run_id"],
                            "session_id": fresh["session_id"],
                            "status": fresh["status"],
                            "pid": fresh.get("pid"),
                            "exit_code": fresh.get("exit_code"),
                            "error": fresh.get("error"),
                        }
                    )
        return finalized

    def active(self) -> list[dict[str, Any]]:
        """Runs whose child is still alive right now (re-checked against the process table)."""
        alive: list[dict[str, Any]] = []
        for record in self.list_runs(limit=100000):
            if record["status"] in ACTIVE:
                fresh = self.status(record["run_id"])
                if fresh["status"] in ACTIVE:
                    alive.append(
                        {
                            "run_id": fresh["run_id"],
                            "session_id": fresh["session_id"],
                            "status": fresh["status"],
                            "pid": fresh.get("pid"),
                            "started_at": fresh.get("started_at"),
                            "event_count": fresh.get("event_count"),
                            "label": fresh.get("label"),
                            "peer": fresh.get("peer"),
                        }
                    )
        return alive

    def doctor(self) -> dict[str, Any]:
        version: str
        try:
            kwargs: dict[str, Any] = {"creationflags": CREATE_NO_WINDOW} if _WIN else {}
            out = subprocess.run(
                list(self.claude) + ["--version"],
                capture_output=True,
                text=True,
                timeout=60,
                env=scrub_env()[0],
                **kwargs,
            )
            version = (out.stdout or out.stderr).strip()
        except (OSError, subprocess.SubprocessError) as exc:
            version = f"unavailable: {exc}"
        return {
            "claude": self.claude,
            "claude_version": version,
            "root": str(self.root),
            "runs": len(list(self.runs_dir.glob("*/run.json"))),
            "active": [r["run_id"] for r in self.list_runs(limit=100000) if r["status"] in ACTIVE],
            "event_cursor": self.journal.cursor,
            "env_scrub": {
                "exact": sorted(SCRUB_EXACT),
                "prefix": list(SCRUB_PREFIX),
                "keep": os.environ.get("CLAUDE_HEADLESS_KEEP_ENV", ""),
            },
            "memory_floor": self.memory_floor(),
            "platform": sys.platform,
        }


# ----------------------------------------------------------------------------- CLI


def _print(value: Any) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    sys.stdout.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Headless Claude control from on-disk run records.")
    parser.add_argument("--root", type=Path, default=None, help=f"runs root (default {DEFAULT_ROOT})")
    parser.add_argument(
        "--min-free-mb",
        type=int,
        default=None,
        help="refuse to spawn a child while free physical RAM is under this many MB "
        "(default 0 = off; CLAUDE_HEADLESS_MIN_FREE_MB; 1024 is what the gateway uses)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def run_opts(p: argparse.ArgumentParser) -> None:
        p.add_argument("--cwd")
        p.add_argument("--model")
        p.add_argument("--tools", help='comma list; "" disables all tools')
        p.add_argument("--permission-mode", default=None, help="claude permission mode (default acceptEdits)")
        p.add_argument(
            "--allowed-tools",
            help="comma list pre-approved without a prompt (--allowedTools); print mode cannot prompt",
        )
        p.add_argument("--disallowed-tools", help="comma list denied outright (--disallowedTools)")
        p.add_argument("--strict-mcp", action="store_true", help="child gets no inherited MCP servers")
        p.add_argument("--mcp-config", action="append", help="MCP config file/JSON for the child (repeatable)")
        p.add_argument("--label")
        p.add_argument("--peer")
        p.add_argument("--partial", action="store_true", help="include partial message deltas in events")
        p.add_argument("--wait", type=float, default=None, help="seconds to wait for the result before returning")
        p.add_argument("--stdin-prompt", action="store_true", help="feed the prompt through stdin instead of argv")

    p_start = sub.add_parser("start", help="start a new conversation")
    p_start.add_argument("prompt")
    p_start.add_argument("--session-id")
    run_opts(p_start)
    p_follow = sub.add_parser("followup", help="continue the same conversation")
    p_follow.add_argument("target", help="run id or session id")
    p_follow.add_argument("prompt")
    run_opts(p_follow)
    for name, help_ in (("status", "show a run"), ("wait", "wait for a run"), ("cancel", "kill that run's process tree")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("run_id")
        if name == "wait":
            p.add_argument("--timeout", type=float, default=None)
    p_events = sub.add_parser("events", help="raw stream-json events after a cursor")
    p_events.add_argument("run_id")
    p_events.add_argument("--after", type=int, default=0)
    p_events.add_argument("--limit", type=int, default=200)
    p_events.add_argument("--wait-ms", type=int, default=0)
    p_list = sub.add_parser("list", help="list runs")
    p_list.add_argument("--session-id")
    p_list.add_argument("--status")
    p_list.add_argument("--limit", type=int, default=50)
    p_sess = sub.add_parser("session", help="runs and transcript for a session")
    p_sess.add_argument("session_id")
    sub.add_parser("recover", help="finalize runs whose controller died")
    sub.add_parser("doctor", help="show the CLI, version, root and env scrub")
    p_journal = sub.add_parser("journal", help="lifecycle events after a cursor")
    p_journal.add_argument("--after", type=int, default=0)
    p_journal.add_argument("--limit", type=int, default=100)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runner = Runner(args.root, min_free_mb=args.min_free_mb)
    try:
        if args.command in ("start", "followup"):
            kwargs: dict[str, Any] = {
                "cwd": args.cwd,
                "model": args.model,
                "tools": args.tools,
                "label": args.label,
                "peer": args.peer,
                "partial": args.partial,
                "via_stdin": True if args.stdin_prompt else None,
            }
            if args.permission_mode is not None:
                kwargs["permission_mode"] = args.permission_mode
            if args.allowed_tools:
                kwargs["allowed_tools"] = args.allowed_tools
            if args.disallowed_tools:
                kwargs["disallowed_tools"] = args.disallowed_tools
            if args.strict_mcp:
                kwargs["strict_mcp"] = True
            if args.mcp_config:
                kwargs["mcp_config"] = list(args.mcp_config)
            if args.command == "start":
                record = runner.start(args.prompt, session_id=args.session_id, **kwargs)
            else:
                record = runner.followup(args.target, args.prompt, **kwargs)
            if args.wait is not None:
                record = runner.wait(record["run_id"], timeout=args.wait)
            _print(record)
        elif args.command == "status":
            _print(runner.status(args.run_id))
        elif args.command == "wait":
            _print(runner.wait(args.run_id, timeout=args.timeout))
        elif args.command == "cancel":
            _print(runner.cancel(args.run_id))
        elif args.command == "events":
            events, cursor = runner.events(args.run_id, after=args.after, limit=args.limit, wait_ms=args.wait_ms)
            _print({"run_id": args.run_id, "events": events, "next_cursor": cursor})
        elif args.command == "list":
            keys = ("run_id", "session_id", "status", "label", "peer", "created_at", "ended_at", "pid")
            _print(
                [
                    {k: r.get(k) for k in keys}
                    for r in runner.list_runs(limit=args.limit, session_id=args.session_id, status=args.status)
                ]
            )
        elif args.command == "session":
            _print(runner.session(args.session_id))
        elif args.command == "recover":
            _print(runner.recover())
        elif args.command == "doctor":
            _print(runner.doctor())
        elif args.command == "journal":
            _print(runner.journal.after(args.after, limit=args.limit))
    except HeadlessError as exc:
        _print({"ok": False, "error": str(exc)})
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
