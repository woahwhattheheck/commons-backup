"""Read Codex quota through the native app-server transport, without model work.

The only protocol operations are initialize, initialized, and
account/rateLimits/read. This module never reads credential files, starts an
app-server daemon, services server requests, or returns raw provider payloads.
An unavailable proxy may use one short-lived stdio child, never a daemon.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

__all__ = ["poll_codex_pool"]

_WALL_SECONDS = 30.0
_CLEANUP_SECONDS = 2.0
_PROXY_CONNECT_SECONDS = 3.0
_MAX_OUTPUT_BYTES = 512 * 1024
_MAX_LINE_BYTES = 256 * 1024
_MAX_BUCKETS = 128
_SOURCE = "account/rateLimits/read"
_INITIALIZE_ID = "commons-token-pools-initialize"
_QUOTA_ID = "commons-token-pools-rate-limits"


class _PoolError(RuntimeError):
    def __init__(self, code: str, error_class: str = "CodexProxyError", provider_code=None):
        super().__init__(code)
        self.code = code
        self.error_class = error_class
        self.provider_code = provider_code if type(provider_code) is int else None


def _number(value):
    if type(value) not in (int, float):
        return None
    try:
        return value if math.isfinite(value) else None
    except OverflowError:
        return None


def _window(value):
    if not isinstance(value, dict):
        return None
    used = _number(value.get("usedPercent"))
    return {
        "usage_percent": used,
        "remaining_percent": max(0, min(100, 100 - used)) if used is not None else None,
        "window_minutes": _number(value.get("windowDurationMins")),
        "resets_at": _number(value.get("resetsAt")),
    }


def _bucket_id(value, index: int, used: set[str]) -> str:
    # Retain short metered names, never arbitrary labels or opaque account IDs.
    safe = isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", value)
    opaque = isinstance(value, str) and (
        re.search(r"^(?:sk[-_]|sess[-_]|token[-_]|account[-_]|acct[-_]|user[-_]|org[-_]|gh[pousr]_|github_pat_|xox[baprs]-|xapp-|AIza)", value, re.I)
        or re.fullmatch(r"[0-9a-f]{16,}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", value, re.I)
    )
    candidate = value if safe and not opaque else f"bucket_{index}"
    while candidate in used:
        candidate = f"bucket_{index}_{len(used)}"
        index += 1
    used.add(candidate)
    return candidate


def _normalize(value: dict) -> dict:
    buckets = value.get("rateLimitsByLimitId")
    if isinstance(buckets, dict) and buckets:
        items = sorted(buckets.items())
    else:
        legacy = value.get("rateLimits")
        items = [(legacy.get("limitId") or "legacy", legacy)] if isinstance(legacy, dict) else []
    if len(items) > _MAX_BUCKETS:
        raise _PoolError("quota_bucket_limit_exceeded", "ProtocolError")
    used: set[str] = set()
    pools = []
    for index, (key, snapshot) in enumerate(items, 1):
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        pools.append({
            "bucket_id": _bucket_id(key, index, used),
            "primary": _window(snapshot.get("primary")),
            "secondary": _window(snapshot.get("secondary")),
        })
    summary = value.get("rateLimitResetCredits")
    count = summary.get("availableCount") if isinstance(summary, dict) else None
    return {
        "pools": pools,
        "banked_resets_available": count if type(count) is int and count >= 0 else None,
    }


def _native_executable(executable) -> str:
    candidate = os.fspath(executable) if executable is not None else shutil.which("codex")
    if executable is None and os.name == "nt":
        # Existing desktop services may predate the app's task-specific PATH.
        # Discover only installed native app binaries; never invoke a shell shim
        # or install a CLI to answer a quota request.
        if not candidate or Path(candidate).name.lower() != "codex.exe":
            local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
            installed = local / "OpenAI/Codex/bin"
            choices = [p for p in installed.glob("*/codex.exe") if p.is_file()]
            if choices:
                candidate = str(max(choices, key=lambda p: (p.stat().st_mtime_ns, str(p))))
    if not candidate:
        raise _PoolError("codex_executable_unavailable", "FileNotFoundError")
    resolved = shutil.which(candidate)
    if resolved is None:
        raise _PoolError("codex_executable_unavailable", "FileNotFoundError")
    path = Path(resolved).resolve()
    # No shell shims or arbitrary executables. The native CLI is the only road.
    if path.name.lower() not in {"codex", "codex.exe"}:
        raise _PoolError("native_codex_executable_required", "ConfigurationError")
    return str(path)


def _messages(stdout):
    pending = bytearray()
    total = 0
    while True:
        chunk = os.read(stdout.fileno(), 8192)
        if not chunk:
            raise _PoolError("codex_proxy_closed")
        total += len(chunk)
        if total > _MAX_OUTPUT_BYTES:
            raise _PoolError("proxy_output_limit_exceeded", "ProtocolError")
        pending.extend(chunk)
        while b"\n" in pending:
            line, _, remaining = pending.partition(b"\n")
            pending = bytearray(remaining)
            if len(line) > _MAX_LINE_BYTES:
                raise _PoolError("proxy_line_limit_exceeded", "ProtocolError")
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except (ValueError, UnicodeError, RecursionError):
                raise _PoolError("invalid_proxy_response", "ProtocolError") from None
            if not isinstance(message, dict):
                raise _PoolError("invalid_proxy_response", "ProtocolError")
            # Never respond to auth refresh, attestation, approvals, or any
            # other server request. Closing our proxy leaves the server alone.
            if "method" in message and "id" in message:
                raise _PoolError("unexpected_server_request", "ProtocolError")
            yield message
        if len(pending) > _MAX_LINE_BYTES:
            raise _PoolError("proxy_line_limit_exceeded", "ProtocolError")


def _send(stdin, message: dict) -> None:
    wire = (json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8")
    view = memoryview(wire)
    while view:
        written = stdin.write(view)
        if not written:
            raise _PoolError("codex_proxy_closed")
        view = view[written:]


def _response(messages, request_id: str) -> dict:
    for message in messages:
        if message.get("id") != request_id:
            continue
        if "error" in message:
            error = message["error"]
            code = error.get("code") if isinstance(error, dict) else None
            raise _PoolError("codex_proxy_request_failed", "RpcError", code)
        result = message.get("result")
        if not isinstance(result, dict):
            raise _PoolError("invalid_proxy_result", "ProtocolError")
        return result
    raise _PoolError("codex_proxy_closed")


def _exchange(process, outcome: dict, done: threading.Event, connected: threading.Event) -> None:
    try:
        messages = _messages(process.stdout)
        _send(process.stdin, {"id": _INITIALIZE_ID, "method": "initialize", "params": {
            "clientInfo": {"name": "commons_token_pools", "version": "1.0"},
        }})
        _response(messages, _INITIALIZE_ID)
        connected.set()
        _send(process.stdin, {"method": "initialized"})
        # Mark dispatch before writing. Even an uncertain write must not be
        # followed by a second quota request on another transport.
        outcome["quota_requested"] = True
        _send(process.stdin, {"id": _QUOTA_ID, "method": _SOURCE})
        outcome["data"] = _normalize(_response(messages, _QUOTA_ID))
    except _PoolError as exc:
        outcome["error"] = exc
    except (OSError, ValueError):
        outcome["error"] = _PoolError("codex_proxy_transport_failed", "TransportError")
    except Exception:
        outcome["error"] = _PoolError("codex_proxy_protocol_failed", "ProtocolError")
    finally:
        done.set()
        connected.set()


def _cleanup(process, worker, deadline: float) -> None:
    try:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=min(1.0, max(0.0, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        if worker is not None:
            worker.join(timeout=max(0.0, deadline - time.monotonic()))
    finally:
        for pipe in (process.stdin, process.stdout):
            if pipe is not None:
                pipe.close()


def _attempt(executable: str, mode: str, deadline: float) -> tuple[dict, _PoolError | None]:
    process = worker = None
    failure = None
    outcome: dict[str, Any] = {}
    try:
        options = {}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = subprocess.SW_HIDE
            options["startupinfo"] = startup
        process = subprocess.Popen(
            [executable, "app-server", "proxy" if mode == "proxy" else "--stdio"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            shell=False, bufsize=0, close_fds=True, **options,
        )
        done = threading.Event()
        connected = threading.Event()
        worker = threading.Thread(target=_exchange, args=(process, outcome, done, connected), daemon=True)
        worker.start()
        if mode == "proxy" and not connected.wait(timeout=min(
            _PROXY_CONNECT_SECONDS, max(0.0, deadline - time.monotonic() - _CLEANUP_SECONDS)
        )):
            raise _PoolError("codex_proxy_connection_timeout", "TimeoutError")
        if not done.wait(timeout=max(0.0, deadline - time.monotonic() - _CLEANUP_SECONDS)):
            raise _PoolError("codex_proxy_timeout", "TimeoutError")
        if "error" in outcome:
            raise outcome["error"]
    except _PoolError as exc:
        failure = exc
    except OSError:
        failure = _PoolError("codex_proxy_unavailable", "ProcessError")
    except Exception:
        failure = _PoolError("codex_proxy_failed", "ProcessError")
    finally:
        if process is not None:
            try:
                _cleanup(process, worker, min(deadline, time.monotonic() + _CLEANUP_SECONDS))
            except Exception:
                failure = _PoolError("codex_proxy_cleanup_failed", "ProcessError")
    # A real response arriving at the connection deadline still wins over a
    # timeout classification. Never retry a provider/protocol rejection.
    late_error = outcome.get("error")
    if (failure is not None and failure.code == "codex_proxy_connection_timeout"
            and isinstance(late_error, _PoolError)
            and late_error.error_class in {"RpcError", "ProtocolError"}):
        failure = late_error
    return outcome, failure


def poll_codex_pool(*, executable=None) -> dict:
    """Read quota within 30 seconds, including bounded child cleanup.

    Prefer the existing control-socket proxy. Only its connection failure before
    quota dispatch permits one stdio child. Provider errors never trigger this
    fallback. Neither transport starts a model turn or changes authentication.
    """
    deadline = time.monotonic() + _WALL_SECONDS
    result: dict[str, Any] = {
        "schema": "commons.token_pool_status.v1",
        "provider": "codex",
        "source": _SOURCE,
        "observed_at": None,
        "ok": False,
        "pools": [],
        "banked_resets_available": None,
    }
    failure = None
    try:
        native = _native_executable(executable)
        outcome, failure = _attempt(native, "proxy", deadline)
        proxy_unavailable = failure is not None and failure.code in {
            "codex_proxy_closed", "codex_proxy_transport_failed", "codex_proxy_connection_timeout",
        }
        if (proxy_unavailable and not outcome.get("quota_requested")
                and time.monotonic() < deadline - _CLEANUP_SECONDS):
            outcome, failure = _attempt(native, "stdio", deadline)
        if failure is None:
            result.update(outcome["data"], ok=True)
    except _PoolError as exc:
        failure = exc
    except Exception:
        failure = _PoolError("codex_proxy_failed", "ProcessError")
    finally:
        result["observed_at"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    if failure is not None:
        result.update(ok=False, pools=[], banked_resets_available=None)
        result["error"] = {"class": failure.error_class, "code": failure.code}
        if failure.provider_code is not None:
            result["error"]["provider_code"] = failure.provider_code
    return result
