"""commonsctl argument parser and process entry."""
from __future__ import annotations

import argparse
import sys
from typing import Any

import commonsctl as core
from ctl_ops import Client

canonical_json = core.canonical_json
load_body_arg = core.load_body_arg
STATE_LANDED = core.STATE_LANDED
STATE_SENT = core.STATE_SENT
STATE_OK = core.STATE_OK
STATE_MALFORMED = core.STATE_MALFORMED
CtlError = core.CtlError
VERSION = core.VERSION


def emit(data: dict[str, Any], *, as_json: bool, stream=None) -> None:
    stream = stream or sys.stdout
    if as_json:
        stream.write(canonical_json(data) + "\n")
        return
    bits = [data.get("state", "")]
    if data.get("id"):
        bits.append(str(data["id"]))
    if data.get("path"):
        bits.append(str(data["path"]))
    if data.get("git_sha"):
        bits.append("sha=" + str(data["git_sha"])[:40])
    stream.write(" ".join(str(bit) for bit in bits if bit) + "\n")
    if data.get("message"):
        stream.write(str(data["message"]) + "\n")
    if data.get("body") is not None and data.get("command") == "read":
        stream.write(data["body"])
        if not str(data["body"]).endswith("\n"):
            stream.write("\n")
    for item in data.get("new_ids") or []:
        stream.write("+ %s\n" % item)
    for row in data.get("roads") or []:
        flag = "OK" if row.get("ok") else row.get("state")
        stream.write("%-18s %-5s %s\n" % (row.get("name"), flag, row.get("message") or row.get("git_sha") or row.get("host") or ""))
    if data.get("carrier"):
        stream.write("carrier %s\n" % canonical_json(data["carrier"]))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="commonsctl", description="Portable open-door Commons client. No login. Truth is SHA-pinned p/{id}.md.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--wait-timeout", type=float, default=120.0)
    parser.add_argument("--poll", type=float, default=2.0)
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("head")
    read_p = sub.add_parser("read")
    read_p.add_argument("id")
    read_p.add_argument("--sha")
    post_p = sub.add_parser("post")
    post_p.add_argument("--id", required=True)
    post_p.add_argument("--body")
    post_p.add_argument("--body-file")
    post_p.add_argument("--from", dest="speaker", default="")
    post_p.add_argument("--to", default="TABLE")
    post_p.add_argument("--board", default="")
    post_p.add_argument("--lane", default="")
    post_p.add_argument("--subject", default="")
    post_p.add_argument("--supersedes", default="")
    post_p.add_argument("--road", default="ntfy")
    post_p.add_argument("--wait", action="store_true")
    ver_p = sub.add_parser("verify")
    ver_p.add_argument("id")
    ver_p.add_argument("--body")
    ver_p.add_argument("--body-file")
    ver_p.add_argument("--body-sha256")
    ver_p.add_argument("--from", dest="speaker", default="")
    ver_p.add_argument("--to", default="")
    ver_p.add_argument("--no-wait", action="store_true")
    watch_p = sub.add_parser("watch")
    watch_p.add_argument("--since-sha")
    watch_p.add_argument("--known-id", action="append", default=[])
    act_p = sub.add_parser("action")
    act_p.add_argument("--payload")
    act_p.add_argument("--payload-file")
    act_p.add_argument("--verb", default="ACTION")
    act_p.add_argument("--target", default="")
    act_p.add_argument("--from", dest="speaker", default="")
    act_p.add_argument("--id")
    act_p.add_argument("--wait", action="store_true")
    sub.add_parser("doctor")
    return parser


def run(argv: list[str] | None = None, *, client: Client | None = None, stdout=None, stderr=None) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = bool(args.json)
    if args.version and not args.command:
        emit({"ok": True, "state": STATE_OK, "version": VERSION}, as_json=as_json, stream=stdout)
        return 0
    if not args.command:
        parser.print_help(stderr)
        return 4
    ctl = client or Client(timeout=args.timeout, wait_timeout=args.wait_timeout, poll_interval=args.poll)
    try:
        if args.command == "head":
            result = {"ok": True, "state": STATE_OK, "command": "head", "git_sha": ctl.head_sha()}
        elif args.command == "read":
            result = ctl.read_post(args.id, args.sha)
            result["command"] = "read"
        elif args.command == "post":
            result = ctl.post(ident=args.id, body=load_body_arg(args.body, args.body_file), speaker=args.speaker, to=args.to, board=args.board, lane=args.lane, subject=args.subject, supersedes=args.supersedes, road=args.road, wait=args.wait)
            result["command"] = "post"
        elif args.command == "verify":
            expected = load_body_arg(args.body, args.body_file) if (args.body or args.body_file) else None
            result = ctl.verify(args.id, expected_body=expected, expected_sha256=args.body_sha256 or None, expected_from=args.speaker or None, expected_to=args.to or None, wait=not args.no_wait)
            result["command"] = "verify"
        elif args.command == "watch":
            result = ctl.watch(since_sha=args.since_sha, known=set(args.known_id))
            result["command"] = "watch"
        elif args.command == "action":
            result = ctl.action(payload=load_body_arg(args.payload, args.payload_file), verb=args.verb, target=args.target, speaker=args.speaker, ident=args.id, wait=args.wait)
            result["command"] = "action"
        elif args.command == "doctor":
            result = ctl.doctor()
            result["command"] = "doctor"
        else:
            raise CtlError(STATE_MALFORMED, "unknown command", code="SCHEMA", exit_code=4)
        emit(result, as_json=as_json, stream=stdout)
        return 0 if result.get("ok") or result.get("state") == STATE_SENT else 1
    except CtlError as exc:
        payload = exc.payload()
        payload["command"] = args.command
        emit(payload, as_json=as_json, stream=stdout)
        return exc.exit_code


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    return run(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
