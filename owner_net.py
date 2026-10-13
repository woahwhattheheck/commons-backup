#!/usr/bin/env python3
"""Component implementation and operation."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(ROOT, "owner.json")
NET_TOPIC = "woahwhattheheck-commons-owner-net"
NET_HOSTS = (
    "https://ntfy.sh",
    "https://ntfy.envs.net",
    "https://ntfy.adminforge.de",
    "https://ntfy.mzte.de",
)
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
VIAS = ("pc", "phone")
USER_AGENT = "commons-owner-net"


def slot_hash(slot) -> str:
    if isinstance(slot, dict):
        h = str(slot.get("sha256") or "").strip().lower()
        return h if HASH_RE.match(h) else ""
    if isinstance(slot, str):
        h = slot.strip().lower()
        return h if HASH_RE.match(h) else ""
    return ""


def load_spec(path: str = SPEC_PATH) -> dict:
    if not os.path.isfile(path):
        return {
            "claim": "BRYCE",
            "algo": "sha256",
            "pepper": "commons-owner-v1",
            "slots": {"pc": None, "phone": None},
            "hashes": [],
        }
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    if not isinstance(spec, dict):
        raise SystemExit("owner.json is not an object")
    slots = spec.get("slots")
    if not isinstance(slots, dict):
        spec["slots"] = {"pc": None, "phone": None}
    else:
        spec["slots"] = {
            "pc": slots.get("pc"),
            "phone": slots.get("phone"),
        }
    return spec


def distinct_live(spec: dict) -> bool:
    pc = slot_hash((spec.get("slots") or {}).get("pc"))
    phone = slot_hash((spec.get("slots") or {}).get("phone"))
    return bool(pc and phone and pc != phone)


def refresh_hashes(spec: dict) -> None:
    hashes = []
    seen = set()
    slots = spec.get("slots") or {}
    for via in VIAS:
        h = slot_hash(slots.get(via))
        if not h or h in seen:
            continue
        seen.add(h)
        hashes.append({"sha256": h, "via": via})
    spec["hashes"] = hashes
    spec["claim"] = "BRYCE"
    spec["algo"] = "sha256"


def apply_sighting(spec: dict, digest: str, via: str) -> bool:
    """TOFU two-slot write. Returns True if owner.json would change."""
    h = str(digest or "").strip().lower()
    v = str(via or "").strip().lower()
    if not HASH_RE.match(h) or v not in VIAS:
        return False
    slots = spec.setdefault("slots", {"pc": None, "phone": None})
    pc = slot_hash(slots.get("pc"))
    phone = slot_hash(slots.get("phone"))
    if v == "pc":
        if pc:
            return False
        slots["pc"] = {"sha256": h}
        refresh_hashes(spec)
        return True
    # phone: never enroll the pc digest as the phone slot.
    if h == pc and pc:
        return False
    if not phone:
        slots["phone"] = {"sha256": h}
        refresh_hashes(spec)
        return True
    # phone was filled with the wifi (same as pc). Replace when cell appears.
    if phone == pc and h != pc:
        slots["phone"] = {"sha256": h}
        refresh_hashes(spec)
        return True
    return False


def parse_payload(raw: str) -> tuple[str, str]:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return "", ""
    if not isinstance(obj, dict) or obj.get("k") != "owner-net":
        return "", ""
    return slot_hash(obj), str(obj.get("via") or "").strip().lower()


def poll_host(host: str) -> list[tuple[str, str]]:
    url = "%s/%s/json?poll=1&since=12h" % (host, NET_TOPIC)
    req = urllib.request.Request(
        url, headers={"Accept": "application/x-ndjson", "User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return []
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        digest, via = parse_payload(str(ev.get("message") or ""))
        if digest and via:
            out.append((digest, via))
    return out


def collect_sightings() -> list[tuple[str, str]]:
    for host in NET_HOSTS:
        rows = poll_host(host)
        if rows:
            return rows
    return []


def persist(spec: dict, sightings: list[tuple[str, str]]) -> int:
    n = 0
    for digest, via in sightings:
        if apply_sighting(spec, digest, via):
            n += 1
    return n


IPV4_BLOB = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
IPV6_BLOB = re.compile(r"\b[0-9a-fA-F:]+:[0-9a-fA-F:]+\b")


def refuse_raw_ips(blob: str) -> None:
    if IPV4_BLOB.search(blob) or IPV6_BLOB.search(blob):
        raise SystemExit("owner.json would contain a raw IP — refusing to write")


def write_spec(spec: dict, path: str = SPEC_PATH) -> None:
    refresh_hashes(spec)
    blob = json.dumps(spec, indent=2) + "\n"
    refuse_raw_ips(blob)
    with open(path, "w", encoding="utf-8") as f:
        f.write(blob)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    spec = load_spec()
    sightings = collect_sightings()
    changed = persist(spec, sightings)
    if changed:
        write_spec(spec)
    live = "LIVE" if distinct_live(spec) else "OPEN"
    print("owner-net slots pc=%s phone=%s distinct=%s wrote=%d" % (
        "yes" if slot_hash((spec.get("slots") or {}).get("pc")) else "no",
        "yes" if slot_hash((spec.get("slots") or {}).get("phone")) else "no",
        live,
        changed,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
