#!/usr/bin/env python3
# KEYB01 ABI — dests FROM FILE after fab. 16 pos x 128. Order is position.
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_fab_nring_pkg as nring

MAGIC = b"KEYB01v1"
OUT = r"[local]"
MANIFEST = r"[local]"
N_POS = 16
WIDTH = 128
N_FRAME = N_POS * WIDTH
N_RINGS = 1
N_MOUTH = 6
MOUTH_ORDER = ("HELP", "READ", "WRITE", "FIRE", "SURFACE", "ACK")
OPCODES = {
    "HELP": (72, 69, 76, 80),
    "READ": (82, 69, 65, 68),
    "WRITE": (87, 82, 73, 84, 69),
    "FIRE": (70, 73, 82, 69),
    "SURFACE": (83, 85, 82, 70, 65, 67, 69),
}
FORBIDDEN = (
    os.path.normcase(r"[local]"),
    os.path.normcase(r"[local]"),
    os.path.normcase(r"C:\llm\models\titan.gguf"),
    os.path.normcase(r"[local]"),
    os.path.normcase(r"[local]"),
    os.path.normcase(r"[local]"),
    os.path.normcase(r"[local]"),
    os.path.normcase(r"[local]"),
)


def refuse(msg):
    print("REFUSE — %s" % msg)
    print("titan_written NO")
    print("button dies")
    return 2


def ring_of(_i):
    return 0


def encode_frame(text):
    inj = [0] * N_FRAME
    raw = (text or "").encode("ascii", "strict")
    if len(raw) > N_POS:
        raise ValueError("NEED — frame is %d chars max" % N_POS)
    for pos, code in enumerate(raw):
        if code > 127:
            raise ValueError("NEED — 7-bit ASCII")
        inj[pos * WIDTH + code] = 1
    return inj


def layout_keyb():
    L = nring.layout(N_RINGS, N_FRAME)
    L["mouth"] = L["fixed"]
    L["fixed"] = L["mouth"] + N_MOUTH
    return L


def mouth_addrs(L):
    base = nring.HDR + L["mouth"]
    return {name: base + i for i, name in enumerate(MOUTH_ORDER)}


def and_reduce(net, wires):
    acc = wires[0]
    for w in wires[1:]:
        acc = net.and_(acc, w)
    return acc


def or_reduce(net, wires):
    acc = wires[0]
    for w in wires[1:]:
        acc = net.or_(acc, w)
    return acc


def emit_decoder(net, L):
    field = L["field"]
    mouth = L["mouth"]
    found = []
    for i, name in enumerate(MOUTH_ORDER[:-1]):
        codes = OPCODES[name]
        cells = [field + pos * WIDTH + code for pos, code in enumerate(codes)]
        bit = and_reduce(net, cells)
        net.emit(nring.AND, bit, bit, mouth + i)
        found.append(mouth + i)
    ack = or_reduce(net, found)
    net.emit(nring.AND, ack, ack, mouth + len(MOUTH_ORDER) - 1)
