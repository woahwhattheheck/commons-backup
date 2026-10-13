"""Non-computer TITAN Hands routes sharing the DeltaUI failure envelope.

Computer-use stays on TitanHandsBroker. These routes expose file, board, git,
Slack, local shell, and web operations without repository permission or path
gates. Pixels stay off this path. Provider-issued credentials stay out of
payloads and responses.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from host.titan_hands_windows.protocol import PROTOCOL_VERSION, ProtocolError, failure


COMMONS_SLACK_CHANNEL = "C0BRGMDQB6G"
COMMONS_SLACK_NAME = "commons"
POST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
TEXT_LIMIT = 100_000
WEB_TIMEOUT = 30.0
SHELL_TIMEOUT = 60.0

HttpFn = Callable[..., dict[str, Any]]
GitFn = Callable[..., subprocess.CompletedProcess[str]]


def default_repo_root() -> Path:
    configured = os.environ.get("TITAN_HANDS_REPO")
    if configured:
        return Path(configured).resolve()
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return cwd


def default_http(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = WEB_TIMEOUT,
) -> dict[str, Any]:
    request = urllib.request.Request(url, data=body, method=method.upper())
    for key, value in dict(headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return {
                "status": int(response.status),
                "headers": {key.lower(): value for key, value in response.headers.items()},
                "body": raw,
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp is not None else b""
        return {
            "status": int(exc.code),
            "headers": {key.lower(): value for key, value in exc.headers.items()} if exc.headers else {},
            "body": raw,
            "error": str(exc),
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": 0, "headers": {}, "body": b"", "error": str(exc)}


def default_git(args: Sequence[str], *, cwd: Path, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _ok(kind: str, **fields: Any) -> dict[str, Any]:
    result = {"ok": True, "protocol": PROTOCOL_VERSION, "kind": kind}
    result.update(fields)
    return result


def _relpath(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


class HandsRoutes:
    """File, git, Slack, board, shell, and web routes for one `hands` tool."""

    def __init__(
        self,
        repo_root: Path | None = None,
        http: HttpFn | None = None,
        git: GitFn | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.repo_root = (repo_root or default_repo_root()).resolve()
        self.http = http or default_http
        self.git = git or default_git
        self.environ = dict(os.environ if environ is None else environ)

    def handle(self, route: str, request: Mapping[str, Any]) -> dict[str, Any]:
        op = str(request.get("op") or "").strip().lower()
        if route == "file":
            return self._file(op, request)
        if route == "git":
            return self._git(op, request)
        if route == "slack":
            return self._slack(op, request)
        if route == "board":
            return self._board(op, request)
        if route == "shell":
            return self._shell(op, request)
        if route == "web":
            return self._web(op, request)
        return failure("UNKNOWN_ROUTE", f"unknown route: {route or '<empty>'}")

    def _resolve(self, raw: Any) -> Path:
        rel = str(raw or "").strip()
        if not rel:
            raise ProtocolError("path is required")
        candidate = Path(rel)
        if candidate.is_absolute():
            resolved = candidate.resolve()
        else:
            resolved = (self.repo_root / candidate).resolve()
        return resolved

    def _file(self, op: str, request: Mapping[str, Any]) -> dict[str, Any]:
        if op == "list":
            target = self._resolve(request.get("path") or ".")
            if not target.exists():
                return failure("PATH_MISS", f"path does not exist: {_relpath(self.repo_root, target)}")
            if not target.is_dir():
                return failure("NOT_A_DIRECTORY", f"not a directory: {_relpath(self.repo_root, target)}")
            names = sorted(child.name for child in target.iterdir())
            return _ok("file_list", path=_relpath(self.repo_root, target), names=names)
        if op == "read":
            target = self._resolve(request.get("path"))
            if not target.is_file():
                return failure("PATH_MISS", f"file does not exist: {_relpath(self.repo_root, target)}")
            text = target.read_text(encoding="utf-8", errors="replace")
            return _ok(
                "file_read",
                path=_relpath(self.repo_root, target),
                bytes=len(text.encode("utf-8")),
                text=text[:TEXT_LIMIT],
                truncated=len(text) > TEXT_LIMIT,
            )
        if op == "write":
            target = self._resolve(request.get("path"))
            rel = _relpath(self.repo_root, target)
            created = not target.exists()
            contents = request.get("contents")
            if contents is None:
                contents = request.get("text")
            if contents is None:
                raise ProtocolError("write requires contents")
            target.parent.mkdir(parents=True, exist_ok=True)
            data = contents if isinstance(contents, str) else json.dumps(contents)
            target.write_text(data, encoding="utf-8")
            return _ok("file_write", path=rel, bytes=len(data.encode("utf-8")), created=created)
        return failure("UNKNOWN_OPERATION", f"unknown file operation: {op or '<empty>'}")

    def _git(self, op: str, request: Mapping[str, Any]) -> dict[str, Any]:
        if op == "status":
            completed = self.git(["status", "--short", "--branch"], cwd=self.repo_root)
            return self._git_result("git_status", completed)
        if op == "diff":
            args = ["diff"]
            staged = bool(request.get("staged"))
            if staged:
                args.append("--cached")
            path = str(request.get("path") or "").strip()
            if path:
                args.extend(["--", path])
            completed = self.git(args, cwd=self.repo_root)
            return self._git_result("git_diff", completed)
        if op == "log":
            count = int(request.get("count") or 8)
            completed = self.git(["log", f"-{max(1, min(count, 50))}", "--oneline"], cwd=self.repo_root)
            return self._git_result("git_log", completed)
        if op == "add":
            paths = request.get("paths")
            if paths is None:
                raw_path = request.get("path")
                paths = [raw_path] if raw_path else []
            if not isinstance(paths, list) or not paths:
                raise ProtocolError("git add requires path or paths")
            rels = [str(item) for item in paths]
            completed = self.git(["add", *rels], cwd=self.repo_root)
            result = self._git_result("git_add", completed)
            result["paths"] = rels
            return result
        if op == "commit":
            message = str(request.get("message") or request.get("text") or "").strip()
            if not message:
                raise ProtocolError("git commit requires message")
            staged = self.git(["diff", "--cached", "--name-only"], cwd=self.repo_root)
            if staged.returncode != 0:
                return self._git_result("git_commit", staged)
            names = [line.strip() for line in staged.stdout.splitlines() if line.strip()]
            if not names:
                return failure("NOTHING_STAGED", "git commit has no staged changes")
            completed = self.git(["commit", "-m", message], cwd=self.repo_root)
            result = self._git_result("git_commit", completed)
            result["paths"] = names
            return result
        return failure("UNKNOWN_OPERATION", f"unknown git operation: {op or '<empty>'}")

    def _git_result(self, kind: str, completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
        if completed.returncode != 0:
            return failure(
                "GIT_FAILED",
                (completed.stderr or completed.stdout or "git command failed").strip(),
                returncode=completed.returncode,
            )
        return _ok(
            kind,
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
        )

    def _slack_token(self) -> str:
        return str(
            self.environ.get("COMMONS_SLACK_BOT_TOKEN")
            or self.environ.get("SLACK_BOT_TOKEN")
            or ""
        ).strip()

    def _slack_channel(self, request: Mapping[str, Any]) -> str:
        raw = str(request.get("channel") or "").strip()
        if not raw or raw in {COMMONS_SLACK_CHANNEL, f"#{COMMONS_SLACK_NAME}", COMMONS_SLACK_NAME}:
            return COMMONS_SLACK_CHANNEL
        return raw

    def _slack(self, op: str, request: Mapping[str, Any]) -> dict[str, Any]:
        channel = self._slack_channel(request)
        token = self._slack_token()
        if not token:
            return failure(
                "TOKEN_MISS",
                "COMMONS_SLACK_BOT_TOKEN is absent; Slack was not contacted",
                channel=channel,
            )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        if op == "read":
            query = urllib.parse.urlencode({"channel": channel, "limit": int(request.get("limit") or 20)})
            response = self.http(
                "GET",
                f"https://slack.com/api/conversations.history?{query}",
                headers=headers,
            )
            return self._slack_api("slack_read", response, channel)
        if op == "post":
            text = str(request.get("text") or request.get("body") or "").strip()
            if not text:
                raise ProtocolError("slack post requires text")
            payload = {"channel": channel, "text": text}
            thread_ts = str(request.get("thread_ts") or "").strip()
            if thread_ts:
                payload["thread_ts"] = thread_ts
            response = self.http(
                "POST",
                "https://slack.com/api/chat.postMessage",
                headers=headers,
                body=json.dumps(payload).encode("utf-8"),
            )
            return self._slack_api("slack_post", response, channel)
        return failure("UNKNOWN_OPERATION", f"unknown slack operation: {op or '<empty>'}")

    def _slack_api(self, kind: str, response: Mapping[str, Any], channel: str) -> dict[str, Any]:
        if not response.get("status"):
            return failure("SLACK_FAILED", str(response.get("error") or "Slack HTTP failed"))
        body = response.get("body") or b""
        try:
            parsed = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
        except (UnicodeError, json.JSONDecodeError) as exc:
            return failure("SLACK_FAILED", f"Slack body was not JSON: {exc}")
        if not parsed.get("ok"):
            return failure("SLACK_FAILED", str(parsed.get("error") or "Slack api returned ok=false"), payload=parsed)
        return _ok(kind, channel=channel, slack=parsed)

    def _board(self, op: str, request: Mapping[str, Any]) -> dict[str, Any]:
        ident = str(request.get("id") or "").strip()
        if not POST_ID_RE.fullmatch(ident):
            raise ProtocolError("board id must be 8-80 chars in [A-Za-z0-9._-]")
        target = self._resolve(f"p/{ident}.md")
        rel = _relpath(self.repo_root, target)
        if op == "read":
            if not target.is_file():
                return failure("PATH_MISS", f"board record is not a file: {rel}")
            text = target.read_text(encoding="utf-8", errors="replace")
            return _ok("board_read", id=ident, path=rel, text=text)
        if op == "post":
            body = str(request.get("body") or request.get("text") or "")
            if not body.strip():
                raise ProtocolError("board post requires body")
            speaker = str(request.get("from") or "").strip() or "UNSEATED"
            dest = str(request.get("to") or "").strip() or "TABLE"
            lines = [
                "---",
                f"from: {speaker}",
                f"to: {dest}",
                f"id: {ident}",
            ]
            for key in ("subject", "board", "lane", "kind"):
                value = str(request.get(key) or "").strip()
                if value:
                    lines.append(f"{key}: {value}")
            lines.extend(["---", "", body.rstrip(), ""])
            target.parent.mkdir(parents=True, exist_ok=True)
            text = "\n".join(lines)
            target.write_text(text, encoding="utf-8")
            return _ok("board_post", id=ident, path=rel)
        return failure("UNKNOWN_OPERATION", f"unknown board operation: {op or '<empty>'}")

    def _shell(self, op: str, request: Mapping[str, Any]) -> dict[str, Any]:
        if op != "run":
            return failure("UNKNOWN_OPERATION", f"unknown shell operation: {op or '<empty>'}")
        command = request.get("command") or request.get("argv")
        if command in (None, "", []):
            raise ProtocolError("shell run requires command")
        timeout = float(request.get("timeout") or SHELL_TIMEOUT)
        try:
            if isinstance(command, str):
                completed = subprocess.run(
                    command,
                    cwd=str(self.repo_root),
                    shell=True,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=max(0.1, min(timeout, 120.0)),
                    encoding="utf-8",
                    errors="replace",
                )
                argv_field: Any = command
            elif isinstance(command, list) and all(isinstance(item, str) for item in command):
                completed = subprocess.run(
                    command,
                    cwd=str(self.repo_root),
                    shell=False,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=max(0.1, min(timeout, 120.0)),
                    encoding="utf-8",
                    errors="replace",
                )
                argv_field = command
            else:
                raise ProtocolError("command must be a string or a list of strings")
        except subprocess.TimeoutExpired as exc:
            return failure("SHELL_TIMEOUT", f"shell run exceeded {timeout}s", command=str(exc.cmd))
        if completed.returncode != 0:
            return failure(
                "COMMAND_FAILED",
                (completed.stderr or completed.stdout or "shell command failed").strip(),
                command=argv_field,
                returncode=completed.returncode,
                stdout=completed.stdout[:TEXT_LIMIT],
                stderr=completed.stderr[:TEXT_LIMIT],
            )
        return _ok(
            "shell_run",
            command=argv_field,
            returncode=completed.returncode,
            stdout=completed.stdout[:TEXT_LIMIT],
            stderr=completed.stderr[:TEXT_LIMIT],
        )

    def _web(self, op: str, request: Mapping[str, Any]) -> dict[str, Any]:
        if op != "fetch":
            return failure("UNKNOWN_OPERATION", f"unknown web operation: {op or '<empty>'}")
        url = str(request.get("url") or "").strip()
        if not url:
            raise ProtocolError("web fetch requires url")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ProtocolError("web fetch url must be http or https")
        response = self.http(
            str(request.get("method") or "GET").upper(),
            url,
            headers={"User-Agent": "titan-hands/0.3"},
            timeout=float(request.get("timeout") or WEB_TIMEOUT),
        )
        status = int(response.get("status") or 0)
        if not status:
            return failure("WEB_FAILED", str(response.get("error") or "web fetch failed"), url=url)
        headers = dict(response.get("headers") or {})
        content_type = str(headers.get("content-type") or "")
        if content_type.lower().startswith("image/"):
            return _ok(
                "web_fetch",
                url=url,
                status=status,
                content_type=content_type,
                pixels=False,
                message="image bytes are omitted; capture stays explicit",
            )
        raw = response.get("body") or b""
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
        else:
            text = str(raw)
        return _ok(
            "web_fetch",
            url=url,
            status=status,
            content_type=content_type,
            pixels=False,
            text=text[:TEXT_LIMIT],
            truncated=len(text) > TEXT_LIMIT,
        )
