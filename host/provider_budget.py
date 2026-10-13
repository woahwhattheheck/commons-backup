#!/usr/bin/env python3
"""Cooperating GitHub publication admission using the existing request budget.

Use the same state directory or --url for one shared command-center authority.
Renew before each connector write and release the lease in finally. This command
performs no provider calls and never sleeps, retries or schedules work.
"""
from __future__ import annotations

import argparse
import http.client
import json
import math
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from integrations.command_center.provider_admission import execute, SCOPE, SHARED_SCOPES


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def shared_request(url, payload, timeout=30):
    """Never replay a POST, follow redirects or fall back to a local ledger."""
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError("--url requires an HTTP(S) command-center base URL without credentials, query or fragment.")
    if not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError("--timeout must be greater than zero and at most 120 seconds.")
    request = urllib.request.Request(url.rstrip("/") + "/api/provider/admission",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"})

    def read_response(response):
        raw = response.read(1048577)
        if len(raw) > 1048576:
            raise ValueError("Shared admission response exceeded the size limit.")
        result = json.loads(raw)
        if not isinstance(result, dict) or type(result.get("ok")) is not bool:
            raise ValueError("Shared admission response requires a boolean ok field.")
        if result["ok"]:
            if result.get("scope") not in {SCOPE, *SHARED_SCOPES}:
                raise ValueError("Shared admission response has no recognized scope.")
            if payload["action"] in {"acquire", "renew"}:
                if (result.get("scope") != SCOPE or result.get("holder") != payload["holder"]
                        or not re.fullmatch(r"[0-9a-f]{32}", str(result.get("lease_id", "")))
                        or not isinstance(result.get("expires_at"), str)):
                    raise ValueError("Shared admission response has no matching lease receipt.")
                if payload["action"] == "renew" and result["lease_id"] != payload["lease_id"]:
                    raise ValueError("Shared admission renewed a different lease.")
        return result

    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            return read_response(response)
    except urllib.error.HTTPError as exc:
        with exc:
            try:
                result = read_response(exc)
            except (OSError, ValueError, UnicodeError, http.client.HTTPException):
                result = {"error": "provider_admission_http_error"}
            result.update(ok=False, http_status=exc.code)
            if exc.headers.get("Retry-After") is not None:
                result["retry_after_header"] = exc.headers["Retry-After"]
            if exc.code >= 500:
                result["status"] = "uncertain"
            return result
    except (OSError, ValueError, UnicodeError, http.client.HTTPException):
        return {"ok": False, "error": "provider_admission_transport_uncertain", "status": "uncertain",
                "message": "Do not publish. Read shared status and reconcile the original action before retrying."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    authority = parser.add_mutually_exclusive_group(required=True)
    authority.add_argument("--state-dir", type=Path)
    authority.add_argument("--url", help="shared command-center base URL through an existing trusted transport")
    parser.add_argument("--timeout", type=float, default=30, help="shared authority request timeout, at most 120 seconds")
    commands = parser.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("configure", help="coordinator sets the shared concurrency cap")
    configure.add_argument("--capacity", type=int, required=True)
    commands.add_parser("status")
    acquire = commands.add_parser("acquire", help="admit one publication per unique holder")
    renew = commands.add_parser("renew", help="check ownership/cooldown and extend before each write")
    release = commands.add_parser("release")
    release.add_argument("--successful", action="store_true", help="reset expired fallback after confirmed provider success")
    for command in (acquire, renew, release):
        command.add_argument("--holder", required=True)
    for command in (acquire, renew):
        command.add_argument("--ttl-seconds", type=int, default=300)
    for command in (renew, release):
        command.add_argument("--lease-id", required=True)
    limited = commands.add_parser("limited", help="record observed provider rate-limit evidence")
    limited.add_argument("--retry-after", help="provider seconds or HTTP date; omit if unavailable")
    limited.add_argument("--reset-at", type=float, help="provider reset epoch when primary quota is exhausted")
    limited.add_argument("--primary-core", action="store_true", help="only for confirmed primary core quota exhaustion")
    limited.add_argument("--observation-id", help="stable unique ID for this provider response; reuse exact evidence on retry")
    args = parser.parse_args(argv)
    try:
        payload = {key: value for key, value in vars(args).items()
                   if key not in {"url", "state_dir", "timeout", "command"} and value is not None}
        payload["action"] = args.command
        result = shared_request(args.url, payload, args.timeout) if args.url else execute(args.state_dir, payload)
        print(json.dumps(result), flush=True)
        return 0 if result.get("ok") is True else (75 if result.get("error") == "provider_admission_deferred" else 1)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": "provider_admission_failed", "message": str(exc)}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
