#!/usr/bin/env python3
"""Prepare real search/read bindings for the connected tool router.

This translates one logical task into the current native tool schemas. It does
not call providers, infer account balances, or change route eligibility.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from integrations.shared_equipment.provider_io import EquipmentError
from host.connected_tool_router import load_routes


def prepare_request(task: dict, routes: list[dict], available_tools: list[str]) -> dict:
    if not isinstance(task, dict):
        raise EquipmentError("task must be a JSON object")
    operation = task.get("operation_id")
    if not isinstance(operation, str) or not operation.strip():
        raise EquipmentError("operation_id must be the existing nonempty task ID")
    capability = task.get("capability")
    if capability not in {"search", "url_read"}:
        raise EquipmentError("this request adapter supports search and url_read")
    if (not isinstance(available_tools, list)
            or any(not isinstance(name, str) or not name for name in available_tools)):
        raise EquipmentError("available_tools must contain discovered tool names")
    names = set(available_tools)
    sensitivity = task.get("input_sensitivity", "public")
    if sensitivity != "public":
        raise EquipmentError("public search/read input must have public sensitivity")
    bindings = {}
    session = task.get("session_id")
    if session is not None and (not isinstance(session, str) or len(session) < 32):
        raise EquipmentError("session_id must reuse the conversation's 32+ character identity")
    objective = task.get("objective", task.get("query", ""))
    if not isinstance(objective, str):
        raise EquipmentError("objective must be text")
    if capability == "search":
        query = task.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 2000:
            raise EquipmentError("search query must contain 1..2000 characters")
        if "search_queries" in task:
            queries = task["search_queries"]
            if (not isinstance(queries, list) or not 1 <= len(queries) <= 8
                    or any(not isinstance(q, str) or not q.strip() or len(q) > 500 for q in queries)):
                raise EquipmentError("search_queries must contain 1..8 nonempty bounded queries")
        else:
            # Parallel's bounded subqueries are a separate contract. Preserve
            # the full main query for other routes rather than truncating it or
            # rejecting those routes because Parallel needs a shorter query.
            queries = [query] if len(query) <= 500 else None
        arguments = {
            "mcp__codex_apps__tinyfish_search": {"query": query, "purpose": objective},
            "mcp__codex_apps__tavily_tavily_search": {
                "query": query, "search_depth": "basic", "max_results": 5},
            "mcp__codex_apps__firecrawl_firecrawl_search": {
                "query": query, "sources": ["web"], "domainTools": False, "limit": 5},
            "exa_search": {"query": query, "num_results": 5},
        }
        if session and queries is not None:
            for name in ("mcp__codex_apps__parallel_search_web_search", "parallel_anonymous_search"):
                arguments[name] = {"objective": objective or query,
                                   "search_queries": queries, "session_id": session}
    else:
        urls = task.get("urls")
        if not isinstance(urls, list) or not 1 <= len(urls) <= 5:
            raise EquipmentError("urls must contain 1..5 public HTTP(S) URLs")
        for url in urls:
            if not isinstance(url, str) or len(url) > 2048:
                raise EquipmentError("each URL must be bounded text")
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
                raise EquipmentError("URLs must be HTTP(S) without embedded credentials")
        arguments = {
            "mcp__codex_apps__tinyfish_fetch_content": {
                "urls": urls, "format": "markdown", "links": False,
                "image_links": False, "page_metadata": True,
                "ttl": 0, "purpose": objective},
            "mcp__codex_apps__tavily_tavily_extract": {
                "urls": urls, "extract_depth": "basic", "format": "markdown"},
            "exa_contents": {"urls": urls, "include_text": True},
        }
        if session:
            for name in ("mcp__codex_apps__parallel_search_web_fetch", "parallel_anonymous_fetch"):
                arguments[name] = {"urls": urls, "session_id": session,
                                   "objective": objective[:200]}
        if len(urls) == 1:
            arguments["jina_public_read"] = {"url": urls[0]}
            arguments["mcp__codex_apps__firecrawl_firecrawl_scrape"] = {
                "url": urls[0], "formats": ["markdown"], "onlyMainContent": True}
    alternate = {
        ("tavily-search", "url_read"): "mcp__codex_apps__tavily_tavily_extract",
        ("firecrawl-public", "url_read"): "mcp__codex_apps__firecrawl_firecrawl_scrape",
        ("exa-existing", "url_read"): "exa_contents",
    }
    for route in routes:
        if capability not in route.get("capabilities", []):
            continue
        name = (route.get("native_tools", {}).get(capability)
                or alternate.get((route["id"], capability)) or route.get("native_tool"))
        if name in names and name in arguments:
            bindings[route["id"]] = {"tool": name, "arguments": arguments[name],
                                       "task_domains": ["*"]}
    if not bindings:
        raise EquipmentError("no schema-supported binding is exposed on this carrier")
    request = {"operation_id": operation, "capability": capability, "effect": "read",
               "input_sensitivity": "public", "bindings": bindings}
    if "task_domain" in task:
        request["task_domain"] = task["task_domain"]
    return request


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routes-file", required=True)
    parser.add_argument("--tools-file", required=True,
                        help="private current-carrier discovered tool-name JSON array")
    args = parser.parse_args(argv)
    try:
        request = prepare_request(json.load(sys.stdin), load_routes(args.routes_file),
                                  json.loads(Path(args.tools_file).read_text(encoding="utf-8")))
        print(json.dumps(request, ensure_ascii=False, allow_nan=False))
        return 0
    except (EquipmentError, ValueError, TypeError, KeyError, OSError) as exc:
        print(f"connected tool request: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
