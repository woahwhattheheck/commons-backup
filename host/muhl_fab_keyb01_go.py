#!/usr/bin/env python3
# KEYB01 fab go — write once, die. python infra/host/muhl_fab_keyb01.py
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_fab_keyb01 as fab
import muhl_keyb01_abi as abi


def main():
    if "--inject" in sys.argv:
        return abi.refuse("--inject 0x01 is WIPE")
    out = os.path.normpath(abi.OUT)
    if os.path.normcase(out) in abi.FORBIDDEN:
        return abi.refuse("forbidden dest")
    print("KEYB01 FAB")
    built = fab.build()
    h = built["h"]
    print("  magic", abi.MAGIC.decode("ascii"), "n_gate", built["n_gate"],
          "depth", built["depth"], "char_base", h["inj_base"])
    help_m, _ = fab.pulse(built["body"], "HELP")
    heap_m, _ = fab.pulse(built["body"], "HEAP")
    if help_m.get("HELP") != 1 or heap_m.get("HELP") != 0:
        return abi.refuse("fab verify failed")
    print("  fab_verify HELP=1 HEAP=0")
    if "--check" in sys.argv:
        print("CHECK only — no write")
        print("DIE")
        return 0
    if os.path.isfile(out):
        return abi.refuse("%s exists. New dest only. Do not smash." % out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        f.write(built["body"])
        f.flush()
        os.fsync(f.fileno())
    man = fab.manifest_of(built, out)
    man["sha256"] = hashlib.sha256(built["body"]).hexdigest()
    man["n_bytes"] = len(built["body"])
    with open(abi.MANIFEST, "w", encoding="utf-8", newline="\n") as f:
        json.dump(man, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    print("  wrote", out, len(built["body"]))
    print("DIE")
    return 0
