#!/usr/bin/env python3
"""Component implementation and operation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(ROOT, "owner.json")
DEFAULT_PEPPER = "commons-owner-v1"
DEFAULT_ECHOES = (
    "https://api.ipify.org",
    "https://api64.ipify.org",
    "https://icanhazip.com",
)
IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
IPV6_RE = re.compile(r"^[0-9a-f:]+$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
USER_AGENT = "commons-owner-enroll"


def normalize_ip(raw: str) -> str:
    s = str(raw or "").strip()
    if s.startswith("[") and s.endswith("]"):
        s = s[1:-1]
    if "%" in s:
        s = s.split("%", 1)[0]
    if ":" in s:
        s = s.lower()
    return s


def looks_like_ip(s: str) -> bool:
    s = str(s or "")
    if IPV4_RE.match(s):
        return True
    if ":" in s and IPV6_RE.match(s):
        return True
    return False


def digest_ip(ip: str, pepper: str = DEFAULT_PEPPER) -> str:
    n = normalize_ip(ip)
    if not looks_like_ip(n):
        raise ValueError("not an IP")
    preimage = (pepper or DEFAULT_PEPPER) + "\n" + n
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


def load_spec() -> dict:
    if not os.path.isfile(SPEC_PATH):
        return {
            "claim": "BRYCE",
            "algo": "sha256",
            "pepper": DEFAULT_PEPPER,
            "hashes": [],
            "echoes": {"host": list(DEFAULT_ECHOES)},
        }
    with open(SPEC_PATH, encoding="utf-8") as f:
        spec = json.load(f)
    if not isinstance(spec, dict):
        raise SystemExit("owner.json is not an object")
    return spec


def echo_urls(spec: dict) -> list[str]:
    echoes = spec.get("echoes") if isinstance(spec.get("echoes"), dict) else {}
    raw = echoes.get("host") or echoes.get("browser") or list(DEFAULT_ECHOES)
    out = []
    seen = set()
    for url in raw:
        u = str(url or "").strip()
        if not u.startswith("https://") or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out or list(DEFAULT_ECHOES)


def fetch_ip(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("echo unreachable") from exc
    ip = normalize_ip(body)
    if not looks_like_ip(ip):
        raise RuntimeError("echo did not return an address")
    return ip


def collect_digests(spec: dict, explicit_ips: list[str]) -> list[str]:
    pepper = str(spec.get("pepper") or DEFAULT_PEPPER)
    found = []
    seen = set()

    def add(ip: str) -> None:
        digest = digest_ip(ip, pepper)
        if digest not in seen:
            seen.add(digest)
            found.append(digest)

    for raw in explicit_ips:
        add(raw)
    if explicit_ips:
        return found
    errors = 0
    for url in echo_urls(spec):
        try:
            add(fetch_ip(url))
        except (RuntimeError, ValueError):
            errors += 1
    if not found:
        raise SystemExit(
            "no digest. every echo failed (%d). try again, or pass --ip on a private fixture only."
            % errors
        )
    return found


def as_hash_item(item) -> str:
    if isinstance(item, str):
        h = item.strip().lower()
    elif isinstance(item, dict):
        h = str(item.get("sha256") or "").strip().lower()
    else:
        h = ""
    return h if HASH_RE.match(h) else ""


def write_hashes(spec: dict, digests: list[str]) -> int:
    hashes = spec.get("hashes")
    if not isinstance(hashes, list):
        hashes = []
    have = {as_hash_item(item) for item in hashes}
    have.discard("")
    added = 0
    for digest in digests:
        if digest in have:
            continue
        hashes.append({"sha256": digest})
        have.add(digest)
        added += 1
    spec["hashes"] = hashes
    spec["claim"] = "BRYCE"
    spec["algo"] = "sha256"
    if not spec.get("pepper"):
        spec["pepper"] = DEFAULT_PEPPER
    with open(SPEC_PATH, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
        f.write("\n")
    return added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Hash this network's public IP for owner.json. Never prints the IP."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="append new digests to owner.json (still does not print IPs)",
    )
    parser.add_argument(
        "--ip",
        action="append",
        default=[],
        dest="ips",
        help="fixture address for tests. do not pass a real public IP; echo mode never shows it",
    )
    args = parser.parse_args(argv)
    spec = load_spec()
    if spec.get("claim") not in (None, "BRYCE"):
        print("owner.json claim must stay BRYCE", file=sys.stderr)
        return 2
    try:
        digests = collect_digests(spec, args.ips)
    except ValueError:
        print("not an address (value omitted)", file=sys.stderr)
        return 2
    print("hashes only. the address never prints.")
    print("pepper: %s" % (spec.get("pepper") or DEFAULT_PEPPER))
    print("preimage: pepper + LF + normalized public IP")
    print("drop into owner.json hashes[]:")
    for digest in digests:
        print('  {"sha256":"%s"}' % digest)
    if args.write:
        added = write_hashes(spec, digests)
        print("owner.json wrote %d new digest(s). total %d." % (
            added, len(spec.get("hashes") or [])
        ))
    else:
        print("dry run. pass --write to append. do not commit a hash that is not his phone or PC.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
