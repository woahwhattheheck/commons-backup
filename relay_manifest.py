#!/usr/bin/env python3
"""One ntfy relay source for Python roads and generated browser declarations."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Sequence
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
DEFAULT_PATH = ROOT / "relay-manifest.json"
BEGIN = "// BEGIN GENERATED COMMONS NTFY RELAYS"
END = "// END GENERATED COMMONS NTFY RELAYS"

# These are format adapters, not separate relay lists.  Every target receives
# exactly the ordered origins and topic from relay-manifest.json.
TARGETS = {
    "carrier.js": {
        "indent": "  ",
        "kind": "var",
        "topic": "NTFY_TOPIC",
        "hosts": "NTFY_HOSTS",
        "markers": False,
    },
    "board.js": {"indent": "  ", "kind": "var", "topic": "NTFY_TOPIC", "hosts": "NTFY_HOSTS"},
    "bazaar.js": {"indent": "  ", "kind": "var", "topic": "topic", "hosts": "hosts"},
    "reply.js": {"indent": "  ", "kind": "var", "topic": "NTFY_TOPIC", "hosts": "NTFY_HOSTS"},
    "action.html": {"indent": "", "kind": "var", "topic": "topic", "hosts": "hosts"},
    "door/src/protocol.ts": {
        "indent": "",
        "kind": "export_const",
        "topic": "NTFY_TOPIC",
        "hosts": "NTFY_HOSTS",
    },
}
JS_TARGETS = TARGETS  # Compatibility name used by existing checks.


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def load_manifest(path: Path = DEFAULT_PATH) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    if manifest.get("schema") != "commons-relay-manifest-v1":
        raise ValueError("unsupported relay manifest schema")
    if manifest.get("participation_effect") != "NONE":
        raise ValueError("relay manifest must stay descriptive")
    if manifest.get("delivery_policy") != "SEQUENTIAL_FIRST_ACCEPT":
        raise ValueError("relay delivery policy drift")
    if manifest.get("observation_policy") != "DIRECT_POLL_EVERY_RELAY":
        raise ValueError("relay observation policy drift")
    topic = manifest.get("topic")
    if not isinstance(topic, str) or not topic or "/" in topic:
        raise ValueError("relay topic must be one nonempty path segment")
    rows = manifest.get("relays")
    if not isinstance(rows, list) or not rows:
        raise ValueError("relay manifest has no relays")
    expected_order = list(range(1, len(rows) + 1))
    if [row.get("order") for row in rows] != expected_order:
        raise ValueError("relay order must be contiguous and start at one")
    urls = []
    for row in rows:
        url = str(row.get("url") or "").rstrip("/")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
            raise ValueError("relay URL must be an HTTPS origin: %r" % url)
        urls.append(url)
    if len(urls) != len(set(urls)):
        raise ValueError("relay URLs must be unique")
    return {**manifest, "relays": [{**row, "url": urls[index]} for index, row in enumerate(rows)]}


def manifest_digest(manifest: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()


def relay_urls(manifest: dict) -> tuple[str, ...]:
    return tuple(row["url"] for row in manifest["relays"])


def render_block(manifest: dict, target: str, newline: str = "\n") -> str:
    config = TARGETS[target]
    indent = config["indent"]
    inner = indent + "  "
    urls = relay_urls(manifest)
    if config["kind"] == "export_const":
        declare = "export const "
        hosts_suffix = " as const"
    else:
        declare = "var "
        hosts_suffix = ""
    lines = [
        "%s%s%s = %s;" % (indent, declare, config["topic"], json.dumps(manifest["topic"])),
        "%s%s%s = [" % (indent, declare, config["hosts"]),
    ]
    for index, url in enumerate(urls):
        comma = "," if index + 1 < len(urls) or config["kind"] == "export_const" else ""
        lines.append("%s%s%s" % (inner, json.dumps(url), comma))
    lines.append(indent + "]" + hosts_suffix + ";")
    if config.get("markers", True):
        lines.insert(0, indent + BEGIN)
        lines.append(indent + END)
    return newline.join(lines)


def _generated_pattern(target: str) -> re.Pattern[str]:
    indent = re.escape(TARGETS[target]["indent"])
    return re.compile(
        r"(?ms)^" + indent + re.escape(BEGIN) + r"\r?\n.*?^" + indent + re.escape(END) + r"(?=\r?$)"
    )


def _initial_pattern(target: str) -> re.Pattern[str]:
    if target in ("carrier.js", "board.js", "reply.js"):
        return re.compile(
            r"(?ms)^  var NTFY_TOPIC = .*?;\r?\n  var NTFY_HOSTS = \[\r?\n.*?^  \];(?=\r?$)"
        )
    if target == "bazaar.js":
        return re.compile(r"(?m)^  var hosts = \[.*?\];\r?\n  var topic = .*?;(?=\r?$)")
    if target == "action.html":
        return re.compile(r"(?m)^var topic=.*?;\r?\nvar hosts=.*?;(?=\r?$)")
    if target == "door/src/protocol.ts":
        return re.compile(
            r"(?ms)^export const NTFY_TOPIC = .*?;\r?\n"
            r"export const NTFY_BYTE_CAP = ([^\r\n]+);\r?\n"
            r"export const NTFY_HOSTS = \[\r?\n.*?^\] as const;(?=\r?$)"
        )
    raise ValueError("unknown relay target: %s" % target)


def sync_text(text: str, target: str, manifest: dict) -> str:
    if target not in TARGETS:
        raise ValueError("unknown relay target: %s" % target)
    newline = "\r\n" if "\r\n" in text else "\n"
    replacement = render_block(manifest, target, newline)
    generated = _generated_pattern(target)
    if TARGETS[target].get("markers", True) and generated.search(text):
        updated, count = generated.subn(lambda _match: replacement, text, count=1)
    else:
        initial = _initial_pattern(target)
        if target == "door/src/protocol.ts":
            replacement += newline + "export const NTFY_BYTE_CAP = \\1;"
            updated, count = initial.subn(lambda match: replacement.replace("\\1", match.group(1)), text, count=1)
        else:
            updated, count = initial.subn(lambda _match: replacement, text, count=1)
    if count != 1:
        raise ValueError("expected one relay block in %s, found %d" % (target, count))
    return updated


def sync_js_text(text: str, target: str, manifest: dict) -> str:
    """Compatibility wrapper retained for earlier tests and callers."""
    return sync_text(text, target, manifest)


def sync_file(path: Path, target: str, manifest: dict, write: bool) -> bool:
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    updated = sync_text(text, target, manifest)
    changed = updated != text
    if changed and write:
        path.write_bytes(updated.encode("utf-8"))
    return changed


MANIFEST = load_manifest()
NTFY_TOPIC = MANIFEST["topic"]
NTFY_HOSTS = relay_urls(MANIFEST)
NTFY_MANIFEST_DIGEST = manifest_digest(MANIFEST)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    manifest = load_manifest((args.manifest or root / "relay-manifest.json").resolve())
    stale = []
    try:
        for target in TARGETS:
            if sync_file(root / target, target, manifest, write=args.write):
                stale.append(target)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        print("RELAY MANIFEST: ERROR — %s" % exc, file=sys.stderr)
        return 2
    if stale and not args.write:
        print("RELAY MANIFEST: STALE — %s" % ", ".join(stale), file=sys.stderr)
        return 1
    print(
        "RELAY MANIFEST: %s — %d relays — %s"
        % ("WROTE" if stale else "CURRENT", len(relay_urls(manifest)), manifest_digest(manifest))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
