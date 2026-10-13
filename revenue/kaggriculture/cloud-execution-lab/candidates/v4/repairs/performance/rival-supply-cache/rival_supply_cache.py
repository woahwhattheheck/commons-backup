# SPDX-License-Identifier: Apache-2.0
"""Pinned, self-contained FrozenSelected transform-local public-supply cache.

This is a candidate source transformer, not a runtime activator. It refuses an
unknown input and an existing output. The generated runtime needs no new module.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SOURCE_BLOB = "fc7baf5c179818a55037f6a61d92984d81d1a21c"
SOURCE_SHA256 = "5ca1bc39efed756de71207f46926744ea69f9d2f300dd7b9c1a8cc4dbefeb9ef"

CACHE_FACTORY = '''
# Cache only the pinned native consumer's pure public-yield query. This closure
# belongs to ONE transform, after observe(), never a callback/episode checkpoint.
# Subclasses and instance/class method overrides keep their original call counts.
_RIVAL_CACHE_NATIVE_METHODS = tuple(getattr(SellScheduler, name) for name in
    ('rival_supply', 'observe', 'cash_reserve', 'receipt_profile'))


def _rival_supply_for_transform(seller, obs):
    def lookup(item):
        return seller.rival_supply(obs, item)
    names = ('rival_supply', 'observe', 'cash_reserve', 'receipt_profile')
    native = (type(seller) is FrozenSelected and all(
        getattr(getattr(seller, name), '__func__', None) is original
        and getattr(getattr(seller, name), '__self__', None) is seller
        for name, original in zip(names, _RIVAL_CACHE_NATIVE_METHODS)))
    # Lazy evaluation preserves errors/unused products; zero is a cached value.
    # Bounded to the complete product universe, including operating-input rows.
    return lru_cache(maxsize=len(m.PRODUCTS))(lookup) if native else lookup

'''


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def transform(source: bytes) -> bytes:
    """Return an exact pinned postimage; do not silently apply to another ABI."""
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")
    if sha256(source) != SOURCE_SHA256 or git_blob(source) != SOURCE_BLOB:
        raise ValueError("unknown FrozenSelected source: explicit composition required")
    text = source.decode("utf-8")
    replacements = (
        ("\n\ndef materialize_sales(", CACHE_FACTORY + "\ndef materialize_sales("),
        ("        self.observe(obs)\n", "        self.observe(obs)\n        rival_supply = _rival_supply_for_transform(self, obs)\n"),
        ("rival_quantity=self.rival_supply(obs,item)", "rival_quantity=rival_supply(item)"),
        ("lambda product:self.rival_supply(obs,product)", "rival_supply"),
    )
    for before, after in replacements:
        if text.count(before) != 1:
            raise ValueError("expected exactly one replacement seam: " + before)
        text = text.replace(before, after, 1)
    compile(text, "frozen_selected.py", "exec")
    return text.encode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        original = args.source.read_bytes()
        revised = transform(original)
        # Exclusive creation also rejects source==output and output symlinks.
        with args.output.open("xb") as stream:
            stream.write(revised)
    except (OSError, ValueError, TypeError, UnicodeError) as error:
        parser.exit(2, f"rival-supply-cache: {error}\n")
    print(json.dumps({
        "source_git_blob": git_blob(original), "source_sha256": sha256(original),
        "output_git_blob": git_blob(revised), "output_sha256": sha256(revised),
        "output_bytes": len(revised), "production_activated": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
