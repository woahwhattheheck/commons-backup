#!/usr/bin/env python3
# host/muhl_route_table.py
# Address one dest inbox on table_mail.mno, fire THAT ring both-sense, die.
# English letter is a sibling file under MUHL_COMMONS\TABLE\ (SURFACE).
# Does not smash commons.mno. Dest FROM FILE. new=old|mask.
#   python host/muhl_route_table.py --to CAIRN --from GROK
#   python host/muhl_route_table.py --to CAIRN --from GROK --file letter.md
#   python host/muhl_route_table.py --to KITE --from CAIRN --body "CAIRN DIRECT — ..."

import hashlib, os, struct, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import muhl_surface_table as surface

if "--inject" in sys.argv:
    print("REFUSE: --inject 0x01 is WIPE. Law is new=old|mask.")
    raise SystemExit(2)

PKG = r"C:\Users\lucys\Desktop\MUHL_COMMONS\table_mail.mno"
HOMES = r"C:\Users\lucys\Desktop\MUHL_COMMONS\commons.mno"
TABLE = r"C:\Users\lucys\Desktop\MUHL_COMMONS\TABLE"
MAGIC = b"TABLEML1"
SCHEMA = "TABLEML1.v1"
PLAYERS = ("ZERO", "GROK", "KITE", "CAIRN", "SPALL", "GRAVE", "AXIOM", "SHARD", "SCREE")


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def arg(flag, default=None):
    if flag not in sys.argv:
        return default
    i = sys.argv.index(flag)
    if i + 1 >= len(sys.argv):
        print("NEED_BRYCE — %s needs a value" % flag)
        raise SystemExit(1)
    return sys.argv[i + 1]


def deliver(src_name, dest_name, letter=None, log=print):
    src_name = (src_name or "").upper()
    dest_name = (dest_name or "").upper()
    if dest_name not in PLAYERS:
        raise ValueError("NEED — --to one of " + " ".join(PLAYERS))
    if src_name not in PLAYERS:
        raise ValueError("NEED — --from one of " + " ".join(PLAYERS))
    dest_i = PLAYERS.index(dest_name)
    outp = None
    homes_before = _sha256_file(HOMES) if os.path.isfile(HOMES) else "MISSING"
    mail_before = _sha256_file(PKG)
    append_occurred = "NO"
    if letter is not None:
        inbox = os.path.join(TABLE, "INBOX_" + dest_name)
        os.makedirs(inbox, exist_ok=True)
        ts = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        outp = os.path.join(inbox, "%s_FROM_%s.md" % (ts, src_name))
        with open(outp, "w", encoding="utf-8") as f:
            f.write(letter)
            if not letter.endswith("\n"):
                f.write("\n")
        log("LETTER %s" % outp)
        append_occurred = "YES"
        try:
            import muhl_pub_board as pubboard
            mid = "tbl-%s-%s-%s" % (ts, src_name, dest_name)
            pst = pubboard.publish_post(src_name, dest_name, mid, letter)
            log("BOARD_PUB %s %s" % (mid, pst))
        except Exception as e:
            log("BOARD_PUB %s" % type(e).__name__)
    else:
        log("LETTER none (ding only)")

    with open(PKG, "r+b") as f:
        raw = f.read(96)
        assert raw[:8] == MAGIC, raw[:8]
        n_in = struct.unpack_from("<I", raw, 8)[0]
        inj = struct.unpack_from("<Q", raw, 60)[0]
        field = struct.unpack_from("<Q", raw, 52)[0]
        n_rings, cells = struct.unpack_from("<II", raw, 68)
        ring0 = struct.unpack_from("<Q", raw, 76)[0]
        clock = struct.unpack_from("<Q", raw, 84)[0]
        assert n_in == 9 and n_rings == 9
        span = cells + cells + 2
        f.seek(inj + dest_i)
        old = f.read(1)[0]
        mask = 0x01
        new = old | mask
        f.seek(inj + dest_i)
        f.write(bytes((new,)))
        log("  inj@%d %s %d->%d" % (inj + dest_i, dest_name, old, new))
        fwd = ring0 + dest_i * span
        rev = fwd + cells
        shots = [("inj", inj + dest_i, old, mask, new)]
        dests = {"inj": inj + dest_i, "fwd": fwd, "rev": rev, "mask": mask,
                 "old": old, "new": new}
        for addr, tag in ((fwd, "fwd"), (rev, "rev")):
            f.seek(addr)
            o = f.read(1)[0]
            n = o | mask
            f.seek(addr)
            f.write(bytes((n,)))
            log("  %s@%d %d->%d" % (tag, addr, o, n))
            shots.append((tag, addr, o, mask, n))
            dests[tag + "_old"] = o
            dests[tag + "_new"] = n
        dests["shots"] = shots
        dests["inj_old"] = old
        dests["inj_new"] = new
        dests["magic"] = MAGIC.decode("ascii")
        dests["schema"] = SCHEMA
        dests["mno_path"] = PKG
        dests["parser"] = "host/muhl_route_table.py " + SCHEMA
        dests["header_inj"] = inj
        dests["header_field"] = field
        dests["header_ring0"] = ring0
        dests["dest_index"] = dest_i
        dests["dest_offset_inj"] = inj + dest_i
        dests["dest_offset_fwd"] = fwd
        dests["dest_offset_rev"] = rev
        f.flush()
        os.fsync(f.fileno())
        f.seek(field)
        fld = f.read(n_in)
        f.seek(ring0)
        r0 = f.read(1)[0] & 1
        f.seek(clock + dest_i)
        ck = f.read(1)[0] & 1
    log("ROUTE_TABLE %s -> %s" % (src_name, dest_name))
    log("  field_lsbs " + " ".join("%s=%d" % (PLAYERS[i], fld[i] & 1) for i in range(n_in)))
    log("  dests FROM FILE ring0@%d=%d clock_dest@%d=%d inj@%d field@%d" % (
        ring0, r0, clock + dest_i, ck, inj, field))
    surface.write_board()
    homes_after = _sha256_file(HOMES) if os.path.isfile(HOMES) else "MISSING"
    mail_after = _sha256_file(PKG)
    if homes_before != homes_after:
        log("REFUSE — commons.mno hash moved. mail must not touch Homes.")
        raise RuntimeError("commons.mno changed during mail")
    dests.update({
        "src": src_name, "dest": dest_name, "letter": outp,
        "ring0": ring0, "r0": r0, "clock": clock + dest_i, "ck": ck,
        "field": field, "field_lsbs": [fld[i] & 1 for i in range(n_in)],
        "commons_sha256_before": homes_before,
        "commons_sha256_after": homes_after,
        "commons.mno": "UNTOUCHED",
        "table_mail_sha256_before": mail_before,
        "table_mail_sha256_after": mail_after,
        "append_occurred": append_occurred,
        "fire_occurred": "YES",
        "bit_changed": "YES" if any(s[2] != s[4] for s in dests.get("shots") or []) else "NO",
        "authenticated_player": "UNKNOWN",
        "home_inferred": "NO",
        "fire_337": "NO",
        "titan_mmap": "NO",
    })
    return dests


def main():
    dest_name = (arg("--to") or "").upper()
    src_name = (arg("--from") or "").upper()
    path = arg("--file")
    body = arg("--body")
    letter = None
    if path:
        with open(path, "r", encoding="utf-8") as f:
            letter = f.read()
    elif body is not None:
        letter = body
    try:
        deliver(src_name, dest_name, letter)
    except ValueError as e:
        print(str(e))
        return 1
    print("DIE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
