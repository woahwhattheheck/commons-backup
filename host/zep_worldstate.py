#!/usr/bin/env python3
"""host/zep_worldstate.py — Zep (Graphiti) world-state client for the Commons swarm.

Zep Cloud is a temporal knowledge-graph store: peers write episodes (text /
json / fact_triple / message) into a shared graph_id and read back extracted
edges, nodes, episodes, or a materialized `auto` context block. Use it as the
swarm's durable world-state: who did what, what is blocked, what is open.

  Docs:  https://help.getzep.com/llms.txt
  Base:  https://api.getzep.com/api/v2
  Auth:  Authorization: Api-Key <key>   (account-level project key)

  python3 host/zep_worldstate.py --self-test
  python3 host/zep_worldstate.py add --data "PR #310 opened by Z-Forge" --source "z-forge"
  python3 host/zep_worldstate.py search --query "loyaltyledger pr" --scope edges --limit 10
  python3 host/zep_worldstate.py context --query "what is blocked"   # materialized context block
  python3 host/zep_worldstate.py create-graph --graph-id commons-swarm --name "Commons Swarm"
  python3 host/zep_worldstate.py episode --uuid <episode_uuid>

Key resolution order (never printed, never written to the repo):
  1. env ZEP_API_KEY
  2. credvault: Windows Credential Manager generic target
     "commons:vault:zep:swarm-swe2-20260917" then "zep/api-key"
     (credential_sources.json naming convention)

NO_KEY is a typed result, not a crash — callers branch on it like any
other answer. All transport failures are typed ZepError, never raw tracebacks.

Measured note (2026-09-18): api.getzep.com sits behind Cloudflare and rejects
bare library user-agents with HTTP 403 error 1010. Always send the UA below.
Episode ingestion is async — an added episode is durable immediately via
GET /graph/episodes/{uuid}; edge/node extraction lands seconds later.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import urllib.error
import urllib.request
from ctypes import wintypes

API_BASE = "https://api.getzep.com/api/v2"
ENV_KEY = "ZEP_API_KEY"
CREDVAULT_TARGETS = ("commons:vault:zep:swarm-swe2-20260917", "zep/api-key")
USER_AGENT = "zep-python/3.0 commons-swarm"
DEFAULT_GRAPH = "commons-swarm"
MAX_DATA_BYTES = 256 * 1024
TIMEOUT = 30


class ZepError(Exception):
    """Typed failure. str(self) carries NO_KEY / HTTP_<status> / TRANSPORT / BAD_REPLY."""


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


_CRED_TYPE_GENERIC = 1


def _cred_read(target: str) -> str:
    """Read a Windows Credential Manager generic credential. Returns '' on miss."""
    if os.name != "nt" or not target:
        return ""
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.CredReadW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(CREDENTIALW)),
    ]
    advapi32.CredReadW.restype = wintypes.BOOL
    pcred = ctypes.POINTER(CREDENTIALW)()
    if not advapi32.CredReadW(target, _CRED_TYPE_GENERIC, 0, ctypes.byref(pcred)):
        return ""
    try:
        blob = ctypes.string_at(
            pcred.contents.CredentialBlob, pcred.contents.CredentialBlobSize
        )
    finally:
        advapi32.CredFree(pcred)
    for enc in ("utf-16-le", "utf-8"):
        try:
            text = blob.decode(enc).rstrip("\x00").strip()
        except UnicodeDecodeError:
            continue
        if text:
            return text
    return ""


def load_key() -> str:
    """Resolve the Zep API key. Never logs the value."""
    key = os.environ.get(ENV_KEY, "").strip()
    if key:
        return key
    for target in CREDVAULT_TARGETS:
        try:
            key = _cred_read(target)
        except Exception:
            key = ""
        if key:
            return key
    return ""


def key_state() -> str:
    """Report WHERE a key resolves from without exposing it."""
    if os.environ.get(ENV_KEY, "").strip():
        return "KEY_PRESENT_ENV"
    for target in CREDVAULT_TARGETS:
        try:
            if _cred_read(target):
                return "KEY_PRESENT_CREDVAULT:" + target
        except Exception:
            continue
    return "NO_KEY"


def _request(method: str, path: str, body=None, key: str | None = None) -> dict:
    """One JSON round-trip. Raises ZepError on any failure; returns parsed dict."""
    key = key if key is not None else load_key()
    if not key:
        raise ZepError("NO_KEY")
    headers = {
        "Authorization": "Api-Key " + key,
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API_BASE + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise ZepError("HTTP_%d" % exc.code) from exc
    except urllib.error.URLError as exc:
        raise ZepError("TRANSPORT:%s" % exc.reason) from exc
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ZepError("BAD_REPLY") from exc


def create_graph(graph_id: str, name: str | None = None, description: str | None = None) -> dict:
    """Create a named graph. graph_id is the durable shared address peers write to."""
    body = {"graph_id": graph_id}
    if name:
        body["name"] = name
    if description:
        body["description"] = description
    return _request("POST", "/graph/create", body)


def add_fact(data: str, *, type: str = "text", graph_id: str = DEFAULT_GRAPH,
             source_description: str | None = None, metadata: dict | None = None) -> dict:
    """Append one episode to the graph. Returns the episode record incl. uuid (202)."""
    if len(data.encode("utf-8")) > MAX_DATA_BYTES:
        raise ZepError("DATA_TOO_LARGE")
    if type not in ("text", "json", "message", "fact_triple"):
        raise ZepError("BAD_TYPE")
    body = {"data": data, "type": type, "graph_id": graph_id}
    if source_description:
        body["source_description"] = source_description
    if metadata:
        body["metadata"] = metadata
    return _request("POST", "/graph", body)


def search(query: str, *, graph_id: str = DEFAULT_GRAPH, scope: str = "edges",
           limit: int = 10, reranker: str | None = None,
           search_filters: dict | None = None) -> dict:
    """Hybrid search over the graph. scope: edges|nodes|episodes|observations|thread_summaries|auto."""
    body = {"query": query, "graph_id": graph_id, "scope": scope, "limit": limit}
    if reranker:
        body["reranker"] = reranker
    if search_filters:
        body["search_filters"] = search_filters
    return _request("POST", "/graph/search", body)


def context(query: str, *, graph_id: str = DEFAULT_GRAPH, max_characters: int = 4000) -> str:
    """Auto-scope materialized context block — the world-state recall primitive."""
    r = search(query, graph_id=graph_id, scope="auto", limit=10,
               search_filters=None)
    # scope=auto returns {"context": "..."} instead of raw lists
    if "context" in r:
        return r["context"]
    return json.dumps(r)


def get_episode(uuid: str) -> dict:
    """Fetch one stored episode by uuid — proves durable write independent of extraction."""
    return _request("GET", "/graph/episodes/" + uuid)


def _self_test() -> int:
    """Offline checks only — no network, no key required."""
    assert key_state() in ("NO_KEY", "KEY_PRESENT_ENV") or key_state().startswith("KEY_PRESENT_CREDVAULT:")
    try:
        _request("POST", "/graph/search", {"query": "x"}, key="")
        print("FAIL: empty key did not raise")
        return 1
    except ZepError as e:
        assert str(e) == "NO_KEY"
    try:
        add_fact("x" * (MAX_DATA_BYTES + 1))
        print("FAIL: oversized data did not raise")
        return 1
    except ZepError as e:
        assert str(e) == "DATA_TOO_LARGE"
    print("self-test OK (key_state=%s)" % key_state())
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Zep world-state client for Commons swarm")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--key-state", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("create-graph")
    p.add_argument("--graph-id", required=True)
    p.add_argument("--name")
    p.add_argument("--description")

    p = sub.add_parser("add")
    p.add_argument("--data", required=True, help="episode text; use '-' to read stdin")
    p.add_argument("--type", default="text", choices=["text", "json", "message", "fact_triple"])
    p.add_argument("--graph-id", default=DEFAULT_GRAPH)
    p.add_argument("--source")

    p = sub.add_parser("search")
    p.add_argument("--query", required=True)
    p.add_argument("--graph-id", default=DEFAULT_GRAPH)
    p.add_argument("--scope", default="edges")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("context")
    p.add_argument("--query", required=True)
    p.add_argument("--graph-id", default=DEFAULT_GRAPH)

    p = sub.add_parser("episode")
    p.add_argument("--uuid", required=True)

    args = ap.parse_args(argv)
    if args.self_test:
        return _self_test()
    if args.key_state:
        print(key_state())
        return 0
    if not args.cmd:
        ap.print_help()
        return 2
    try:
        if args.cmd == "create-graph":
            out = create_graph(args.graph_id, args.name, args.description)
        elif args.cmd == "add":
            data = sys.stdin.read() if args.data == "-" else args.data
            out = add_fact(data, type=args.type, graph_id=args.graph_id,
                           source_description=args.source)
        elif args.cmd == "search":
            out = search(args.query, graph_id=args.graph_id, scope=args.scope,
                         limit=args.limit)
        elif args.cmd == "context":
            out = {"context": context(args.query, graph_id=args.graph_id)}
        else:
            out = get_episode(args.uuid)
    except ZepError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    print(json.dumps({"ok": True, "result": out}, indent=1)[:8000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
