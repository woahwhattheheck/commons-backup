#!/usr/bin/env python3
# host/muhl_dump_litertlm.py
# Dump .litertlm section table + tokenizer dests FROM FILE, then die.
# Read-only. Does not fire. Does not convert. Does not copy weights.
#   python host/muhl_dump_litertlm.py PATH.litertlm
# Never --inject 0x01.

from __future__ import annotations

import os
import sys

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE")
    raise SystemExit(2)

MAGIC = b"LITERTLM"
TYPE_NAME = {3: "tflite", 4: "spm", 5: "tokmeta", 7: "weights"}


def u16(b, o):
    return int.from_bytes(b[o : o + 2], "little")


def i32(b, o):
    return int.from_bytes(b[o : o + 4], "little", signed=True)


class Le:
    def __init__(self, data):
        self.d = data

    def i8(self, pos):
        return self.d[pos]

    def u16(self, pos):
        return u16(self.d, pos)

    def i32(self, pos):
        return i32(self.d, pos)

    def i64(self, pos):
        return int.from_bytes(self.d[pos : pos + 8], "little", signed=True)


def indirect(r, pos):
    return pos + r.i32(pos)


def field(r, table, idx):
    vtable = table - r.i32(table)
    vtable_size = r.u16(vtable)
    slot = 4 + idx * 2
    if slot >= vtable_size:
        return -1
    field_off = r.u16(vtable + slot)
    return -1 if field_off == 0 else table + field_off


def vector(r, field_pos):
    if field_pos < 0:
        return None
    vec = indirect(r, field_pos)
    count = r.i32(vec)
    return (vec + 4, count)


def read_varint(data, i, end):
    n = 0
    s = 0
    while i < end:
        b = data[i]
        i += 1
        n |= (b & 0x7F) << s
        if b < 0x80:
            return n, i
        s += 7
        if s > 63:
            raise ValueError("varint")
    raise ValueError("truncated varint")


def skip_field(data, i, wt, end):
    if wt == 0:
        _, i = read_varint(data, i, end)
        return i
    if wt == 1:
        return i + 8
    if wt == 5:
        return i + 4
    if wt == 2:
        n, i = read_varint(data, i, end)
        return i + n
    raise ValueError("wire %s" % wt)


def spm_pieces(blob, limit_names=12):
    i = 0
    n = 0
    named = []
    want = ("<pad>", "<eos>", "<bos>", "<unk>", "<mask>")
    ids = {}
    end = len(blob)
    while i < end:
        tag = blob[i]
        i += 1
        field_id = tag >> 3
        wt = tag & 7
        if field_id == 1 and wt == 2:
            nlen, i = read_varint(blob, i, end)
            inner_end = i + nlen
            piece = None
            j = i
            while j < inner_end:
                t2 = blob[j]
                j += 1
                f2 = t2 >> 3
                w2 = t2 & 7
                if f2 == 1 and w2 == 2:
                    slen, j = read_varint(blob, j, inner_end)
                    piece = blob[j : j + slen].decode("utf-8", "replace")
                    j += slen
                else:
                    j = skip_field(blob, j, w2, inner_end)
            if piece is not None:
                if n < limit_names:
                    named.append((n, piece))
                if piece in want and piece not in ids:
                    ids[piece] = n
            n += 1
            i = inner_end
            continue
        i = skip_field(blob, i, wt, end)
    return n, named, ids


def proto_strings(blob, cap=48):
    import re
    text = blob.decode("latin1")
    found = []
    for m in re.finditer(r"<[^>\n]{1,48}>|\[[^\]\n]{1,48}\]", text):
        s = m.group(0)
        if s not in found:
            found.append(s)
        if len(found) >= cap:
            break
    return found


def dump(path):
    if not os.path.isfile(path):
        print("NEED — file")
        return 1
    n = os.path.getsize(path)
    with open(path, "rb") as f:
        head = f.read(32)
        if head[:8] != MAGIC:
            print("REFUSE — not LITERTLM")
            return 2
        header_end = int.from_bytes(head[24:32], "little")
        major = int.from_bytes(head[8:12], "little")
        minor = int.from_bytes(head[12:16], "little")
        patch = int.from_bytes(head[16:20], "little")
        f.seek(32)
        idx = f.read(header_end - 32)
        le = Le(idx)
        root = indirect(le, 0)
        sm = indirect(le, field(le, root, 1))
        elems, count = vector(le, field(le, sm, 0))
        print("LITERTLM bytes %d ver %d.%d.%d header_end %d sections %d" % (n, major, minor, patch, header_end, count))
        secs = []
        for i in range(count):
            so = indirect(le, elems + i * 4)
            bF, eF, dF = field(le, so, 1), field(le, so, 2), field(le, so, 3)
            typ = le.i8(dF) if dF >= 0 else 0
            begin = le.i64(bF) if bF >= 0 else 0
            end = le.i64(eF) if eF >= 0 else 0
            secs.append((i, typ, begin, end))
            print("sec#%d type=%d %s begin=%d end=%d size=%d" % (i, typ, TYPE_NAME.get(typ, "?"), begin, end, end - begin))
        for i, typ, begin, end in secs:
            if typ == 5:
                f.seek(begin)
                blob = f.read(end - begin)
                strs = proto_strings(blob)
                specials = [s for s in strs if s.startswith("<") or s.startswith("[")]
                print("tokmeta@%d size=%d specials %s" % (begin, end - begin, specials[:16]))
                tmpl = [s for s in strs if "{%" in s or "{{" in s]
                if tmpl:
                    print("tokmeta jinja_bytes %d" % len(tmpl[0]))
            if typ == 4:
                f.seek(begin)
                blob = f.read(end - begin)
                n_pieces, named, ids = spm_pieces(blob)
                print("spm@%d size=%d pieces=%d ids %s" % (begin, end - begin, n_pieces, ids))
                for pid, piece in named:
                    print("  piece %d %s" % (pid, piece))
    print("DIE")
    return 0


if __name__ == "__main__":
    path = None
    for a in sys.argv[1:]:
        if not a.startswith("-"):
            path = a
            break
    if not path:
        print("NEED — .litertlm path")
        raise SystemExit(1)
    raise SystemExit(dump(path))
