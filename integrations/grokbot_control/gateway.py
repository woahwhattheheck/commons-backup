#!/usr/bin/env python3
"""Loopback HTTP peer gateway for GrokBot pools.

Endpoints (C1 / Gemini event-cursor compatible shape):
  GET  /health
  GET  /v1/pools
  POST /v1/runs              submit {pool_id, prompt, seat?, async?, case?}
  GET  /v1/runs/{run_id}     inspect (?wait_ms=)
  POST /v1/runs/{run_id}/follow-up {prompt, async?}
  POST /v1/runs/{run_id}/cancel
  GET  /v1/sessions/{session_id}
  GET  /v1/events?after=&limit=&wait_ms=&pool_id=

Default listen: 127.0.0.1:8881 (not 8788/8789 grok_slack, not 8879 C1).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .memory import free_physical_mb, resolve_min_free_mb
from .pools import DEFAULT_POOL_ID, HARNESS, list_pools, require_pool
from .runner import EchoSeatRunner, InProcessSeatRunner, SeatRunner
from .store import TERMINAL, RunStore, normalize_case

DEFAULT_PORT = 8881
DEFAULT_DB = Path.home() / ".grokbot_control" / "runs.sqlite3"
DEFAULT_SEAT = os.environ.get("GROKBOT_CONTROL_SEAT", "SPARK")
DEFAULT_MIN_FREE_MB = 0


class MemoryGuardError(RuntimeError):
    """Refuse to start a seat run while free physical RAM is under the floor."""

    def __init__(self, *, free_mb: int, min_free_mb: int) -> None:
        self.free_mb = int(free_mb)
        self.min_free_mb = int(min_free_mb)
        super().__init__(
            "memory_guard: free_physical_mb=%d under min_free_mb=%d"
            % (self.free_mb, self.min_free_mb)
        )


class Controller:
    def __init__(
        self,
        store: RunStore,
        runner: SeatRunner,
        *,
        min_free_mb: int = DEFAULT_MIN_FREE_MB,
        free_mb_fn=None,
    ) -> None:
        self.store = store
        self.runner = runner
        self.min_free_mb = max(0, int(min_free_mb))
        self._free_mb_fn = free_mb_fn or free_physical_mb
        self._cancel: dict[str, threading.Event] = {}
        self._lock = threading.RLock()
        self._held_refused = 0

    def memory_guard(self) -> dict:
        free = self._free_mb_fn()
        holding = (
            self.min_free_mb > 0
            and free is not None
            and int(free) < self.min_free_mb
        )
        return {
            "min_free_mb": self.min_free_mb,
            "free_physical_mb": free,
            "holding": bool(holding),
            "held_refused": self._held_refused,
            "note": "0 disables; unreadable free never holds",
        }

    def _guard_or_raise(self) -> None:
        if self.min_free_mb <= 0:
            return
        free = self._free_mb_fn()
        if free is None:
            return
        if int(free) < self.min_free_mb:
            with self._lock:
                self._held_refused += 1
            raise MemoryGuardError(free_mb=int(free), min_free_mb=self.min_free_mb)

    def submit(
        self,
        *,
        pool_id: str,
        prompt: str,
        seat: str | None = None,
        session_id: str | None = None,
        parent_run_id: str | None = None,
        async_mode: bool = True,
        case: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        pool = require_pool(pool_id)
        seat_name = (seat or DEFAULT_SEAT).strip() or DEFAULT_SEAT
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be nonempty UTF-8 text")
        normalized_case = normalize_case(case)
        self._guard_or_raise()
        created = self.store.create_run(
            pool_id=pool,
            seat=seat_name,
            prompt=prompt,
            session_id=session_id,
            parent_run_id=parent_run_id,
            case=normalized_case,
        )
        cancel = threading.Event()
        with self._lock:
            self._cancel[created["run_id"]] = cancel
        thread = threading.Thread(
            target=self._execute,
            args=(created["run_id"], cancel),
            name="grokbot-control-%s" % created["run_id"][:8],
            daemon=True,
        )
        thread.start()
        if async_mode:
            out = {
                "ok": True,
                "run_id": created["run_id"],
                "session_id": created["session_id"],
                "status": "queued",
                "pool_id": pool,
                "seat": seat_name,
                "case": created.get("case"),
            }
            return out
        run = self.store.wait_run(created["run_id"], wait_ms=120_000)
        return {"ok": run["status"] == "completed", **run}

    def follow_up(
        self,
        run_id: str,
        prompt: str,
        *,
        async_mode: bool = True,
    ) -> dict[str, Any]:
        parent = self.store.get_run(run_id)
        return self.submit(
            pool_id=parent["pool_id"],
            prompt=prompt,
            seat=parent["seat"],
            session_id=parent["session_id"],
            parent_run_id=run_id,
            async_mode=async_mode,
            case=parent.get("case"),
        )

    def cancel(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        with self._lock:
            ev = self._cancel.get(run_id)
            if ev is not None:
                ev.set()
        if run["status"] in TERMINAL:
            return {"ok": True, **run, "note": "already_terminal"}
        updated = self.store.set_status(run_id, "cancelled")
        return {"ok": True, **updated}

    def _execute(self, run_id: str, cancel: threading.Event) -> None:
        try:
            run = self.store.get_run(run_id)
            self.store.set_status(run_id, "running")
            session = self.store.get_session(run["session_id"])
            history = [
                r
                for r in session["runs"]
                if r["run_id"] != run_id and r["status"] == "completed"
            ]
            if cancel.is_set():
                self.store.set_status(run_id, "cancelled")
                return
            result = self.runner.execute(
                run_id=run_id,
                session_id=run["session_id"],
                pool_id=run["pool_id"],
                seat=run["seat"],
                prompt=run["prompt"],
                history=history,
                cancel_event=cancel,
            )
            if result.cancelled or cancel.is_set():
                self.store.set_status(run_id, "cancelled")
                return
            self.store.set_status(
                run_id,
                "completed",
                result_text=result.result_text,
                attribution=result.attribution,
            )
        except Exception as exc:
            try:
                self.store.set_status(
                    run_id,
                    "error",
                    error="%s: %s" % (type(exc).__name__, exc),
                )
            except Exception:
                pass
        finally:
            with self._lock:
                self._cancel.pop(run_id, None)
                try:
                    ended = self.store.get_run(run_id)
                    busy = any(self.store.get_run(other).get("seat") == ended.get("seat")
                               for other in self._cancel)
                    with self.store._lock:
                        outstanding = self.store._db.execute(
                            "SELECT 1 FROM runs WHERE seat=? AND run_id<>? "
                            "AND status IN ('queued','running','interrupted') LIMIT 1",
                            (ended.get("seat"), run_id)).fetchone()
                    configured = (isinstance(self.runner, InProcessSeatRunner)
                                  and callable(self.runner._handler))
                    available = configured and not busy and outstanding is None
                except Exception:
                    ended, available = None, False
            # A cancellation request is not exit. This point is reached only
            # after execute returned/unwound, and never calls back under locks.
            if ended is not None and ended.get("status") in TERMINAL:
                try:
                    self._notify_swarm_exit(ended, worker_available=available,
                                           execution_road="configured_handler" if configured else "unconfigured")
                except Exception as exc:
                    logging.getLogger(__name__).warning(
                        "Canonical exit notification deferred: %s", type(exc).__name__)

    @staticmethod
    def _notify_swarm_exit(run, *, worker_available, execution_road):
        """Reuse an existing local center; retain exact handles, never run text."""
        state = Path(os.environ.get("COMMONS_COMMAND_CENTER_STATE",
                                    str(Path.home() / ".commons" / "command-center")))
        database = state / "command-center.sqlite3"
        if not database.is_file():
            return {"status": "unavailable", "reason": "existing_command_center_missing"}
        runtime_ids = set()
        db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            rows = db.execute("SELECT runtime,summary FROM operations "
                              "WHERE kind='tool' AND name='grokbot_submit' AND summary LIKE ?",
                              ("%" + run["run_id"] + "%",))
            for runtime_id, raw in rows:
                summary = json.loads(raw)
                bound = summary.get("swarm") or {}
                if (runtime_id and bound.get("task_key") and bound.get("worker") == run.get("seat")
                        and any(ref.get("key") == "run_id" and ref.get("value") == run["run_id"]
                                for ref in summary.get("provider_refs", []))):
                    runtime_ids.add(runtime_id)
            if not runtime_ids and db.execute(
                    "SELECT 1 FROM records WHERE kind='runtimes' AND id='shared-equipment'").fetchone():
                # The callback can precede the submit receipt's run_id. Retain
                # scoped metadata now; consuming still requires its exact ID.
                runtime_ids.add("shared-equipment")
        finally:
            db.close()
        if not runtime_ids:
            return {"status": "unavailable", "reason": "existing_runtime_missing"}
        from integrations.command_center.core import CommandCenter
        from integrations.command_center.swarm_lifecycle import observe_terminal
        center = CommandCenter(state, initialize=False)
        event = {key: run[key] for key in ("run_id", "session_id", "pool_id", "seat", "status", "updated_at")
                 if key in run}
        event.update(upstream_terminal=True, worker_available=bool(worker_available),
                     execution_road=execution_road)
        return [observe_terminal(center, "grokbot", event, runtime_id=runtime_id)
                for runtime_id in sorted(runtime_ids)]


class Gateway(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        controller: Controller,
    ) -> None:
        super().__init__(address, Handler)
        self.controller = controller


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: Gateway

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
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

    def _read_json(self) -> dict[str, Any]:
        size = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(size).decode("utf-8") if size else "{}"
        value = json.loads(raw or "{}")
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    @staticmethod
    def _qi(query: dict[str, list[str]], name: str, default: int) -> int:
        return int((query.get(name) or [default])[0])

    def do_GET(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        ctrl = self.server.controller
        try:
            if parsed.path in ("/", "/health"):
                self._send(
                    200,
                    {
                        "ok": True,
                        "service": "commons-grokbot-control",
                        "harness": HARNESS,
                        "pools": list_pools(),
                        "default_pool_id": DEFAULT_POOL_ID,
                        "default_seat": DEFAULT_SEAT,
                        "event_cursor": ctrl.store.cursor,
                        "memory_guard": ctrl.memory_guard(),
                        "listen_note": "GrokBot pools only; not grok.com; not Cursor cloud",
                    },
                )
                return
            if parsed.path == "/v1/pools":
                self._send(
                    200,
                    {
                        "ok": True,
                        "pools": list_pools(),
                        "cite": "clans.json#grokbot; p/cursor-lead-two-grokbot-accounts-cite-20260902-01.md",
                    },
                )
                return
            if parsed.path == "/v1/events":
                cursor = max(0, self._qi(query, "after", 0))
                limit = min(200, max(1, self._qi(query, "limit", 50)))
                wait_ms = min(55_000, max(0, self._qi(query, "wait_ms", 0)))
                pool = (query.get("pool_id") or [None])[0]
                events = ctrl.store.events_after(
                    cursor, pool_id=pool, limit=limit, wait_ms=wait_ms
                )
                next_cursor = max([cursor] + [int(e["event_id"]) for e in events])
                self._send(
                    200,
                    {"ok": True, "events": events, "next_cursor": next_cursor},
                )
                return
            if parsed.path.startswith("/v1/runs/"):
                run_id = parsed.path[len("/v1/runs/") :].strip("/")
                if "/" in run_id:
                    self._send(404, {"ok": False, "error": "not_found"})
                    return
                wait_ms = min(55_000, max(0, self._qi(query, "wait_ms", 0)))
                try:
                    run = (
                        ctrl.store.wait_run(run_id, wait_ms)
                        if wait_ms
                        else ctrl.store.get_run(run_id)
                    )
                except KeyError:
                    self._send(404, {"ok": False, "error": "run_not_found"})
                    return
                self._send(200, {"ok": True, **run})
                return
            if parsed.path.startswith("/v1/sessions/"):
                sid = parsed.path[len("/v1/sessions/") :].strip("/")
                try:
                    session = ctrl.store.get_session(sid)
                except KeyError:
                    self._send(404, {"ok": False, "error": "session_not_found"})
                    return
                self._send(200, {"ok": True, **session})
                return
            self._send(404, {"ok": False, "error": "not_found"})
        except Exception as exc:
            self._send(
                502,
                {"ok": False, "error": type(exc).__name__, "message": str(exc)},
            )

    def do_POST(self) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        ctrl = self.server.controller
        try:
            if parsed.path == "/v1/runs":
                payload = self._read_json()
                result = ctrl.submit(
                    pool_id=payload.get("pool_id") or DEFAULT_POOL_ID,
                    prompt=str(payload.get("prompt") or ""),
                    seat=payload.get("seat"),
                    async_mode=bool(payload.get("async", True)),
                    case=payload.get("case"),
                )
                code = 202 if result.get("status") == "queued" else 200
                self._send(code, result)
                return
            if parsed.path.endswith("/follow-up") and parsed.path.startswith(
                "/v1/runs/"
            ):
                mid = parsed.path[len("/v1/runs/") : -len("/follow-up")]
                run_id = mid.strip("/")
                payload = self._read_json()
                result = ctrl.follow_up(
                    run_id,
                    str(payload.get("prompt") or ""),
                    async_mode=bool(payload.get("async", True)),
                )
                code = 202 if result.get("status") == "queued" else 200
                self._send(code, result)
                return
            if parsed.path.endswith("/cancel") and parsed.path.startswith("/v1/runs/"):
                mid = parsed.path[len("/v1/runs/") : -len("/cancel")]
                run_id = mid.strip("/")
                result = ctrl.cancel(run_id)
                self._send(200, result)
                return
            self._send(404, {"ok": False, "error": "not_found"})
        except KeyError:
            self._send(404, {"ok": False, "error": "run_not_found"})
        except MemoryGuardError as exc:
            self._send(
                503,
                {
                    "ok": False,
                    "error": "memory_guard",
                    "message": str(exc),
                    "free_physical_mb": exc.free_mb,
                    "min_free_mb": exc.min_free_mb,
                    "memory_guard": self.server.controller.memory_guard(),
                },
            )
        except Exception as exc:
            self._send(
                400,
                {"ok": False, "error": type(exc).__name__, "message": str(exc)},
            )


def build_server(
    *,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
    db_path: Path | None = None,
    runner: SeatRunner | None = None,
    mode: str = "inprocess",
    min_free_mb: int | None = None,
    free_mb_fn=None,
) -> Gateway:
    store = RunStore(db_path or DEFAULT_DB)
    if runner is None:
        if mode == "echo":
            runner = EchoSeatRunner()
        else:
            runner = InProcessSeatRunner()
    controller = Controller(
        store,
        runner,
        min_free_mb=resolve_min_free_mb(min_free_mb),
        free_mb_fn=free_mb_fn,
    )
    return Gateway((host, port), controller)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument(
        "--mode",
        choices=("inprocess", "echo"),
        default="inprocess",
        help="inprocess=live GrokBot seat in this process; echo=hermetic",
    )
    parser.add_argument(
        "--min-free-mb",
        type=int,
        default=1024,
        help="Refuse new runs while free physical RAM is under this MB (0=off; default 1024)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    server = build_server(
        host=args.host,
        port=args.port,
        db_path=args.db,
        mode=args.mode,
        min_free_mb=args.min_free_mb,
    )
    print(
        json.dumps(
            {
                "ready": True,
                "listen": "http://%s:%d" % (args.host, args.port),
                "mode": args.mode,
                "pools": list_pools(),
                "service": "commons-grokbot-control",
            },
            separators=(",", ":"),
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
        server.controller.store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
