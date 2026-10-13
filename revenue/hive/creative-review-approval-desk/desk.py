#!/usr/bin/env python3
"""Local-first creative review and approval operations desk.

This public facade records owner-supplied workflow facts. It does not infer
creative quality, rights, compliance, publication authority, or acceptance.
"""
from __future__ import annotations

import argparse
import sys
from typing import Any

from _bundle import verify_bundle
from _manifest import ManifestMixin
from _review import ReviewWorkflowMixin
from _store_base import CreativeReviewStore
from _validation import (
    AUTHORITY,
    DeskError,
    IdempotencyConflict,
    InvalidInput,
    InvalidState,
    canonical_bytes,
    canonical_json,
    normalize_spec,
    read_json_file,
    strict_json_loads,
)


class CreativeReviewDesk(ManifestMixin, ReviewWorkflowMixin, CreativeReviewStore):
    """Complete local workspace composed from the transaction and snapshot layers."""

def _json_out(value: Any) -> None:
    sys.stdout.write(canonical_json(value) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("--db", required=True)
    create.add_argument("--spec", required=True)
    create.add_argument("--request-id", required=True)

    revise = sub.add_parser("revise")
    revise.add_argument("--db", required=True)
    revise.add_argument("--spec", required=True)
    revise.add_argument("--expected-revision", required=True, type=int)
    revise.add_argument("--request-id", required=True)

    submit = sub.add_parser("submit")
    submit.add_argument("--db", required=True)
    submit.add_argument("--campaign", required=True)
    submit.add_argument("--asset", required=True)
    submit.add_argument("--author", required=True)
    submit.add_argument("--file", required=True)
    submit.add_argument("--media-type", required=True)
    submit.add_argument("--metadata", required=True)
    submit.add_argument("--provenance-ref", required=True)
    submit.add_argument("--request-id", required=True)

    assign = sub.add_parser("assign")
    assign.add_argument("--db", required=True)
    assign.add_argument("--campaign", required=True)
    assign.add_argument("--asset", required=True)
    assign.add_argument("--role", required=True)
    assign.add_argument("--reviewer", required=True)
    assign.add_argument("--request-id", required=True)

    annotate = sub.add_parser("annotate")
    annotate.add_argument("--db", required=True)
    annotate.add_argument("--campaign", required=True)
    annotate.add_argument("--asset", required=True)
    annotate.add_argument("--role", required=True)
    annotate.add_argument("--reviewer", required=True)
    annotate.add_argument("--annotation-id", required=True)
    annotate.add_argument("--location", required=True)
    annotate.add_argument("--category", required=True)
    annotate.add_argument("--note", required=True)
    annotate.add_argument("--request-id", required=True)

    resolve = sub.add_parser("resolve")
    resolve.add_argument("--db", required=True)
    resolve.add_argument("--campaign", required=True)
    resolve.add_argument("--annotation-id", required=True)
    resolve.add_argument("--resolver", required=True)
    resolve.add_argument("--request-id", required=True)

    decide = sub.add_parser("decide")
    decide.add_argument("--db", required=True)
    decide.add_argument("--campaign", required=True)
    decide.add_argument("--asset", required=True)
    decide.add_argument("--role", required=True)
    decide.add_argument("--reviewer", required=True)
    decide.add_argument("--decision", required=True)
    decide.add_argument("--note", default="")
    decide.add_argument("--request-id", required=True)

    status_parser = sub.add_parser("status")
    status_parser.add_argument("--db", required=True)
    status_parser.add_argument("--campaign", required=True)

    export = sub.add_parser("export")
    export.add_argument("--db", required=True)
    export.add_argument("--campaign", required=True)
    export.add_argument("--output-dir", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--output-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "verify":
            _json_out(verify_bundle(args.output_dir))
            return 0
        desk = CreativeReviewDesk(args.db)
        if args.command == "create":
            result = desk.create_campaign(args.request_id, read_json_file(args.spec))
        elif args.command == "revise":
            result = desk.revise_campaign(args.request_id, args.expected_revision, read_json_file(args.spec))
        elif args.command == "submit":
            result = desk.submit_asset(
                args.request_id,
                args.campaign,
                args.asset,
                args.author,
                args.file,
                args.media_type,
                read_json_file(args.metadata),
                args.provenance_ref,
            )
        elif args.command == "assign":
            result = desk.assign_reviewer(args.request_id, args.campaign, args.asset, args.role, args.reviewer)
        elif args.command == "annotate":
            result = desk.add_annotation(
                args.request_id,
                args.annotation_id,
                args.campaign,
                args.asset,
                args.role,
                args.reviewer,
                read_json_file(args.location),
                args.category,
                args.note,
            )
        elif args.command == "resolve":
            result = desk.resolve_annotation(args.request_id, args.campaign, args.annotation_id, args.resolver)
        elif args.command == "decide":
            result = desk.decide(
                args.request_id,
                args.campaign,
                args.asset,
                args.role,
                args.reviewer,
                args.decision,
                args.note,
            )
        elif args.command == "status":
            result = desk.status(args.campaign)
        elif args.command == "export":
            result = desk.export(args.campaign, args.output_dir)
        else:  # pragma: no cover
            raise InvalidInput("unknown command")
        _json_out(result)
        return 0
    except DeskError as exc:
        sys.stderr.write(canonical_json({"error": type(exc).__name__, "message": str(exc)}) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
