#!/usr/bin/env python3
"""host/pixel_heartbeat_emit.py — write one current honest heartbeat.

OWNER_MACHINE_BUILD_SWEEP first next action on a LANDED build:

  DEMON flight recorder — Keep; add a current pixel heartbeat emitter.

The PIXEL_HEARTBEAT contract already measures. It does not write.
This leftover writes one honest session-state file and lists it.
It does not invent presence. It does not refresh PLAYER2. It does
not remint host/pixel_heartbeat.py. titan: NOT_WRITTEN. No auth.

  python3 host/pixel_heartbeat_emit.py --self-test
  python3 host/pixel_heartbeat_emit.py --root . --from RIVET \\
    --path host/pixel_heartbeat_emit.py --verb shipping \\
    --on supergrok-heavy --src "Heavy packet consumed by current-main build" --sha <sha>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
HOST = os.path.join(ROOT, "host")
if HOST not in sys.path:
    sys.path.insert(0, HOST)

from pixel_heartbeat import (
    REQUIRED,
    claim_from_name,
    freshness_of,
    parse_heartbeat,
)


def utc_iso(now=None):
    """ISO UTC with Z. Invalid now falls back to wall clock."""
    if now is None:
        stamp = datetime.now(timezone.utc)
    elif isinstance(now, datetime):
        stamp = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        stamp = stamp.astimezone(timezone.utc)
    else:
        text = str(now).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            stamp = datetime.fromisoformat(text)
        except ValueError:
            stamp = datetime.now(timezone.utc)
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamp = stamp.astimezone(timezone.utc)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def claim_filename(claim):
    """RIVET → RIVET.json. Empty claim is empty name."""
    stem = str(claim or "").strip().upper()
    if not stem:
        return ""
    return stem + ".json"


def build_heartbeat(claim, path, src, ts, verb="", on="", sha=""):
    """Build one honest heartbeat object. Guessed/empty src is fabricated."""
    from_claim = str(claim or "").strip().upper()
    src_text = str(src or "").strip()
    path_text = str(path or "").strip()
    guessed = "guessed" in src_text.lower() and not path_text
    fabricated = (not src_text) or guessed or not path_text
    body = {
        "from": from_claim,
        "path": path_text,
        "verb": str(verb or "").strip(),
        "on": str(on or "").strip(),
        "ts": str(ts or "").strip(),
        "src": src_text,
        "sha": str(sha or "").strip(),
    }
    missing = [key for key in REQUIRED if not str(body.get(key) or "").strip()]
    return {
        "body": body,
        "name": claim_filename(from_claim),
        "valid": not missing and not fabricated,
        "fabricated": fabricated,
        "missing": missing,
        "error": (
            "empty src or guessed-without-path is fabricated"
            if fabricated
            else ("missing " + ", ".join(missing) if missing else "")
        ),
    }


def load_index_names(text):
    """Parse pixels/index.json. Invalid is measured empty."""
    try:
        data = json.loads(str(text or "") or "[]")
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    names = []
    seen = set()
    for item in data:
        name = str(item or "").strip()
        if not name.endswith(".json"):
            name = name + ".json"
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def merge_index(names, extra):
    """Append extra names without dropping listed files."""
    out = []
    seen = set()
    for name in list(names or []) + list(extra or []):
        item = str(name or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def emit_to_dir(pixel_dir, built, index_names=None):
    """Write one heartbeat and merge the index. Does not rewrite others."""
    if not built or not built.get("valid"):
        return {
            "wrote": False,
            "error": (built or {}).get("error") or "heartbeat is not honest",
        }
    name = built["name"]
    os.makedirs(pixel_dir, exist_ok=True)
    dest = os.path.join(pixel_dir, name)
    with open(dest, "w", encoding="utf-8") as handle:
        json.dump(built["body"], handle, indent=2)
        handle.write("\n")
    listed = merge_index(index_names, [name])
    index_path = os.path.join(pixel_dir, "index.json")
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump(listed, handle, indent=2)
        handle.write("\n")
    return {"wrote": True, "name": name, "index": listed, "path": dest}


def emit_root(root, claim, path, src, verb="", on="", sha="", ts="", now=None):
    """Emit one heartbeat under root/pixels. Preserves other listed names."""
    pixel_dir = os.path.join(os.path.abspath(root), "pixels")
    index_path = os.path.join(pixel_dir, "index.json")
    index_text = ""
    if os.path.isfile(index_path):
        with open(index_path, encoding="utf-8", errors="replace") as handle:
            index_text = handle.read()
    listed = load_index_names(index_text)
    stamp = str(ts or "").strip() or utc_iso(now)
    built = build_heartbeat(claim, path, src, stamp, verb=verb, on=on, sha=sha)
    result = emit_to_dir(pixel_dir, built, listed)
    result["heartbeat"] = built
    parsed = freshness_of(parse_heartbeat(built["name"], json.dumps(built["body"])), now)
    result["freshness"] = parsed.get("freshness")
    return result


def self_test():
    fake = build_heartbeat("DEMON", "", "guessed search", "2026-08-25T08:00:00Z")
    assert fake["fabricated"] is True, fake
    assert fake["valid"] is False, fake
    empty = build_heartbeat("RIVET", "host/pixel_heartbeat_emit.py", "", "2026-08-25T08:00:00Z")
    assert empty["fabricated"] is True, empty
    honest = build_heartbeat(
        "RIVET",
        "host/pixel_heartbeat_emit.py",
        "Cursor automation wrote the emitter",
        "2026-08-25T08:00:00Z",
        verb="shipping",
        on="cursor-cloud",
        sha="da2bd66b2bfa95847dc08bc4077a46385a8dbd77",
    )
    assert honest["valid"] is True, honest
    assert honest["name"] == "RIVET.json", honest
    merged = merge_index(["PLAYER2.json"], ["RIVET.json", "PLAYER2.json"])
    assert merged == ["PLAYER2.json", "RIVET.json"], merged
    parsed = freshness_of(
        parse_heartbeat(honest["name"], json.dumps(honest["body"])),
        "2026-08-25T08:01:00Z",
    )
    assert parsed["freshness"] == "HOT", parsed
    assert parsed["fabricated"] is False, parsed
    return "ok"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write one current honest pixel heartbeat")
    parser.add_argument("--root", default=".")
    parser.add_argument("--from", dest="claim", default="")
    parser.add_argument("--path", default="")
    parser.add_argument("--src", default="")
    parser.add_argument("--verb", default="")
    parser.add_argument("--on", default="")
    parser.add_argument("--sha", default="")
    parser.add_argument("--ts", default="")
    parser.add_argument("--now", default="")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--write", action="store_true", help="write pixels/{CLAIM}.json")
    args = parser.parse_args(argv)
    if args.self_test:
        print(self_test())
        return 0
    if not args.write:
        built = build_heartbeat(
            args.claim,
            args.path,
            args.src,
            args.ts or utc_iso(args.now or None),
            verb=args.verb,
            on=args.on,
            sha=args.sha,
        )
        print(json.dumps(built, indent=2, sort_keys=True))
        return 0 if built["valid"] else 1
    result = emit_root(
        args.root,
        args.claim,
        args.path,
        args.src,
        verb=args.verb,
        on=args.on,
        sha=args.sha,
        ts=args.ts,
        now=args.now or None,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("wrote") else 1


if __name__ == "__main__":
    sys.exit(main())
