"""Public Commons truth: git HEAD plus SHA-pinned raw. Bakes are labeled."""
from __future__ import annotations

import json
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from . import RAW_ROOT, REPO_GIT, SERVER_VERSION
from .envelope import EnvelopeError


SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class HttpError(Exception):
    def __init__(self, status: int, body: str = ""):
        super().__init__("HTTP %d" % status)
        self.status = status
        self.body = body


def default_http(method: str, url: str, data: bytes | None = None, headers: dict[str, str] | None = None, timeout: float = 20.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=headers or {"User-Agent": "%s/%s" % ("independent-commons", SERVER_VERSION)},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read(1_000_000)
            return {
                "status": int(response.status),
                "body": raw.decode("utf-8", "replace"),
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        raw = exc.read(4096) if exc.fp else b""
        return {
            "status": int(exc.code),
            "body": raw.decode("utf-8", "replace"),
            "error": "HTTP %d" % exc.code,
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"status": 0, "body": "", "error": type(exc).__name__}


class GitTruth:
    def __init__(
        self,
        *,
        git_url: str = REPO_GIT,
        raw_root: str = RAW_ROOT,
        timeout: float = 20.0,
        http: Callable[..., dict[str, Any]] | None = None,
        ls_remote: Callable[[], str] | None = None,
    ):
        self.git_url = git_url
        self.raw_root = raw_root.rstrip("/")
        self.timeout = timeout
        self.http = http or default_http
        self._ls_remote = ls_remote

    def head_sha(self) -> str:
        if self._ls_remote is not None:
            sha = self._ls_remote()
        else:
            try:
                proc = subprocess.run(
                    ["git", "ls-remote", "--exit-code", self.git_url, "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                raise EnvelopeError("TRUTH_UNAVAILABLE", "could not resolve Commons git HEAD") from exc
            if proc.returncode:
                raise EnvelopeError("TRUTH_UNAVAILABLE", "could not resolve Commons git HEAD")
            sha = (proc.stdout.split() or [""])[0].lower()
        if not SHA_RE.fullmatch(sha):
            raise EnvelopeError("TRUTH_UNAVAILABLE", "Commons HEAD response was not a commit SHA")
        return sha

    def read_at_sha(self, path: str, sha: str) -> tuple[int, str | None]:
        if not SHA_RE.fullmatch(str(sha or "").lower()):
            raise EnvelopeError("SCHEMA", "sha must be 40 lowercase hexadecimal characters")
        raw = str(path or "").replace("\\", "/").lstrip("/")
        if not raw or ".." in raw.split("/") or raw.startswith(".git/"):
            raise EnvelopeError("SCHEMA", "invalid repository read path")
        url = "%s/%s/%s" % (self.raw_root, sha, urllib.parse.quote(raw, safe="/._-"))
        row = self.http("GET", url, timeout=self.timeout)
        if row["status"] == 200:
            return 200, row["body"]
        if row["status"] == 404:
            return 404, None
        raise EnvelopeError(
            "TRUTH_UNAVAILABLE",
            "immutable Commons read returned HTTP %d" % row["status"],
            http_status=row["status"],
        )

    def read_json(self, path: str, sha: str) -> Any:
        status, text = self.read_at_sha(path, sha)
        if status == 404 or text is None:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise EnvelopeError("DURABLE_PARSE", "%s is not valid JSON" % path) from exc

    def public_urls(self, ident: str, sha: str) -> dict[str, str]:
        return {
            "git_sha": sha,
            "path": "p/%s.md" % ident,
            "sha_pinned_raw": "%s/%s/p/%s.md" % (self.raw_root, sha, ident),
            "head_html": "https://woahwhattheheck.github.io/commons/head.html",
            "pages_hint": "https://woahwhattheheck.github.io/commons/p/%s.html" % ident,
        }
