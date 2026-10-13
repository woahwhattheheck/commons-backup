# SPDX-License-Identifier: MIT
"""Replay public forecast/outcome JSONL without importing a game controller."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from calibration import CausalWindowEnsemble, summarize


def replay(events):
    learners, metadata, forecasts, records = {}, {}, [], []
    for line, event in enumerate(events, 1):
        try:
            key = (event["game_id"], event["product"])
            kind = event["kind"]
            if kind == "start":
                if key in learners:
                    raise ValueError("duplicate game/product start")
                learners[key] = CausalWindowEnsemble(*key, **event.get("parameters", {}))
                meta = {"split": event.get("split", "unspecified"),
                        "opponent_family": event.get("opponent_family", "unspecified")}
                if key[0] in metadata and metadata[key[0]] != meta:
                    raise ValueError("a complete game must have one split/family")
                metadata[key[0]] = meta
            elif kind == "forecast":
                f = learners[key].predict(event["prediction"], **{k: event[k] for k in ("now", "end", "cutoff", "threshold")})
                forecasts.append(f)
            elif kind == "outcome":
                # The exact ticket is explicit in the persisted event stream.
                r = learners[key].resolve(event["ticket"], event["intervals"], observed_at=event["observed_at"])
                r.update(metadata[key[0]]); records.append(r)
            else:
                raise ValueError(f"unknown event kind {kind!r}")
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"event {line}: {exc}") from exc
    return {"forecasts": forecasts, "outcomes": records, "summary": summarize(records),
            "pending": [m.state() for m in learners.values() if m.state()["pending"] is not None]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    try:
        with args.input.open(encoding="utf-8") as handle:
            events = [json.loads(line) for line in handle if line.strip()]
        text = json.dumps(replay(events), indent=2, sort_keys=True, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
    except (OSError, ValueError) as exc:
        print(f"replay error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
