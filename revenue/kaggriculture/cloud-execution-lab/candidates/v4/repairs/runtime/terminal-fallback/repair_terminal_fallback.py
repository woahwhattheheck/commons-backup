# SPDX-License-Identifier: Apache-2.0
"""Pure, exact-source repair of the current-runtime terminal deadline fallback.

This does not run the legacy V4 materializer, change feature defaults, or publish
anything. Input must match the reviewed production blob; output is a separate
file. All timer and nonterminal fallback code is retained byte-for-byte.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

EXPECTED_SOURCE = '664aa4f8a21368c388dfa6714406519b6535ef7f'
EXPECTED_POSTIMAGE = '8f36fbe5d05fb71731ef4b799a664189a6dae153'
OLD = b'    maximum = int(cfg.get("maxMarketOrdersPerTurn", 10))\n    return {"farmer": units[0], "hands": units[1:], "market": market[:maximum]}\n'
NEW = b'    maximum = max(1, int(cfg.get("maxMarketOrdersPerTurn", 10)))\n    # The engine stores animals in the shed but cannot SELL them. They still\n    # occupy raw market slots. Recover otherwise omitted product lots in those\n    # inert slots WITHOUT moving any already-executable product SELL: its raw\n    # index determines lockstep quotation against the rival\'s matching row.\n    products = frozenset(("WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",\n                          "EGG", "MILK", "WOOL", "FERTILIZER"))\n    prefix = market[:maximum]\n    omitted = iter(row for row in market[maximum:] if row[1] in products)\n    for index, row in enumerate(prefix):\n        if row[1] not in products:\n            replacement = next(omitted, None)\n            if replacement is None:\n                break\n            prefix[index] = replacement\n    return {"farmer": units[0], "hands": units[1:], "market": prefix}\n'


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def repair(source: bytes) -> bytes:
    if not isinstance(source, bytes):
        raise TypeError("source must be exact bytes")
    actual = git_blob(source)
    if actual != EXPECTED_SOURCE:
        raise ValueError(f"source drift: expected {EXPECTED_SOURCE}, got {actual}")
    if source.count(OLD) != 1:
        raise ValueError("expected unique terminal-fallback anchor")
    result = source.replace(OLD, NEW, 1)
    if git_blob(result) != EXPECTED_POSTIMAGE:
        raise ValueError("postimage identity mismatch")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("write the candidate to a separate output; this tool does not activate production")
    result = repair(args.source.read_bytes())
    with args.output.open("xb") as stream:
        stream.write(result)
    print(f"source={EXPECTED_SOURCE} postimage={git_blob(result)} bytes={len(result)}")


if __name__ == "__main__":
    main()
