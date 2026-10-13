from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .engine import (
        ContractError,
        canonical_bytes,
        compile_result,
        evaluate_external_actions,
        loads_strict,
        render_external_markdown,
        render_markdown,
        verify_external_result,
        verify_result,
    )
    from .io_secure import _read_regular, _write_exclusive
except ImportError:
    from engine import (
        ContractError,
        canonical_bytes,
        compile_result,
        evaluate_external_actions,
        loads_strict,
        render_external_markdown,
        render_markdown,
        verify_external_result,
        verify_result,
    )
    from io_secure import _read_regular, _write_exclusive


def _publish_pair(json_out: str, markdown_out: str, result: dict, markdown: str) -> None:
    json_raw = canonical_bytes(result) + b"\n"
    md_raw = markdown.encode("utf-8")
    _write_exclusive(Path(json_out), json_raw)
    try:
        _write_exclusive(Path(markdown_out), md_raw)
    except Exception as exc:
        raise ContractError(f"authoritative JSON committed; Markdown projection failed: {exc}") from exc


def command_compile(args: argparse.Namespace) -> int:
    scenario = loads_strict(_read_regular(Path(args.scenario)))
    result = compile_result(scenario)
    _publish_pair(args.json_out, args.markdown_out, result, render_markdown(result))
    print(result["status"])
    print(result["receipt"]["result_sha256"])
    return 0


def command_verify(args: argparse.Namespace) -> int:
    scenario = loads_strict(_read_regular(Path(args.scenario)))
    result = loads_strict(_read_regular(Path(args.result)))
    valid = verify_result(scenario, result)
    print(json.dumps({"valid": valid}, sort_keys=True, separators=(",", ":")))
    return 0 if valid else 2


def command_evaluate_actions(args: argparse.Namespace) -> int:
    scenario = loads_strict(_read_regular(Path(args.scenario)))
    actions = loads_strict(_read_regular(Path(args.actions)))
    result = evaluate_external_actions(scenario, actions)
    _publish_pair(args.json_out, args.markdown_out, result, render_external_markdown(result))
    print(result["status"])
    print(result["receipt"]["result_sha256"])
    return 0


def command_verify_actions(args: argparse.Namespace) -> int:
    scenario = loads_strict(_read_regular(Path(args.scenario)))
    actions = loads_strict(_read_regular(Path(args.actions)))
    result = loads_strict(_read_regular(Path(args.result)))
    valid = verify_external_result(scenario, actions, result)
    print(json.dumps({"valid": valid}, sort_keys=True, separators=(",", ":")))
    return 0 if valid else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DARPA DV026 deterministic market technical proof")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser("compile")
    compile_p.add_argument("--scenario", required=True)
    compile_p.add_argument("--json-out", required=True)
    compile_p.add_argument("--markdown-out", required=True)
    compile_p.set_defaults(func=command_compile)

    verify_p = sub.add_parser("verify")
    verify_p.add_argument("--scenario", required=True)
    verify_p.add_argument("--result", required=True)
    verify_p.set_defaults(func=command_verify)

    evaluate_p = sub.add_parser("evaluate-actions")
    evaluate_p.add_argument("--scenario", required=True)
    evaluate_p.add_argument("--actions", required=True)
    evaluate_p.add_argument("--json-out", required=True)
    evaluate_p.add_argument("--markdown-out", required=True)
    evaluate_p.set_defaults(func=command_evaluate_actions)

    verify_actions_p = sub.add_parser("verify-actions")
    verify_actions_p.add_argument("--scenario", required=True)
    verify_actions_p.add_argument("--actions", required=True)
    verify_actions_p.add_argument("--result", required=True)
    verify_actions_p.set_defaults(func=command_verify_actions)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ContractError, OSError, UnicodeError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
