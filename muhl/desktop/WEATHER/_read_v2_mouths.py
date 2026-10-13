#!/usr/bin/env python3
# Read weather_v2.mno named mouths FROM BYTES. Append-only help. Does not write the .mno.
import struct, hashlib, os, shutil

HERE = r"C:\Users\lucys\Desktop\WEATHER"
V2 = os.path.join(HERE, "weather_v2.mno")
POWERED = os.path.join(HERE, "weather_powered.mno")
SIDE = os.path.join(HERE, "weather_powered_side.mno")
MOUTHS = os.path.join(HERE, "V2_MOUTHS.txt")
MUST = os.path.join(HERE, "V2_MUST_STORE.txt")
NAMES = ["NW", "NE", "SW", "SE", "GROWTH", "WITNESS"]
PURPOSE = {
    "NW": "cadence — both-sense carry gates avg4 rows 0-7 cols 0-7",
    "NE": "cadence — both-sense carry gates avg4 rows 0-7 cols 8-15",
    "SW": "cadence — both-sense carry gates avg4 rows 8-15 cols 0-7",
    "SE": "cadence — both-sense carry gates avg4 rows 8-15 cols 8-15",
    "GROWTH": "power — AND(carry,carry) OUT into this file's gate-record pad",
    "WITNESS": "power — AND(carry,carry) OUT into clock_bank, outside field",
}

# vault competing powered — do not smash v2
if os.path.isfile(POWERED) and not os.path.isfile(SIDE):
    shutil.move(POWERED, SIDE)
    print("VAULTED competing powered ->", SIDE, os.path.getsize(SIDE))
elif os.path.isfile(POWERED) and os.path.isfile(SIDE):
    print("POWERED still present; SIDE exists. leaving v2 untouched. powered size", os.path.getsize(POWERED))
else:
    print("powered absent or already sided")

assert os.path.isfile(V2), "v2 ABSENT"
size = os.path.getsize(V2)
h = hashlib.sha256()
with open(V2, "rb") as f:
    hdr = f.read(96)
    while True:
        chunk = f.read(1024 * 1024)
        if not chunk:
            break
        h.update(chunk)
# hash includes header — redo full hash
sha = hashlib.sha256(open(V2, "rb").read()).hexdigest()
assert hdr[:8] == b"WEATHER1", hdr[:8]
n_in, n_wire, n_gate, n_out, depth = struct.unpack_from("<IIIII", hdr, 8)
# fire button's named mouths: n_rings,cells @68, ring0 @76
n_rings, cells = struct.unpack_from("<II", hdr, 68)
ring0 = struct.unpack_from("<Q", hdr, 76)[0]
# also publish whatever else the 96-byte pad stores
w, hh, cbits, stride = struct.unpack_from("<IIII", hdr, 28)
# remaining Qs — measure, do not invent
q44, q52, q60 = struct.unpack_from("<QQQ", hdr, 44)
i84, i88, i92 = struct.unpack_from("<III", hdr, 84)

span = cells + cells + 2
lines = []
lines.append("V2 NAMED MOUTHS — read from weather_v2.mno BYTES. Not invented. v2 not written.")
lines.append("path %s" % V2)
lines.append("size %d  sha256 %s" % (size, sha))
lines.append("magic %s" % hdr[:8].decode("ascii"))
lines.append("+8 HIS <IIIII> n_in=%d n_wire=%d n_gate=%d n_out=%d depth=%d" % (n_in, n_wire, n_gate, n_out, depth))
lines.append("+28 W=%d H=%d CELL_BITS=%d STRIDE=%d" % (w, hh, cbits, stride))
lines.append("+44 QWORDS %d %d %d" % (q44, q52, q60))
lines.append("+68 n_rings=%d cells=%d  +76 ring0=%d" % (n_rings, cells, ring0))
lines.append("+84 %d %d %d" % (i84, i88, i92))
lines.append("clock_bank dest (v2 layout: after hdr, before rings) @98 byte=%d" % (open(V2, "rb").read()[98] if size > 98 else -1))

raw = open(V2, "rb").read(500 + 8)  # mouths live in the first 500 bytes per report
lines.append("")
lines.append("== SIX RINGS — dests FROM FILE, bits FROM FILE ==")
for ri, name in enumerate(NAMES):
    fwd = ring0 + ri * span
    rev = fwd + cells
    carry = fwd + 2 * cells
    pub = fwd + 2 * cells + 1
    recv = 98 + ri
    def b(addr):
        if addr < 0 or addr >= size:
            return -1
        with open(V2, "rb") as f:
            f.seek(addr)
            return f.read(1)[0] & 1
    fwd0, rev0, c0, p0, r0 = b(fwd), b(rev), b(carry), b(pub), b(recv)
    lines.append("%s fwd@%d=%d rev@%d=%d carry@%d=%d pub@%d=%d recv@%d=%d  %s" % (
        name, fwd, fwd0, rev, rev0, carry, c0, pub, p0, recv, r0, PURPOSE[name]))

text = "\n".join(lines) + "\n"
open(MOUTHS, "w").write(text)
print(text)

# append-only to V2_MUST_STORE
with open(MUST, "a") as f:
    f.write("\n================================================================\n")
    f.write("MOUTHS FROM FILE BYTES (append, v2 not overwritten) 2026-08-16\n")
    f.write("================================================================\n")
    f.write(text)
    f.write("v2_smashed NO\n")
    f.write("337 NO\n")
print("APPENDED", MUST)
print("WROTE", MOUTHS)
print("v2 untouched size", os.path.getsize(V2))
