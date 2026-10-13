#!/usr/bin/env python3
"""Tiny operator for the existing Commons claims/feed/seat runtime.

Use --url for the shared command center (one cache and provider quota pool).
Without --url this uses the same canonical state/claims branch through git.
--no-push produces a native GitHub Git Data publication proposal, not custody.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load(path, default=None):
    return json.loads(Path(path).read_text(encoding="utf-8")) if path else default


def shared_request(url, payload):
    """Keep uncertain responses and retry hints; never replay a failed POST."""
    request = urllib.request.Request(url.rstrip("/") + "/api/swarm/tasks",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.load(response)
        if not isinstance(result, dict):
            raise ValueError("Shared service response must be a JSON object")
        return result
    except urllib.error.HTTPError as exc:
        with exc:
            try:
                result = json.loads(exc.read(1048577))
                if not isinstance(result, dict):
                    raise ValueError("JSON object required")
            except (OSError, ValueError, UnicodeError, http.client.HTTPException):
                result = {"error": "http_error", "message": "Shared service error response could not be read as a JSON object"}
            result.update(ok=False, http_status=exc.code)
            if exc.headers.get("Retry-After") is not None:
                result["retry_after_header"] = exc.headers["Retry-After"]
            if exc.code >= 500:
                result.setdefault("status", "uncertain")
    except (OSError, ValueError, UnicodeError, http.client.HTTPException) as exc:
        # An accepted request can lose its response. Do not report definite
        # failure or replay it merely because parsing or transport failed.
        result = {"ok": False, "error": type(exc).__name__, "status": "uncertain",
                  "message": "Read operation state before retrying the original request."}
    if payload.get("operation_id"):
        result["operation_id"] = payload["operation_id"]
    return result


def save_output(path, output):
    """An interrupted receipt save preserves the previous complete result."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".pending", delete=False) as out:
            temporary = out.name
            out.write(output)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--url", default=os.environ.get("COMMONS_SWARM_URL"))
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--worker", default=os.environ.get("COMMONS_SEAT"))
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--output", type=Path, help="write full response to this file")
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync")
    sync.add_argument("--work-snapshot")
    sync.add_argument("--facts")
    sync.add_argument("--events")
    sync.add_argument("--max-calls", type=int, default=4)
    sync.add_argument("--cached", action="store_true", help="ingest existing evidence without provider calls")
    status = commands.add_parser("status")
    status.add_argument("--fresh", action="store_true")
    status.add_argument("--ledger", type=Path,
                        help="read a saved canonical runtime ledger without Git or provider requests")
    status.add_argument("--limit", type=int, default=100)
    status.add_argument("--task", help="exact task identity or GitHub issue/PR URL")
    status.add_argument("--context", action="store_true",
                        help="include the retained event bundle for --task")
    status.add_argument("--state", dest="states", action="append",
                        choices=("OPEN", "ACTIVE", "SHIPPED", "BLOCKED", "SUPERSEDED", "ABANDONED"),
                        help="filter lifecycle state; repeat to include several states")
    status.add_argument("--owner", help="filter current worker by exact name")
    status.add_argument("--after", help="exclusive task-key cursor returned by the previous page")
    for name in ("open", "take", "heartbeat", "release", "ship", "block", "abandon", "next"):
        command = commands.add_parser(name)
        command.add_argument("task", nargs="?")
        command.add_argument("--operation-id")
        command.add_argument("--data", help="JSON operation metadata file (seat, capabilities, artifact, blocker)")
        command.add_argument("--blocker")
        command.add_argument("--next-action")
        command.add_argument("--feed-cursor")
        if name == "release":
            command.add_argument("--expected-started-at",
                                help="current task started_at from status; required here or in --data")
    args = parser.parse_args(argv)
    try:
        if args.command == "sync":
            if not 0 <= args.max_calls <= 20:
                raise ValueError("max-calls must be between 0 and 20")
            payload = {"work_snapshot": load(args.work_snapshot), "provider_facts": load(args.facts, {}),
                       "events": load(args.events, []), "max_calls": args.max_calls,
                       "refresh_providers": not args.cached}
        elif args.command == "status":
            if args.context and not args.task:
                raise ValueError("--context requires --task")
            payload = {"refresh": args.fresh, "limit": args.limit, "worker": args.worker}
            payload.update({key: value for key, value in
                            (("task", args.task), ("states", args.states),
                             ("owner", args.owner), ("after", args.after)) if value is not None})
            if args.context:
                payload["context"] = True
        else:
            payload = load(args.data, {})
            if not isinstance(payload, dict):
                raise ValueError("data must be a JSON object")
            for field, value in (("worker", args.worker), ("task_key", args.task),
                                 ("blocker", args.blocker), ("next_action", args.next_action),
                                 ("feed_cursor", args.feed_cursor),
                                 ("expected_started_at", getattr(args, "expected_started_at", None))):
                if value is not None:
                    payload[field] = value
            operation_id = args.operation_id or payload.get("operation_id")
            if not operation_id:
                # Stable command replays; heartbeats advance in minute buckets.
                from host.swarm_runtime.runtime import now_iso
                seed = {"action": args.command, "payload": payload}
                if args.command in {"heartbeat", "next"}:
                    seed["minute"] = now_iso()[:16]
                operation_id = "cli-" + hashlib.sha256(json.dumps(seed, sort_keys=True).encode()).hexdigest()[:32]
            payload["operation_id"] = operation_id
            print("operation_id=" + operation_id, file=sys.stderr, flush=True)
        if args.command == "status" and args.ledger is not None:
            if args.fresh:
                raise ValueError("--fresh cannot refresh a saved ledger; fetch a newer ledger first")
            from host.swarm_runtime.runtime import read_status
            from host.swarm_runtime.store import _state
            raw = args.ledger.read_bytes()
            state = json.loads(raw.decode("utf-8"))
            if not isinstance(state, dict) or state.get("schema") != "commons-swarm-runtime/v1":
                raise ValueError("--ledger requires a saved canonical swarm runtime ledger")
            result = read_status(_state(state), authority="retained_ledger",
                                 **{key: value for key, value in payload.items() if key != "refresh"})
            result.update(source_path=str(args.ledger),
                          source_ledger_sha256=hashlib.sha256(raw).hexdigest())
        elif args.url:
            if args.no_push:
                raise ValueError("--no-push applies to local Git Data proposals, not shared HTTP operations")
            result = shared_request(args.url, {**payload, "action": args.command})
        else:
            from host.swarm_runtime.runtime import Runtime
            runtime = Runtime(args.root, state_dir=args.state_dir)
            if args.command == "status":
                result = runtime.read(**payload)
            elif args.command == "sync":
                result = runtime.sync(**payload, push=not args.no_push)
            else:
                result = runtime.operate(args.command, payload, push=not args.no_push)
        output = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if args.output:
            try:
                save_output(args.output, output)
            except OSError:
                # Publication may have succeeded. Keep its full receipt even
                # when the requested local destination cannot be replaced.
                print(output, end="")
                print(json.dumps({"ok": False, "error": "output_save_failed",
                                  "output": str(args.output), "receipt": "stdout"}), file=sys.stderr)
                return 2
            print(json.dumps({"ok": result.get("ok"), "published": result.get("published"),
                              "output": str(args.output), "changed": result.get("changed")}))
        else:
            print(output, end="")
        if not result.get("ok", True):
            return 2
        if (result.get("result") or {}).get("rejected"):
            return 2
        return 0
    except Exception as exc:
        from host.swarm_runtime.store import StoreError
        if isinstance(exc, StoreError):
            error = exc.as_dict()
        else:
            error = {"ok": False, "error": type(exc).__name__, "message": str(exc)}
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
