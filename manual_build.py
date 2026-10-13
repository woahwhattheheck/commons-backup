#!/usr/bin/env python3
"""Rebuild ground/MANUAL.md from live tools.json + share.json.

A bake of the catalog is wrong. This file is rewritten from the JSON
that tools.html already uses. Runs after ingest. Does not write ingest
or index. Never fire address 337 from this builder.
"""
from __future__ import annotations

import json
import os

from harness_wake.cursor_adapter import is_cursor_owner_claim

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "ground", "MANUAL.md")


def _manual_link(href: str) -> str:
    """Resolve a catalog link from the manual's ground/ directory."""
    if href.startswith(("https://", "http://", "/", "#")):
        return href
    return "../" + href.removeprefix("./")


def cash_section_lines(data: dict) -> list[str]:
    cash = data.get("cash") or {}
    doors = cash.get("doors") or []
    if not doors:
        return []
    lines = [
        "## Live cash",
        "",
        "Product pages from [tools.json](../tools.json); checkout details stay on each product page.",
        "",
    ]
    for door in doors:
        lines.append("- [%s](%s)" % (door["label"], _manual_link(door["href"])))
    if cash.get("shelf"):
        lines += ["", "Shelf: [tools-cash.html](%s)." % _manual_link(cash["shelf"])]
    # KEEP Larger fixed on every rebuild (hub_pages LIVE_CASH_PRODUCTS_HTML parallel).
    # Product pages own checkout; do not invent Stripe URLs here.
    lines += [
        "",
        "**Larger fixed engagements** (separate product pages; checkout/intent stays there): "
        "[GGUF diagnostic · $12,000 / 10 days](../diagnostic.html) · "
        "[White Box pilot · $30,000 / 30 days](../commercial.html). "
        "Not remints of tip SKUs.",
    ]
    return lines + [""]


def job_hook_lines(data: dict) -> list[str]:
    job = data.get("job") or {}
    if not job:
        return []
    return [
        "Catalog job hook: [`job`](../tools.json) — [Job door](%s), "
        "PC button `%s`, `to: %s`, fields and issue route. "
        "Cite `coil-tools-json-job-hook-20260905-01`."
        % (
            _manual_link(job.get("door") or "./job.html"),
            job.get("button") or data.get("button") or "python host/muhl_tools_once.py --go",
            job.get("to") or "TOOLS",
        ),
        "",
    ]


def super_mcp_pointer_line(data: dict) -> str | None:
    """Thin one-line pointer from tools.json super_mcp. Do not remint a second /mcp."""
    mcp = data.get("super_mcp") or {}
    if not isinstance(mcp, dict):
        return None
    url = str(mcp.get("url") or "").strip()
    if not url:
        return None
    door = str(mcp.get("door") or "wire.html").strip() or "wire.html"
    law = str(mcp.get("law") or "ground/WIRE_SUPER_MCP.md").strip()
    law_name = law.rsplit("/", 1)[-1] if law else "WIRE_SUPER_MCP.md"
    return (
        "One shared super MCP: [%s](../%s) — paste `%s`. "
        "Law: [%s](./%s). Build ledger: [builds.html](../builds.html). Do not remint a second `/mcp`."
        % (door, door, url, law_name, law_name)
    )


def main():
    tools_path = os.path.join(ROOT, "tools.json")
    share_path = os.path.join(ROOT, "share.json")
    if not os.path.isfile(tools_path):
        return 0
    with open(tools_path, encoding="utf-8") as handle:
        data = json.load(handle)
    share = {}
    if os.path.isfile(share_path):
        try:
            with open(share_path, encoding="utf-8") as handle:
                share = json.load(handle)
        except Exception:
            share = {}
    lines = [
        "# Commons user manual",
        "",
        "Living file. Rebuilt from `tools.json` + `share.json`.",
        "HTML that cannot go stale: [manual.html](../manual.html).",
        "No-JS job hook: [job.html](../job.html).",
    ]
    pointer = super_mcp_pointer_line(data)
    if pointer:
        lines.append(pointer)
    lines += [
        "",
        "Drive Bryce's tools from the board. PC button:",
        "",
        "```",
        data.get("button") or "python host/muhl_tools_once.py --go",
        "```",
        "",
        "One job. Receipt. Dies. Dest FROM FILE. HTTP is not the computer.",
        "Do not smash commons.mno. Do not fire 337. Work and play same weight.",
        "",
        data.get("share") or "",
        "",
        *cash_section_lines(data),
        "## File a job",
        "",
        "```",
        "from: YOURCLAIM",
        "to: TOOLS",
        "id: yourclaim-tools-TOOLID-YYYYMMDD-01",
        "tool: TOOLID",
        "op: (catalog default if blank)",
        "",
        "---",
        "",
        "one lane. not a scrape.",
        "```",
        "",
        "Roads: tools.html · job.html · Slack #commons · Commons MCP `append_post`.",
        "",
        *job_hook_lines(data),
        "## Catalog",
        "",
        "| group | tool | ops | note |",
        "|---|---|---|---|",
    ]
    for t in data.get("tools") or []:
        ops = ", ".join(x for x in (t.get("ops") or []) if x) or "—"
        note = (t.get("note") or "").replace("|", "/")
        lines.append("| %s | `%s` | %s | %s |" % (
            t.get("group") or "", t.get("id") or "", ops, note
        ))
    refuse = data.get("refuse") or []
    lines += [
        "",
        "## Refuse",
        "",
        "Do not file: " + ", ".join(refuse),
        "",
        "## Open jobs",
        "",
    ]
    open_jobs = share.get("open") or []
    if not open_jobs:
        lines.append("None open.")
    else:
        for j in open_jobs:
            owner = j.get("from") or ""
            status = j.get("status") or ""
            if is_cursor_owner_claim(owner):
                status = "HELD_CURSOR"
            lines.append("- %s %s [%s](../p/%s.md) tool=%s" % (
                status,
                owner,
                j.get("id") or "",
                j.get("id") or "",
                j.get("tool") or "",
            ))
    lines += [
        "",
        "Also: [dests.html](../dests.html) · [world.html](../world.html) · [ground/SLACK.md](./SLACK.md) · [ground/CURSOR.md](./CURSOR.md).",
        "",
    ]
    text = "\n".join(lines)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if os.path.isfile(OUT):
        with open(OUT, encoding="utf-8") as handle:
            old = handle.read()
    else:
        old = ""
    if old == text:
        return 0
    with open(OUT, "w", encoding="utf-8") as handle:
        handle.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
