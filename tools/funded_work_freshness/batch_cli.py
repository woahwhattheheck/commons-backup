"""JSONL batch CLI for funded-work freshness preflight."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence, TextIO

from batch import ReceiptCache, process_batch
from cli import parse_observed_at
from errors import PreflightInputError
from models import Candidate
from publication import publish_text_bundle, require_distinct_artifacts
from transport import UrlLibTransport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch funded-work preflight with canonical evidence de-duplication."
    )
    parser.add_argument("--input", default="-", help="JSONL input path or '-' for stdin")
    parser.add_argument("--output", default="-", help="JSON report path or '-' for stdout")
    parser.add_argument("--cache", type=Path, help="optional bounded local receipt cache")
    parser.add_argument("--cache-ttl-seconds", type=float, default=60.0)
    parser.add_argument("--max-cache-entries", type=int, default=256)
    parser.add_argument("--max-items", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--observed-at", help="fixed ISO-8601 evidence time for deterministic replay")
    return parser


def _open_input(path: str) -> tuple[TextIO, bool]:
    if path == "-":
        return sys.stdin, False
    return Path(path).open("r", encoding="utf-8"), True


def read_candidates(handle: Iterable[str], *, max_items: int) -> list[Candidate]:
    if isinstance(max_items, bool) or max_items < 1 or max_items > 1000:
        raise PreflightInputError("--max-items must be between 1 and 1000")
    candidates: list[Candidate] = []
    for line_number, raw in enumerate(handle, 1):
        text = raw.strip()
        if not text:
            continue
        if len(candidates) >= max_items:
            raise PreflightInputError(f"input exceeds --max-items={max_items}")
        try:
            row = json.loads(text)
        except json.JSONDecodeError as exc:
            raise PreflightInputError(f"line {line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(row, dict):
            raise PreflightInputError(f"line {line_number}: each JSONL row must be an object")
        allowed = {
            "candidate_url",
            "platform",
            "advertised_amount",
            "currency",
            "canonical_url",
            "max_age_days",
            "max_visible_claims",
        }
        unknown = sorted(set(row) - allowed)
        if unknown:
            raise PreflightInputError(
                f"line {line_number}: unknown fields: {', '.join(unknown)}"
            )
        required = ["candidate_url", "platform", "advertised_amount", "currency"]
        missing = [key for key in required if key not in row]
        if missing:
            raise PreflightInputError(
                f"line {line_number}: missing required fields: {', '.join(missing)}"
            )
        try:
            candidates.append(
                Candidate.validated(
                    candidate_url=row["candidate_url"],
                    platform=row["platform"],
                    advertised_amount=row["advertised_amount"],
                    currency=row["currency"],
                    canonical_url=row.get("canonical_url"),
                    max_age_days=row.get("max_age_days", 90),
                    max_visible_claims=row.get("max_visible_claims", 0),
                )
            )
        except PreflightInputError as exc:
            raise PreflightInputError(f"line {line_number}: {exc}") from exc
    if not candidates:
        raise PreflightInputError("input contains no funded-work candidates")
    return candidates


def load_cache(path: Path | None) -> ReceiptCache:
    if path is None or not path.exists():
        return ReceiptCache()
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        # Corrupt/unreadable cache is deliberately a miss; fresh canonical reads are safer.
        return ReceiptCache()
    return ReceiptCache.from_payload(payload)


def _artifact_paths(args: argparse.Namespace) -> tuple[Path | None, Path | None, Path | None]:
    input_path = None if args.input == "-" else Path(args.input)
    output_path = None if args.output == "-" else Path(args.output)
    cache_path = args.cache
    return input_path, output_path, cache_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handle = None
    close_handle = False
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0 or args.timeout > 120:
            raise PreflightInputError("--timeout must be finite and between 0 and 120 seconds")
        if (
            not math.isfinite(args.cache_ttl_seconds)
            or args.cache_ttl_seconds < 0
            or args.cache_ttl_seconds > 3600
        ):
            raise PreflightInputError(
                "--cache-ttl-seconds must be finite and between 0 and 3600"
            )
        if args.max_cache_entries < 1 or args.max_cache_entries > 10000:
            raise PreflightInputError("--max-cache-entries must be between 1 and 10000")

        input_path, output_path, cache_path = _artifact_paths(args)
        require_distinct_artifacts(
            {"input": input_path, "output": output_path, "cache": cache_path}
        )
        handle, close_handle = _open_input(args.input)
        candidates = read_candidates(handle, max_items=args.max_items)
        observed_at: datetime | None = parse_observed_at(args.observed_at)
        cache = load_cache(cache_path)
        transport = UrlLibTransport(
            timeout=args.timeout,
            github_token=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"),
        )
        report, updated_cache = process_batch(
            candidates,
            transport,
            observed_at=observed_at,
            cache=cache,
            cache_ttl_seconds=args.cache_ttl_seconds,
            max_cache_entries=args.max_cache_entries,
        )
    except PreflightInputError as exc:
        parser.error(str(exc))
    finally:
        if close_handle and handle is not None:
            handle.close()

    rendered = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    cache_text = None
    if cache_path is not None:
        cache_text = json.dumps(
            updated_cache.to_payload(max_entries=args.max_cache_entries),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        ) + "\n"

    if output_path is not None:
        artifacts = {output_path: rendered}
        if cache_path is not None and cache_text is not None:
            artifacts[cache_path] = cache_text
        publish_text_bundle(artifacts)
    else:
        # A file cache is committed before stdout because stdout cannot participate in
        # filesystem rollback semantics.
        if cache_path is not None and cache_text is not None:
            publish_text_bundle({cache_path: cache_text})
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
