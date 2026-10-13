"""Factories for the direct isolated UArk CURRENT CLI entrypoint."""
from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any, Callable


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UArk verifier-clock qualification")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_cmd = sub.add_parser("compile")
    compile_cmd.add_argument("input_json")
    compile_cmd.add_argument("--json-out")
    compile_cmd.add_argument("--markdown-out")
    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("packet_json")
    verify_cmd.add_argument("--verification-out")
    return parser


def make_entry_guard(
    error_type: type[Exception],
    direct_entry: bool,
    isolated: bool,
    no_site: bool,
) -> Callable[[], None]:
    message = (
        "CURRENT authority requires direct isolated/no-site execution: "
        "python -I -S current_authority.py ..."
    )

    def require_direct_isolated_entry() -> None:
        if not direct_entry or not isolated or not no_site:
            raise error_type(message)

    return require_direct_isolated_entry


def make_main(
    error_type: type[Exception],
    require_entry: Callable[[], None],
    compile_at_now: Callable[[Any, datetime], dict[str, Any]],
    verify_at_now: Callable[[Any, datetime], dict[str, Any]],
    process_now: Callable[[], datetime],
    read_json: Callable[[str], Any],
    canonicalize: Callable[[Any], str],
    write_exclusive: Callable[[str, str], None],
    render_current: Callable[[dict[str, Any]], str],
    stdout: Any,
    stderr: Any,
) -> Callable[[list[str] | None], int]:
    parser = make_parser()

    def main(argv: list[str] | None = None) -> int:
        try:
            require_entry()
            args = parser.parse_args(argv)
            if args.command == "compile":
                packet = compile_at_now(read_json(args.input_json), process_now())
                packet_text = canonicalize(packet) + "\n"
                if args.json_out:
                    write_exclusive(args.json_out, packet_text)
                else:
                    stdout.write(packet_text)
                if args.markdown_out:
                    write_exclusive(args.markdown_out, render_current(packet))
                return 0
            if args.command == "verify":
                verification = verify_at_now(read_json(args.packet_json), process_now())
                text = canonicalize(verification) + "\n"
                if args.verification_out:
                    write_exclusive(args.verification_out, text)
                else:
                    stdout.write(text)
                return 0
            raise error_type("unknown command")
        except (error_type, OSError, ValueError, TypeError) as exc:
            print(f"ERROR: {exc}", file=stderr)
            return 2

    return main
