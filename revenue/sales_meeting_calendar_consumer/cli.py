"""Non-authorizing historical audit CLI for the sales-meeting Calendar consumer.

Current READY compilation is intentionally *not* exposed through a file/JSON CLI:
it requires an in-process independent authority-store implementation and verifier-
owned current time.  The CLI exists only to replay retained bytes for audit, whose
wrapper state is permanently HISTORICAL_REPLAY_ONLY.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from .calendar_consumer import (
    CalendarConsumerError,
    compile_calendar_consumer_historical,
    render_markdown,
    strict_json_loads,
)


def _read_json(path: str):
    return strict_json_loads(Path(path).read_bytes())


def _parse_as_of(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CalendarConsumerError("--as-of must be an offset-aware RFC3339 timestamp") from exc
    if dt.tzinfo is None:
        raise CalendarConsumerError("--as-of must include timezone")
    return dt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Historical/non-authorizing audit replay for sales meeting Calendar evidence."
    )
    parser.add_argument("--trigger", required=True)
    parser.add_argument("--human-authority", required=True)
    parser.add_argument("--capture", required=True)
    parser.add_argument("--as-of", required=True,
                        help="historical verifier instant; output remains HISTORICAL_REPLAY_ONLY")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args(argv)
    try:
        receipt = compile_calendar_consumer_historical(
            _read_json(args.trigger),
            _read_json(args.human_authority),
            _read_json(args.capture),
            as_of=_parse_as_of(args.as_of),
        )
        if args.markdown:
            text = render_markdown(receipt)
            sys.stdout.write(text)
            if not text.endswith("\n"):
                sys.stdout.write("\n")
        else:
            sys.stdout.write(json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n")
        return 0
    except (CalendarConsumerError, OSError, ValueError) as exc:
        sys.stderr.write(f"sales-meeting-calendar-consumer: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
