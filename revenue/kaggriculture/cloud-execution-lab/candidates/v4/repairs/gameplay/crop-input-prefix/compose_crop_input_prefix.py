# SPDX-License-Identifier: Apache-2.0
"""Offline, method-pinned native crop input repair. Never rewrites production.

Two safety screens must use the same executable prefix as the other existing
crop guards. The entire raw queue is still retained and bound to its receipt.
The current crop mechanism supports exactly the standard 10-slot configuration;
this delta does not broaden its configuration or gameplay admission contract.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
from pathlib import Path

SOURCE_BLOB = "dd318e5bbe6245913c3dcb8c07d0752fd1ebd735"
METHOD = "propose_input_repair"
BEFORE = "51cb005d8f1d35fd0345361ed8f9b5b8924d722771ea2dace52ac81516386cca"
AFTER = "5c10ee9313c0018aef1f758179d12956aea988b2a1d646487a1ab1304d2687ab"
REPLACEMENTS = (
    (b"for a in orders):\n        report['reason']='existing_wheat_purchase_needs_its_own_receipt'", b"for a in orders[:10]):\n        report['reason']='existing_wheat_purchase_needs_its_own_receipt'"),
    (b"    for a in orders:\n        if a and a[0] in ('BUY_PRODUCT','BUY_ANIMAL'):", b"    for a in orders[:10]:\n        if a and a[0] in ('BUY_PRODUCT','BUY_ANIMAL'):"),
)


def compose(source: bytes) -> bytes:
    """Preserve every byte outside the authenticated top-level method.

    Unrelated peer edits are allowed. Unknown, decorated, duplicated, partial,
    or syntactically broken method versions fail closed. Reapplication is exact
    identity. This function builds bytes only; it never writes a runtime file.
    """
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")
    tree = ast.parse(source.decode("utf-8"))
    matches = [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == METHOD]
    if len(matches) != 1 or matches[0] not in tree.body or matches[0].decorator_list:
        raise ValueError("expected one undecorated top-level crop repair method")
    n = matches[0]
    lines = source.splitlines(keepends=True)
    start = sum(map(len, lines[:n.lineno - 1]))
    end = sum(map(len, lines[:n.end_lineno]))
    method = source[start:end]
    digest = hashlib.sha256(method).hexdigest()
    if digest == AFTER:
        return source
    if digest != BEFORE:
        raise ValueError("crop repair method drift; compose explicitly with its owner")
    repaired = method
    for old, new in REPLACEMENTS:
        if repaired.count(old) != 1:
            raise ValueError("crop prefix anchor mismatch")
        repaired = repaired.replace(old, new, 1)
    if hashlib.sha256(repaired).hexdigest() != AFTER:
        raise ValueError("unexpected crop repair output")
    result = source[:start] + repaired + source[end:]
    compile(result, "crop_release.py", "exec")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path, help="NEW scratch component file")
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve() or args.output.is_symlink():
        parser.error("refusing same-path or symlink output")
    result = compose(args.source.read_bytes())
    # Exclusive creation protects existing source/composed files, including races.
    with args.output.open("xb") as stream:
        stream.write(result)
    print(hashlib.sha256(result).hexdigest())


if __name__ == "__main__":
    main()
