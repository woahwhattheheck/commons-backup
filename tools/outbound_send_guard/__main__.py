"""Package-module entrypoint is intentionally non-authorizing for CURRENT."""
from __future__ import annotations

import sys


def main() -> int:
    print(
        "outbound-send CURRENT authority requires direct isolated startup: "
        "python -I -S tools/outbound_send_guard/cli.py ...",
        file=sys.stderr,
    )
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
