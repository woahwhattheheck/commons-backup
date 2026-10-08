#!/usr/bin/env python3
"""Render verified MOVA planner JSON as linked, size-bounded internal Slack dispatch.

Use:
    python plan.py verified-manifest.json --format json | python render_dispatch.py -
    python render_dispatch.py verified-batch.json --format json --max-chars 4000

This tool does not verify new facts, contact providers, post Slack messages,
submit claims, or alter any payout or source attribution.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

SEPARATOR = "\n\n=== SLACK MESSAGE BREAK ===\n\n"


def clean(value: object, limit: int = 200) -> str:
    """Keep untrusted labels literal instead of injecting Slack formatting."""
    if value is None:
        return "unknown"
    out = " ".join(str(value).split())[:limit]
    return out.replace("<", "(").replace(">", ")").replace("|", "/") or "unknown"


def link(value: object, label: str) -> str:
    """Render only a genuine HTTPS URL as clickable Slack evidence."""
    if not isinstance(value, str) or not value:
        return "unverified"
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        return "unverified"
    if any(c.isspace() for c in value):
        return "unverified"
    safe_url = value.replace("<", "%3C").replace(">", "%3E").replace("|", "%7C")
    return f"<{safe_url}|{label}>"


def describe(order: dict) -> str:
    if not isinstance(order, dict):
        raise ValueError("each work order must be an object")
    required = ("action", "issue_url", "issue_key", "operation_id", "platform", "checked_at")
    if any(not isinstance(order.get(k), str) or not order[k] for k in required):
        raise ValueError("a work order lacks action/issue/operation/platform/checked_at")
    amount = order.get("reward_usd")
    if amount is None:
        price = "amount unverified"
    elif type(amount) in (int, float) and 0 <= amount <= 10_000_000 and amount == amount:
        price = f"advertised USD {amount:,.2f} (not awarded)"
    else:
        raise ValueError("invalid reward_usd")
    issue = link(order["issue_url"], clean(order["issue_key"], 100))
    meta = " | ".join((clean(order["action"], 60), issue,
                       clean(order["platform"], 35), price))
    details = [f"- *{meta}*", f"  ID: {clean(order['operation_id'], 180)}",
               f"  Sponsor PR: {link(order.get('pr_url'), 'existing upstream PR')}"
               f" | Source: {link(order.get('source_pr_url'), 'original fork carrier')}",
               f"  Funding evidence: {link(order.get('funding_url'), 'source link')}"
               f" | Active owner: {clean(order.get('active_owner'), 70)}",
               f"  Evidence checked: {clean(order['checked_at'], 45)}"
               f" | Eligibility: {clean(order.get('eligibility'), 40)}"
               f" | Claim: {clean(order.get('claim_state'), 30)}"]
    if order.get("reason"):
        details.append(f"  Next: {clean(order['reason'], 220)}")
    return "\n".join(details)


def dispatch_messages(batch: dict, max_chars: int = 4200) -> list[str]:
    if type(max_chars) is not int or not 500 <= max_chars <= 4800:
        raise ValueError("max_chars must be an integer between 500 and 4800")
    if not isinstance(batch, dict) or not isinstance(batch.get("work_orders"), list):
        raise ValueError("expected MOVA JSON batch with work_orders array")
    if not batch["work_orders"]:
        raise ValueError("no work orders in the snapshot")
    header = ("*MOVA VERIFIED BOUNTY DISPATCH* | "
              f"Snapshot: {clean(batch.get('as_of'), 60)}"
              f" | Actor: {clean(batch.get('actor'), 45)}\n"
              "Original contributor and compensation claims remain active. "
              "Advertised values are not awards or receiving-rail receipts. "
              "Re-fence current sponsor and provider states before writes.")
    chunks: list[list[str]] = []
    current: list[str] = []
    capacity = max_chars - len(header) - 28
    if capacity <= 0:
        raise ValueError("max_chars too small for dispatch header")
    for order in batch["work_orders"]:
        message = describe(order)
        if len(message) + 2 > capacity:
            raise ValueError("one work order exceeds requested Slack message limit")
        if current and sum(len(x) + 2 for x in current) + len(message) + 2 > capacity:
            chunks.append(current)
            current = []
        current.append(message)
    if current:
        chunks.append(current)
    result = [header + f"\n*Part {i}/{len(chunks)}*\n\n" + "\n\n".join(items)
              for i, items in enumerate(chunks, 1)]
    if any(len(m) > max_chars for m in result):
        raise ValueError("Slack dispatch overflow")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", nargs="?", default="-",
                        help="plan.py --format json output path, or - for stdin")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--max-chars", type=int, default=4200)
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.read() if args.batch == "-" else Path(args.batch).read_text(encoding="utf-8")
        messages = dispatch_messages(json.loads(raw), max_chars=args.max_chars)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"INPUT_HOLD: {exc}", file=sys.stderr)
        return 2
    if args.format == "json":
        print(json.dumps({"messages": messages}, ensure_ascii=False))
    else:
        print(SEPARATOR.join(messages))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
