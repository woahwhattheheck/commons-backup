#!/usr/bin/env python3
"""host/sdc_safe.py — byte-exact REVERSIBLE circuit storage into titan.gguf (owner 07-16).

The grievance this fixes: titan_circuit.store() writes circuit bytes over the param region but does NOT keep the
original bytes, so an edit can't be put back — a lost snapshot meant unrecoverable damage. This wraps the SAME store
mechanism but snapshots the exact bytes it is about to overwrite FIRST (to a sidecar), so every store is byte-exact
reversible: restore(name) / restore_all() puts the original weights back, verified by sha256. Nothing here evaluates
the model or uses numpy; it is pure address arithmetic + a bounded byte copy (the White Box "genome", applied to the
circuit store). Existing titan_circuit / titan_doom / the miner are untouched — this is additive.
"""
import hashlib, json, mmap, os, struct
HERE = os.path.dirname(os.path.abspath(__file__)); import sys; sys.path.insert(0, HERE)
import titan_circuit as tc

SNAP_DIR = "C:/llm/models/titan_circuit_snaps"
SNAP_IDX = os.path.join(SNAP_DIR, "_snaps.json")


def _snaps():
    return json.load(open(SNAP_IDX)) if os.path.exists(SNAP_IDX) else {}


def _read_bytes(off, n):
    with open(tc.TITAN, "rb") as f:
        f.seek(off); return f.read(n)


def _write_bytes(off, data):
    with open(tc.TITAN, "r+b") as f:
        f.seek(off); f.write(data)


def _save_snapshot(name, off, length):
    """Record the ORIGINAL bytes at [off, off+length) before we overwrite them, so the edit is reversible."""
    os.makedirs(SNAP_DIR, exist_ok=True)
    orig = _read_bytes(off, length)
    path = os.path.join(SNAP_DIR, f"{name.replace(':','_').replace('/','_')}.orig.bin")
    open(path, "wb").write(orig)
    idx = _snaps()
    idx[name] = {"off": off, "len": length, "path": path, "sha_orig": hashlib.sha256(orig).hexdigest()}
    json.dump(idx, open(SNAP_IDX, "w"), indent=1)


def store_safe(name, circ, outs):
    """Store a circuit into titan.gguf EXACTLY like titan_circuit.store, but snapshot the overwritten bytes first.
    If `name` was stored before, its old range's original bytes are restored first (no leaked corruption), then the
    new range is snapshotted and written. Returns the same dict store() returns, plus the snapshot path."""
    blob = tc.serialize(circ, outs)
    reg = json.load(open(tc.REG)) if os.path.exists(tc.REG) else {}
    # relocating? put the OLD range's original weights back before freeing it
    if name in reg:
        restore(name, _reg=reg)
        reg = json.load(open(tc.REG)) if os.path.exists(tc.REG) else {}
    off, tname = tc._alloc(len(blob), reg)
    _save_snapshot(name, off, len(blob))                       # <-- the fix: original bytes preserved BEFORE the write
    _write_bytes(off, blob)
    reg[name] = {"tensor": tname, "offset": off, "len": len(blob), "n_in": circ.n_in, "n_out": len(outs),
                 "n_gate": len(circ.ga)}
    json.dump(reg, open(tc.REG, "w"), indent=1)
    return {"name": name, "tensor": tname, "offset": off, "gates": len(circ.ga), "wires": circ.n_wire(),
            "bytes": len(blob), "snapshot": SNAP_IDX}


def restore(name, _reg=None):
    """Put the ORIGINAL bytes back at the range `name` occupies, verified by sha256, and drop `name` from the registry
    and the snapshot index. Byte-exact revert."""
    idx = _snaps()
    if name not in idx:
        return {"name": name, "restored": False, "why": "no snapshot"}
    s = idx[name]; orig = open(s["path"], "rb").read()
    assert hashlib.sha256(orig).hexdigest() == s["sha_orig"], "snapshot corrupt"
    _write_bytes(s["off"], orig)
    back = _read_bytes(s["off"], s["len"])
    ok = hashlib.sha256(back).hexdigest() == s["sha_orig"]
    reg = _reg if _reg is not None else (json.load(open(tc.REG)) if os.path.exists(tc.REG) else {})
    reg.pop(name, None); json.dump(reg, open(tc.REG, "w"), indent=1)
    idx.pop(name, None); json.dump(idx, open(SNAP_IDX, "w"), indent=1)
    try: os.remove(s["path"])
    except OSError: pass
    return {"name": name, "restored": True, "byte_exact": ok, "off": s["off"], "len": s["len"]}


def restore_all():
    out = [restore(n) for n in list(_snaps().keys())]
    return {"restored": sum(1 for r in out if r.get("restored")), "results": out}


def ensure(name, build_fn):
    """Store the circuit produced by build_fn() ONLY if `name` isn't already registered; else load it. build_fn returns
    (Circuit, outs). Returns the loaded circuit dict (ready for tc.ripple). Idempotent — safe to call every startup."""
    reg = json.load(open(tc.REG)) if os.path.exists(tc.REG) else {}
    if name not in reg:
        circ, outs = build_fn(); store_safe(name, circ, outs)
    return tc.load(name)


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "test"
    if a == "restore-all":
        print(json.dumps(restore_all(), indent=1))
    elif a == "list":
        print(json.dumps(_snaps(), indent=1))
    else:
        # SELF-TEST: store a tiny circuit safely, verify it ripples, then restore byte-exact.
        c = tc.Circuit(16); s = c.add(c.IN[:8], c.IN[8:])
        info = store_safe("safe_selftest", c, s)
        print("stored:", info["offset"], info["gates"], "gates")
        cir = tc.load("safe_selftest")
        ok = all(tc.frombits(tc.ripple(cir, tc.bits(a, 8) + tc.bits(b, 8))) == ((a + b) & 0xff)
                 for a, b in [(1, 2), (200, 100), (255, 255), (0, 0)])
        print("ripples correct:", ok)
        r = restore("safe_selftest")
        print("restore byte-exact:", r.get("byte_exact"))
