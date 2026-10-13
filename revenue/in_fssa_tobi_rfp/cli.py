from __future__ import annotations

import json
import sys

from .readiness import InputError, evaluate, loads_strict


def main() -> int:
    try:
        data = loads_strict(sys.stdin.read())
        receipt = evaluate(data)
    except InputError as exc:
        print(json.dumps({"schema_version": "tjlabs.in-fssa-tobi-readiness/error-v1", "error": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
