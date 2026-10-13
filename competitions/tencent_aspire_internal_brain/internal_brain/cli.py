from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .core import AuditError, AuthorizationError, BrainError, InternalBrain, SchemaError, strict_loads, verify_audit
from .replay import OPERATIONS_SCHEMA, artifact_summary, execute_session, replay_session


def _load(path: str) -> Any:
    return strict_loads(Path(path).read_text("utf-8"))


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def _emit(value: Any) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False))


def _output_paths(outputs: dict[str, str | None], inputs: list[str]) -> dict[str, Path]:
    input_paths = {Path(path).resolve() for path in inputs}
    resolved: dict[str, Path] = {}
    seen: set[Path] = set()
    for name, raw_path in outputs.items():
        if raw_path is None:
            continue
        original = Path(raw_path)
        path = original.resolve()
        if path in input_paths:
            raise SchemaError(f"{name} output aliases an input: {raw_path}")
        if path in seen:
            raise SchemaError(f"{name} output aliases another output: {raw_path}")
        if original.is_symlink() or path.exists():
            raise FileExistsError(f"refusing to replace existing {name} output: {raw_path}")
        seen.add(path)
        resolved[name] = path
    return resolved


def _write_new(outputs: dict[str, Path], values: dict[str, Any]) -> dict[str, str]:
    # Serialize first and reserve destinations exclusively. If writing fails,
    # remove only paths still identifying files created by this call.
    serialized = {name: _json(value) for name, value in values.items() if name in outputs}
    opened: list[tuple[Path, Any, os.stat_result]] = []
    try:
        for name in serialized:
            path = outputs[name]
            stream = path.open("x", encoding="utf-8", newline="\n")
            opened.append((path, stream, os.fstat(stream.fileno())))
        for (_, stream, _), value in zip(opened, serialized.values()):
            stream.write(value)
            stream.flush()
        for _, stream, _ in opened:
            stream.close()
    except (OSError, UnicodeError):
        for path, stream, created in opened:
            try:
                stream.close()
            except (OSError, UnicodeError):
                pass
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                    path.unlink()
            except OSError:
                pass
        raise
    return {name: str(outputs[name]) for name in serialized}


def _audit_actor(args: argparse.Namespace) -> str:
    if not args.audit_actor:
        raise SchemaError("retaining an audit or session requires --audit-actor with audit:read permission")
    return args.audit_actor


def _operation_error(outcome: dict[str, Any]) -> dict[str, Any]:
    error = outcome["error"]
    return {"error": error["type"], **{key: value for key, value in error.items() if key != "type"}}


def _single_operation(args: argparse.Namespace) -> int:
    inputs = [args.bundle, args.request if args.command == "query" else args.document]
    outputs = _output_paths(
        {
            "audit": args.audit_out,
            "run": args.run_out,
            "bundle": getattr(args, "bundle_out", None),
        },
        inputs,
    )
    bundle = _load(args.bundle)
    if args.command == "query":
        operation = {"operation": "query", "request": _load(args.request)}
    else:
        operation = {
            "operation": "ingest",
            "request": {
                "tenant_id": args.tenant,
                "actor_user_id": args.actor,
                "document": _load(args.document),
            },
        }
    if args.run_out or args.audit_out:
        artifact, final_bundle = execute_session(
            bundle, {"schema": OPERATIONS_SCHEMA, "operations": [operation]},
            audit_actor_user_id=_audit_actor(args),
        )
        outcome = artifact["outcomes"][0]
        values = {"run": artifact, "audit": artifact["audit"]["events"]}
        if outcome["status"] == "ok":
            values["bundle"] = final_bundle
        written = _write_new(outputs, values)
        if args.run_out:
            _emit({"outcome": outcome, "outputs": written, **artifact_summary(artifact)})
        else:
            _emit(outcome["receipt"] if outcome["status"] == "ok" else _operation_error(outcome))
        return artifact["summary"]["exit_code"]
    brain = InternalBrain(bundle)
    if args.command == "query":
        result = brain.query(operation["request"])
    else:
        result = brain.ingest(**operation["request"])
    if "bundle" in outputs:
        _write_new(outputs, {"bundle": brain.export_bundle()})
    _emit(result)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Local trusted-operator retrieval, ingestion and replay; tenant actors are declared, not authenticated."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    query = sub.add_parser("query", help="run an authorized deterministic retrieval")
    query.add_argument("bundle")
    query.add_argument("request")
    ingest = sub.add_parser("ingest", help="ingest one document and retain a new normalized bundle")
    ingest.add_argument("bundle")
    ingest.add_argument("document")
    ingest.add_argument("--tenant", required=True)
    ingest.add_argument("--actor", required=True)
    ingest.add_argument("--bundle-out", required=True)
    for command in (query, ingest):
        command.add_argument("--audit-actor", help="declared user with audit:read; required for audit/session export")
        command.add_argument("--audit-out", help="new file for the exported chain")
        command.add_argument("--run-out", help="new file for a replayable single-operation session")
    session = sub.add_parser("session", help="execute ordered query/ingest operations and retain a replay artifact")
    session.add_argument("bundle")
    session.add_argument("operations")
    session.add_argument("--audit-actor", required=True)
    session.add_argument("--run-out", required=True)
    session.add_argument("--audit-out")
    replay = sub.add_parser("replay", help="re-execute and compare a retained operation session")
    replay.add_argument("run")
    replay.add_argument("--audit-actor", required=True)
    replay.add_argument("--expected-artifact-sha256", help="optional independently retained trusted digest")
    verify = sub.add_parser("verify-audit", help="verify chain consistency, optionally against a retained checkpoint")
    verify.add_argument("audit")
    verify.add_argument("--expected-head-digest")
    verify.add_argument("--expected-event-count", type=int)
    validate = sub.add_parser("validate", help="validate and print the full normalized local bundle")
    validate.add_argument("bundle")
    args = parser.parse_args(argv)
    try:
        if args.command in ("query", "ingest"):
            return _single_operation(args)
        if args.command == "session":
            outputs = _output_paths(
                {"run": args.run_out, "audit": args.audit_out}, [args.bundle, args.operations]
            )
            artifact, _ = execute_session(
                _load(args.bundle), _load(args.operations), audit_actor_user_id=args.audit_actor
            )
            written = _write_new(outputs, {"run": artifact, "audit": artifact["audit"]["events"]})
            _emit({"outputs": written, **artifact_summary(artifact)})
            return artifact["summary"]["exit_code"]
        if args.command == "replay":
            result = replay_session(
                _load(args.run), audit_actor_user_id=args.audit_actor,
                expected_artifact_sha256=args.expected_artifact_sha256,
            )
            _emit(result)
            return result["summary"]["exit_code"]
        if args.command == "verify-audit":
            raw = _load(args.audit)
            if not isinstance(raw, list):
                raise SchemaError("audit file must contain a JSON list")
            checkpoint = {}
            if args.expected_head_digest is not None:
                checkpoint["expected_head_digest"] = args.expected_head_digest
            if args.expected_event_count is not None:
                checkpoint["expected_event_count"] = args.expected_event_count
            _emit(verify_audit(raw, **checkpoint))
            return 0
        brain = InternalBrain(_load(args.bundle))
        normalized = brain.export_bundle()
        _emit({
            "valid": True,
            "tenant_id": brain.tenant_id,
            "roles": len(brain.roles),
            "users": len(brain.users),
            "documents": len(brain.documents),
            "bundle": normalized,
        })
        return 0
    except AuthorizationError as exc:
        _emit({"error": "AuthorizationError", "code": exc.code, "message": str(exc)})
        return 3
    except (SchemaError, AuditError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        _emit({"error": type(exc).__name__, "message": str(exc)})
        return 2
    except BrainError as exc:
        _emit({"error": type(exc).__name__, "message": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
