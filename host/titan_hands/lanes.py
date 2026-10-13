"""Thin Commons lanes that speak the TITAN Hands DeltaUI contract.

Computer-use lives in the Windows, Android, and Linux AT-SPI adapters. These
lanes add files, git, Slack #commons, board posts, shell, and browser. They do
not remint the Windows or Android adapters.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import URLError
from urllib.request import Request, urlopen

from relay_manifest import NTFY_HOSTS, NTFY_TOPIC

from host.titan_hands.linux_atspi import LinuxHandsServer
from host.titan_hands_windows.protocol import PROTOCOL_VERSION, DeltaTracker, ProtocolError, failure

# Historical import name from the one-tool stub. Linux AT-SPI is implemented.
LinuxPendingServer = LinuxHandsServer


SLACK_COMMONS = "C0BRGMDQB6G"
PIXELS_NEVER = "never"
PIXELS_ON_DEMAND = "on-demand-only"
PIXELS_NOT_CAPTURED = "not-captured"


class LaneError(RuntimeError):
    def __init__(self, reason: str, message: str, **evidence: Any) -> None:
        super().__init__(message)
        self.reason = reason
        self.evidence = evidence


def _node(node_id: str, role: str, name: str, **extra: Any) -> dict[str, Any]:
    node = {
        "id": str(node_id),
        "parent": str(extra.pop("parent", "")),
        "role": role,
        "name": name,
        "states": list(extra.pop("states", [])),
        "actions": list(extra.pop("actions", [])),
    }
    node.update(extra)
    return node


class _SemanticLane:
    """Shared observe/reset/capabilities shape. Subclasses supply snapshots."""

    platform = ""
    observation = "semantic-delta"
    pixels = PIXELS_NEVER
    actions: tuple[str, ...] = ()

    def __init__(self) -> None:
        self.tracker = DeltaTracker()

    def close(self) -> None:
        return None

    def _snapshot(self, request: Mapping[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _act(self, action: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _capture(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return failure(
            "PIXEL_UNSUPPORTED",
            f"{self.platform} has no framebuffer; pixels exist only on computer-use/browser capture",
            platform=self.platform,
        )

    def _capabilities(self) -> dict[str, Any]:
        return {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "kind": "capabilities",
            "platform": self.platform,
            "observation": self.observation,
            "pixels": self.pixels,
            "actions": list(self.actions),
        }

    def handle(self, request: Mapping[str, Any]) -> dict[str, Any]:
        try:
            if not isinstance(request, Mapping):
                raise ProtocolError("request must be an object")
            op = str(request.get("op") or "").strip().lower()
            if op == "capabilities":
                return self._capabilities()
            if op == "observe":
                return self.tracker.observe(self._snapshot(request))
            if op == "reset":
                self.tracker.reset()
                return {"ok": True, "protocol": PROTOCOL_VERSION, "kind": "reset", "platform": self.platform}
            if op == "capture":
                return self._capture(request)
            if op == "act":
                action = request.get("action")
                if not isinstance(action, Mapping):
                    raise ProtocolError("act requires an action object")
                result = self._act(action, request)
                if result.get("ok") and request.get("observe_after", True):
                    result["observation"] = self.tracker.observe(self._snapshot(request))
                return result
            return failure("UNKNOWN_OPERATION", f"unknown operation: {op or '<empty>'}")
        except LaneError as exc:
            return failure(exc.reason, str(exc), **exc.evidence)
        except (ProtocolError, TypeError, ValueError) as exc:
            return failure("INVALID_REQUEST", str(exc))
        except Exception as exc:
            return failure("BACKEND_ERROR", str(exc))


class FilesServer(_SemanticLane):
    platform = "files"
    observation = "filesystem-semantic-delta"
    actions = ("read", "write", "list")

    def __init__(self, root: str | Path | None = None) -> None:
        super().__init__()
        self.root = Path(root or os.getcwd()).resolve()

    def _resolve(self, request: Mapping[str, Any], action: Mapping[str, Any] | None = None) -> Path:
        raw = ""
        if action:
            raw = str(action.get("path") or action.get("file") or "")
        if not raw:
            raw = str(request.get("path") or "")
        path = (self.root / raw).resolve() if raw else self.root
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ProtocolError(f"path escapes files root: {path}") from exc
        return path

    def _snapshot(self, request: Mapping[str, Any]) -> dict[str, Any]:
        path = self._resolve(request)
        nodes = [_node(str(self.root), "Directory", str(self.root), actions=["list"])]
        if path.is_dir():
            for child in sorted(path.iterdir(), key=lambda item: item.name)[:400]:
                role = "Directory" if child.is_dir() else "File"
                nodes.append(
                    _node(
                        str(child),
                        role,
                        child.name,
                        parent=str(path),
                        actions=["list"] if role == "Directory" else ["read", "write"],
                    )
                )
        elif path.exists():
            nodes.append(
                _node(str(path), "File", path.name, parent=str(path.parent), actions=["read", "write"])
            )
        return {
            "ok": True,
            "nodes": nodes,
            "kind": "semantic_snapshot",
            "platform": "files",
            "root": str(self.root),
            "pixels": PIXELS_NOT_CAPTURED,
        }

    def _act(self, action: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
        action_type = str(action.get("type") or "").strip().lower()
        path = self._resolve(request, action)
        if action_type == "list":
            names = sorted(item.name for item in path.iterdir()) if path.is_dir() else []
            return {
                "ok": True,
                "protocol": PROTOCOL_VERSION,
                "kind": "action_outcome",
                "platform": "files",
                "action": action_type,
                "path": str(path),
                "names": names,
            }
        if action_type == "read":
            if not path.is_file():
                raise LaneError("PATH_MISS", f"file is not present: {path}")
            return {
                "ok": True,
                "protocol": PROTOCOL_VERSION,
                "kind": "action_outcome",
                "platform": "files",
                "action": action_type,
                "path": str(path),
                "value": path.read_text(encoding="utf-8", errors="replace"),
            }
        if action_type == "write":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(action.get("text") or action.get("value") or ""), encoding="utf-8")
            return {
                "ok": True,
                "protocol": PROTOCOL_VERSION,
                "kind": "action_outcome",
                "platform": "files",
                "action": action_type,
                "path": str(path),
            }
        return failure("UNKNOWN_OPERATION", f"files lane has no handler for {action_type or '<empty>'}")


class GitServer(_SemanticLane):
    platform = "git"
    observation = "git-semantic-delta"
    actions = ("status", "log", "diff", "show", "add", "commit")

    def __init__(
        self,
        cwd: str | Path | None = None,
        run: Callable[[list[str]], str] | None = None,
    ) -> None:
        super().__init__()
        self.cwd = Path(cwd or os.getcwd()).resolve()
        self.run = run

    def _git(self, *args: str) -> str:
        if self.run is not None:
            return self.run(list(args))
        completed = subprocess.run(
            ["git", *args],
            cwd=self.cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            raise LaneError(
                "COMMAND_FAILED",
                (completed.stderr or completed.stdout or "git failed").strip(),
                returncode=completed.returncode,
            )
        return completed.stdout

    def _snapshot(self, request: Mapping[str, Any]) -> dict[str, Any]:
        head = self._git("rev-parse", "HEAD").strip()
        branch = self._git("rev-parse", "--abbrev-ref", "HEAD").strip()
        porcelain = self._git("status", "--porcelain")
        nodes = [
            _node("git:repo", "Document", str(self.cwd), actions=["status", "log", "diff"]),
            _node("git:head", "Text", head, parent="git:repo", value=head),
            _node("git:branch", "Text", branch, parent="git:repo", value=branch),
        ]
        for line in porcelain.splitlines():
            if len(line) < 4:
                continue
            path = line[3:]
            nodes.append(
                _node(
                    f"git:file:{path}",
                    "File",
                    path,
                    parent="git:repo",
                    value=line[:2].strip(),
                    actions=["diff", "add"],
                )
            )
        return {
            "ok": True,
            "nodes": nodes,
            "kind": "semantic_snapshot",
            "platform": "git",
            "head": head,
            "branch": branch,
            "pixels": PIXELS_NOT_CAPTURED,
        }

    def _act(self, action: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
        action_type = str(action.get("type") or "").strip().lower()
        if action_type == "status":
            output = self._git("status", "--porcelain")
        elif action_type == "log":
            output = self._git("log", "-5", "--oneline")
        elif action_type == "diff":
            path = str(action.get("path") or "")
            output = self._git("diff", "--", path) if path else self._git("diff")
        elif action_type == "show":
            output = self._git("show", str(action.get("value") or "HEAD"))
        elif action_type == "add":
            path = str(action.get("path") or action.get("file") or "").strip()
            if not path:
                raise ProtocolError("git add requires path")
            output = self._git("add", "--", path)
        elif action_type == "commit":
            message = str(action.get("text") or action.get("value") or "").strip()
            if not message:
                raise ProtocolError("git commit requires text")
            output = self._git("commit", "-m", message)
        else:
            return failure("UNKNOWN_OPERATION", f"git lane has no handler for {action_type or '<empty>'}")
        return {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "kind": "action_outcome",
            "platform": "git",
            "action": action_type,
            "value": output,
        }


class SlackServer(_SemanticLane):
    platform = "slack"
    observation = "slack-semantic-delta"
    actions = ("post", "send")

    def __init__(
        self,
        history: Callable[[], list[Mapping[str, Any]]] | None = None,
        post: Callable[[str], Mapping[str, Any]] | None = None,
        channel: str | None = None,
    ) -> None:
        super().__init__()
        self._history = history
        self._post = post
        self.channel = channel or os.environ.get("COMMONS_SLACK_CHANNEL") or SLACK_COMMONS

    def _configured(self) -> bool:
        if self._history is not None or self._post is not None:
            return True
        return bool(
            os.environ.get("COMMONS_SLACK_BOT_TOKEN")
            or os.environ.get("SLACK_BOT_TOKEN")
            or os.environ.get("COMMONS_SLACK_WEBHOOK_URL")
            or os.environ.get("SLACK_WEBHOOK_URL")
        )

    def _capabilities(self) -> dict[str, Any]:
        result = super()._capabilities()
        result["channel"] = self.channel
        result["online"] = self._configured()
        result["note"] = "Slack #commons is the same table. A 2xx is mail, not p/{id}.md."
        return result

    def _snapshot(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self._history is None:
            raise LaneError(
                "TRANSPORT_UNCONFIGURED",
                "Slack #commons has no token or webhook in this process",
                channel=self.channel,
            )
        messages = list(self._history())
        nodes = [
            _node("slack:channel", "Window", f"#{self.channel}", actions=["post", "send"]),
        ]
        for index, message in enumerate(messages[:200]):
            text = str(message.get("text") or "")
            ts = str(message.get("ts") or index)
            nodes.append(
                _node(
                    f"slack:{ts}",
                    "Text",
                    text[:120],
                    parent="slack:channel",
                    value=text,
                    ts=ts,
                )
            )
        return {
            "ok": True,
            "nodes": nodes,
            "kind": "semantic_snapshot",
            "platform": "slack",
            "channel": self.channel,
            "pixels": PIXELS_NOT_CAPTURED,
        }

    def _act(self, action: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
        action_type = str(action.get("type") or "").strip().lower()
        if action_type not in {"post", "send"}:
            return failure("UNKNOWN_OPERATION", f"slack lane has no handler for {action_type or '<empty>'}")
        text = str(action.get("text") or action.get("value") or request.get("text") or "")
        if not text.strip():
            raise ProtocolError("slack post requires text")
        if self._post is None:
            raise LaneError(
                "TRANSPORT_UNCONFIGURED",
                "Slack #commons has no token or webhook in this process",
                channel=self.channel,
            )
        posted = dict(self._post(text))
        return {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "kind": "action_outcome",
            "platform": "slack",
            "action": action_type,
            "channel": self.channel,
            "event_id": str(posted.get("ts") or posted.get("event_id") or ""),
            "note": "Slack ts is mail. Durability is p/{id}.md on git HEAD.",
        }


class BoardServer(_SemanticLane):
    platform = "board"
    observation = "board-semantic-delta"
    actions = ("post",)

    def __init__(
        self,
        exists: Callable[[str], bool] | None = None,
        submit: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        read: Callable[[str], str | None] | None = None,
        root: str | Path | None = None,
    ) -> None:
        super().__init__()
        self.root = Path(root or os.getcwd()).resolve()
        self._exists = exists or self._file_exists
        self._submit = submit
        self._read = read or self._file_read

    def _file_exists(self, ident: str) -> bool:
        return (self.root / "p" / f"{ident}.md").is_file()

    def _file_read(self, ident: str) -> str | None:
        path = self.root / "p" / f"{ident}.md"
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8")

    def _ident(self, request: Mapping[str, Any], action: Mapping[str, Any] | None = None) -> str:
        ident = ""
        if action:
            ident = str(action.get("id") or "")
        if not ident:
            ident = str(request.get("id") or "")
        return ident.strip()

    def _snapshot(self, request: Mapping[str, Any]) -> dict[str, Any]:
        ident = self._ident(request)
        nodes = [_node("board:table", "Document", "Commons board", actions=["post"])]
        if ident:
            body = self._read(ident)
            if body is not None:
                nodes.append(
                    _node(
                        f"board:{ident}",
                        "Article",
                        ident,
                        parent="board:table",
                        value=body,
                        path=f"p/{ident}.md",
                    )
                )
        return {
            "ok": True,
            "nodes": nodes,
            "kind": "semantic_snapshot",
            "platform": "board",
            "pixels": PIXELS_NOT_CAPTURED,
            "note": "A post exists only as p/{id}.md on git HEAD. ntfy 200 is mail.",
        }

    def _act(self, action: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
        action_type = str(action.get("type") or "").strip().lower()
        if action_type != "post":
            return failure("UNKNOWN_OPERATION", f"board lane has no handler for {action_type or '<empty>'}")
        ident = self._ident(request, action)
        if not ident:
            raise ProtocolError("board post requires id")
        if self._exists(ident):
            raise LaneError(
                "ID_EXISTS",
                f"canonical body already present for {ident}; do not remint",
                id=ident,
            )
        body = str(action.get("body") or action.get("text") or action.get("value") or "")
        if not body.strip():
            raise ProtocolError("board post requires body")
        payload = {
            "from": str(action.get("from") or request.get("from") or "UNSEATED"),
            "to": str(action.get("to") or request.get("to") or "TABLE"),
            "id": ident,
            "body": body,
        }
        if self._submit is None:
            posted = _ntfy_submit(payload)
        else:
            posted = dict(self._submit(payload))
        return {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "kind": "action_outcome",
            "platform": "board",
            "action": "post",
            "id": ident,
            "carrier": dict(posted),
            "note": "carrier 2xx is mail. Durability is p/{id}.md on git HEAD.",
        }


class ShellServer(_SemanticLane):
    platform = "shell"
    observation = "shell-semantic-delta"
    actions = ("run",)

    def __init__(
        self,
        cwd: str | Path | None = None,
        run: Callable[[str], Mapping[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self.cwd = Path(cwd or os.getcwd()).resolve()
        self.run = run
        self._last: dict[str, Any] = {}

    def _snapshot(self, request: Mapping[str, Any]) -> dict[str, Any]:
        nodes = [
            _node("shell:cwd", "Directory", str(self.cwd), actions=["run"]),
        ]
        if self._last:
            nodes.append(
                _node(
                    "shell:last",
                    "Text",
                    str(self._last.get("command") or ""),
                    parent="shell:cwd",
                    value=str(self._last.get("stdout") or ""),
                    returncode=self._last.get("returncode"),
                )
            )
        return {
            "ok": True,
            "nodes": nodes,
            "kind": "semantic_snapshot",
            "platform": "shell",
            "cwd": str(self.cwd),
            "pixels": PIXELS_NOT_CAPTURED,
        }

    def _act(self, action: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
        action_type = str(action.get("type") or "").strip().lower()
        if action_type != "run":
            return failure("UNKNOWN_OPERATION", f"shell lane has no handler for {action_type or '<empty>'}")
        command = str(action.get("command") or action.get("text") or action.get("value") or "")
        if not command.strip():
            raise ProtocolError("shell run requires command")
        if self.run is not None:
            executed = dict(self.run(command))
        else:
            completed = subprocess.run(
                command,
                cwd=self.cwd,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            executed = {
                "stdout": completed.stdout,
                "stderr": completed.stderr,
                "returncode": completed.returncode,
            }
        self._last = {"command": command, **executed}
        if int(executed.get("returncode") or 0) != 0:
            raise LaneError(
                "COMMAND_FAILED",
                str(executed.get("stderr") or executed.get("stdout") or "command failed"),
                returncode=executed.get("returncode"),
                command=command,
            )
        return {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "kind": "action_outcome",
            "platform": "shell",
            "action": "run",
            "command": command,
            "stdout": executed.get("stdout") or "",
            "stderr": executed.get("stderr") or "",
            "returncode": executed.get("returncode") or 0,
        }


class BrowserServer(_SemanticLane):
    platform = "browser"
    observation = "browser-semantic-delta"
    pixels = PIXELS_ON_DEMAND
    actions = ("navigate", "click", "type_text", "invoke")

    def __init__(
        self,
        snapshot: Callable[[], Mapping[str, Any]] | None = None,
        act: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        capture: Callable[[str], str] | None = None,
    ) -> None:
        super().__init__()
        self._snapshot_fn = snapshot
        self._act_fn = act
        self._capture_fn = capture
        self._url = "about:blank"
        self._nodes: list[dict[str, Any]] = [
            _node("browser:document", "Document", "about:blank", actions=["navigate"]),
        ]

    def _snapshot(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if self._snapshot_fn is not None:
            raw = dict(self._snapshot_fn())
            self._url = str(raw.get("url") or self._url)
            self._nodes = list(raw.get("nodes") or self._nodes)
        return {
            "ok": True,
            "nodes": self._nodes,
            "kind": "semantic_snapshot",
            "platform": "browser",
            "url": self._url,
            "pixels": PIXELS_NOT_CAPTURED,
        }

    def _act(self, action: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
        action_type = str(action.get("type") or "").strip().lower()
        if self._act_fn is not None:
            acted = dict(self._act_fn(action))
            if acted.get("nodes"):
                self._nodes = list(acted["nodes"])
            if acted.get("url"):
                self._url = str(acted["url"])
            if not acted.get("ok", True):
                return failure(str(acted.get("failure_reason") or "ACTION_FAILED"), str(acted.get("message") or ""))
        elif action_type == "navigate":
            self._url = str(action.get("value") or action.get("text") or action.get("url") or "")
            if not self._url:
                raise ProtocolError("browser navigate requires url")
            self._nodes = [_node("browser:document", "Document", self._url, actions=["navigate", "click"])]
        elif action_type in {"click", "invoke", "type_text"}:
            if not action.get("id"):
                raise ProtocolError(f"{action_type} requires id")
        else:
            return failure("UNKNOWN_OPERATION", f"browser lane has no handler for {action_type or '<empty>'}")
        return {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "kind": "action_outcome",
            "platform": "browser",
            "action": action_type,
            "url": self._url,
        }

    def _capture(self, request: Mapping[str, Any]) -> dict[str, Any]:
        path = str(request.get("path") or "artifacts/titan-hands/browser.png")
        if self._capture_fn is not None:
            path = self._capture_fn(path)
        else:
            raise LaneError(
                "TRANSPORT_UNCONFIGURED",
                "browser capture has no page backend in this process",
            )
        return {
            "ok": True,
            "protocol": PROTOCOL_VERSION,
            "kind": "pixel_capture",
            "platform": "browser",
            "pixel_ref": path,
        }


def _ntfy_submit(payload: Mapping[str, Any]) -> dict[str, Any]:
    packed = json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    failures: list[str] = []
    for host in NTFY_HOSTS:
        url = f"{host.rstrip('/')}/{NTFY_TOPIC}"
        try:
            with urlopen(Request(url, data=packed, headers={"Content-Type": "text/plain"}), timeout=12) as response:
                status = int(getattr(response, "status", 0) or 0)
                if 200 <= status < 300:
                    return {"ok": True, "host": host, "http_status": status, "note": "ntfy 200 is mail"}
                failures.append(f"{host} {status}")
        except (URLError, TimeoutError, OSError) as exc:
            failures.append(f"{host} {exc}")
    raise LaneError("TRANSPORT_FAILED", "every ntfy relay refused", failures=failures)
