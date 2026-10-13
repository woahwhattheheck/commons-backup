#!/usr/bin/env python3
"""Narrow support donor for #12620 / 12a3 import-root custody.

12a3 already owns exact static apply grammar, canonical-member collision checks,
predecessor-overlay immutability, and constrained new-overlay names.  This donor
adds only the residual theorem: an additive root overlay must not newly satisfy
an import root that was already referenced by authenticated predecessor package
bytes.  Scan excludes the additive HEAD files themselves so a candidate cannot
manufacture its own deny-set.
"""
from __future__ import annotations

import ast
import sys
from pathlib import PurePosixPath


class ImportRootCustodyError(RuntimeError):
    pass


def _req(cond: object, message: str) -> None:
    if not cond:
        raise ImportRootCustodyError(message)


def _safe_rel(name: str) -> str:
    _req(isinstance(name, str) and "\\" not in name and "\x00" not in name,
         f"unsafe package-relative path {name!r}")
    path = PurePosixPath(name)
    _req(not path.is_absolute() and path.parts
         and all(part not in ("", ".", "..") for part in path.parts),
         f"unsafe package-relative path {name!r}")
    return path.as_posix()


def _existing_import_roots(
    materialized_pre_v4: dict[str, bytes],
    *,
    exclude_paths: set[str] | frozenset[str] = frozenset(),
) -> set[str]:
    """Import roots referenced by authenticated predecessor bytes only."""
    excluded = {_safe_rel(name) for name in exclude_paths}
    roots = set(getattr(sys, "stdlib_module_names", ()))
    for raw_name, blob in materialized_pre_v4.items():
        name = _safe_rel(raw_name)
        if name in excluded or not name.endswith(".py"):
            continue
        _req(type(blob) is bytes, f"{name}: predecessor package member is not bytes")
        try:
            text = blob.decode("utf-8")
            tree = ast.parse(text, filename="PREDECESSOR:" + name)
        except (UnicodeDecodeError, SyntaxError) as exc:
            raise ImportRootCustodyError(
                f"{name}: cannot authenticate predecessor Python imports: {exc}"
            ) from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".", 1)[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".", 1)[0])
    return roots


def require_no_new_overlay_import_shadow(
    *,
    base_overlay_paths,
    head_overlay_paths,
    materialized_pre_v4: dict[str, bytes],
) -> set[str]:
    """Reject an additive root module that hijacks an existing import root.

    Integration point for 12a3:
      1. obtain BASE and HEAD overlay snapshots from authenticated Git objects;
      2. run the existing immutable/additive overlay validation;
      3. build the trusted pre-V4 package exactly as today;
      4. call this with that package and the two overlay path sets.

    materialized_pre_v4 may contain the new HEAD overlay bytes; they are excluded
    from the import scan before roots are derived.
    """
    base = {_safe_rel(str(name)) for name in base_overlay_paths}
    head = {_safe_rel(str(name)) for name in head_overlay_paths}
    _req(base <= head, "HEAD removed predecessor overlay path(s)")
    new = head - base
    roots = _existing_import_roots(materialized_pre_v4, exclude_paths=new)

    for name in sorted(new):
        path = PurePosixPath(name)
        # 12a3 allows checks/*.py as non-runtime support. Runtime additions are
        # root r04_*.py; keep this donor narrow and do not alter that grammar.
        if len(path.parts) != 1:
            continue
        first = path.parts[0]
        root = first[:-3] if first.endswith(".py") else first
        _req(root not in roots,
             f"new overlay path {name!r} hijacks authenticated predecessor import root {root!r}")
    return new


def _expect_red(call, needle: str) -> None:
    try:
        call()
    except ImportRootCustodyError as exc:
        assert needle in str(exc), (needle, str(exc))
        return
    raise AssertionError(f"poison unexpectedly GREEN: {needle}")


def self_test() -> None:
    base = {"r04_existing.py"}
    package = {
        "main.py": b"import r04_optional\n",
        "titan_runtime.py": b"from r04_existing import install\n",
        "r04_existing.py": b"VALUE = 1\n",
        # New HEAD byte is present in the materialized package but MUST NOT be
        # allowed to contribute to the predecessor import deny-set.
        "r04_new_lane.py": b"import r04_new_lane\n",
    }

    assert require_no_new_overlay_import_shadow(
        base_overlay_paths=base,
        head_overlay_paths=base | {"r04_new_lane.py"},
        materialized_pre_v4=package,
    ) == {"r04_new_lane.py"}

    _expect_red(
        lambda: require_no_new_overlay_import_shadow(
            base_overlay_paths=base,
            head_overlay_paths=base | {"r04_optional.py"},
            materialized_pre_v4={
                **package,
                "r04_optional.py": b"VALUE = 2\n",
            },
        ),
        "authenticated predecessor import root",
    )

    _expect_red(
        lambda: require_no_new_overlay_import_shadow(
            base_overlay_paths=base,
            head_overlay_paths=base | {"r04_transitive.py"},
            materialized_pre_v4={
                "main.py": b"pass\n",
                "r04_existing.py": b"from r04_transitive.helper import run\n",
                "r04_transitive.py": b"VALUE = 3\n",
            },
        ),
        "authenticated predecessor import root",
    )

    # Nested checks are not package-root runtime additions under 12a3 grammar.
    assert require_no_new_overlay_import_shadow(
        base_overlay_paths=base,
        head_overlay_paths=base | {"checks/r04_optional.py"},
        materialized_pre_v4={
            "main.py": b"import r04_optional\n",
            "r04_existing.py": b"VALUE = 1\n",
            "checks/r04_optional.py": b"VALUE = 4\n",
        },
    ) == {"checks/r04_optional.py"}

    _expect_red(
        lambda: require_no_new_overlay_import_shadow(
            base_overlay_paths=base,
            head_overlay_paths=base | {"r04_new_lane.py"},
            materialized_pre_v4={
                "main.py": b"if :\n",
                "r04_existing.py": b"VALUE = 1\n",
                "r04_new_lane.py": b"VALUE = 2\n",
            },
        ),
        "cannot authenticate predecessor Python imports",
    )


if __name__ == "__main__":
    self_test()
    print("IMPORT-ROOT CUSTODY SELF-TEST OK")
