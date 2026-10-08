"""Lossless, rate-conscious Slack-message chunking for MOVA bounty work orders.

Accepts rendered plain text, not portal claims or GitHub source. Offline only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCHEMA = "commons-mova-slack-chunks/v1"
DEFAULT_MAX_BYTES = 4000
HEADER_RESERVE = 160


def split_messages(source: str, max_bytes: int = DEFAULT_MAX_BYTES, *, split_long_lines: bool = False) -> list[dict]:
    """Preserve every source character in ordered, individually postable messages.

    Size uses UTF-8 bytes, conservatively bounded below the Slack text limit.
    Long lines fail by default; explicit splitting preserves Unicode codepoint boundaries.
    """
    if not isinstance(source, str) or not source:
        raise ValueError("nonempty UTF-8 text required")
    if type(max_bytes) is not int or not 256 <= max_bytes <= 5000:
        raise ValueError("max_bytes must be an integer from 256 through 5000")
    try:
        raw = source.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("source is not valid UTF-8 text") from error
    digest = hashlib.sha256(raw).hexdigest()
    payload_limit = max_bytes - HEADER_RESERVE
    payloads: list[str] = []
    current: list[str] = []
    used = 0
    for line in source.splitlines(keepends=True):
        width = len(line.encode("utf-8"))
        if width > payload_limit:
            if not split_long_lines:
                raise ValueError("one indivisible work-order line exceeds chunk capacity")
            if current:
                payloads.append("".join(current))
                current, used = [], 0
            encoded = line.encode("utf-8")
            offset = 0
            while offset < len(encoded):
                end = min(offset + payload_limit, len(encoded))
                if end < len(encoded):
                    while end > offset and (encoded[end] & 0xC0) == 0x80:
                        end -= 1
                if end == offset:
                    raise ValueError("chunk capacity cannot hold a UTF-8 codepoint")
                payloads.append(encoded[offset:end].decode("utf-8"))
                offset = end
            continue
        if used + width > payload_limit and current:
            payloads.append("".join(current))
            current, used = [], 0
        current.append(line)
        used += width
    if current:
        payloads.append("".join(current))
    if "".join(payloads) != source:
        raise AssertionError("chunker lost source text")
    output = []
    for index, payload in enumerate(payloads, 1):
        header = f"MOVA dispatch | sha256:{digest} | part {index}/{len(payloads)}\n"
        message = header + payload
        if len(message.encode("utf-8")) > max_bytes:
            raise AssertionError("header exceeded reserved capacity")
        output.append({"part": index, "text": message})
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="-", help="UTF-8 text file; '-' reads stdin")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--split-long-lines", action="store_true",
                        help="explicitly allow lossless UTF-8 reassembly across message boundaries")
    args = parser.parse_args(argv)
    try:
        raw = sys.stdin.buffer.read() if args.input == "-" else Path(args.input).read_bytes()
        source = raw.decode("utf-8")
        messages = split_messages(source, args.max_bytes, split_long_lines=args.split_long_lines)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    print(json.dumps({"schema": SCHEMA, "source_sha256": hashlib.sha256(raw).hexdigest(),
                      "max_message_bytes": args.max_bytes, "message_count": len(messages),
                      "messages": messages}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
