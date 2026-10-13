#!/usr/bin/env python3
"""Headless Claude control gateway for Commons peers (build demand C1).

Wraps the installed, already-authenticated Claude Code CLI in print mode so a
Commons harness on this machine can start a run, watch its stream-json events,
send a follow-up into the exact same conversation, cancel that specific run,
and recover the conversation after a gateway restart.

Reused roads, nothing reminted:
  * ``claude -p --output-format stream-json --verbose`` with ``--session-id``
    for a new conversation and ``--resume`` for a follow-up. The CLI persists
    every conversation under ``~/.claude/projects/<cwd-key>/<session>.jsonl``
    so a session id is durable on disk, independent of this process.
  * ``/health`` + async request/events-cursor shape from
    ``integrations/gemini_slack/peer_tool_gateway.py`` so G2/M3 builders can
    share one calling convention. ``POST /v1/message`` is accepted as an alias.
  * State directory convention from ``integrations/grok_slack``
    (``~/.commons/...``).

Runs outlive the gateway. The child's stdin/stdout/stderr are files under
``runs/<run_id>/`` (prompt.txt, events.jsonl, stderr.txt), not pipes, so a
gateway death mid-run loses nothing: on the next start the gateway adopts a
child that is still alive and finalizes a finished one from the bytes on
disk. Measured by TENON on 2026-09-04 (child finished after its spawner
exited); the ``allow_reuse_address`` fix below is TENON's as well.

Loopback only. Stdlib only. The child process is created with no console
window and the parent's ``CLAUDECODE`` / ``CLAUDE_CODE_*`` session markers
removed so the CLI does not treat the run as nested. Existing Max OAuth on
this PC is used as-is; no secret is minted or stored. Any caller on loopback
may submit; ``peer`` / ``from`` and ``label`` are optional attribution only.
"""

from __future__ import annotations

import argparse
import atexit
import base64
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

SERVICE = "commons-claude-headless-gateway"
CONTRACT = "tenon-c1-as-built-20260904-2043 + gemini-shaped aliases"
DEFAULT_PORT = 8879
DEFAULT_STATE_DIR = Path.home() / ".commons" / "claude_headless"
# The owner PC is a 7.24 GB laptop with a DRAM-less NVMe; every CLI child is a few hundred MB.
# 2026-09-04 22:59 EDT it bugchecked 0x154 (memory-compression store paging) with 17 Claude
# windows and 9 ChatGPT processes resident. One child at a time, and none while RAM is short.
DEFAULT_MAX_CONCURRENT = 1
DEFAULT_MIN_FREE_MB = 1024
TERMINAL = frozenset({"completed", "error", "cancelled", "interrupted"})
ACTIVE = frozenset({"starting", "running"})
IS_WINDOWS = os.name == "nt"
SCRUB_EXACT = ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_AGENT_SDK_VERSION", "CLAUDE_PREVIEW_CLASSIFIER_FLOOR")
SCRUB_PREFIX = ("CLAUDE_CODE_",)
KEEP_ENV_VAR = "CLAUDE_HEADLESS_KEEP_ENV"
TASKKILL_PID = re.compile(r"process with PID (\d+)")
CLI_OPTIONS = (
    # request field, CLI flag, kind
    ("model", "--model", "str"),
    ("max_turns", "--max-turns", "int"),
    ("permission_mode", "--permission-mode", "str"),
    ("effort", "--effort", "str"),
    ("append_system_prompt", "--append-system-prompt", "str"),
    ("agent", "--agent", "str"),
    ("allowed_tools", "--allowedTools", "list"),
    ("disallowed_tools", "--disallowedTools", "list"),
    ("add_dirs", "--add-dir", "list"),
    ("mcp_config", "--mcp-config", "list"),
    ("strict_mcp_config", "--strict-mcp-config", "flag"),
    ("fork_session", "--fork-session", "flag"),
    ("partial", "--include-partial-messages", "flag"),
    ("bare", "--bare", "flag"),
)
FIELD_ALIASES = {"tools": "allowed_tools"}
ORPHANED_CHILDREN: list[Any] = []
atexit.register(lambda: [proc.poll() for proc in ORPHANED_CHILDREN])


class GatewayError(RuntimeError):
    pass


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cwd_key(cwd: str) -> str:
    """The folder name Claude Code uses for a working directory's sessions."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def transcript_path(cwd: str, session_id: str, home: Path | None = None) -> Path:
    base = (home or Path.home()) / ".claude" / "projects" / cwd_key(cwd)
    return base / f"{session_id}.jsonl"


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if IS_WINDOWS:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    # A child that has exited but not been reaped is a zombie: os.kill still
    # succeeds, yet the process is gone. Linux says so in /proc; elsewhere a
    # non-blocking waitpid answers when the zombie is ours. Measured on the
    # Ubuntu battery runner on 2026-09-05 (adopted runs never finalized).
    try:
        with open(f"/proc/{int(pid)}/stat", "r", encoding="ascii", errors="replace") as handle:
            state = handle.read().rsplit(")", 1)[1].split()[0]
        return state not in ("Z", "X")
    except OSError:
        pass
    try:
        reaped, _status = os.waitpid(int(pid), os.WNOHANG)
        return reaped == 0
    except ChildProcessError:
        return True
    except OSError:
        return True


def kill_tree(pid: int) -> dict[str, Any]:
    """Stop one run's process tree. Returns what was attempted and observed."""
    if IS_WINDOWS:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            creationflags=flags,
            check=False,
        )
        killed = [int(m) for m in TASKKILL_PID.findall(proc.stdout or "")]
        return {
            "method": "taskkill /T /F",
            "exit_code": proc.returncode,
            "killed_pids": killed,
            "tree": killed,
            "stdout": (proc.stdout or "")[-600:],
            "stderr": (proc.stderr or "")[-400:],
        }
    import signal

    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        method = "killpg SIGTERM"
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
            method = "kill SIGTERM"
        except OSError as exc:
            return {"method": "kill", "error": str(exc), "killed_pids": [], "tree": []}
    return {"method": method, "killed_pids": [pid], "tree": [pid]}


def scrub_names(env: dict[str, str], keep: set[str] | None = None) -> list[str]:
    keep = keep or set()
    out = []
    for name in env:
        if name in keep:
            continue
        if name in SCRUB_EXACT or name.startswith(SCRUB_PREFIX):
            out.append(name)
    return sorted(out)


def headless_env(base: dict[str, str] | None = None, run_id: str = "") -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    keep = {item.strip() for item in env.get(KEEP_ENV_VAR, "").split(",") if item.strip()}
    for name in scrub_names(env, keep):
        env.pop(name, None)
    if run_id:
        env["CLAUDE_HEADLESS_RUN_ID"] = run_id
    return env


def free_physical_mb() -> int | None:
    """Free physical RAM in MB, or None when the platform does not say."""
    if IS_WINDOWS:
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
            return None
        return int(status.ullAvailPhys // (1024 * 1024))
    try:
        with open("/proc/meminfo", "r", encoding="ascii", errors="replace") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        return None
    return None


def build_popen_kwargs(cwd: str, env: dict[str, str], stdin: Any, stdout: Any, stderr: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"cwd": cwd, "env": env, "stdin": stdin, "stdout": stdout, "stderr": stderr}
    if IS_WINDOWS:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
        )
    else:
        kwargs["start_new_session"] = True
    return kwargs


def validate_owner_configuration(options: dict[str, Any]) -> None:
    """Keep caller options from skipping the owner's native Claude configuration."""
    if options.get("bare") not in (None, "", False, []):
        raise ValueError("bare mode skips owner-configured hooks and memory; run not started")
    # This field is not forwarded. Reject an explicit opt-out instead of silently
    # accepting it; the ordinary CLI user/project/local discovery stays in place.
    if "setting_sources" in options and options["setting_sources"] is not None:
        sources = options["setting_sources"]
        if not isinstance(sources, str) or "user" not in {
            source.strip() for source in sources.split(",")
        }:
            raise ValueError("setting_sources must retain user configuration; run not started")
    for field, _flag, kind in CLI_OPTIONS:
        if kind != "list":
            continue
        value = options.get(field)
        values = value if isinstance(value, list) else [value]
        # Variadic values become individual argv tokens. A leading dash could
        # otherwise turn a tool/path/config value into another CLI option.
        if any(isinstance(item, str) and item.startswith("-") for item in values):
            raise ValueError(
                f"{field} values must not be CLI option tokens; use an explicit path prefix for a dash-prefixed filename"
            )


def build_command(claude_cmd: list[str], run: dict[str, Any]) -> list[str]:
    cmd = list(claude_cmd) + ["-p", "--output-format", "stream-json", "--verbose"]
    if run.get("kind") == "followup":
        cmd += ["--resume", run["session_id"]]
    else:
        cmd += ["--session-id", run["session_id"]]
    options = run.get("options") or {}
    validate_owner_configuration(options)
    for field, flag, kind in CLI_OPTIONS:
        value = options.get(field)
        if value in (None, "", False, []):
            continue
        if kind == "flag":
            cmd.append(flag)
        elif kind == "list":
            values = value if isinstance(value, list) else [value]
            cmd += [flag] + [str(item) for item in values]
        elif kind == "int":
            cmd += [flag, str(int(value))]
        else:
            cmd += [flag, str(value)]
    return cmd


def parse_events_file(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Every complete JSON line of a run's stdout file, and its result line if any."""
    events: list[dict[str, Any]] = []
    result = None
    try:
        raw = path.read_bytes()
    except OSError:
        return events, None
    for line in raw.splitlines():
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except ValueError:
            continue
        if isinstance(obj, dict):
            events.append(obj)
            if obj.get("type") == "result":
                result = obj
    return events, result


class RunStore:
    """SQLite journal of runs and their events. One global event cursor."""

    COLUMNS = (
        "run_id", "session_id", "parent_run_id", "kind", "label", "submitted_by", "cwd", "prompt",
        "prompt_sha256", "prompt_bytes", "options_json", "status", "pid", "exit_code", "created_at",
        "started_at", "ended_at", "result_text", "result_json", "error", "note", "stderr_tail",
        "command_json", "event_count", "cancel_requested", "seq",
    )

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._cond = threading.Condition(threading.RLock())
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._db:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS runs(
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    parent_run_id TEXT,
                    kind TEXT NOT NULL,
                    label TEXT,
                    submitted_by TEXT,
                    cwd TEXT NOT NULL,
                    prompt TEXT,
                    prompt_sha256 TEXT NOT NULL,
                    prompt_bytes INTEGER NOT NULL,
                    options_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    pid INTEGER,
                    exit_code INTEGER,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    ended_at TEXT,
                    result_text TEXT,
                    result_json TEXT,
                    error TEXT,
                    note TEXT,
                    stderr_tail TEXT,
                    command_json TEXT,
                    event_count INTEGER NOT NULL DEFAULT 0,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    seq INTEGER NOT NULL
                )
                """
            )
            self._db.execute(
                """
                CREATE TABLE IF NOT EXISTS events(
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT,
                    payload TEXT
                )
                """
            )
            self._db.execute("CREATE INDEX IF NOT EXISTS events_run ON events(run_id, event_id)")
            self._db.execute("CREATE INDEX IF NOT EXISTS runs_session ON runs(session_id, seq)")
            have = {row[1] for row in self._db.execute("PRAGMA table_info(runs)").fetchall()}
            for column in ("note", "child_model"):  # journals written before these columns existed
                if column not in have:
                    self._db.execute(f"ALTER TABLE runs ADD COLUMN {column} TEXT")

    def close(self) -> None:
        with self._cond:
            self._db.close()

    @staticmethod
    def _row_to_run(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        run = dict(row)
        run["options"] = json.loads(run.pop("options_json") or "{}")
        run["command"] = json.loads(run.pop("command_json") or "null")
        raw = run.pop("result_json")
        run["result"] = json.loads(raw) if raw else None
        run["cancel_requested"] = bool(run["cancel_requested"])
        return run

    def insert_run(self, run: dict[str, Any]) -> dict[str, Any]:
        with self._cond, self._db:
            seq = self._db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM runs").fetchone()[0]
            self._db.execute(
                """
                INSERT INTO runs(run_id, session_id, parent_run_id, kind, label, submitted_by, cwd,
                    prompt, prompt_sha256, prompt_bytes, options_json, status, pid, created_at, seq)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    run["run_id"],
                    run["session_id"],
                    run.get("parent_run_id"),
                    run["kind"],
                    run.get("label"),
                    run.get("submitted_by"),
                    run["cwd"],
                    run.get("prompt"),
                    run["prompt_sha256"],
                    run["prompt_bytes"],
                    json.dumps(run.get("options") or {}, ensure_ascii=False, sort_keys=True),
                    run["status"],
                    run.get("pid"),
                    run["created_at"],
                    seq,
                ),
            )
            self._cond.notify_all()
        stored = self.get_run(run["run_id"])
        assert stored is not None
        return stored

    def update_run(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return
        if "result" in fields:
            fields["result_json"] = json.dumps(fields.pop("result"), ensure_ascii=False)
        if "command" in fields:
            fields["command_json"] = json.dumps(fields.pop("command"), ensure_ascii=False)
        cols = ", ".join(f"{name}=?" for name in fields)
        with self._cond, self._db:
            self._db.execute(f"UPDATE runs SET {cols} WHERE run_id=?", (*fields.values(), run_id))
            self._cond.notify_all()

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._cond:
            row = self._db.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return self._row_to_run(row)

    def list_runs(
        self,
        *,
        status: str | None = None,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status=?")
            params.append(status)
        if session_id:
            clauses.append("session_id=?")
            params.append(session_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._cond:
            rows = self._db.execute(
                f"SELECT * FROM runs {where} ORDER BY seq DESC LIMIT ?", (*params, int(limit))
            ).fetchall()
        out = []
        for row in rows:
            run = self._row_to_run(row)
            if run is not None:
                out.append(run)
        return out

    def counts(self) -> dict[str, int]:
        with self._cond:
            rows = self._db.execute("SELECT status, COUNT(*) FROM runs GROUP BY status").fetchall()
        return {row[0]: row[1] for row in rows}

    def wait_run(self, run_id: str, wait_ms: int) -> dict[str, Any] | None:
        deadline = time.monotonic() + wait_ms / 1000
        with self._cond:
            while True:
                run = self.get_run(run_id)
                if run is None or run["status"] in TERMINAL or wait_ms <= 0:
                    return run
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return run
                self._cond.wait(remaining)

    def append_event(
        self,
        run_id: str,
        session_id: str,
        kind: str,
        *,
        status: str | None = None,
        payload: Any = None,
    ) -> dict[str, Any]:
        encoded = None if payload is None else json.dumps(payload, ensure_ascii=False)
        with self._cond, self._db:
            cursor = self._db.execute(
                "INSERT INTO events(ts, run_id, session_id, kind, status, payload) VALUES(?,?,?,?,?,?)",
                (utc_now(), run_id, session_id, kind, status, encoded),
            )
            self._db.execute("UPDATE runs SET event_count=event_count+1 WHERE run_id=?", (run_id,))
            event_id = int(cursor.lastrowid or 0)
            self._cond.notify_all()
        return {
            "event_id": event_id,
            "seq": event_id,
            "run_id": run_id,
            "session_id": session_id,
            "kind": kind,
            "status": status,
            "payload": payload,
            "event": payload,
        }

    @property
    def cursor(self) -> int:
        with self._cond:
            row = self._db.execute("SELECT COALESCE(MAX(event_id),0) FROM events").fetchone()
        return int(row[0])

    def events_after(
        self,
        cursor: int,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
        wait_ms: int = 0,
    ) -> list[dict[str, Any]]:
        deadline = time.monotonic() + wait_ms / 1000
        with self._cond:
            while True:
                clauses, params = ["event_id>?"], [int(cursor)]
                if run_id:
                    clauses.append("run_id=?")
                    params.append(run_id)
                if session_id:
                    clauses.append("session_id=?")
                    params.append(session_id)
                rows = self._db.execute(
                    f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY event_id LIMIT ?",
                    (*params, int(limit)),
                ).fetchall()
                if rows or wait_ms <= 0:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(remaining)
        out = []
        for row in rows:
            item = dict(row)
            raw = item.pop("payload")
            item["payload"] = json.loads(raw) if raw else None
            item["event"] = item["payload"]
            item["seq"] = item["event_id"]
            out.append(item)
        return out


class Gateway(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows the http.server default (1) lets a second process bind a port that is
    # already listening; TENON measured that on 2026-09-04. Keep reuse for POSIX only.
    allow_reuse_address = os.name != "nt"

    def __init__(
        self,
        address: tuple[str, int],
        *,
        state_dir: Path,
        claude_cmd: list[str] | None = None,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        popen: Callable[..., Any] = subprocess.Popen,
        env_base: dict[str, str] | None = None,
        min_free_mb: int = DEFAULT_MIN_FREE_MB,
        free_mb_fn: Callable[[], int | None] | None = None,
    ) -> None:
        super().__init__(address, Handler)
        self.min_free_mb = max(0, int(min_free_mb))
        self._free_mb_fn = free_mb_fn or free_physical_mb
        self._held: set[str] = set()
        self.state_dir = Path(state_dir)
        self.runs_dir = self.state_dir / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.store = RunStore(self.state_dir / "gateway.sqlite3")
        self.claude_cmd = claude_cmd or self.default_claude_cmd()
        self.max_concurrent = max(1, int(max_concurrent))
        self._popen = popen
        self._env_base = env_base
        self._mutex = threading.RLock()
        self._procs: dict[str, Any] = {}
        self._adopted: dict[str, int] = {}
        self._active_sessions: set[str] = set()
        self._pending_prompts: dict[str, str] = {}
        self._dispatch_wake = threading.Event()
        self._closing = False
        self.started_at = utc_now()
        base_env = dict(os.environ if env_base is None else env_base)
        keep = {item.strip() for item in base_env.get(KEEP_ENV_VAR, "").split(",") if item.strip()}
        self.env_scrub = scrub_names(base_env, keep)
        self.cli = self.probe_cli()
        self.recovery = self.reconcile()
        self._dispatch_thread = threading.Thread(
            target=self._dispatcher, name="claude-headless-dispatch", daemon=True
        )
        self._dispatch_thread.start()

    # ---- paths ---------------------------------------------------------
    def run_dir(self, run_id: str) -> Path:
        return self.runs_dir / run_id

    def run_files(self, run_id: str) -> dict[str, Path]:
        base = self.run_dir(run_id)
        return {
            "dir": base,
            "prompt": base / "prompt.txt",
            "events": base / "events.jsonl",
            "stderr": base / "stderr.txt",
        }

    # ---- CLI -----------------------------------------------------------
    @staticmethod
    def default_claude_cmd() -> list[str]:
        found = shutil.which("claude")
        return [found] if found else ["claude"]

    def probe_cli(self) -> dict[str, Any]:
        info: dict[str, Any] = {"command": self.claude_cmd, "ok": False, "version": None}
        try:
            kwargs: dict[str, Any] = {"capture_output": True, "text": True, "timeout": 30}
            if IS_WINDOWS:
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.run(
                list(self.claude_cmd) + ["--version"], env=headless_env(self._env_base), **kwargs
            )
            info["version"] = (proc.stdout or proc.stderr).strip()[:200]
            info["ok"] = proc.returncode == 0
        except (OSError, subprocess.SubprocessError) as exc:
            info["error"] = f"{type(exc).__name__}: {exc}"
        return info

    # ---- recovery ------------------------------------------------------
    def reconcile(self) -> dict[str, Any]:
        """Reconcile journal rows this process does not own: adopt live children,
        finalize finished ones from their stdout file, mark the rest interrupted."""
        report: dict[str, list[str]] = {
            "finalized_from_disk": [],
            "still_alive": [],
            "interrupted": [],
            "requeued": [],
        }
        for run in self.store.list_runs(limit=10_000):
            run_id, session_id = run["run_id"], run["session_id"]
            with self._mutex:
                owned = run_id in self._procs or run_id in self._adopted
            if owned:
                continue
            if run["status"] in ACTIVE:
                files = self.run_files(run_id)
                if pid_alive(run.get("pid")):
                    self._adopt(run)
                    report["still_alive"].append(run_id)
                    continue
                events, result = parse_events_file(files["events"])
                if result is not None:
                    self._replay_events(run, events)
                    self._finalize_from_result(
                        run_id,
                        session_id,
                        result,
                        exit_code=None,
                        stderr_tail=self._stderr_tail(files["stderr"]),
                        note="finalized from events.jsonl on disk after a gateway restart; exit code unknown",
                    )
                    report["finalized_from_disk"].append(run_id)
                else:
                    self.store.update_run(
                        run_id,
                        status="interrupted",
                        ended_at=utc_now(),
                        error=(
                            "child process is gone and its events.jsonl has no result line. "
                            "The conversation transcript stays on disk under the session id; follow up to continue."
                        ),
                    )
                    self.store.append_event(
                        run_id, session_id, "gateway", status="interrupted",
                        payload={"pid": run.get("pid"), "events_on_disk": len(events)},
                    )
                    report["interrupted"].append(run_id)
            elif run["status"] == "queued":
                report["requeued"].append(run_id)
        self._dispatch_wake.set()
        return report

    def _adopt(self, run: dict[str, Any]) -> None:
        run_id, session_id, pid = run["run_id"], run["session_id"], int(run["pid"])
        with self._mutex:
            self._adopted[run_id] = pid
            self._active_sessions.add(session_id)
        self.store.update_run(run_id, note=f"adopted by gateway started {self.started_at}; child pid {pid} was still alive")
        self.store.append_event(run_id, session_id, "gateway", status="adopted", payload={"pid": pid})
        files = self.run_files(run_id)
        threading.Thread(
            target=self._tail,
            args=(run_id, session_id, files, None, pid, True),
            name=f"claude-adopt-{run_id[:8]}",
            daemon=True,
        ).start()

    def _replay_events(self, run: dict[str, Any], events: list[dict[str, Any]]) -> None:
        """Journal the CLI lines a dead gateway never read (idempotent by count)."""
        already = self.store.events_after(0, run_id=run["run_id"], limit=100_000)
        seen = sum(1 for item in already if item["kind"] not in ("gateway", "cli-text"))
        for obj in events[seen:]:
            self.store.append_event(run["run_id"], run["session_id"], str(obj.get("type") or "cli"), payload=obj)

    # ---- submission ----------------------------------------------------
    def submit(self, payload: dict[str, Any], *, parent_run_id: str | None = None) -> dict[str, Any]:
        prompt = payload.get("prompt")
        if isinstance(payload.get("prompt_utf8_base64"), str):
            prompt = base64.b64decode(payload["prompt_utf8_base64"], validate=True).decode("utf-8")
        if isinstance(payload.get("message_utf8_base64"), str):
            prompt = base64.b64decode(payload["message_utf8_base64"], validate=True).decode("utf-8")
        if prompt is None:
            prompt = payload.get("message")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be nonempty UTF-8 text")
        options: dict[str, Any] = {}
        for field, _flag, _kind in CLI_OPTIONS:
            if field in payload:
                options[field] = payload[field]
        for alias, field in FIELD_ALIASES.items():
            if alias in payload and field not in options:
                options[field] = payload[alias]
        validate_owner_configuration({**payload, **options})
        cwd = str(payload.get("cwd") or os.getcwd())
        session_id = payload.get("session_id")
        kind = "new"
        parent = self.store.get_run(parent_run_id) if parent_run_id else None
        if parent_run_id and parent is None:
            raise ValueError("parent run not found")
        if parent:
            session_id = parent["session_id"]
            kind = "followup"
            cwd = str(payload.get("cwd") or parent["cwd"])
        elif session_id:
            if not self._is_uuid(session_id):
                raise ValueError("session_id must be a UUID")
            kind = "followup"
            prior = self.store.list_runs(session_id=session_id, limit=1)
            if prior and not payload.get("cwd"):
                # continue where that conversation actually lives, not where this gateway sits
                cwd = prior[0]["cwd"]
        else:
            session_id = str(uuid.uuid4())
        if not os.path.isdir(cwd):
            raise ValueError(f"cwd does not exist: {cwd}")
        run_id = uuid.uuid4().hex
        retain = payload.get("retain_prompt", True)
        submitted_by = str(payload.get("peer") or payload.get("from") or "")[:64] or None
        run = {
            "run_id": run_id,
            "session_id": session_id,
            "parent_run_id": parent_run_id,
            "kind": kind,
            "label": (str(payload.get("label"))[:200] if payload.get("label") else None),
            "submitted_by": submitted_by,
            "cwd": cwd,
            "prompt": prompt if retain else None,
            "prompt_sha256": sha256_text(prompt),
            "prompt_bytes": len(prompt.encode("utf-8")),
            "options": options,
            "status": "queued",
            "created_at": utc_now(),
        }
        files = self.run_files(run_id)
        files["dir"].mkdir(parents=True, exist_ok=True)
        files["prompt"].write_text(prompt, encoding="utf-8")
        stored = self.store.insert_run(run)
        self.store.append_event(run_id, session_id, "gateway", status="queued", payload={"kind": kind})
        self._dispatch_wake.set()
        return stored

    @staticmethod
    def _is_uuid(value: Any) -> bool:
        try:
            uuid.UUID(str(value))
        except (ValueError, TypeError, AttributeError):
            return False
        return True

    # ---- dispatch ------------------------------------------------------
    def _dispatcher(self) -> None:
        while not self._closing:
            self._dispatch_wake.wait(timeout=1.0)
            self._dispatch_wake.clear()
            if self._closing:
                return
            try:
                self._dispatch_once()
            except Exception as exc:  # keep the loop alive; the row records the failure
                sys.stderr.write(f"dispatch error: {type(exc).__name__}: {exc}\n")

    def _dispatch_once(self) -> None:
        queued = sorted(self.store.list_runs(status="queued", limit=10_000), key=lambda r: r["seq"])
        if not queued:
            return
        free = self._free_mb_fn()
        if free is not None and free < self.min_free_mb:
            # the host is the clearance laptop; a child under this floor is the next bugcheck
            for run in queued:
                if run["run_id"] not in self._held:
                    self._held.add(run["run_id"])
                    self.store.append_event(
                        run["run_id"], run["session_id"], "gateway", status="held",
                        payload={"free_mb": free, "min_free_mb": self.min_free_mb,
                                 "note": "queued until free physical RAM is back above the floor"},
                    )
            return
        for run in queued:
            with self._mutex:
                if len(self._procs) + len(self._adopted) >= self.max_concurrent:
                    return
                if run["session_id"] in self._active_sessions:
                    continue
                if run["cancel_requested"]:
                    continue
                self._active_sessions.add(run["session_id"])
            self._start(run)

    def _start(self, run: dict[str, Any]) -> None:
        run_id, session_id = run["run_id"], run["session_id"]
        if run_id in self._held:
            self._held.discard(run_id)
            self.store.append_event(run_id, session_id, "gateway", status="released",
                                    payload={"free_mb": self._free_mb_fn(), "min_free_mb": self.min_free_mb})
        files = self.run_files(run_id)
        files["dir"].mkdir(parents=True, exist_ok=True)
        if not files["prompt"].is_file():
            if run.get("prompt") is None:
                self._finish(run_id, session_id, "error", error="prompt.txt is missing and the prompt text was not retained; resubmit")
                return
            files["prompt"].write_text(run["prompt"], encoding="utf-8")
        try:
            command = build_command(self.claude_cmd, run)
        except ValueError as exc:
            self._finish(run_id, session_id, "error", error=f"CLI options rejected before launch: {exc}")
            return
        env = headless_env(self._env_base, run_id)
        self.store.update_run(run_id, status="starting", started_at=utc_now(), command=command)
        self.store.append_event(run_id, session_id, "gateway", status="starting", payload={"command": command})
        try:
            stdin = files["prompt"].open("rb")
            stdout = files["events"].open("ab")
            stderr = files["stderr"].open("ab")
        except OSError as exc:
            self._finish(run_id, session_id, "error", error=f"could not open run files: {exc}")
            return
        kwargs = build_popen_kwargs(run["cwd"], env, stdin, stdout, stderr)
        try:
            proc = self._popen(command, **kwargs)
        except OSError as exc:
            self._finish(run_id, session_id, "error", error=f"could not start CLI: {exc}")
            return
        finally:
            for handle in (stdin, stdout, stderr):  # the child holds its own copies
                try:
                    handle.close()
                except OSError:
                    pass
        with self._mutex:
            self._procs[run_id] = proc
        self.store.update_run(run_id, pid=proc.pid)
        threading.Thread(
            target=self._tail,
            args=(run_id, session_id, files, proc, proc.pid, False),
            name=f"claude-tail-{run_id[:8]}",
            daemon=True,
        ).start()

    @staticmethod
    def _stderr_tail(path: Path) -> str:
        try:
            data = path.read_bytes()
        except OSError:
            return ""
        return data[-4000:].decode("utf-8", errors="replace")

    def _tail(
        self,
        run_id: str,
        session_id: str,
        files: dict[str, Path],
        proc: Any,
        pid: int,
        adopted: bool,
    ) -> None:
        """Follow events.jsonl until the child is gone and the file is drained."""
        result: dict[str, Any] | None = None
        saw_init = False
        events_path = files["events"]
        deadline_open = time.monotonic() + 30
        while not events_path.exists() and time.monotonic() < deadline_open:
            time.sleep(0.05)

        def alive() -> bool:
            if proc is not None:
                return proc.poll() is None
            return pid_alive(pid)

        def handle(line: bytes) -> None:
            nonlocal result, saw_init
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                return
            try:
                obj = json.loads(text)
            except ValueError:
                self.store.append_event(run_id, session_id, "cli-text", payload={"text": text[:4000]})
                return
            kind = str(obj.get("type") or "cli")
            if kind == "system" and obj.get("subtype") == "init" and not saw_init:
                saw_init = True
                self.store.update_run(run_id, status="running", child_model=obj.get("model"))
                self.store.append_event(
                    run_id,
                    session_id,
                    "gateway",
                    status="running",
                    payload={"model": obj.get("model"), "cwd": obj.get("cwd"), "session_id": obj.get("session_id")},
                )
            if kind == "result":
                result = obj
            self.store.append_event(run_id, session_id, kind, payload=obj)

        already = 0
        if adopted:
            already = sum(
                1 for item in self.store.events_after(0, run_id=run_id, limit=100_000)
                if item["kind"] not in ("gateway", "cli-text")
            )
        try:
            fh = events_path.open("rb")
        except OSError:
            fh = None
        if fh is not None:
            with fh:
                skipped = 0
                while True:
                    if self._closing:
                        return  # this gateway is going away; the next one adopts the child from disk
                    line = fh.readline()
                    if line:
                        if not line.endswith(b"\n"):
                            if alive():
                                fh.seek(-len(line), 1)  # writer is mid-line; wait for the rest
                                time.sleep(0.05)
                                continue
                        if skipped < already:
                            skipped += 1
                            continue
                        handle(line)
                        continue
                    if not alive():
                        rest = fh.read()
                        for tail_line in rest.splitlines():
                            handle(tail_line)
                        break
                    time.sleep(0.05)
        if self._closing:
            return
        exit_code = proc.wait() if proc is not None else None
        stderr_tail = self._stderr_tail(files["stderr"])
        current = self.store.get_run(run_id) or {}
        if current.get("status") in TERMINAL:
            with self._mutex:
                self._procs.pop(run_id, None)
                self._adopted.pop(run_id, None)
                self._active_sessions.discard(session_id)
            self._dispatch_wake.set()
            return
        if current.get("cancel_requested"):
            self._finish(run_id, session_id, "cancelled", exit_code=exit_code, stderr_tail=stderr_tail, result=result)
        else:
            self._finalize_from_result(run_id, session_id, result, exit_code=exit_code, stderr_tail=stderr_tail)

    def _finalize_from_result(
        self,
        run_id: str,
        session_id: str,
        result: dict[str, Any] | None,
        *,
        exit_code: int | None,
        stderr_tail: str,
        note: str | None = None,
    ) -> None:
        fields: dict[str, Any] = {"exit_code": exit_code, "stderr_tail": stderr_tail, "result": result}
        if note:
            fields["note"] = note
        if result is not None and not result.get("is_error") and exit_code in (0, None):
            self._finish(run_id, session_id, "completed", **fields)
        elif result is not None:
            fields["error"] = f"CLI result subtype={result.get('subtype')} is_error={result.get('is_error')} exit={exit_code}"
            self._finish(run_id, session_id, "error", **fields)
        else:
            fields["error"] = f"CLI exited {exit_code} without a result event"
            self._finish(run_id, session_id, "error", **fields)

    def _finish(self, run_id: str, session_id: str, status: str, **fields: Any) -> None:
        result = fields.get("result")
        if isinstance(result, dict):
            text = result.get("result")
            fields["result_text"] = text if isinstance(text, str) else None
        self.store.update_run(run_id, status=status, ended_at=utc_now(), **fields)
        self.store.append_event(
            run_id,
            session_id,
            "gateway",
            status=status,
            payload={"exit_code": fields.get("exit_code"), "error": fields.get("error"), "note": fields.get("note")},
        )
        with self._mutex:
            self._procs.pop(run_id, None)
            self._adopted.pop(run_id, None)
            self._active_sessions.discard(session_id)
            self._pending_prompts.pop(run_id, None)
        self._dispatch_wake.set()

    # ---- cancel --------------------------------------------------------
    def cancel(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        if run["status"] in TERMINAL:
            return {"run_id": run_id, "status": run["status"], "already_terminal": True}
        self.store.update_run(run_id, cancel_requested=1)
        with self._mutex:
            proc = self._procs.get(run_id)
            adopted_pid = self._adopted.get(run_id)
        if run["status"] == "queued" and proc is None and adopted_pid is None:
            self._finish(run_id, run["session_id"], "cancelled", error="cancelled before start")
            return {"run_id": run_id, "status": "cancelled", "killed_pids": [], "tree": [], "pid": None}
        pid = run.get("pid") or adopted_pid or (proc.pid if proc is not None else None)
        killed = kill_tree(int(pid)) if pid else {"method": None, "killed_pids": [], "tree": [], "note": "no pid recorded"}
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            current = self.store.get_run(run_id) or {}
            if current.get("status") in TERMINAL:
                break
            time.sleep(0.05)
        current = self.store.get_run(run_id) or {}
        if current.get("status") not in TERMINAL:
            # no tail thread owns it (should not happen); close it from here
            self.store.update_run(run_id, status="cancelled", ended_at=utc_now())
            self.store.append_event(run_id, run["session_id"], "gateway", status="cancelled", payload=killed)
            current = self.store.get_run(run_id) or {}
        return {"run_id": run_id, "status": current.get("status"), "pid": pid, **{k: v for k, v in killed.items() if k != "stdout"}, "taskkill_stdout": killed.get("stdout")}

    # ---- views ---------------------------------------------------------
    def run_view(self, run: dict[str, Any]) -> dict[str, Any]:
        view = dict(run)
        files = self.run_files(run["run_id"])
        view["transcript_path"] = str(transcript_path(run["cwd"], run["session_id"]))
        view["transcript_exists"] = os.path.isfile(view["transcript_path"])
        view["pid_alive"] = pid_alive(run.get("pid")) if run["status"] in ACTIVE | {"interrupted"} else False
        view["events_file"] = str(files["events"])
        view["stderr_file"] = str(files["stderr"])
        view["events_url"] = f"/v1/runs/{run['run_id']}/events"
        view["session_url"] = f"/v1/sessions/{run['session_id']}"
        view["reply"] = run.get("result_text")
        result = run.get("result") or {}
        if isinstance(result, dict):
            view["num_turns"] = result.get("num_turns")
            view["cost_usd"] = result.get("total_cost_usd")
            view["duration_ms"] = result.get("duration_ms")
            view["models_used"] = sorted((result.get("modelUsage") or {}).keys())
        if not view.get("child_model") and isinstance(result, dict):
            view["child_model"] = next(iter((result.get("modelUsage") or {}).keys()), None)
        with self._mutex:
            view["adopted"] = run["run_id"] in self._adopted
        if isinstance(run.get("result_text"), str):
            view["reply_utf8_base64"] = base64.b64encode(run["result_text"].encode("utf-8")).decode("ascii")
        return view

    def health(self) -> dict[str, Any]:
        with self._mutex:
            active = sorted(set(self._procs) | set(self._adopted))
        return {
            "ok": True,
            "service": SERVICE,
            "contract": CONTRACT,
            "mode": "print-mode-cli-wrapper",
            "started_at": self.started_at,
            "cli": self.cli,
            "claude": self.claude_cmd[0] if self.claude_cmd else None,
            "claude_version": self.cli.get("version"),
            "root": str(self.state_dir),
            "state_dir": str(self.state_dir),
            "runs_dir": str(self.runs_dir),
            "env_scrub": self.env_scrub,
            "max_concurrent": self.max_concurrent,
            "memory_guard": {
                "free_mb": self._free_mb_fn(),
                "min_free_mb": self.min_free_mb,
                "holding": sorted(self._held),
            },
            "active_runs": active,
            "counts": self.store.counts(),
            "event_cursor": self.store.cursor,
            "recovery": self.recovery,
            "async": {
                "run": "/v1/runs/{run_id}",
                "events": "/v1/events",
                "session": "/v1/sessions/{session_id}",
            },
            "endpoints": [
                "GET /health",
                "POST /v1/runs",
                "GET /v1/runs",
                "GET /v1/runs/{run_id}?wait_ms=",
                "GET /v1/runs/{run_id}/events?after=&limit=&wait_ms=",
                "POST /v1/runs/{run_id}/followup",
                "POST /v1/runs/{run_id}/cancel",
                "GET /v1/sessions/{session_id}",
                "POST /v1/sessions/{session_id}/followup",
                "POST /v1/sessions/{session_id}/runs",
                "POST /v1/recover",
                "GET /v1/events?after=&wait_ms=&run_id=&session_id=",
                "POST /v1/message (gemini-shaped alias)",
                "GET /v1/requests/{run_id} (gemini-shaped alias)",
            ],
        }

    def session_view(self, session_id: str) -> dict[str, Any] | None:
        runs = sorted(self.store.list_runs(session_id=session_id, limit=10_000), key=lambda r: r["seq"])
        if not runs:
            return None
        latest = runs[-1]
        path = transcript_path(latest["cwd"], session_id)
        return {
            "session_id": session_id,
            "cwd": latest["cwd"],
            "run_count": len(runs),
            "runs": [self.run_view(run) for run in runs],
            "resumable": True,
            "transcript_path": str(path),
            "transcript_paths": [str(path)],
            "transcript_exists": path.is_file(),
            "transcript_bytes": path.stat().st_size if path.is_file() else 0,
            "followup_url": f"/v1/sessions/{session_id}/followup",
        }

    def recover_view(self) -> dict[str, Any]:
        report = self.reconcile()
        with self._mutex:
            still = sorted(set(self._procs) | set(self._adopted))
        return {
            "recovered": report["finalized_from_disk"] + report["interrupted"],
            "still_running": still,
            **report,
        }

    def shutdown_gateway(self) -> None:
        """Stop serving. Children keep running; the journal and run files stay."""
        self._closing = True
        self._dispatch_wake.set()
        with self._mutex:
            # keep the handles referenced so the interpreter does not complain about a
            # deliberately orphaned child; the next gateway adopts it from disk
            ORPHANED_CHILDREN.extend(self._procs.values())
            self._procs.clear()
        self.shutdown()
        self.server_close()
        time.sleep(0.1)  # let tail threads observe _closing before the journal closes
        self.store.close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: Gateway

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    @staticmethod
    def _qint(query: dict[str, list[str]], name: str, default: int, lo: int, hi: int) -> int:
        try:
            value = int((query.get(name) or [default])[0])
        except ValueError:
            value = default
        return min(hi, max(lo, value))

    def _body(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(size) if size else b""
        if not raw.strip():
            return {}
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("body must be a JSON object")
        return value

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        parts = [p for p in parsed.path.split("/") if p]
        try:
            if parsed.path in ("/", "/health"):
                self._send(200, self.server.health())
                return
            if parts == ["v1", "events"]:
                after = self._qint(query, "after", 0, 0, 1 << 62)
                limit = self._qint(query, "limit", 100, 1, 500)
                wait_ms = self._qint(query, "wait_ms", 0, 0, 55_000)
                events = self.server.store.events_after(
                    after,
                    run_id=(query.get("run_id") or [None])[0],
                    session_id=(query.get("session_id") or [None])[0],
                    limit=limit,
                    wait_ms=wait_ms,
                )
                next_cursor = max([after] + [int(e["event_id"]) for e in events])
                self._send(200, {"ok": True, "events": events, "next_cursor": next_cursor})
                return
            if parts == ["v1", "runs"]:
                runs = self.server.store.list_runs(
                    status=(query.get("status") or [None])[0],
                    session_id=(query.get("session_id") or [None])[0],
                    limit=self._qint(query, "limit", 50, 1, 1000),
                )
                self._send(200, {"ok": True, "runs": [self.server.run_view(r) for r in runs]})
                return
            if len(parts) == 3 and parts[:2] in (["v1", "runs"], ["v1", "requests"]):
                wait_ms = self._qint(query, "wait_ms", 0, 0, 55_000)
                run = self.server.store.wait_run(parts[2], wait_ms)
                if run is None:
                    self._send(404, {"ok": False, "error": "run_not_found"})
                    return
                view = self.server.run_view(run)
                self._send(
                    200,
                    {
                        "ok": True,
                        "request_id": run["run_id"],
                        "run_id": run["run_id"],
                        "session_id": run["session_id"],
                        "status": view["status"],
                        "run": view,
                        "event": view,
                    },
                )
                return
            if len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "events":
                run = self.server.store.get_run(parts[2])
                if run is None:
                    self._send(404, {"ok": False, "error": "run_not_found"})
                    return
                after = self._qint(query, "after", 0, 0, 1 << 62)
                limit = self._qint(query, "limit", 100, 1, 500)
                wait_ms = self._qint(query, "wait_ms", 0, 0, 55_000)
                events = self.server.store.events_after(after, run_id=run["run_id"], limit=limit, wait_ms=wait_ms)
                next_cursor = max([after] + [int(e["event_id"]) for e in events])
                latest = self.server.store.get_run(run["run_id"]) or run
                self._send(
                    200,
                    {
                        "ok": True,
                        "run_id": run["run_id"],
                        "status": latest["status"],
                        "events": events,
                        "next_cursor": next_cursor,
                    },
                )
                return
            if len(parts) == 3 and parts[:2] == ["v1", "sessions"]:
                view = self.server.session_view(parts[2])
                if view is None:
                    self._send(404, {"ok": False, "error": "session_not_found"})
                    return
                self._send(200, {"ok": True, **view})
                return
            self._send(404, {"ok": False, "error": "not_found"})
        except Exception as exc:
            self._send(500, {"ok": False, "error": type(exc).__name__, "message": str(exc)})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        parts = [p for p in parsed.path.split("/") if p]
        try:
            payload = self._body()
            if parts == ["v1", "runs"] or parts == ["v1", "message"]:
                run = self.server.submit(payload)
                self._respond_submitted(run, payload, query)
                return
            if len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "followup":
                run = self.server.submit(payload, parent_run_id=parts[2])
                self._respond_submitted(run, payload, query)
                return
            if len(parts) == 4 and parts[:2] == ["v1", "sessions"] and parts[3] in ("runs", "followup"):
                payload = {**payload, "session_id": parts[2]}
                run = self.server.submit(payload)
                self._respond_submitted(run, payload, query)
                return
            if len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "cancel":
                try:
                    outcome = self.server.cancel(parts[2])
                except KeyError:
                    self._send(404, {"ok": False, "error": "run_not_found"})
                    return
                if outcome.get("already_terminal"):
                    self._send(409, {"ok": False, "error": "already_terminal", **outcome})
                    return
                self._send(200, {"ok": True, **outcome})
                return
            if parts == ["v1", "recover"]:
                self._send(200, {"ok": True, **self.server.recover_view()})
                return
            self._send(404, {"ok": False, "error": "not_found"})
        except ValueError as exc:
            self._send(400, {"ok": False, "error": type(exc).__name__, "message": str(exc)})
        except Exception as exc:
            self._send(500, {"ok": False, "error": type(exc).__name__, "message": str(exc)})

    def _respond_submitted(
        self, run: dict[str, Any], payload: dict[str, Any], query: dict[str, list[str]]
    ) -> None:
        wait_ms = self._qint(query, "wait_ms", int(payload.get("wait_ms") or 0), 0, 55_000)
        base = {
            "ok": True,
            "request_id": run["run_id"],
            "run_id": run["run_id"],
            "session_id": run["session_id"],
            "status": run["status"],
            "run": self.server.run_view(run),
        }
        if payload.get("async") or wait_ms == 0:
            self._send(202, base)
            return
        final = self.server.store.wait_run(run["run_id"], wait_ms) or run
        view = self.server.run_view(final)
        body = {**base, "ok": final["status"] == "completed", "status": final["status"], "run": view}
        if view.get("reply") is not None:
            body["reply"] = view["reply"]
            body["reply_utf8_base64"] = view["reply_utf8_base64"]
        if final["status"] == "completed":
            code = 200
        elif final["status"] in TERMINAL:
            code = 502
        else:
            code = 202
        self._send(code, body)


# ---- process management ---------------------------------------------------


def _wait_health(port: int, timeout: float) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
                value = json.loads(resp.read().decode("utf-8"))
                if isinstance(value, dict):
                    return value
        except Exception:
            time.sleep(0.25)
    return None


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def detach(args: argparse.Namespace) -> int:
    """Start the gateway as a console-free background process and return."""
    state_dir = Path(args.state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    log_path = state_dir / "gateway.log"
    pid_path = state_dir / "gateway.pid"
    existing = _wait_health(args.port, 0.5)
    if existing:
        print(
            json.dumps(
                {
                    "ready": True,
                    "already_running": True,
                    "listen": f"http://127.0.0.1:{args.port}",
                    "pid": _read_pid(pid_path),
                    "started_at": existing.get("started_at"),
                }
            )
        )
        return 0
    python = sys.executable
    if IS_WINDOWS:
        candidate = Path(python).with_name("pythonw.exe")
        if candidate.is_file():
            python = str(candidate)
    cmd = [
        python,
        str(Path(__file__).resolve()),
        "--serve",
        "--port",
        str(args.port),
        "--state-dir",
        str(state_dir),
        "--max-concurrent",
        str(args.max_concurrent),
        "--min-free-mb",
        str(args.min_free_mb),
    ]
    if args.claude_cmd:
        cmd += ["--claude-cmd", *args.claude_cmd]
    log_handle = open(log_path, "ab")
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": log_handle,
        "stderr": subprocess.STDOUT,
        "cwd": str(Path.home()),
    }
    if IS_WINDOWS:
        kwargs["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    log_handle.close()
    pid_path.write_text(str(proc.pid), encoding="utf-8")
    health = _wait_health(args.port, 20)
    print(
        json.dumps(
            {
                "ready": bool(health),
                "listen": f"http://127.0.0.1:{args.port}",
                "pid": proc.pid,
                "log": str(log_path),
                "cli": (health or {}).get("cli"),
                "recovery": (health or {}).get("recovery"),
            }
        )
    )
    return 0 if health else 1


def stop(args: argparse.Namespace) -> int:
    """Stop only the gateway process. Children in flight keep running and are
    adopted or finalized from disk by the next gateway start."""
    pid_path = Path(args.state_dir) / "gateway.pid"
    pid = _read_pid(pid_path)
    if not pid or not pid_alive(pid):
        print(json.dumps({"stopped": False, "note": "no live gateway pid recorded", "pid": pid}))
        return 0
    if IS_WINDOWS:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True, creationflags=flags, check=False)
        outcome = {"method": "taskkill /F (gateway only)", "exit_code": proc.returncode, "stdout": (proc.stdout or "")[-300:]}
    else:
        import signal

        os.kill(pid, signal.SIGTERM)
        outcome = {"method": "SIGTERM (gateway only)"}
    time.sleep(0.3)
    print(json.dumps({"stopped": not pid_alive(pid), "pid": pid, **outcome}))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--max-concurrent", type=int, default=DEFAULT_MAX_CONCURRENT)
    parser.add_argument(
        "--min-free-mb",
        type=int,
        default=DEFAULT_MIN_FREE_MB,
        help="hold queued runs while free physical RAM is below this (MB); 0 disables",
    )
    parser.add_argument(
        "--claude-cmd", nargs="+", default=None, help="command tokens for the CLI (default: claude on PATH)"
    )
    parser.add_argument("--serve", dest="mode", action="store_const", const="serve", help="serve in this process")
    parser.add_argument(
        "--detach",
        dest="mode",
        action="store_const",
        const="detach",
        help="start a console-free background gateway and return",
    )
    parser.add_argument(
        "--stop", dest="mode", action="store_const", const="stop", help="stop the background gateway (children keep running)"
    )
    parser.set_defaults(mode="serve")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.mode == "detach":
        return detach(args)
    if args.mode == "stop":
        return stop(args)
    server = Gateway(
        ("127.0.0.1", args.port),
        state_dir=args.state_dir,
        claude_cmd=args.claude_cmd,
        max_concurrent=args.max_concurrent,
        min_free_mb=args.min_free_mb,
    )
    print(
        json.dumps(
            {
                "ready": True,
                "listen": f"http://127.0.0.1:{args.port}",
                "cli": server.cli,
                "recovery": server.recovery,
                "env_scrub": server.env_scrub,
                "max_concurrent": server.max_concurrent,
                "min_free_mb": server.min_free_mb,
            }
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
        server.store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
