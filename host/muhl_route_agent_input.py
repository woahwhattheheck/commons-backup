#!/usr/bin/env python3
# host/muhl_route_agent_input.py
# Routing button: encode with AGENT SPM dest FROM FILE, compare to installed
# fwd_input mouth dest FROM FILE, then die.
# Does not invent a bigger mouth. Does not write titan. Does not fire.
#   python host/muhl_route_agent_input.py "cl5"
# Never --inject 0x01.

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_address_agent as addr

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

REG = r"C:\llm\models\titan_circuits.json"


def main():
    prompt = "cl5"
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        prompt = args[0]
    if not os.path.isfile(REG):
        print("NEED — titan_circuits.json")
        return 1
    reg = json.load(open(REG, encoding="utf-8"))
    mouth = reg.get("fwd_input") or {}
    inst = reg.get("pfc_installed_model") or {}
    mouth_off = int(mouth.get("offset") or 0)
    mouth_len = int(mouth.get("len") or 0)
    n_vocab = int(inst.get("n_vocab") or 0)
    path = addr.installed_litert()
    if not os.path.isfile(path):
        print("NEED — AGENT .litertlm")
        return 1
    vocab, pieces, maxtok = addr.load_vocab(path)
    ids = addr.encode(prompt, vocab, maxtok, add_bos=True)
    bits = max(1, (max(ids) if ids else 1).bit_length())
    need = (4 + 4 * len(ids))  # u32 n + u32 ids; measured packing guess, not a dest
    print("AGENT SPM dest FROM FILE pieces=%d n_vocab=%d" % (len(pieces), n_vocab))
    print("prompt %r ids %s" % (prompt, ids))
    print("fwd_input dest FROM FILE offset=%d len=%d layout=[op:1][A:2le][B:2le]" % (mouth_off, mouth_len))
    print("id_bits_max=%d bytes_if_u32n=%d A16_max=%d" % (bits, need, 65535))
    wired = (inst.get("wired_to") or inst.get("wired_to") or {}).get("input")
    print("pfc_installed_model.wired_to.input=%s" % wired)
    over = [i for i in ids if i > 65535]
    print("ids_gt_A16 %s" % over)
    mdl = reg.get("mdl_input") or {}
    print("mdl_input dest FROM FILE len=%s note=%s" % (mdl.get("len"), (mdl.get("note") or "")[:80]))
    print("mdl_input CLASS=bit_wires_not_token_ids. Do not hijack for SPM ids.")
    if over:
        print("GAP — even sequential one-token pack truncates. A is u16; SPM id needs %d bits." % bits)
    elif mouth_len < need:
        print("GAP — mouth too small for this id list. Do not invent dest. Do not widen on the host.")
    else:
        print("MOUTH FITS — not writing this button. Address then one start is a later --go.")
    print("NO WRITE")
    print("NO FIRE")
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
