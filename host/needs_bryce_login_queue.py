#!/usr/bin/env python3
"""Exact-action queue for #needs-bryce. Not a Commons admission gate.

Owner hub 1788319779.597119: provider sessions only Bryce can complete
go to existing #needs-bryce (C0BRX6EV739). Channel law: a top-level post
must include a clickable URL or literal command, the expected visible
result, and the worker that resumes afterward.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_QUEUE = ROOT / "ground" / "NEEDS_BRYCE_QUEUE.json"

REQUIRED = (
    "NEED",
    "WHY ONLY BRYCE",
    "SMALLEST ACTION",
    "EVIDENCE",
    "AFTER",
)

SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|api[_-]?key|client_secret|access_token|refresh_token|"
    r"session(?:_?token)?|token|xox[pbasr]-|ghp_|github_pat_|sk-ant-|sk-)\s*[:=]"
)
URL_RE = re.compile(r"https://[^\s>|]+")
SLASH_RE = re.compile(r"(?:^|\s)/[A-Za-z][A-Za-z0-9_-]*(?:\s+\S+)?")
SHELL_RE = re.compile(
    r"(?:^|\s)(?:slack|python3|git|gh|curl)\s+\S+",
    re.IGNORECASE,
)
VAGUE_RE = re.compile(
    r"(?i)\b(owner gate|need owner|whenever you can|please advise|status report|"
    r"code word|just approve)\b"
)

# Official provider consoles. Never a password field. App secrets stay off Slack.
SIGNIN_URLS = {
    "facebook": "https://developers.facebook.com/apps/",
    "instagram": "https://developers.facebook.com/docs/instagram-platform/",
    "linkedin": "https://www.linkedin.com/developers/apps",
    "x": "https://developer.x.com/en/portal/dashboard",
    "threads": "https://developers.facebook.com/docs/threads",
    "tiktok": "https://developers.tiktok.com/",
    "youtube": "https://console.cloud.google.com/apis/library/youtube.googleapis.com",
    "reddit": "https://www.reddit.com/prefs/apps",
    "bluesky": "https://bsky.app/settings",
    "discord": "https://discord.com/developers/applications",
    "whatsapp": "https://developers.facebook.com/docs/whatsapp/cloud-api/get-started",
    "telegram": "https://my.telegram.org/apps",
    "google": "https://console.cloud.google.com/",
    "calendar": "https://console.cloud.google.com/apis/library/calendar-json.googleapis.com",
    "drive": "https://console.cloud.google.com/apis/library/drive.googleapis.com",
    "dropbox": "https://www.dropbox.com/developers/apps",
    "notion": "https://www.notion.so/my-integrations",
    "linear": "https://linear.app/settings/api",
    "figma": "https://www.figma.com/developers",
    "stripe": "https://dashboard.stripe.com/apikeys",
    "shopify": "https://partners.shopify.com/",
    "paypal": "https://developer.paypal.com/dashboard/",
    "salesforce": "https://login.salesforce.com/",
    "hubspot": "https://app.hubspot.com/",
    "zoom": "https://marketplace.zoom.us/develop/create",
    "openai": "https://platform.openai.com/api-keys",
    "anthropic": "https://console.anthropic.com/",
    "xai": "https://console.x.ai/",
    "slack_cli": None,
}


def load_queue(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_QUEUE
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("queue spec is not an object")
    return data


def signin_url(tag: str) -> str | None:
    return SIGNIN_URLS.get(str(tag or "").lower().strip())


def has_action_surface(smallest: str) -> bool:
    text = str(smallest or "")
    if URL_RE.search(text):
        return True
    if SLASH_RE.search(text):
        return True
    if SHELL_RE.search(text):
        return True
    return False


def contains_secret(blob: str) -> bool:
    return bool(SECRET_RE.search(blob or ""))


def validate_item(item: dict[str, Any]) -> list[str]:
    """Return problem strings. Empty list means the item may be posted."""
    problems: list[str] = []
    fields = {str(k).upper(): str(item.get(k) or item.get(k.lower()) or "").strip() for k in REQUIRED}
    # Also accept exact keys.
    for key in REQUIRED:
        if not str(item.get(key) or "").strip():
            # try already-normalized
            if not fields.get(key):
                problems.append("missing:" + key)
    need = str(item.get("NEED") or "").strip()
    why = str(item.get("WHY ONLY BRYCE") or "").strip()
    smallest = str(item.get("SMALLEST ACTION") or "").strip()
    evidence = str(item.get("EVIDENCE") or "").strip()
    after = str(item.get("AFTER") or "").strip()
    blob = "\n".join([need, why, smallest, evidence, after])
    if contains_secret(blob):
        problems.append("secrets_forbidden")
    if not has_action_surface(smallest):
        problems.append("no_action_surface")
    if VAGUE_RE.search(need) or VAGUE_RE.search(smallest):
        problems.append("vague_owner_gate")
    if "commons admission" in (need + why).lower():
        problems.append("not_a_commons_gate")
    return problems


def format_item(item: dict[str, Any], queue: dict[str, Any] | None = None) -> str:
    problems = validate_item(item)
    if problems:
        raise ValueError("invalid needs-bryce item: " + ",".join(problems))
    spec = queue if queue is not None else load_queue()
    channel = str(spec.get("channel_name") or "needs-bryce")
    worker = str(item.get("resume_worker_url") or spec.get("resume_worker_url") or "").strip()
    lines = [
        f"*#needs-bryce exact action* (`{channel}` / `{spec.get('channel_id')}`). Not a Commons login.",
        f"*NEED:* {item['NEED'].strip()}",
        f"*WHY ONLY BRYCE:* {item['WHY ONLY BRYCE'].strip()}",
        f"*SMALLEST ACTION:* {item['SMALLEST ACTION'].strip()}",
        f"*EVIDENCE:* {item['EVIDENCE'].strip()}",
        f"*AFTER:* {item['AFTER'].strip()}",
    ]
    expected = str(item.get("EXPECTED") or "").strip()
    if expected:
        lines.append(f"*EXPECTED VISIBLE RESULT:* {expected}")
    if worker:
        lines.append(f"*RESUME:* {worker}")
    lines.append("Do not paste a password, API key, session token, or other secret into Slack.")
    return "\n".join(lines)


def provider_signin_item(
    tag: str,
    body: str = "",
    evidence: str = "owner hub 1788319779.597119",
    resume_worker_url: str = "",
) -> dict[str, Any]:
    name = str(tag or "service").lower().strip() or "service"
    url = signin_url(name)
    if name == "slack_cli":
        raise ValueError("use slack_cli_ticket_item for Slack CLI login")
    if not url:
        url = "https://developers.facebook.com/apps/" if name == "facebook" else ""
        if not url:
            raise ValueError("no official sign-in URL for tag:" + name)
    remainder = str(body or "").strip()
    action = (
        f"Open {url} while signed into the owner {name} account. "
        "Create or open the official app/console, complete that provider's login UI, "
        "then reply in this thread with OWNER ACTION DONE and only the public app id "
        "(never the secret)."
    )
    if remainder:
        action += f" Tagged body waiting: {remainder}"
    return {
        "NEED": (
            f"complete the official {name} provider session so Slack custom tool "
            f"@{name} can drive that service"
        ),
        "WHY ONLY BRYCE": (
            f"this harness has Slack MCP, not an in-harness {name} connector; "
            f"{name} app creation / OAuth is an owner account action"
        ),
        "SMALLEST ACTION": action,
        "EVIDENCE": evidence,
        "AFTER": (
            f"this desk stores the public {name} app id locally (not in git/Slack) "
            f"and resumes the tagged @{name} custom tool"
        ),
        "EXPECTED": f"{name} developer console visible while signed in",
        "resume_worker_url": resume_worker_url,
        "channel_id": "C0BRX6EV739",
        "tag": name,
        "copy_secrets": False,
    }


def slack_cli_ticket_item(
    slash_command: str,
    evidence: str = "owner hub 1788319779.597119",
    resume_worker_url: str = "",
) -> dict[str, Any]:
    cmd = str(slash_command or "").strip()
    if not cmd.startswith("/slackauthticket "):
        raise ValueError("slash_command must be /slackauthticket <ticket>")
    return {
        "NEED": "authenticate Slack CLI on this workspace so the custom-tools app can be installed",
        "WHY ONLY BRYCE": (
            "slack login --no-prompt prints a one-use ticket; Slack renders the "
            "challenge code only to the human who sends the slash command"
        ),
        "SMALLEST ACTION": (
            f"Paste this exact slash command into the Slack message box of this "
            f"workspace (any channel) and send it.\n{cmd}\n"
            "Then reply in this thread with the challenge code from the Slack modal."
        ),
        "EVIDENCE": evidence,
        "AFTER": (
            "this desk runs `slack login --ticket <ticket> --challenge <code>` "
            "then `slack run` to install Commons Service Tools"
        ),
        "EXPECTED": "Slack modal with a short challenge code (not a browser page)",
        "resume_worker_url": resume_worker_url,
        "channel_id": "C0BRX6EV739",
        "tag": "slack_cli",
        "copy_secrets": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="", help="provider tag (facebook, discord, ...)")
    parser.add_argument("--body", default="", help="tagged remainder body")
    parser.add_argument("--slash", default="", help="/slackauthticket ...")
    args = parser.parse_args(argv)
    if args.slash:
        item = slack_cli_ticket_item(args.slash)
    elif args.tag:
        item = provider_signin_item(args.tag, args.body)
    else:
        parser.error("need --tag or --slash")
    print(format_item(item))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
