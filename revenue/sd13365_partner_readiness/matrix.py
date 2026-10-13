#!/usr/bin/env python3
"""SD13365 matrix API with retained-dirfd output custody.

The reviewed semantic/classification engine is preserved byte-for-byte in
``matrix_core.py``.  This wrapper intentionally changes only the authority-
bearing receipt writer, then patches the core CLI's runtime global so direct
API calls and ``python matrix.py`` share the same safe output primitive.
"""
from __future__ import annotations

import json
from pathlib import Path

import matrix_core as _core
import safe_output
from matrix_core import *  # noqa: F401,F403 - preserve the existing public API


def write_receipt(path: Path, receipt: dict[str, object]) -> None:
    payload = (
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    try:
        safe_output.atomic_write_bytes(Path(path), payload)
    except safe_output.OutputCustodyError as exc:
        raise MatrixError(f"unsafe receipt output custody: {exc}") from exc


# matrix_core.main resolves its globals at call time.  Override only the writer
# so the existing reviewed CLI parser / receipt semantics remain unchanged.
_core.write_receipt = write_receipt


if __name__ == "__main__":
    raise SystemExit(_core.main())
