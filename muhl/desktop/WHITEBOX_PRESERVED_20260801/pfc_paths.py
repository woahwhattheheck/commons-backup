#!/usr/bin/env python3
"""host/pfc_paths.py — WHERE THE Muhlnickel LIVES ON THIS MACHINE. One env var, nothing else.

The lab was written with `C:/llm/...` spelled out in every script, which is correct on the owner's box and
unrunnable anywhere else. This module resolves that one root and hands back the same paths.

    PFC_ROOT unset            ->  C:/llm            (the owner's box: byte-identical to the old literals)
    set PFC_ROOT=D:/llm       ->  D:/llm            (another drive)
    export PFC_ROOT=/mnt/llm  ->  /mnt/llm          (another machine entirely)

Nothing here computes; it is a path constant. No pfc logic, no state, no I/O.
"""
import os

ROOT = os.environ.get("PFC_ROOT", "C:/llm").replace("\\", "/").rstrip("/")


def p(rel):
    """ROOT-relative path, forward slashes, exactly as the literals were written."""
    return ROOT + "/" + str(rel).replace("\\", "/").lstrip("/")


MODELS = p("models")
SBX    = p("sdc_sandbox")
OUT    = p("sdc_out")
TITAN  = p("models/titan.gguf")
REG    = p("models/titan_circuits.json")

if __name__ == "__main__":
    for k in ("ROOT", "MODELS", "SBX", "OUT", "TITAN", "REG"):
        print(f"  {k:<7} {globals()[k]}")
    print(f"\n  exists: ROOT={os.path.isdir(ROOT)}  TITAN={os.path.exists(TITAN)}  REG={os.path.exists(REG)}")
