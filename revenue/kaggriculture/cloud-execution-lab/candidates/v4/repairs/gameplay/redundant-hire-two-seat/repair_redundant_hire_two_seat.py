#!/usr/bin/env python3
"""Exact-source repair for current redundant_hire public seat/player admission."""
from __future__ import annotations
import argparse, hashlib, pathlib

INPUT_GIT='9ded2a9b636793df0511103da802bd3f26dbbb94'
OUTPUT_GIT='a58ba3403d89f0d9a17e56225f891f1aa81a4c8f'
OLD='''    cfg = dict(configuration or {})\n    board = _uint(cfg.get("boardSize", 10), "boardSize", 1)\n'''
NEW='''    farms = observation.get("farms")\n    player = observation.get("player")\n    if (not isinstance(farms, list) or len(farms) != 2\n            or type(player) is not int or player not in (0, 1)):\n        report["reason"] = "unsupported_public_seat_schema"\n        return out, report\n    cfg = dict(configuration or {})\n    board = _uint(cfg.get("boardSize", 10), "boardSize", 1)\n'''

def git_blob(data: bytes)->str:
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def transform(data: bytes)->bytes:
    if git_blob(data)!=INPUT_GIT:
        raise RuntimeError(f'wrong input blob: {git_blob(data)}')
    text=data.decode('utf-8')
    if text.count(OLD)!=1:
        raise RuntimeError(f'expected exactly one repair anchor, found {text.count(OLD)}')
    out=text.replace(OLD,NEW,1).encode()
    if git_blob(out)!=OUTPUT_GIT:
        raise RuntimeError(f'unexpected output blob: {git_blob(out)}')
    return out

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('source',type=pathlib.Path,nargs='?'); ap.add_argument('--output',type=pathlib.Path); ns=ap.parse_args()
    if ns.source is None: ap.error('source path required')
    out=transform(ns.source.read_bytes())
    if ns.output: ns.output.write_bytes(out)
    else: print(OUTPUT_GIT)
    return 0
if __name__=='__main__': raise SystemExit(main())
