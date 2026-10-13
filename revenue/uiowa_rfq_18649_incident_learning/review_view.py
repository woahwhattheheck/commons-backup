"""Render the canonical incident-learning packet into one offline review page.

This is a presentation adapter, not another assessor. It calls analyze.py and
keeps that complete result in every selection export. Source locators are text,
never automatically fetched. No service, clock, upload or assessment edit occurs.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

if __package__:
    from .analyze import analyze
    from .contract import moment
else:
    from analyze import analyze
    from contract import moment

ROOT = Path(__file__).resolve().parent
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_NODES = 100_000
MAX_DEPTH = 60
VIEW_SCHEMA = "uiowa-067-review-view/v1"


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def _bad_constant(value):
    raise ValueError("non-finite JSON number: " + value)


def read_packet(raw: bytes) -> dict:
    """Decode one bounded UTF-8 generation, rejecting lossy JSON ambiguity."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_INPUT_BYTES:
        raise ValueError("input must be nonempty bytes, at most 4 MiB")
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                      parse_constant=_bad_constant)
    stack, count = [(data, 0)], 0
    while stack:
        value, depth = stack.pop()
        count += 1
        if depth > MAX_DEPTH or count > MAX_NODES:
            raise ValueError("JSON structure exceeds the presentation input limit")
        if isinstance(value, dict):
            for key, child in value.items():
                key.encode("utf-8")
                stack.append((child, depth + 1))
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)
        elif isinstance(value, str):
            value.encode("utf-8")
    # Also refuses numeric overflow such as 1e500, not seen by parse_constant.
    json.dumps(data, allow_nan=False)
    if not isinstance(data, dict):
        raise ValueError("incident packet must be a JSON object")
    return data


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def make_payload(raw: bytes) -> dict:
    packet = read_packet(raw)
    report = analyze(packet)
    canonical = json.dumps(report, ensure_ascii=True, allow_nan=False,
                           sort_keys=True, separators=(",", ":")).encode("ascii")
    return {
        "schema": VIEW_SCHEMA,
        "input_sha256": _digest(raw),
        "input_bytes": len(raw),
        "report_sha256": _digest(canonical),
        "original_packet_base64": base64.b64encode(raw).decode("ascii"),
        "report": report,
        "presentation": {
            "timeline_order": {
                incident["id"]: [event["kind"] for event in sorted(
                    incident["events"], key=lambda event: moment(event["at"]))]
                for incident in report["incidents"]
            }
        },
        "notice": "Hashes identify supplied bytes, not source authenticity or approval. "
                  "The viewer does not change the canonical assessment."
    }


def render_packet(raw: bytes) -> str:
    payload = make_payload(raw)
    encoded = base64.b64encode(json.dumps(payload, ensure_ascii=True, allow_nan=False,
                            sort_keys=True, separators=(",", ":")).encode("ascii")).decode("ascii")
    script = (ROOT / "review_view.js").read_text(encoding="utf-8")
    css = (ROOT / "review_view.css").read_text(encoding="utf-8")
    template = (ROOT / "review_view.html").read_text(encoding="utf-8")
    script_hash = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
    style_hash = base64.b64encode(hashlib.sha256(css.encode("utf-8")).digest()).decode("ascii")
    policy = ("default-src 'none'; script-src 'sha256-" + script_hash +
              "'; style-src 'sha256-" + style_hash + "'; connect-src 'none'; "
              "object-src 'none'; base-uri 'none'; form-action 'none'; frame-src 'none'")
    for token, value in (("__POLICY__", policy), ("__STYLE__", css),
                         ("__PAYLOAD__", encoded), ("__SCRIPT__", script)):
        if template.count(token) != 1:
            raise ValueError("invalid review template placeholder: " + token)
        template = template.replace(token, value)
    return template


def publish_new(path: Path, text: str) -> None:
    """Create a new page exclusively; existing files and aliases are untouched.

    Parent-directory management is the operator's responsibility. No directories
    are created or recursively removed. A failed write removes only the inode
    created by this call, never a replacement supplied by another process.
    """
    content = text.encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    identity = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        try:
            current = path.lstat()
            if (current.st_dev, current.st_ino) == (identity.st_dev, identity.st_ino):
                path.unlink()
        except FileNotFoundError:
            pass
        raise


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="canonical raw packet, not report.py output")
    source.add_argument("--demo", action="store_true", help="use fixture.py's existing fictional packet")
    parser.add_argument("--out", type=Path, required=True, help="new standalone .html file")
    args = parser.parse_args(argv)
    try:
        if args.demo:
            if __package__:
                from .fixture import sample
            else:
                from fixture import sample
            raw = (json.dumps(sample(), indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        else:
            # Read once; parsing and the displayed byte count/hash share these bytes.
            with args.input.open("rb") as source_file:
                raw = source_file.read(MAX_INPUT_BYTES + 1)
        page = render_packet(raw)
        publish_new(args.out, page)
        print("Created offline review page; input_sha256=" + _digest(raw))
        return 0
    except (ValueError, TypeError, KeyError, OSError, UnicodeError, RecursionError) as error:
        print("Review page not created: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
