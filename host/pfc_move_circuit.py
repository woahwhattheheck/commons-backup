#!/usr/bin/env python3
"""host/pfc_move_circuit.py — MOVE the baked Muhlnickel circuits OUT of a model's active FFN weight rows, WITHOUT deleting them
and WITHOUT taking them out of the file (owner 2026-07-24, verbatim: "move the circuit", "never delete gates only move",
"never move in part make sure its targeted and right not blind", "DO NOT move my circuits out of the file keep them in
the binary", "the tests work via addressing — fix them so they don't break, bring to me if they do").

THE PROBLEM (measured): the model files have baked TITANCIR circuits (von Neumann machines) sitting INSIDE FFN weight
tensors of the early layers (e.g. Mistral blk.2.ffn_gate rows 28176-29893, magic at byte 1,900,000,000). During a forward
pass those circuit BYTES get read as Q4_K weights → NaN/inf/huge → generation garbles. Proven: SmolLM (no early-FFN
circuit) → "Paris"; Mistral (7 circuits in blk.0/1/2 FFN) → garbage.

THE MOVE (targeted, whole-circuit, reversible, in-file):
  1. LOCATE every circuit by its magic; read its EXACT length from the header (24 + 8·n_gate + 4·n_out) — the WHOLE circuit.
  2. PRESERVE it: append a PFCMOVED record to EOF  [MAGIC8 | orig_off u64 | length u64 | tensor-name | circuit-bytes].
     Stock GGUF readers stop at the declared tensor-data end, so trailing bytes are ignored (the model still loads); the
     circuit stays IN THE BINARY, byte-exact, addressable at its new EOF offset.
  3. BACKFILL the vacated region — the WHOLE affected ROWS (row-aligned superset of the circuit) — with the Q4_K bytes of
     an adjacent CLEAN row block, so those FFN neurons become valid weights and the forward pass is coherent.
  4. REVERSIBLE: a .circmove.json sidecar records every original (offset, bytes) so `restore` puts it back byte-exact.
  5. TESTS: they address circuits by offset. In-model circuits (Mistral/phi/Llama) are NOT in titan_circuits.json, so the
     pfc battery (which addresses titan.gguf) is unaffected — but the manifest records old→new offsets for any addresser,
     and `verify` re-reads each moved circuit from its EOF home and ripple-checks it byte-exact.

  python host/pfc_move_circuit.py <model.gguf> --scan      # list circuits, no writes
  python host/pfc_move_circuit.py <model.gguf> --move      # do the move (reversible)
  python host/pfc_move_circuit.py <model.gguf> --verify    # moved circuits byte-exact at EOF + no magic left in weights
  python host/pfc_move_circuit.py <model.gguf> --restore   # byte-exact revert from the sidecar
"""
import os, sys, json, struct, mmap, base64
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import gguf

MAGIC = b"TITANCIR"; MOVED = b"PFCMOVED"
_QBYTES = {gguf.GGMLQuantizationType.Q4_K: (144, 256), gguf.GGMLQuantizationType.Q6_K: (210, 256),
           gguf.GGMLQuantizationType.Q8_0: (34, 32), gguf.GGMLQuantizationType.Q4_0: (18, 32)}


def _rowbytes(qtype, n_in):
    bpb, wpb = _QBYTES[qtype]; return n_in // wpb * bpb


def _circuit_len(mm, off):
    """the WHOLE circuit's byte length from its TITANCIR header — 24 + 8·n_gate + 4·n_out (targeted, never partial)."""
    n_in, n_wire, n_gate, n_out = struct.unpack_from("<IIII", mm, off + 8)
    return 24 + 8 * n_gate + 4 * n_out, (n_in, n_wire, n_gate, n_out)


def scan(path):
    """every TITANCIR circuit: which tensor it's in, its byte range, and its occupied row range."""
    r = gguf.GGUFReader(path)
    tinfo = [(t.name, int(t.data_offset), int(t.data.nbytes), t.tensor_type, [int(s) for s in t.shape]) for t in r.tensors]
    f = open(path, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    out = []
    pos = mm.find(MAGIC)
    while pos != -1:
        length, hdr = _circuit_len(mm, pos)
        owner = next(((nm, o, b, qt, sh) for (nm, o, b, qt, sh) in tinfo if o <= pos < o + b), None)
        if owner:
            nm, o, b, qt, sh = owner
            n_in = int(sh[0]); rb = _rowbytes(qt, n_in)      # gguf shape[0] = n_in (row length in elements)
            r0 = (pos - o) // rb                              # first occupied row (row-aligned floor)
            r1 = (pos + length - 1 - o) // rb                 # last occupied row (row-aligned ceil)
            out.append({"tensor": nm, "off": pos, "len": length, "hdr": hdr, "t_off": o, "t_bytes": b,
                        "qtype": qt.name, "rowbytes": rb, "row0": r0, "row1": r1, "n_in": n_in})
        pos = mm.find(MAGIC, pos + 1)
    mm.close(); f.close()
    return out


def _clean_source_rows(f, t_off, rb, nrows, a, b, dirty):
    """`n=b-a+1` rows of CLEAN, IN-BOUNDS weight bytes to backfill the dirty run [a,b] — so those FFN neurons become
    valid weights and the forward pass is coherent. HARD guarantees (the old backfill violated both, which spread a
    circuit's magic into a fresh weight row): (1) never read outside [t_off, t_off+nrows*rb); (2) never return bytes
    containing the circuit MAGIC. Prefer a contiguous clean block adjacent to the run (distinct real weights); else tile
    the nearest clean rows."""
    n = b - a + 1
    def block_clean(start):
        return start >= 0 and start + n <= nrows and all((start + k) not in dirty for k in range(n))
    start = b + 1 if block_clean(b + 1) else (a - n if block_clean(a - n) else None)
    if start is not None:
        f.seek(t_off + start * rb); data = f.read(n * rb)
        if MAGIC not in data and len(data) == n * rb: return data
    clean_rows = [rw for rw in range(nrows) if rw not in dirty]        # fallback: tile nearest clean rows
    if not clean_rows: return b"\x00" * (n * rb)                       # (impossible here) whole tensor dirty → zeros
    center = (a + b) / 2.0; clean_rows.sort(key=lambda rw: abs(rw - center))
    out = bytearray(); i = 0
    while len(out) < n * rb:
        f.seek(t_off + clean_rows[i % len(clean_rows)] * rb); rowb = f.read(rb); i += 1
        if MAGIC in rowb: continue
        out += rowb
    return bytes(out[: n * rb])


def _sidecar(path): return path + ".circmove.json"

import glob
REG_GLOB = "C:/llm/models/*.json"


def _update_registries(model_path, oldnew, revert=None):
    """SLIGHTLY update the SDC-fleet registries to the circuits' NEW addresses (owner: 'NOT REDESIGNING just slightly
    update to match new address'). For THIS model's entry only, replace any offset field whose value is a moved circuit's
    OLD offset with its NEW offset. `oldnew`: {old_off:new_off} (or the reverse map when reverting). Returns the edits."""
    base = os.path.basename(model_path).replace("\\", "/")
    edits = []
    for jf in sorted(glob.glob(REG_GLOB)):
        try: d = json.load(open(jf, encoding="utf-8"))
        except Exception: continue
        if not isinstance(d, dict): continue
        changed = False
        for k, v in d.items():                                   # top-level keys are model paths
            if os.path.basename(str(k).replace("\\", "/")) != base: continue
            if not isinstance(v, dict): continue
            for field, val in list(v.items()):
                if isinstance(val, int) and val in oldnew:
                    v[field] = oldnew[val]; changed = True
                    edits.append({"registry": os.path.basename(jf), "model_key": k, "field": field,
                                  "from": val, "to": oldnew[val]})
        if changed:
            json.dump(d, open(jf, "w", encoding="utf-8"), indent=1)
    return edits


def move(path):
    circs = scan(path)
    if not circs:
        print("no TITANCIR circuits found in weight tensors — nothing to move."); return 0
    side = _sidecar(path)
    if os.path.exists(side):
        print(f"already moved (sidecar exists: {side}). run --restore first to redo."); return 1
    filesize = os.path.getsize(path)
    manifest = {"file": path, "orig_size": filesize, "moved": []}
    print(f"=== MOVE {len(circs)} circuit(s) out of the active FFN weight rows (reversible, kept in-binary at EOF) ===", flush=True)
    with open(path, "r+b") as f:
        # PASS 1 — read EVERY circuit's exact bytes FIRST, before any write (safe for circuits that share a row)
        for c in circs:
            f.seek(c["off"]); c["_bytes"] = f.read(c["len"])
        # Per TENSOR, the exact set of CIRCUIT-OCCUPIED ROWS (union of each circuit's own row span). Distant circuits
        # in one tensor are NOT merged into a giant span (that clobbered thousands of unoccupied rows) — only the rows
        # are touched, split into contiguous runs. Each tensor's full dirty set guards the backfill source selection.
        by_t = {}                                                       # t_off -> {rb, nrows, tensor, rows:set}
        for c in circs:
            info = by_t.setdefault(c["t_off"], {"rb": c["rowbytes"], "nrows": c["t_bytes"] // c["rowbytes"],
                                                "tensor": c["tensor"], "rows": set()})
            info["rows"].update(range(c["row0"], c["row1"] + 1))
        region_backup = []                                              # one entry per contiguous dirty run
        for t_off, info in by_t.items():
            rows = sorted(info["rows"]); rb = info["rb"]; a = prev = rows[0]
            runs = []
            for rw in rows[1:]:
                if rw == prev + 1: prev = rw
                else: runs.append((a, prev)); a = prev = rw
            runs.append((a, prev))
            for (r0, r1) in runs:
                lo = t_off + r0 * rb; hi = t_off + (r1 + 1) * rb
                f.seek(lo); orig = f.read(hi - lo)
                region_backup.append({"t_off": t_off, "rb": rb, "nrows": info["nrows"], "r0": r0, "r1": r1,
                                      "lo": lo, "hi": hi, "dirty": sorted(info["rows"]),
                                      "orig_rows_b64": base64.b64encode(orig).decode()})
        # PASS 2 — PRESERVE: append every circuit to EOF (kept in binary, byte-exact, addressable)
        for c in circs:
            o, L, nm = c["off"], c["len"], c["tensor"]
            rec = MOVED + struct.pack("<QQ", o, L) + struct.pack("<I", len(nm)) + nm.encode() + c["_bytes"]
            f.seek(0, os.SEEK_END); rec_off = f.tell(); f.write(rec)
            c["_new_off"] = rec_off + len(MOVED) + 16 + 4 + len(nm)     # where the circuit's TITANCIR magic now lives
            manifest["moved"].append({"tensor": nm, "orig_off": o, "len": L, "new_off": c["_new_off"],
                                      "circuit_b64": base64.b64encode(c["_bytes"]).decode(), "hdr": c["hdr"], "rows": [c["row0"], c["row1"]]})
            print(f"  moved {nm} circuit ({L:,} B, gates={c['hdr'][2]:,}) rows {c['row0']}..{c['row1']} → EOF, magic @ {c['_new_off']:,}", flush=True)
        # PASS 3 — BACKFILL each dirty run with CLAMPED, magic-verified CLEAN weight bytes (real weights → coherent gen)
        for rgn in region_backup:
            dirty = set(rgn["dirty"])
            clean = _clean_source_rows(f, rgn["t_off"], rgn["rb"], rgn["nrows"], rgn["r0"], rgn["r1"], dirty)
            assert MAGIC not in clean and len(clean) == rgn["hi"] - rgn["lo"], "backfill produced magic/short block"
            f.seek(rgn["lo"]); f.write(clean)
        manifest["regions"] = region_backup
    # SLIGHT registry update: repoint the SDC-fleet offsets (this model's entries only) to the circuits' new addresses
    oldnew = {m["orig_off"]: m["new_off"] for m in manifest["moved"]}
    reg_edits = _update_registries(path, oldnew)
    manifest["registry_edits"] = reg_edits
    json.dump(manifest, open(side, "w"), indent=1)
    print(f"  ✓ sidecar {side} (reversible). file grew {os.path.getsize(path)-filesize:,} B (circuits appended at EOF).", flush=True)
    for e in reg_edits:
        print(f"    registry {e['registry']}: {e['field']} {e['from']:,} → {e['to']:,}", flush=True)
    print(f"  circuits are STILL in the binary (EOF PFCMOVED records), byte-exact, and the fleet now addresses their new "
          f"homes ({len(reg_edits)} offsets updated) — run --verify.", flush=True)
    return 0


def restore(path):
    side = _sidecar(path)
    if not os.path.exists(side): print("no sidecar — nothing to restore."); return 1
    man = json.load(open(side))
    with open(path, "r+b") as f:
        for rgn in man["regions"]:                                      # put every original row-region back byte-exact
            f.seek(rgn["lo"]); f.write(base64.b64decode(rgn["orig_rows_b64"]))
        f.truncate(man["orig_size"])                                    # drop the appended EOF records
    # revert the registry offset edits (new → original)
    rev = {m["new_off"]: m["orig_off"] for m in man["moved"]}
    reg_reverted = _update_registries(path, rev)
    os.remove(side)
    print(f"restored {path} byte-exact ({len(man['moved'])} circuit(s) put back, EOF records dropped, size={man['orig_size']:,}); "
          f"registries reverted ({len(reg_reverted)} offsets).")
    return 0


def verify(path):
    side = _sidecar(path)
    if not os.path.exists(side): print("no sidecar — run --move first."); return 1
    man = json.load(open(side)); f = open(path, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    ok = True
    for m in man["moved"]:
        want = base64.b64decode(m["circuit_b64"]); got = bytes(mm[m["new_off"]: m["new_off"] + len(want)])
        exact = got == want; ok &= exact
        print(f"  {m['tensor']} circuit @ EOF {m['new_off']}: byte-exact={exact} ({len(want):,} B)")
    # confirm no TITANCIR magic remains inside any active weight tensor region (only in the EOF trailer)
    left = []
    pos = mm.find(MAGIC)
    trailer_start = min((m["new_off"] for m in man["moved"]), default=os.path.getsize(path))
    while pos != -1:
        if pos < trailer_start - 100: left.append(pos)
        pos = mm.find(MAGIC, pos + 1)
    mm.close(); f.close()
    print(f"  TITANCIR magic still inside weight region: {len(left)} {'✓ none' if not left else '✗ '+str(left)}")
    print(f"  => circuits MOVED (in binary, byte-exact) and OUT of the weight path: {'YES' if ok and not left else 'NO'}")
    return 0 if ok and not left else 1


def main():
    if len(sys.argv) < 2: print(__doc__); return 2
    path = sys.argv[1]; op = sys.argv[2] if len(sys.argv) > 2 else "--scan"
    if op == "--scan":
        for c in scan(path):
            print(f"{c['tensor']:26s} off {c['off']:,} len {c['len']:,} gates {c['hdr'][2]:,} rows {c['row0']}..{c['row1']} ({c['qtype']})")
        return 0
    return {"--move": move, "--restore": restore, "--verify": verify}.get(op, lambda p: 2)(path)


if __name__ == "__main__":
    raise SystemExit(main())
