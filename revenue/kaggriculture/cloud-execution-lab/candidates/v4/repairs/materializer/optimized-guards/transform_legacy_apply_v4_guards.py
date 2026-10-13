#!/usr/bin/env python3
"""Ancestry-neutral hardening for TITAN V4 apply_v4.py materializers.

Replaces optimization-sensitive assert guards with explicit fail-closed checks.
Gameplay/router semantics are untouched.
"""
from __future__ import annotations

import argparse
from pathlib import Path


class TransformError(RuntimeError):
    pass


OLD_REPLACE = '''def _replace_once(text, old, new, label):
    count = text.count(old)
    assert count == 1, "%s: expected 1 match, found %d" % (label, count)
    return text.replace(old, new)
'''
NEW_REPLACE = '''def _replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError("%s: expected 1 match, found %d" % (label, count))
    return text.replace(old, new, 1)
'''

OLD_CONFIG = '''    for key in KEYS:
        assert key not in data, key
        data[key] = False
'''
NEW_CONFIG = '''    for key in KEYS:
        if key in data:
            raise RuntimeError("config key already present: %s" % key)
        data[key] = False
'''


def _once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise TransformError(f"{label}: expected exactly one source match, found {n}")
    return text.replace(old, new, 1)


def transform(source: str) -> str:
    out = _once(source, OLD_REPLACE, NEW_REPLACE, "replace-once guard")
    out = _once(out, OLD_CONFIG, NEW_CONFIG, "config-key guard")
    if "assert count == 1" in out or "assert key not in data" in out:
        raise TransformError("optimized-away materializer guard remains")
    return out


def self_test() -> None:
    fixture = (
        "HEAD\n" + OLD_REPLACE + "\nKEYS = ('x',)\n\n"
        "def demo(data):\n" + OLD_CONFIG.replace("    for key", "    for key") + "    return data\n"
    )
    out = transform(fixture)
    assert NEW_REPLACE in out
    assert NEW_CONFIG in out
    assert "assert count == 1" not in out
    assert "assert key not in data" not in out

    for poisoned in (
        fixture.replace(OLD_REPLACE, ""),
        fixture.replace(OLD_REPLACE, OLD_REPLACE + "\n" + OLD_REPLACE),
        fixture.replace(OLD_CONFIG, ""),
        fixture.replace(OLD_CONFIG, OLD_CONFIG + OLD_CONFIG),
    ):
        try:
            transform(poisoned)
        except TransformError:
            pass
        else:
            raise AssertionError("poisoned source did not fail closed")

    # Prove the emitted guards themselves do not rely on assertions.  Compile a
    # tiny executable fixture and exercise both failure modes; this runs under -O too.
    ns = {}
    exec(NEW_REPLACE + "\n", ns)
    try:
        ns["_replace_once"]("abc abc", "abc", "x", "dup")
    except RuntimeError:
        pass
    else:
        raise AssertionError("duplicate replacement did not fail closed")
    try:
        ns["_replace_once"]("zzz", "abc", "x", "missing")
    except RuntimeError:
        pass
    else:
        raise AssertionError("missing replacement did not fail closed")

    cfg_ns = {"KEYS": ("x",), "data": {"x": True}, "RuntimeError": RuntimeError}
    guard = "for key in KEYS:\n    if key in data:\n        raise RuntimeError('config key already present: %s' % key)\n    data[key] = False\n"
    try:
        exec(guard, cfg_ns)
    except RuntimeError:
        pass
    else:
        raise AssertionError("pre-existing config key did not fail closed")
    print("SELF_TEST_PASS")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", type=Path)
    ap.add_argument("--self-test", action="store_true")
    ns = ap.parse_args()
    if ns.self_test:
        self_test()
        return 0
    if ns.path is None:
        ap.error("path required unless --self-test")
    src = ns.path.read_text(encoding="utf-8")
    out = transform(src)
    ns.path.write_text(out, encoding="utf-8", newline="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
