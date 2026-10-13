from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from .io import atomic_write, load_json_object, paths_alias
from .model import AcceptanceInputError
from .validate import evaluate_matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate OHSU Oracle EBS AP acceptance evidence."
    )
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.output is not None and paths_alias(args.matrix, args.output):
            raise AcceptanceInputError("input and output must not alias")
        matrix, raw = load_json_object(args.matrix)
        report = evaluate_matrix(
            matrix, input_sha256=hashlib.sha256(raw).hexdigest()
        )
        payload = (
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        if args.output is None:
            sys.stdout.buffer.write(payload)
        else:
            atomic_write(args.output, payload)
        return 0 if report["decision"] == "ACCEPTANCE_MATRIX_READY" else 2
    except AcceptanceInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
