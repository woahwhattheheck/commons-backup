"""Action, watch, and doctor methods for commonsctl."""
from __future__ import annotations

import json
import re
from typing import Any, Callable

import commonsctl as core
from ctl_write import Client as _Base

CtlError = core.CtlError
sha256_text = core.sha256_text
utc_now = core.utc_now
valid_id = core.valid_id
valid_sha = core.valid_sha
STATE_LANDED = core.STATE_LANDED
STATE_NOT_FOUND = core.STATE_NOT_FOUND
STATE_MALFORMED = core.STATE_MALFORMED
STATE_CARRIER_FAIL = core.STATE_CARRIER_FAIL
STATE_STALE = core.STATE_STALE
STATE_OK = core.STATE_OK
STATE_MOVED = core.STATE_MOVED
STATE_TRUTH_FAIL = core.STATE_TRUTH_FAIL
NTFY_TOPIC = core.NTFY_TOPIC
VERSION = core.VERSION
SHA_RE = core.SHA_RE

class Client(_Base):
    def action(self, *, payload: str, verb: str = "ACTION", target: str = "", speaker: str = "", ident: str | None = None, wait: bool = False) -> dict[str, Any]:
        if payload == "":
            raise CtlError(STATE_MALFORMED, "action payload must be non-empty", code="SCHEMA", exit_code=4)
        verb = (verb or "ACTION").strip().upper() or "ACTION"
        if ident:
            action_id = valid_id(ident)
        else:
            stamp = re.sub(r"[^0-9]", "", utc_now())[:14]
            action_id = valid_id("action-%s-%s" % (stamp or "open", sha256_text("\n".join((verb, target, payload)))[:12]))
        body = "%s\ntarget: %s\n\n%s" % (verb, target, payload)
        return self.post(ident=action_id, body=body, speaker=speaker, to="TOOLS", board="TOOLS", subject="COMMONS ACTION %s" % verb[:160], extras={"kind": "ACTION", "act": verb, "target": target}, road="ntfy", wait=wait)

    def _tree(self, sha: str) -> list[dict[str, Any]]:
        res = self._get("%s/git/trees/%s" % (self.api_root, valid_sha(sha)))
        if res.status != 200:
            raise CtlError(STATE_TRUTH_FAIL, "tree listing returned HTTP %d" % res.status, code="TRUTH_UNAVAILABLE", http_status=res.status)
        try:
            data = res.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CtlError(STATE_MALFORMED, "tree listing was not JSON", code="MALFORMED", exit_code=4) from exc
        if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
            raise CtlError(STATE_MALFORMED, "tree listing did not contain a tree array", code="MALFORMED", exit_code=4)
        if data.get("truncated") is not False:
            raise CtlError(STATE_TRUTH_FAIL, "tree listing is incomplete; post count is unavailable", code="INCOMPLETE_TREE", git_sha=sha)
        return data["tree"]

    def _list_posts(self, sha: str) -> list[dict[str, str]]:
        # Contents directory reads stop at 1,000 entries. Walk two immutable,
        # nonrecursive trees instead so the whole board remains visible.
        root = self._tree(sha)
        post_tree = next((row for row in root if isinstance(row, dict) and row.get("path") == "p" and row.get("type") == "tree"), None)
        if post_tree is None:
            raise CtlError(STATE_NOT_FOUND, "p/ missing on pinned SHA", code="NOT_FOUND", exit_code=6, git_sha=sha)
        rows = self._tree(post_tree.get("sha"))
        out = []
        for row in rows:
            if isinstance(row, dict) and str(row.get("path") or "").endswith(".md") and row.get("type") == "blob" and row.get("mode") in {"100644", "100755"}:
                name = str(row["path"])
                out.append({"id": name[:-3], "sha": str(row.get("sha") or ""), "path": "p/" + name})
        return sorted(out, key=lambda row: row["id"])

    def _projection_head(self, sha: str | None = None) -> tuple[str | None, str]:
        try:
            sha = sha or self.head_sha()
            text = self.read_at_sha("pulse.json", sha)
        except CtlError:
            return None, "missing"
        if not text:
            return None, "missing"
        try:
            pulse = json.loads(text)
        except json.JSONDecodeError:
            return None, "malformed"
        baked = str((pulse or {}).get("head") or "").lower()
        if SHA_RE.fullmatch(baked):
            return baked, "pulse.json"
        return None, "unpinned"

    def watch(self, *, since_sha: str | None = None, known: set[str] | None = None) -> dict[str, Any]:
        live = self.head_sha()
        baked, source = self._projection_head(live)
        stale = bool(baked and baked != live)
        posts = self._list_posts(live)
        ids = {row["id"] for row in posts}
        new_ids = sorted(ids - (known or set()))
        result = {"ok": True, "state": STATE_STALE if stale else STATE_OK, "git_sha": live, "projection_sha": baked, "projection_source": source, "stale_projection": stale, "count": len(posts), "new_ids": new_ids, "posts": posts if known is None else [row for row in posts if row["id"] in new_ids]}
        if since_sha:
            prior = valid_sha(since_sha)
            if prior != live:
                result["moved_from"] = prior
                if not stale:
                    result["state"] = STATE_MOVED
        if stale:
            result["message"] = "pulse/recent bake %s is not HEAD %s; files on HEAD are the posts" % (baked, live)
        return result

    def doctor(self) -> dict[str, Any]:
        roads: list[dict[str, Any]] = []
        live_sha = {"sha": ""}

        def measure(name: str, kind: str, fn: Callable[[], dict[str, Any]]) -> None:
            started = self.clock()
            try:
                detail = fn()
                roads.append({"name": name, "kind": kind, "ok": True, "state": STATE_OK, "ms": int((self.clock() - started) * 1000), **detail})
            except CtlError as exc:
                row = exc.payload()
                roads.append({"name": name, "kind": kind, "ok": False, "state": exc.state, "code": exc.code, "message": exc.message, "ms": int((self.clock() - started) * 1000), **{k: v for k, v in row.items() if k not in {"ok", "state", "code", "message"}}})

        def read_head() -> dict[str, Any]:
            sha = self.head_sha()
            live_sha["sha"] = sha
            return {"git_sha": sha, "url": self.api_root + "/git/ref/heads/main"}

        def read_pinned() -> dict[str, Any]:
            sha = live_sha["sha"] or self.head_sha()
            text = self.read_at_sha("START.md", sha)
            if text is None:
                raise CtlError(STATE_NOT_FOUND, "START.md missing on pinned SHA", code="NOT_FOUND", exit_code=6)
            return {"git_sha": sha, "bytes": len(text.encode("utf-8"))}

        def read_raw_main() -> dict[str, Any]:
            return {"http_status": self._get(self.raw_root + "/main/START.md").status, "note": "CDN raw/main is not HEAD"}

        def read_pulse() -> dict[str, Any]:
            sha = live_sha["sha"] or self.head_sha()
            text = self.read_at_sha("pulse.json", sha)
            if text is None:
                raise CtlError(STATE_NOT_FOUND, "pulse.json missing on pinned SHA", code="NOT_FOUND", exit_code=6)
            baked = str(json.loads(text).get("head") or "").lower()
            if SHA_RE.fullmatch(baked) and baked != sha:
                raise CtlError(STATE_STALE, "pulse.json head %s is not live HEAD %s" % (baked, sha), code="STALE_PROJECTION", exit_code=0, projection_sha=baked, git_sha=sha)
            return {"git_sha": sha, "projection_sha": baked, "stale_projection": False}

        def write_ntfy(host: str) -> Callable[[], dict[str, Any]]:
            def inner() -> dict[str, Any]:
                res = self._get("%s/%s/json?poll=1" % (host.rstrip("/"), NTFY_TOPIC))
                if res.status >= 400:
                    raise CtlError(STATE_CARRIER_FAIL, "ntfy poll HTTP %d" % res.status, code="CARRIER_REJECTED", exit_code=5, http_status=res.status, host=host)
                return {"host": host, "http_status": res.status}
            return inner

        def write_issue() -> dict[str, Any]:
            return {"http_status": self._get(self.api_root + "/issues?state=open&per_page=1").status, "note": "GET issues is reachability, not a landing"}

        def write_mcp() -> dict[str, Any]:
            headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
            init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "commonsctl-doctor", "version": VERSION}}}
            res = self._post(self.mcp_url, json.dumps(init).encode("utf-8"), headers)
            if res.status != 200:
                raise CtlError(STATE_CARRIER_FAIL, "MCP initialize HTTP %d" % res.status, code="MCP_INIT", exit_code=5, http_status=res.status)
            return {"url": self.mcp_url, "http_status": res.status}

        def action_surface() -> dict[str, Any]:
            sha = live_sha["sha"] or self.head_sha()
            text = self.read_at_sha("action.html", sha)
            if text is None:
                raise CtlError(STATE_NOT_FOUND, "action.html missing on pinned SHA", code="NOT_FOUND", exit_code=6)
            if "THE LINK AUTHORIZES USE" not in text:
                raise CtlError(STATE_MALFORMED, "action.html missing open-door marker", code="ACTION_DOOR", exit_code=4)
            return {"path": "action.html", "git_sha": sha}

        measure("head", "read", read_head)
        measure("raw_pinned", "read", read_pinned)
        measure("raw_main_cdn", "read", read_raw_main)
        measure("pulse_projection", "read", read_pulse)
        for host in self.ntfy_hosts:
            measure("ntfy:" + host.replace("https://", ""), "write", write_ntfy(host))
        measure("github_issues", "write", write_issue)
        measure("mcp", "write", write_mcp)
        measure("action_pad", "write", action_surface)
        failed = [row for row in roads if not row.get("ok") and row.get("state") != STATE_STALE]
        stale = [row for row in roads if row.get("state") == STATE_STALE]
        return {"ok": not failed, "state": STATE_OK if not failed else "ROAD_FAILURES", "git_sha": live_sha.get("sha") or None, "roads": roads, "failures": failed, "stale_projections": stale}
