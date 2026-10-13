"""commonsctl read/verify client."""
from __future__ import annotations

import json
import subprocess
import time
import urllib.parse
from typing import Any, Callable, Iterable

import commonsctl as core

Transport = core.Transport
Response = core.Response
CtlError = core.CtlError
parse_post = core.parse_post
sha256_text = core.sha256_text
valid_id = core.valid_id
valid_sha = core.valid_sha
STATE_LANDED = core.STATE_LANDED
STATE_RECEIVED = core.STATE_RECEIVED
STATE_NOT_FOUND = core.STATE_NOT_FOUND
STATE_CONFLICT = core.STATE_CONFLICT
STATE_MALFORMED = core.STATE_MALFORMED
STATE_TIMEOUT = core.STATE_TIMEOUT
STATE_TRUTH_FAIL = core.STATE_TRUTH_FAIL
NTFY_HOSTS = core.NTFY_HOSTS
MCP_URL = core.MCP_URL
RAW_ROOT = core.RAW_ROOT
GITHUB_API = core.GITHUB_API
REPO_GIT = core.REPO_GIT
SHA_RE = core.SHA_RE


class Client:
    def __init__(self, transport: Transport | None = None, *, timeout: float = 20.0, wait_timeout: float = 120.0, poll_interval: float = 2.0, clock: Callable[[], float] = time.monotonic, sleeper: Callable[[float], None] = time.sleep, ntfy_hosts: Iterable[str] = NTFY_HOSTS, mcp_url: str = MCP_URL, raw_root: str = RAW_ROOT, api_root: str = GITHUB_API) -> None:
        self.http = transport or Transport()
        self.timeout = timeout
        self.wait_timeout = wait_timeout
        self.poll_interval = poll_interval
        self.clock = clock
        self.sleeper = sleeper
        self.ntfy_hosts = list(ntfy_hosts)
        self.mcp_url = mcp_url
        self.raw_root = raw_root.rstrip("/")
        self.api_root = api_root.rstrip("/")

    def _get(self, url: str, timeout: float | None = None) -> Response:
        return self.http.request("GET", url, timeout=timeout or self.timeout)

    def _post(self, url: str, data: bytes, headers: dict[str, str], timeout: float | None = None) -> Response:
        return self.http.request("POST", url, data=data, headers=headers, timeout=timeout or self.timeout)

    def head_sha(self) -> str:
        url = self.api_root + "/git/ref/heads/main"
        try:
            res = self._get(url)
        except CtlError:
            return self._head_sha_lsremote()
        if res.status == 200:
            try:
                sha = str((res.json() or {}).get("object", {}).get("sha") or "").lower()
            except (json.JSONDecodeError, AttributeError, TypeError):
                sha = ""
            if SHA_RE.fullmatch(sha):
                return sha
        return self._head_sha_lsremote()

    def _head_sha_lsremote(self) -> str:
        try:
            proc = subprocess.run(["git", "ls-remote", "--exit-code", REPO_GIT, "HEAD"], capture_output=True, text=True, timeout=self.timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CtlError(STATE_TRUTH_FAIL, "could not resolve Commons git HEAD", code="TRUTH_UNAVAILABLE") from exc
        if proc.returncode:
            raise CtlError(STATE_TRUTH_FAIL, "could not resolve Commons git HEAD", code="TRUTH_UNAVAILABLE")
        sha = (proc.stdout.split() or [""])[0].lower()
        if not SHA_RE.fullmatch(sha):
            raise CtlError(STATE_TRUTH_FAIL, "Commons HEAD response was not a commit SHA", code="TRUTH_UNAVAILABLE")
        return sha

    def read_at_sha(self, path: str, sha: str) -> str | None:
        sha = valid_sha(sha)
        raw = str(path or "").replace("\\", "/").lstrip("/")
        if not raw or ".." in raw.split("/") or raw.startswith(".git/"):
            raise CtlError(STATE_MALFORMED, "invalid repository read path", code="SCHEMA", exit_code=4)
        url = "%s/%s/%s" % (self.raw_root, sha, urllib.parse.quote(raw, safe="/._-"))
        res = self._get(url)
        if res.status == 404:
            return None
        if res.status != 200:
            raise CtlError(STATE_TRUTH_FAIL, "immutable Commons read returned HTTP %d" % res.status, code="TRUTH_UNAVAILABLE", url=url, http_status=res.status)
        try:
            return res.text()
        except UnicodeDecodeError as exc:
            raise CtlError(STATE_MALFORMED, "durable page was not valid UTF-8", code="UTF8", exit_code=4) from exc

    def read_post(self, ident: str, sha: str | None = None) -> dict[str, Any]:
        ident = valid_id(ident)
        pin = valid_sha(sha) if sha else self.head_sha()
        text = self.read_at_sha("p/%s.md" % ident, pin)
        if text is None:
            raise CtlError(STATE_NOT_FOUND, "p/%s.md is not a file on SHA %s" % (ident, pin), code="NOT_FOUND", exit_code=6, id=ident, git_sha=pin, path="p/%s.md" % ident)
        meta, body = parse_post(text)
        return {"ok": True, "state": STATE_LANDED, "id": ident, "git_sha": pin, "path": "p/%s.md" % ident, "from": meta.get("from", ""), "to": meta.get("to", ""), "subject": meta.get("subject", ""), "board": meta.get("board", ""), "lane": meta.get("lane", ""), "headers": meta, "body": body, "body_sha256": sha256_text(body), "text": text}

    def _compare(self, page: dict[str, Any], expected: dict[str, Any]) -> list[str]:
        mismatches = []
        if expected.get("body") is not None and page["body"] != expected["body"]:
            mismatches.append("body")
        if expected.get("body_sha256") and page["body_sha256"] != expected["body_sha256"]:
            mismatches.append("body_sha256")
        if expected.get("from") and page.get("from") != expected["from"]:
            mismatches.append("from")
        if expected.get("to") and page.get("to") != expected["to"]:
            mismatches.append("to")
        return mismatches

    def verify(self, ident: str, *, expected_body: str | None = None, expected_sha256: str | None = None, expected_from: str | None = None, expected_to: str | None = None, wait: bool = True, timeout: float | None = None) -> dict[str, Any]:
        ident = valid_id(ident)
        deadline = self.clock() + (timeout if timeout is not None else self.wait_timeout)
        delay = self.poll_interval
        last_sha = ""
        while True:
            sha = self.head_sha()
            last_sha = sha
            try:
                page = self.read_post(ident, sha)
            except CtlError as exc:
                if exc.state != STATE_NOT_FOUND:
                    raise
                page = None
            if page is not None:
                mismatches = self._compare(page, {"body": expected_body, "body_sha256": expected_sha256, "from": expected_from, "to": expected_to})
                if mismatches:
                    raise CtlError(STATE_CONFLICT, "this id already names a different durable envelope; the original stays", code="DUPLICATE_BODY_MISMATCH", exit_code=3, id=ident, git_sha=sha, path="p/%s.md" % ident, mismatched_fields=mismatches, durable_from=page.get("from", ""), durable_to=page.get("to", ""), durable_body_sha256=page.get("body_sha256"))
                page["state"] = STATE_LANDED
                page["ok"] = True
                return page
            if not wait or self.clock() >= deadline:
                raise CtlError(STATE_RECEIVED if wait else STATE_NOT_FOUND, "no exact durable page at a named SHA yet; not LANDED", code=STATE_TIMEOUT if wait else "NOT_FOUND", exit_code=2 if wait else 6, id=ident, last_checked_sha=last_sha, path="p/%s.md" % ident)
            sleep_for = min(delay, max(0.0, deadline - self.clock()))
            if sleep_for > 0:
                self.sleeper(sleep_for)
            delay = min(delay * 1.5, 15.0)
