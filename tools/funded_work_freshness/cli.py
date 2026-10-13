"""Command-line interface and atomic receipt writer."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Sequence

from engine import preflight
from errors import PreflightInputError
from evaluation import parse_timestamp
from models import Candidate
from transport import UrlLibTransport


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def parse_observed_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    stamp = parse_timestamp(value)
    if stamp is None:
        raise PreflightInputError("--observed-at must be an ISO-8601 timestamp with timezone")
    return stamp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed freshness preflight for advertised funded work."
    )
    parser.add_argument("candidate_url")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--amount", required=True, dest="advertised_amount")
    parser.add_argument("--currency", required=True)
    parser.add_argument("--canonical-url")
    parser.add_argument("--max-age-days", type=int, default=90)
    parser.add_argument("--max-visible-claims", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--observed-at", help="fixed ISO-8601 evidence time for deterministic replay")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        candidate = Candidate.validated(
            candidate_url=args.candidate_url,
            platform=args.platform,
            advertised_amount=args.advertised_amount,
            currency=args.currency,
            canonical_url=args.canonical_url,
            max_age_days=args.max_age_days,
            max_visible_claims=args.max_visible_claims,
        )
        observed_at = parse_observed_at(args.observed_at)
        transport = UrlLibTransport(
            timeout=args.timeout,
            github_token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"),
        )
        receipt = preflight(candidate, transport, observed_at=observed_at)
    except PreflightInputError as exc:
        parser.error(str(exc))
    rendered = json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        write_atomic(args.output, rendered)
    else:
        print(rendered, end="")
    return {"actionable": 0, "occupied": 3, "stale": 4, "ambiguous": 5}[
        receipt["freshness_status"]
    ]
