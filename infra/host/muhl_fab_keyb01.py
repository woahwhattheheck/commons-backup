#!/usr/bin/env python3
# KEYB01 fab. HIS nring2. New dest only. Do not smash.
# --inject 0x01 is WIPE. exists. New dest only.
# python infra/host/muhl_fab_keyb01.py --check
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_fab_nring_pkg as nring
import muhl_keyb01_abi as abi

MAGIC = abi.MAGIC
OUT = abi.OUT
MANIFEST = abi.MANIFEST
N_POS = abi.N_POS
WIDTH = abi.WIDTH
N_FRAME = abi.N_FRAME
N_RINGS = abi.N_RINGS
MOUTH_ORDER = abi.MOUTH_ORDER
encode_frame = abi.encode_frame
layout_keyb = abi.layout_keyb
mouth_addrs = abi.mouth_addrs


def build():
    L = abi.layout_keyb()
    rings = nring.emit_rings(L, abi.N_RINGS)
    net = nring.emit_net(L, abi.N_FRAME, abi.N_RINGS, abi.ring_of)
    abi.emit_decoder(net, L)
    assert nring.net_ops_ok(net) and nring.ring_ops_ok(rings)
    ok, w = nring.one_writer(list(rings) + list(net.gates))
    assert ok, w
    z = [0] * abi.N_FRAME
    body, n_gate, n_wire, depth, growth = nring.serialize(
        abi.MAGIC, L, net, rings, abi.N_FRAME, abi.N_RINGS, z, z)
    h = nring.parse_hdr(body, abi.MAGIC)
    assert h["n_in"] == abi.N_FRAME and body[:8] == abi.MAGIC
    return {"body": body, "L": L, "h": h, "n_gate": n_gate,
            "n_wire": n_wire, "depth": depth, "growth_base": growth}


def manifest_of(built, path):
    h, L = built["h"], built["L"]
    return {
        "magic": abi.MAGIC.decode("ascii"), "path": path,
        "n_pos": abi.N_POS, "alphabet_width": abi.WIDTH,
        "char_base": h["inj_base"], "field_base": h["cell_base"],
        "commit_fwd": h["ring0"], "commit_rev": h["ring0"] + h["cells"],
        "commit_span": h["cells"] * 2 + 2, "clock": h["clock"],
        "n_gate": built["n_gate"], "n_wire": built["n_wire"],
        "depth": built["depth"], "mouths": abi.mouth_addrs(L),
        "formula": "addr = char_base + position * alphabet_width + char_code",
        "abi": "7-bit ASCII plus CR/LF/space/tab/backspace. Order is position.",
        "git_copy_runs": "NO", "HTTP_is_the_computer": "NO",
    }


def pulse(body, text, enable=True):
    h = nring.parse_hdr(body, abi.MAGIC)
    img = bytearray(body)
    for i, v in enumerate(abi.encode_frame(text)):
        img[h["inj_base"] + i] = v & 1
    bit = 1 if enable else 0
    img[h["ring0"]] = bit
    img[h["ring0"] + h["cells"]] = bit
    nring.address_stored(img, abi.MAGIC)
    return {n: img[a] & 1 for n, a in abi.mouth_addrs(abi.layout_keyb()).items()}, img


FORBIDDEN = abi.FORBIDDEN


if __name__ == "__main__":
    import muhl_fab_keyb01_go as go
    raise SystemExit(go.main())
