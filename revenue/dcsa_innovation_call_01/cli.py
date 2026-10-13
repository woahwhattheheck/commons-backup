"""Command-line interface for the DCSA Innovation Call #01 carrier."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence

from .gate import compile_current, compile_historical, verify_current, verify_historical
from .strict import (
    DcsaError,
    ValidationError,
    canonical_json_bytes,
    read_bounded_regular_file,
    write_exclusive_regular_files,
)


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValidationError(f"argument error: {message}")


def _read(path: str) -> bytes:
    return read_bounded_regular_file(path)


def _json_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _text_bytes(value: str) -> bytes:
    if not isinstance(value, str):
        raise ValidationError("text artifact must be a string")
    return value.encode("utf-8")


def _publish(items: Sequence[tuple[str, bytes]]) -> None:
    """Publish all requested artifacts as one rollback-safe generation set."""
    outputs: dict[str, bytes] = {}
    for path, data in items:
        if path in outputs:
            raise ValidationError("artifact destinations must be unique")
        outputs[path] = data
    write_exclusive_regular_files(outputs)


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(description="DCSA Innovation Call #01 internal pursuit carrier")
    sub = parser.add_subparsers(dest="command", required=True)

    current = sub.add_parser("compile-current")
    current.add_argument("--candidate", required=True)
    current.add_argument("--report", required=True)
    current.add_argument("--concept")
    current.add_argument("--acceptance-json")
    current.add_argument("--acceptance-markdown")

    historical = sub.add_parser("compile-historical")
    historical.add_argument("--candidate", required=True)
    historical.add_argument("--source", required=True)
    historical.add_argument("--authority", required=True)
    historical.add_argument("--floor", required=True)
    historical.add_argument("--as-of", required=True)
    historical.add_argument("--report", required=True)

    verify_now = sub.add_parser("verify-current")
    verify_now.add_argument("--candidate", required=True)
    verify_now.add_argument("--report", required=True)

    verify_old = sub.add_parser("verify-historical")
    verify_old.add_argument("--candidate", required=True)
    verify_old.add_argument("--source", required=True)
    verify_old.add_argument("--authority", required=True)
    verify_old.add_argument("--floor", required=True)
    verify_old.add_argument("--as-of", required=True)
    verify_old.add_argument("--report", required=True)

    concept = sub.add_parser("render-concept")
    concept.add_argument("--candidate", required=True)
    concept.add_argument("--report", required=True)
    concept.add_argument("--output", required=True)

    matrix = sub.add_parser("render-acceptance")
    matrix.add_argument("--json-output", required=True)
    matrix.add_argument("--markdown-output", required=True)
    return parser


def _emit(value: Any, *, stream: Any = None) -> None:
    target = sys.stdout if stream is None else stream
    target.write(json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "compile-current":
            candidate_bytes = _read(args.candidate)
            report = compile_current(candidate_bytes)
            report_bytes = _json_bytes(report)
            artifacts: list[tuple[str, bytes]] = [(args.report, report_bytes)]
            if args.concept:
                from .concept import render_concept
                artifacts.append((args.concept, _text_bytes(render_concept(candidate_bytes, report_bytes))))
            if args.acceptance_json or args.acceptance_markdown:
                from .acceptance import compile_matrix, render_matrix_markdown, verify_matrix
                matrix = compile_matrix()
                if not verify_matrix(matrix):
                    raise ValidationError("internal acceptance matrix failed verification")
                if args.acceptance_json:
                    artifacts.append((args.acceptance_json, _json_bytes(matrix)))
                if args.acceptance_markdown:
                    artifacts.append((args.acceptance_markdown, _text_bytes(render_matrix_markdown(matrix))))
            _publish(artifacts)
            _emit({
                "ok": True,
                "state": report["state"],
                "mode": report["mode"],
                "receipt_sha256": report["receipt_sha256"],
                "external_contact_authorized": False,
                "external_submission_authorized": False,
            })
            return 0 if report["state"] in {"DIRECT_READY", "TEAMING_REQUIRED"} else 3

        if args.command == "compile-historical":
            report = compile_historical(
                _read(args.candidate),
                _read(args.source),
                _read(args.authority),
                _read(args.floor),
                as_of=args.as_of,
            )
            _publish([(args.report, _json_bytes(report))])
            _emit({
                "ok": True,
                "state": report["state"],
                "historical_route_projection": report["historical_route_projection"],
                "mode": report["mode"],
                "receipt_sha256": report["receipt_sha256"],
            })
            return 0

        if args.command == "verify-current":
            valid = verify_current(_read(args.candidate), _read(args.report))
            _emit({"ok": valid, "mode": "CURRENT"})
            return 0 if valid else 4

        if args.command == "verify-historical":
            valid = verify_historical(
                _read(args.candidate),
                _read(args.source),
                _read(args.authority),
                _read(args.floor),
                _read(args.report),
                as_of=args.as_of,
            )
            _emit({"ok": valid, "mode": "HISTORICAL_INTEGRITY_ONLY"})
            return 0 if valid else 4

        if args.command == "render-concept":
            from .concept import render_concept
            candidate_bytes = _read(args.candidate)
            report_bytes = _read(args.report)
            concept_text = render_concept(candidate_bytes, report_bytes)
            _publish([(args.output, _text_bytes(concept_text))])
            _emit({"ok": True, "output": args.output})
            return 0

        if args.command == "render-acceptance":
            from .acceptance import compile_matrix, render_matrix_markdown, verify_matrix
            matrix = compile_matrix()
            if not verify_matrix(matrix):
                raise ValidationError("internal acceptance matrix failed verification")
            _publish([
                (args.json_output, _json_bytes(matrix)),
                (args.markdown_output, _text_bytes(render_matrix_markdown(matrix))),
            ])
            _emit({"ok": True, "receipt_sha256": matrix["receipt_sha256"]})
            return 0

        raise ValidationError("unsupported command")
    except (DcsaError, OSError) as exc:
        _emit({"ok": False, "error": exc.__class__.__name__, "message": str(exc)}, stream=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
