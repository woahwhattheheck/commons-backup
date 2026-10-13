"""CLI for the public-sector workshare pack."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

from .workshare import compile_pack, load_json_strict, render_markdown, verify_packet, write_exclusive


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile/verify paid public-sector workshare capture packets")
    sub = parser.add_subparsers(dest="command", required=True)

    compile_p = sub.add_parser("compile")
    compile_p.add_argument("manifest")
    compile_p.add_argument("--out-json", required=True)
    compile_p.add_argument("--out-md", required=True)

    verify_p = sub.add_parser("verify")
    verify_p.add_argument("packet")
    verify_p.add_argument("--current", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "compile":
        manifest = load_json_strict(args.manifest)
        packet = compile_pack(manifest, as_of_utc=now_utc())
        write_exclusive(args.out_json, (json.dumps(packet, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        write_exclusive(args.out_md, render_markdown(packet).encode("utf-8"))
        print(json.dumps({"overall_state": packet["overall_state"], "receipt_sha256": packet["receipt_sha256"]}, sort_keys=True))
        return 0

    packet = load_json_strict(args.packet)
    result = verify_packet(packet, current_as_of_utc=now_utc() if args.current else None)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
