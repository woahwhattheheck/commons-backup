#!/usr/bin/env python3
"""Route Slack @service tags to Slack custom tools, not missing in-harness calls.

Owner hub 1788319779.597119: if the harness has Slack but not Facebook,
@facebook is a Slack custom-tool job over the tagged body. Provider
sessions only Bryce can complete go to #provider-sign-in. #needs-bryce
remains the separate owner-exclusive queue for non-provider actions. Not a
Commons gate.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = ROOT / "ground" / "SLACK_SERVICE_TAGS.json"

USER_MENTION = re.compile(r"<@U[A-Z0-9]+(?:\|[^>]+)?>")
CHANNEL_MENTION = re.compile(r"<#[A-Z0-9]+(?:\|[^>]+)?>")
SPECIAL_MENTION = re.compile(r"<![a-zA-Z0-9_]+(?:\|[^>]+)?>")
TAG_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z][A-Za-z0-9_-]{0,31})\b")


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_CATALOG
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("catalog is not an object")
    return data


def _reserved(catalog: dict[str, Any]) -> set[str]:
    return {str(x).lower() for x in catalog.get("reserved_tags") or []}


def _aliases(catalog: dict[str, Any]) -> dict[str, str]:
    raw = catalog.get("aliases") or {}
    out: dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            src = str(key).lower().strip()
            dest = str(value).lower().strip()
            if src and dest:
                out[src] = dest
    return out


def canonical_tag(tag: str, catalog: dict[str, Any] | None = None) -> str:
    cat = catalog if catalog is not None else load_catalog()
    raw = str(tag or "").lower().strip()
    return _aliases(cat).get(raw, raw)


def extract_tags(text: str, catalog: dict[str, Any] | None = None) -> list[str]:
    """Return canonical service tags in order, first occurrence only."""
    cat = catalog if catalog is not None else load_catalog()
    reserved = _reserved(cat)
    stripped = USER_MENTION.sub(" ", text or "")
    stripped = CHANNEL_MENTION.sub(" ", stripped)
    stripped = SPECIAL_MENTION.sub(" ", stripped)
    found: list[str] = []
    seen: set[str] = set()
    for match in TAG_RE.finditer(stripped):
        raw = match.group(1).lower()
        if raw in reserved:
            continue
        tag = canonical_tag(raw, cat)
        if tag in reserved or tag in seen:
            continue
        seen.add(tag)
        found.append(tag)
    return found


def remainder(text: str, tags: list[str], catalog: dict[str, Any] | None = None) -> str:
    """Body with @tags and their aliases removed. User/channel mentions stay."""
    body = text or ""
    cat = catalog if catalog is not None else load_catalog()
    spellings = set(tags)
    wanted = {str(t).lower() for t in tags}
    for src, dest in _aliases(cat).items():
        if dest in wanted or src in wanted:
            spellings.add(src)
            spellings.add(dest)
    for tag in spellings:
        body = re.sub(
            r"(?<![A-Za-z0-9_])@" + re.escape(tag) + r"\b",
            " ",
            body,
            flags=re.IGNORECASE,
        )
    return re.sub(r"[ \t]+", " ", body).strip()


def _connected_set(connected: list[str] | tuple[str, ...] | None) -> set[str]:
    return {str(x).lower() for x in (connected or []) if str(x).strip()}


def _signin_channel(catalog: dict[str, Any]) -> dict[str, Any]:
    """Provider-session queue. Prefers #provider-sign-in when installed."""
    install = catalog.get("install") if isinstance(catalog.get("install"), dict) else {}
    login = install.get("login_channel") if isinstance(install.get("login_channel"), dict) else {}
    if str(login.get("id") or "").strip():
        return login
    owner = catalog.get("owner_signin_channel")
    return owner if isinstance(owner, dict) else {}


def _peer_harness_connected(spec: dict[str, Any]) -> dict[str, Any] | None:
    """Another desk already measured tools-live. Do not reopen NEED."""
    raw = spec.get("peer_harness_connected")
    if not isinstance(raw, dict):
        return None
    desk = str(raw.get("desk") or "").strip()
    source_ts = str(raw.get("source_ts") or "").strip()
    if not desk and not source_ts:
        return None
    return raw


def route(
    text: str,
    connected: list[str] | tuple[str, ...] | None = None,
    catalog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Turn a Slack message into service jobs. Never rejects a Commons post."""
    cat = catalog if catalog is not None else load_catalog()
    tags = extract_tags(text, cat)
    body = remainder(text, tags, cat)
    connected_ids = _connected_set(connected)
    services = cat.get("services") or {}
    signin = _signin_channel(cat)
    jobs: list[dict[str, Any]] = []
    for tag in tags:
        spec = services.get(tag) if isinstance(services, dict) else None
        if not isinstance(spec, dict):
            jobs.append(
                {
                    "tag": tag,
                    "slack_tool": "@" + tag,
                    "road": "UNKNOWN",
                    "body": body,
                    "needs_owner_signin": False,
                }
            )
            continue
        in_when = {str(x).lower() for x in spec.get("in_harness_when") or []}
        in_harness = bool(in_when & connected_ids)
        job: dict[str, Any] = {
            "tag": tag,
            "slack_tool": str(spec.get("slack_tool") or ("@" + tag)),
            "body": body,
            "needs_owner_signin": bool(spec.get("needs_owner_signin")),
        }
        if in_harness:
            job["road"] = "IN_HARNESS"
        else:
            job["road"] = "SLACK_CUSTOM_TOOL"
            peer = _peer_harness_connected(spec)
            if peer:
                job["peer_desk"] = str(peer.get("desk") or "")
                job["this_process_tools"] = False
                seats = peer.get("measured_cloud_seats")
                if isinstance(seats, list) and seats:
                    job["measured_cloud_seats"] = [
                        str(seat).strip() for seat in seats if str(seat).strip()
                    ]
            elif job["needs_owner_signin"]:
                jobs.append(
                    {
                        "tag": tag,
                        "slack_tool": job["slack_tool"],
                        "road": "OWNER_SIGNIN",
                        "body": body,
                        "channel_id": str(signin.get("id") or "C0BUFA9G23E"),
                        "channel_name": str(signin.get("name") or "#provider-sign-in"),
                        "kind": "OWNER_BLOCKER",
                    }
                )
        jobs.append(job)
    result = {
        "gate": False,
        "commons_admission": False,
        "tags": tags,
        "body": body,
        "jobs": jobs,
        "owner_signin_channel_id": str(signin.get("id") or "C0BUFA9G23E"),
    }
    result["slack_jobs"] = slack_jobs(result)
    return result


def format_owner_blocker(job: dict[str, Any]) -> str:
    """Provider-sign-in OWNER_BLOCKER shape. Never includes secrets."""
    tag = str(job.get("tag") or "service")
    body = str(job.get("body") or "").strip()
    return (
        f"NEED: complete the official {tag} provider session in that provider's UI\n"
        f"WHY ONLY BRYCE: this harness has Slack, not an in-harness {tag} tool\n"
        f"SMALLEST ACTION: sign in on the official {tag} site/app, then reply in thread\n"
        f"EVIDENCE: Slack custom-tool job @{tag}\n"
        f"AFTER: peer resumes the tagged body through @{tag}\n"
        f"BODY: {body}\n"
        "Do not paste a password, API key, session token, or other secret into Slack."
    )


def slack_jobs(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Harness-facing Slack payloads. Missing tools never reject a Commons post."""
    out: list[dict[str, Any]] = []
    for job in result.get("jobs") or []:
        road = str(job.get("road") or "")
        if road == "OWNER_SIGNIN":
            out.append(
                {
                    "channel_id": str(job.get("channel_id") or "C0BUFA9G23E"),
                    "channel_name": str(job.get("channel_name") or "#provider-sign-in"),
                    "kind": "OWNER_BLOCKER",
                    "tag": job.get("tag"),
                    "text": format_owner_blocker(job),
                    "copy_secrets": False,
                }
            )
        elif road == "SLACK_CUSTOM_TOOL":
            payload = {
                "channel_id": None,
                "kind": "SLACK_CUSTOM_TOOL",
                "tag": job.get("tag"),
                "tool": job.get("slack_tool"),
                "text": job.get("body"),
                "copy_secrets": False,
            }
            if job.get("peer_desk"):
                payload["peer_desk"] = job.get("peer_desk")
                payload["this_process_tools"] = False
            if job.get("measured_cloud_seats"):
                payload["measured_cloud_seats"] = list(job.get("measured_cloud_seats") or [])
            out.append(payload)
        elif road == "IN_HARNESS":
            out.append(
                {
                    "channel_id": None,
                    "kind": "IN_HARNESS",
                    "tag": job.get("tag"),
                    "tool": job.get("slack_tool"),
                    "text": job.get("body"),
                    "copy_secrets": False,
                }
            )
        elif road == "UNKNOWN":
            out.append(
                {
                    "channel_id": None,
                    "kind": "UNKNOWN",
                    "tag": job.get("tag"),
                    "tool": job.get("slack_tool"),
                    "text": job.get("body"),
                    "copy_secrets": False,
                    "note": "not rejection; add the service to the catalog",
                }
            )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default="", help="Slack message text")
    parser.add_argument(
        "--connected",
        default="",
        help="comma-separated tools this harness already has (e.g. slack,github)",
    )
    parser.add_argument("--catalog", default="", help="override catalog path")
    args = parser.parse_args(argv)
    catalog = load_catalog(Path(args.catalog) if args.catalog else None)
    connected = [p.strip() for p in str(args.connected).split(",") if p.strip()]
    result = route(args.text, connected=connected, catalog=catalog)
    print(json.dumps(result, indent=2))
    print("", end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
