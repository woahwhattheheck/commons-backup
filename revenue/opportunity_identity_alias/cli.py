"""Offline CLI over the repository-carried current opportunity alias registry."""
from __future__ import annotations
import argparse,json,sys
from .registry import read_json_file_no_follow, validate_transition
from .resolver import resolve_current, verify_current
from .strict import IdentityAliasError, canonical_json

def _load(path: str):
    return read_json_file_no_follow(path, label=f"input {path}")

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command",required=True)
    resolve=sub.add_parser("resolve-current"); resolve.add_argument("observation")
    verify=sub.add_parser("verify-current"); verify.add_argument("observation"); verify.add_argument("result")
    transition=sub.add_parser("validate-transition"); transition.add_argument("previous"); transition.add_argument("candidate")
    args=parser.parse_args(argv)
    try:
        if args.command=="resolve-current": out=resolve_current(_load(args.observation))
        elif args.command=="verify-current":
            out={"verified":verify_current(_load(args.observation),_load(args.result))}
            if not out["verified"]:
                print(json.dumps(out,sort_keys=True,separators=(",",":")),file=sys.stderr); return 2
        else: out=validate_transition(_load(args.previous),_load(args.candidate))
        sys.stdout.buffer.write(canonical_json(out)+b"\n"); return 0
    except (IdentityAliasError,OSError) as exc:
        print(str(exc),file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
