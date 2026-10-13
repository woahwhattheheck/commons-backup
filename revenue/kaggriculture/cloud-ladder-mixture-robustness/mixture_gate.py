#!/usr/bin/env python3
"""Fail-closed TITAN V3 release gate for hosted opponent-mixture shift."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any, Sequence

from mixture_common import (
    SCHEMA, RECEIPT_SCHEMA, MixFamily, ValidationError, _require, _sha256,
)
from mixture_evaluate import evaluate
from mixture_optimize import _worst_case_mixture

def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _require(not path.is_symlink(), "OUTPUT_SYMLINK", "output path must not be a symlink", output=str(path))
    payload = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("DUPLICATE_JSON_KEY", "JSON object contains a duplicate key", key=key)
        result[key] = value
    return result


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle, parse_float=Decimal, object_pairs_hook=_reject_duplicate_keys)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    safe_output: Path | None = None
    try:
        input_path = args.input.expanduser().resolve(strict=True)
        raw_output = args.output.expanduser()
        _require(not raw_output.is_symlink(), "OUTPUT_SYMLINK", "output path must not be a symlink", output=str(raw_output))
        output_path = raw_output.absolute()
        aliases_input = False
        if output_path.exists():
            try:
                aliases_input = os.path.samefile(input_path, output_path)
            except OSError:
                aliases_input = output_path.resolve(strict=False) == input_path
        else:
            aliases_input = output_path.resolve(strict=False) == input_path
        _require(not aliases_input, "OUTPUT_ALIAS", "output must not overwrite or alias input")
        safe_output = output_path
        document = _read_json(input_path)
        receipt = evaluate(document)
        _atomic_write_json(output_path, receipt)
        print(json.dumps({"verdict": receipt["verdict"], "receipt_sha256": receipt["receipt_sha256"]}, sort_keys=True))
        return 0
    except ValidationError as exc:
        failure = {
            "schema": RECEIPT_SCHEMA,
            "verdict": "MALFORMED_EVIDENCE",
            "error": exc.as_dict(),
        }
        failure["receipt_sha256"] = _sha256(failure)
        if safe_output is not None:
            try:
                _atomic_write_json(safe_output, failure)
            except Exception:
                pass
        print(json.dumps(failure, sort_keys=True), file=os.sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        failure = {
            "schema": RECEIPT_SCHEMA,
            "verdict": "MALFORMED_EVIDENCE",
            "error": {"code": "IO_OR_JSON", "message": str(exc), "details": {}},
        }
        failure["receipt_sha256"] = _sha256(failure)
        if safe_output is not None:
            try:
                _atomic_write_json(safe_output, failure)
            except Exception:
                pass
        print(json.dumps(failure, sort_keys=True), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
