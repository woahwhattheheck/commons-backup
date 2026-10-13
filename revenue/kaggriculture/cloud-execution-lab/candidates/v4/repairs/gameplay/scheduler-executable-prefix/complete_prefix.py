#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Complete the authenticated peer prefix postimage; never patch production in place."""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

PARENT_BLOB = "4ce07cd005043d09b7d9f53acc3bef814dc54343"
RESULT_BLOB = "5c51553c4c6cf819b07a52f56a4a8c8ad6b5f1d3"
BEFORE = "        for o in base['market']:\n            if o and o[0]=='SELL' and len(o)>2 and o[1]!=item:\n"
AFTER = "        for o in _engine_market_prefix(base,config):\n            if o and o[0]=='SELL' and len(o)>2 and o[1]!=item:\n"


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def complete(parent: bytes) -> bytes:
    if git_blob(parent) != PARENT_BLOB:
        raise ValueError("expected exact 5e8 donor postimage 4ce07cd; source drift or repeat")
    text = parent.decode("utf-8")
    if text.count(BEFORE) != 1 or AFTER in text:
        raise ValueError("current SELL debit anchor missing, ambiguous, or already repaired")
    result = text.replace(BEFORE, AFTER, 1).encode("utf-8")
    compile(result, "<three-consumer-scheduler>", "exec")
    if git_blob(result) != RESULT_BLOB:
        raise ValueError("unexpected completion postimage")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.parent.is_symlink() or not args.parent.is_file():
        parser.error("parent must be a regular non-symlink file")
    data = complete(args.parent.read_bytes())
    if args.output.resolve() == args.parent.resolve():
        parser.error("output must not alias parent")
    with args.output.open("xb") as out:
        out.write(data)
    print(RESULT_BLOB)


if __name__ == "__main__":
    main()
