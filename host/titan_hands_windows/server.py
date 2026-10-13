#!/usr/bin/env python3
"""JSONL server for the native Windows TITAN Hands backend."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Mapping, Protocol

from .protocol import PROTOCOL_VERSION, DeltaTracker, ProtocolError, failure
from .retarget import canonical_type, focused_id, needs_tree, prepare_action, run_assert, verify_after


class Backend(Protocol):
    def request(self, message: Mapping[str, Any]) -> dict[str, Any]: ...

    def close(self) -> None: ...


class PowerShellBridge:
    """Keeps AutomationElement references alive inside one PowerShell process."""

    def __init__(self, script: Path | None = None) -> None:
        self.script = script or Path(__file__).with_name("backend.ps1")
        executable = os.environ.get("TITAN_HANDS_POWERSHELL", "powershell.exe")
        self.process = subprocess.Popen(
            [
                executable,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.script),
                "-Stdio",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._lock = threading.Lock()

    def request(self, message: Mapping[str, Any]) -> dict[str, Any]:
        if self.process.poll() is not None:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise RuntimeError(f"Windows backend exited: {stderr.strip()}")
        line = json.dumps(dict(message), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            assert self.process.stdin is not None
            assert self.process.stdout is not None
            self.process.stdin.write(line + "\n")
            self.process.stdin.flush()
            response = self.process.stdout.readline()
        if not response:
            stderr = self.process.stderr.read() if self.process.stderr else ""
            raise RuntimeError(f"Windows backend returned no response: {stderr.strip()}")
        parsed = json.loads(response)
        if not isinstance(parsed, dict):
            raise RuntimeError("Windows backend response was not an object")
        return parsed

    def close(self) -> None:
        if self.process.poll() is not None:
            return
        try:
            self.request({"op": "shutdown"})
        except Exception:
            self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()


class TitanHandsServer:
    def __init__(self, backend: Backend | None = None) -> None:
        self.backend = backend or PowerShellBridge()
        self.tracker = DeltaTracker()
        self._handle_lock = threading.RLock()

    def close(self) -> None:
        with self._handle_lock:
            self.backend.close()

    def _observe(self, request: Mapping[str, Any]) -> dict[str, Any]:
        raw = self.backend.request(
            {
                "op": "snapshot",
                "max_nodes": int(request.get("max_nodes") or 600),
                "max_depth": int(request.get("max_depth") or 8),
                "include_offscreen": bool(request.get("include_offscreen", False)),
            }
        )
        if not raw.get("ok"):
            return raw
        return self.tracker.observe(raw)

    def _bind_input_target(self, raw_action: Mapping[str, Any]) -> dict[str, Any]:
        """Bind input to a control from the snapshot prepared in this request."""
        action = dict(raw_action)
        action_type = canonical_type(action)
        nodes = self.tracker.current_nodes()
        meta = self.tracker.current_meta()
        target_id = str(action.get("id") or "").strip()

        # prepare_action already retargeted labels and stale ids using the
        # fresh tree. Untargeted keys bind to the exact current focused node.
        if not target_id and action_type in {"set_value", "type_text", "key"}:
            target_id = focused_id(nodes, meta)
            if target_id:
                action["id"] = target_id

        target = nodes.get(target_id) if target_id else None
        if target is None:
            return failure(
                "INPUT_TARGET_MISSING",
                "text/key input requires a control present in the fresh UIA snapshot",
                target_id=target_id,
            )

        if action_type in {"set_value", "type_text"}:
            role = str(target.get("role") or "").lower()
            # retarget.py intentionally recognizes Document for its broad
            # editable matching; native typing is limited to actual edit fields.
            if role not in {"edit", "combobox", "spinner", "textbox"}:
                return failure(
                    "INPUT_TARGET_NOT_EDITABLE",
                    "text input requires a scoped Edit, ComboBox, Spinner, or TextBox control",
                    target_id=target_id,
                    role=role,
                )
            if action_type == "set_value" and "set_value" not in {
                str(item) for item in target.get("actions", [])
            }:
                return failure(
                    "VALUE_PATTERN_UNAVAILABLE",
                    "set_value requires a supported per-control ValuePattern",
                    target_id=target_id,
                )

        if action_type == "key":
            current_focus = focused_id(nodes, meta)
            if not current_focus or target_id != current_focus:
                return failure(
                    "INPUT_FOCUS_MISMATCH",
                    "key input must target the control reported focused by the fresh UIA snapshot",
                    target_id=target_id,
                    focus_id=current_focus,
                )
        return action

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        # A fresh snapshot, target resolution, backend action, and post-action
        # observation form one transaction because the PowerShell element map
        # is replaced on every snapshot.
        with self._handle_lock:
            return self._handle_serialized(request)

    def _handle_serialized(self, request: Mapping[str, Any]) -> dict[str, Any]:
        try:
            if not isinstance(request, Mapping):
                raise ProtocolError("request must be an object")
            op = str(request.get("op") or "").strip().lower()
            if op == "capabilities":
                backend = self.backend.request({"op": "capabilities"})
                if not backend.get("ok"):
                    return backend
                backend_actions = [str(item) for item in (backend.get("actions") or [])]
                extra = ["assert", "verify", "check", "set_text", "type", "tap", "clear"]
                advertised = list(dict.fromkeys([*backend_actions, *extra]))
                return {
                    "ok": True,
                    "protocol": PROTOCOL_VERSION,
                    "kind": "capabilities",
                    "platform": "windows",
                    "transport": "jsonl",
                    "implementation": "windows-uia-adapter",
                    "retarget": True,
                    "verify_after": True,
                    "actions": advertised,
                    "backend": backend,
                }
            if op == "observe":
                return self._observe(request)
            if op == "reset":
                self.tracker.reset()
                return {"ok": True, "protocol": PROTOCOL_VERSION, "kind": "reset"}
            if op == "capture":
                result = self.backend.request(dict(request))
                result.setdefault("protocol", PROTOCOL_VERSION)
                return result
            if op == "act":
                action = request.get("action")
                if not isinstance(action, Mapping):
                    raise ProtocolError("act requires an action object")
                requested_type = canonical_type(action)
                input_requested = requested_type in {"set_value", "type_text", "key", "clear"}
                if input_requested:
                    fresh = self._observe(request)
                    if not fresh.get("ok"):
                        return failure(
                            "INPUT_OBSERVE_FAILED",
                            "fresh focus observation failed; no input was sent",
                            backend_failure=fresh.get("failure_reason") or fresh.get("kind"),
                        )
                elif needs_tree(action) and not self.tracker.current_nodes():
                    self._observe(request)
                prepared = prepare_action(
                    action, self.tracker.current_nodes(), self.tracker.current_meta()
                )
                if prepared.failure is not None:
                    return prepared.failure
                if input_requested:
                    bound = self._bind_input_target(prepared.action)
                    if bound.get("ok") is False:
                        return bound
                    prepared.action = bound
                expect = request.get("expect")
                if expect is None:
                    expect = action.get("expect")
                if prepared.local:
                    result = run_assert(
                        prepared.action, self.tracker.current_nodes(), self.tracker.current_meta()
                    )
                    result.setdefault("protocol", PROTOCOL_VERSION)
                    if prepared.retarget:
                        result["retarget"] = prepared.retarget
                    if request.get("observe_after", True):
                        result["observation"] = self._observe(request)
                    return result
                before_nodes = dict(self.tracker.current_nodes())
                result = self.backend.request({"op": "action", "action": prepared.action})
                result.setdefault("protocol", PROTOCOL_VERSION)
                if prepared.retarget:
                    result["retarget"] = prepared.retarget
                if result.get("ok") and request.get("observe_after", True):
                    result["observation"] = self._observe(request)
                    result["verification"] = verify_after(
                        prepared.action,
                        before_nodes=before_nodes,
                        after_nodes=self.tracker.current_nodes(),
                        observation=result["observation"],
                        expect=expect,
                        meta=self.tracker.current_meta(),
                    )
                elif result.get("ok"):
                    result["verification"] = {
                        "kind": "verification",
                        "status": "unchecked",
                        "message": "observe_after disabled; action-return is not proof",
                        "checked": [],
                        "ok": False,
                    }
                return result
            return failure("UNKNOWN_OPERATION", f"unknown operation: {op or '<empty>'}")
        except (ProtocolError, TypeError, ValueError) as exc:
            return failure("INVALID_REQUEST", str(exc))
        except Exception as exc:
            return failure("BACKEND_ERROR", str(exc))


def serve_jsonl(server: TitanHandsServer) -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = server.handle(request)
        except json.JSONDecodeError as exc:
            response = failure("INVALID_JSON", str(exc))
        sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="strict")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", help="process one JSON request and exit")
    args = parser.parse_args(argv)
    server = TitanHandsServer()
    try:
        if args.request is not None:
            response = server.handle(json.loads(args.request))
            print(json.dumps(response, ensure_ascii=False, indent=2))
            return 0 if response.get("ok") else 1
        return serve_jsonl(server)
    finally:
        server.close()


if __name__ == "__main__":
    raise SystemExit(main())


