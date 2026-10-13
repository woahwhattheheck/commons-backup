#!/usr/bin/env python3
"""Pull private cloud jobs into the owner's interactive Windows session.

The cloud writes one JSON request to the private pc-bridge branch. This process
polls that branch with the already-installed GitHub CLI, claims each request by
creating a started marker, calls the existing TITAN Hands broker, and writes
the result back to the same private branch. No listener, tunnel, checkout, or
model process is started while idle.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from typing import Any, Iterator


OWNER = "woahwhattheheck"
REPOSITORY = "commons-ship-enforcer"
BRANCH = "pc-bridge"
API = "repos/%s/%s" % (OWNER, REPOSITORY)
JOB_SCHEMA = "commons-cloud-pc-job/v1"
START_SCHEMA = "commons-cloud-pc-start/v1"
RESULT_SCHEMA = "commons-cloud-pc-result/v1"
ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
MAX_JOB_BYTES = 256 * 1024
MAX_RESULT_BYTES = 512 * 1024
STARTED_STALE_SECONDS = 1800
# Retain only the current in-flight result in memory; never create a PC cache.
_pending_result: dict[str, Any] | None = None

TOKEN_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{12,}\b"),
    re.compile(r"\bsk-(?:ant|proj)-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\brk_live_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bwhsec_[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bxai-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}={0,2}"),
)
SECRET_KEYS = ("password", "passwd", "secret", "api_key", "private_key", "access_token", "refresh_token", "token", "credential", "cookie")
KEY_VALUE_PATTERN = re.compile(
    r"(?i)\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|"
    r"password|passwd|secret|authorization|cookie)\b\s*[:=]\s*['\"]?[^\s'\",;]{8,}"
)


class BridgeError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class RequestError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise RequestError("duplicate JSON key: %s" % key)
        out[key] = value
    return out


def _contains_secret(value: Any, key: str = "") -> bool:
    if any(marker in key.lower() for marker in SECRET_KEYS):
        if value not in (None, False, True, "", "present", "missing", "redacted"):
            return True
    if isinstance(value, dict):
        return any(_contains_secret(item, str(name)) for name, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_secret(item, key) for item in value)
    if isinstance(value, str):
        return KEY_VALUE_PATTERN.search(value) is not None or any(pattern.search(value) for pattern in TOKEN_PATTERNS)
    return False


def _redact(value: Any, key: str = "") -> Any:
    if any(marker in key.lower() for marker in SECRET_KEYS):
        if value not in (None, False, True, "", "present", "missing", "redacted"):
            return "[redacted]"
    if isinstance(value, dict):
        return {str(name): _redact(item, str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact(item, key) for item in value]
    if isinstance(value, str):
        text = value
        text = KEY_VALUE_PATTERN.sub("[redacted]", text)
        for pattern in TOKEN_PATTERNS:
            text = pattern.sub("[redacted]", text)
        return text
    return value


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _api(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None,
         missing_ok: bool = False) -> Any:
    if not shutil.which("gh"):
        raise BridgeError("GITHUB_CLI_MISSING", "Install GitHub CLI and use its existing sign-in.")
    command = ["gh", "api", "--hostname", "github.com"]
    if method != "GET":
        command.extend(["--method", method])
    command.append(path.lstrip("/"))
    body = None
    if payload is not None:
        command.extend(["--input", "-"])
        body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    try:
        no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        proc = subprocess.run(command, input=body, text=True, capture_output=True, timeout=45,
                              check=False, creationflags=no_window)
    except subprocess.TimeoutExpired as exc:
        raise BridgeError("GITHUB_TIMEOUT", "GitHub request timed out.") from exc
    except OSError as exc:
        raise BridgeError("GITHUB_CLI_FAILED", "GitHub CLI could not start.") from exc
    if proc.returncode:
        error = proc.stderr or ""
        match = re.search(r"\b(401|403|404|409|422|429)\b", error)
        status = match.group(1) if match else ""
        if status == "404" and missing_ok:
            return None
        if status == "401":
            code = "GITHUB_SIGN_IN_REQUIRED"
        elif status == "403":
            code = "GITHUB_ACCESS_DENIED"
        elif status == "404":
            code = "GITHUB_RESOURCE_NOT_FOUND"
        elif status in {"409", "422"}:
            code = "GITHUB_WRITE_CONFLICT"
        elif status == "429":
            code = "GITHUB_RATE_LIMITED"
        else:
            code = "GITHUB_REQUEST_FAILED"
        raise BridgeError(code, "GitHub request failed%s." % (" (HTTP " + status + ")" if status else ""))
    if not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise BridgeError("GITHUB_RESPONSE_INVALID", "GitHub returned invalid JSON.") from exc


def _encoded_path(path: str) -> str:
    return "/".join(quote(part, safe="") for part in path.split("/"))


def _contents_path(path: str) -> str:
    return "%s/contents/%s?ref=%s" % (API, _encoded_path(path), quote(BRANCH, safe=""))


def _read_file(path: str, *, missing_ok: bool = False) -> bytes | None:
    row = _api(_contents_path(path), missing_ok=missing_ok)
    if row is None:
        return None
    if not isinstance(row, dict) or row.get("type") != "file":
        raise BridgeError("QUEUE_SCHEMA", "Queue path is not a regular file: %s" % path)
    encoded = str(row.get("content") or "").replace("\n", "")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise BridgeError("QUEUE_SCHEMA", "Queue file is not valid base64: %s" % path) from exc
    return raw


def _list_json(directory: str) -> dict[str, str]:
    row = _api(_contents_path(directory), missing_ok=True)
    if row is None:
        return {}
    if not isinstance(row, list):
        raise BridgeError("QUEUE_SCHEMA", "Queue directory is not a directory: %s" % directory)
    out: dict[str, str] = {}
    for item in row:
        if not isinstance(item, dict) or item.get("type") != "file":
            continue
        name = str(item.get("name") or "")
        if name.endswith(".json"):
            ident = name[:-5]
            if ID_RE.fullmatch(ident):
                out[ident] = str(item.get("path") or (directory + "/" + name))
    return out


def _require_queue_branch() -> None:
    _api("%s/git/ref/heads/%s" % (API, quote(BRANCH, safe="")))


def _write_json(path: str, value: dict[str, Any], message: str) -> bool:
    raw = _json_bytes(value)
    if len(raw) > MAX_RESULT_BYTES:
        raise BridgeError("RESULT_TOO_LARGE", "Queue record exceeds the private GitHub contents limit.")
    body = {
        "message": message[:120],
        "content": base64.b64encode(raw).decode("ascii"),
        "branch": BRANCH,
    }
    endpoint = "%s/contents/%s" % (API, _encoded_path(path))
    for _attempt in range(4):
        if _read_file(path, missing_ok=True) is not None:
            return False
        try:
            _api(endpoint, method="PUT", payload=body)
            return True
        except BridgeError as exc:
            if _read_file(path, missing_ok=True) is not None:
                return False
            if exc.code != "GITHUB_WRITE_CONFLICT":
                raise
    raise BridgeError("GITHUB_WRITE_CONFLICT", "Could not claim a queue path after four retries.")


def _load_job(job_id: str, path: str) -> dict[str, Any]:
    raw = _read_file(path)
    if raw is None:
        raise RequestError("request disappeared from the queue")
    if len(raw) > MAX_JOB_BYTES:
        raise RequestError("request exceeds the 256 KiB limit")
    try:
        row = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=lambda _: (_ for _ in ()).throw(RequestError("non-finite number")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RequestError("request is not valid UTF-8 JSON") from exc
    if not isinstance(row, dict):
        raise RequestError("request must be a JSON object")
    if row.get("schema") != JOB_SCHEMA or row.get("job_id") != job_id:
        raise RequestError("request schema or job_id does not match its path")
    request = row.get("request")
    if not isinstance(request, dict):
        raise RequestError("request.request must be an object")
    if _contains_secret(row):
        raise RequestError("request contains credential material; credentials are not transported through the queue")
    return row


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _result_record(job_id: str, *, state: str, started_at: str | None,
                   result: Any = None, message: str = "") -> dict[str, Any]:
    clean_result = _redact(result) if result is not None else None
    row: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "job_id": job_id,
        "state": state,
        "ok": state == "DONE" and isinstance(clean_result, dict) and clean_result.get("ok") is True,
        "started_at": started_at,
        "finished_at": utc_now(),
        "message": _redact(message),
        "result": clean_result,
    }
    raw = _json_bytes(row)
    if len(raw) > MAX_RESULT_BYTES:
        row = {
            "schema": RESULT_SCHEMA,
            "job_id": job_id,
            "state": "RESULT_TOO_LARGE",
            "ok": False,
            "started_at": started_at,
            "finished_at": utc_now(),
            "result_bytes": len(raw),
            "result_sha256": hashlib.sha256(raw).hexdigest(),
            "message": "Result exceeded the 512 KiB bridge limit. Request a smaller, targeted extract.",
        }
    return row


def _uncertain_start(job_id: str, raw: bytes | None) -> dict[str, Any] | None:
    """Finish an unreadable or stale claim without replaying its side effects."""
    try:
        marker = json.loads((raw or b"").decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RequestError):
        marker = {}
    started_at = marker.get("started_at") if isinstance(marker, dict) else None
    stamp = _parse_time(started_at)
    now = datetime.now(timezone.utc)
    valid = (isinstance(marker, dict) and marker.get("schema") == START_SCHEMA
             and marker.get("job_id") == job_id and stamp is not None
             and stamp <= now + timedelta(minutes=5))
    if valid:
        if (now - stamp).total_seconds() <= STARTED_STALE_SECONDS:
            return None
        message = "Execution started but no result was saved. The bridge will not replay it."
    else:
        message = "Start marker is invalid; execution cannot be determined. The bridge will not replay it."
    return _result_record(job_id, state="UNCERTAIN",
                          started_at=started_at if isinstance(started_at, str) else None,
                          message=message)


def _once_exit_code(outcome: dict[str, Any]) -> int:
    if outcome.get("state") == "IDLE":
        return 0
    return 0 if outcome.get("state") == "DONE" and outcome.get("ok") is True else 1


def _run_hands(request: dict[str, Any]) -> dict[str, Any]:
    from host.titan_hands.one_tool import TitanHandsOne

    hands = TitanHandsOne()
    try:
        value = hands.handle(request)
        if isinstance(value, dict):
            return value
        return {"ok": True, "value": value}
    finally:
        hands.close()


@contextmanager
def _worker_lock() -> Iterator[None]:
    """Serialize patched workers on this host without a lock file or local cache."""
    import ctypes
    from ctypes import wintypes

    try:
        kernel = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    except OSError as exc:
        raise BridgeError("MUTEX_UNAVAILABLE", "Cannot load the Windows worker mutex API.") from exc
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.ReleaseMutex.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateMutexW(None, False, r"Global\CommonsCloudPCBridge-woahwhattheheck-pc-bridge")
    if not handle:
        raise BridgeError("MUTEX_UNAVAILABLE", "Cannot open the Windows worker mutex (%s)." % ctypes.get_last_error())
    owned = False
    try:
        wait = kernel.WaitForSingleObject(handle, 0)
        if wait == 0x102:  # WAIT_TIMEOUT: another bridge is active.
            raise BridgeError("BRIDGE_BUSY", "Another bridge process is active on this Windows host.")
        if wait not in (0, 0x80):  # WAIT_OBJECT_0 or WAIT_ABANDONED grants ownership.
            raise BridgeError("MUTEX_UNAVAILABLE", "Cannot acquire the Windows worker mutex (%s)." % ctypes.get_last_error())
        owned = True
        yield
    finally:
        released = not owned or bool(kernel.ReleaseMutex(handle))
        closed = bool(kernel.CloseHandle(handle))
        if not released or not closed:
            raise BridgeError("MUTEX_UNAVAILABLE", "Cannot release the Windows worker mutex.")


def _deliver_pending() -> dict[str, Any]:
    global _pending_result
    record = _pending_result
    if record is None:
        raise BridgeError("NO_PENDING_RESULT", "There is no result awaiting delivery.")
    job_id = record["job_id"]
    path = "pc_bridge/results/%s.json" % job_id
    _write_json(path, record, "pc bridge: result %s" % job_id)
    observed = _read_file(path, missing_ok=True)
    if observed is None:
        raise BridgeError("RESULT_UNCONFIRMED", "Result readback is missing; delivery remains pending in this process.")
    if observed != _json_bytes(record):
        raise BridgeError("RESULT_CONFLICT", "A different result exists; it was not overwritten. Do not replay the job.")
    _pending_result = None
    return {"state": record["state"], "ok": record["ok"], "processed": True,
            "job_id": job_id, "result_published": True}


def _finish(record: dict[str, Any]) -> dict[str, Any]:
    global _pending_result
    if _pending_result is not None:
        raise BridgeError("RESULT_PENDING", "Deliver the previous result before processing another job.")
    _pending_result = record
    return _deliver_pending()


def queue_status() -> dict[str, Any]:
    """Read queue metadata only; no claims, result writes or broker import."""
    _require_queue_branch()
    inbox = set(_list_json("pc_bridge/inbox"))
    started = set(_list_json("pc_bridge/started"))
    results = set(_list_json("pc_bridge/results"))
    return {"state": "STATUS", "processed": False, "queued": len(inbox - started - results),
            "started_without_result": len(started - results), "result_files": len(results),
            "worker_running": "UNKNOWN", "queue_snapshot_atomic": False}


def process_one() -> dict[str, Any]:
    """Poll under the process-lifetime worker mutex held by main()."""
    if _pending_result is not None:
        return _deliver_pending()
    _require_queue_branch()
    inbox = _list_json("pc_bridge/inbox")
    started = _list_json("pc_bridge/started")
    results = _list_json("pc_bridge/results")
    for job_id in sorted(set(inbox) | set(started)):
        if job_id in results:
            continue
        if job_id in started:
            marker_raw = _read_file(started[job_id], missing_ok=True)
            uncertain = _uncertain_start(job_id, marker_raw)
            if uncertain is not None:
                return _finish(uncertain)
            continue
        try:
            job = _load_job(job_id, inbox[job_id])
        except RequestError as exc:
            invalid = _result_record(job_id, state="INVALID_REQUEST", started_at=None, message=str(exc))
            return _finish(invalid)
        started_at = utc_now()
        marker = {"schema": START_SCHEMA, "job_id": job_id, "started_at": started_at}
        if not _write_json("pc_bridge/started/%s.json" % job_id, marker, "pc bridge: started %s" % job_id):
            continue
        try:
            result = _run_hands(job["request"])
            state = "DONE" if result.get("ok") is True else "FAILED"
            record = _result_record(job_id, state=state, started_at=started_at, result=result)
        except Exception as exc:
            record = _result_record(job_id, state="UNCERTAIN", started_at=started_at,
                                    message="%s: %s" % (type(exc).__name__, str(exc)[:2000]))
        return _finish(record)
    return {"state": "WAITING_RESULT" if set(started) - set(results) else "IDLE", "processed": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lightweight private cloud-to-PC bridge using TITAN Hands.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="poll and process at most one request, then exit")
    mode.add_argument("--status", action="store_true", help="read queue metadata without executing jobs or writing results")
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args(argv)
    if args.poll_seconds < 5:
        parser.error("--poll-seconds must be at least 5")
    if os.name != "nt" and not args.status:
        print(json.dumps({"state": "WINDOWS_REQUIRED", "ok": False}, sort_keys=True))
        return 2
    try:
        if args.status:
            print(json.dumps(queue_status(), ensure_ascii=True, sort_keys=True))
            return 0
        with _worker_lock():
            if args.once:
                outcome = process_one()
                print(json.dumps(outcome, ensure_ascii=True, sort_keys=True))
                return _once_exit_code(outcome)
            while True:
                try:
                    outcome = process_one()
                    if outcome.get("processed"):
                        print(json.dumps(outcome, ensure_ascii=True, sort_keys=True), flush=True)
                except BridgeError as exc:
                    print("CLOUD_PC_BRIDGE %s" % exc.code, file=sys.stderr, flush=True)
                time.sleep(args.poll_seconds)
    except BridgeError as exc:
        print("CLOUD_PC_BRIDGE %s" % exc.code, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
