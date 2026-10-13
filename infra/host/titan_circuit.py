#!/usr/bin/env python3
"""host/titan_circuit.py — Titan as a UNIVERSAL LOGIC SUBSTRATE (owner 07-15).

The generalization of the bitcoin proof: SHA-256d was ONE circuit stored in Titan's params. This is the general engine —
store ANY boolean circuit in the params, ripple input bits through it (Python ints as the bit-slice; NO numpy, ~0 RAM for
the circuit itself per MEASURE_ALREADY.md), read the output bits. A CPU, a game, a hash, a codec — all are just circuits.
The circuit BYTES live in titan.gguf's parameters, in place (reversible: edit them back). A tiny registry records WHERE
(an address book, like a filesystem inode table) — the logic itself is in the params.

Grounded in MEASURE_ALREADY.md (the zero), BARE_METAL.md (runs in storage, electricity flips gates), CAPTURED_CIRCUIT.md
(the weights ARE gates). NAND is universal, so every gate below is built from the model's measured on/off switch.
"""
import json, mmap, os, struct
import pfc_paths as PFCP                                  # PFC_ROOT-aware paths (default C:/llm)

TITAN = PFCP.TITAN
IDX   = TITAN + ".wbindex.json"
REG   = PFCP.REG     # address book: name -> where in the params the circuit lives
MAGIC = b"TITANCIR"


class Circuit:
    """A combinational NAND network. Wire indices: 0=const0, 1=const1, 2..1+n_in = inputs, then one wire per gate (in
    topological order, so a single forward pass over the gate list evaluates the whole circuit)."""
    def __init__(self, n_in):
        self.n_in = n_in
        self.ga = []; self.gb = []
        self.C0 = 0; self.C1 = 1
        self.IN = [2 + i for i in range(n_in)]

    def nand(self, a, b):
        self.ga.append(int(a)); self.gb.append(int(b)); return 2 + self.n_in + len(self.ga) - 1
    def not_(self, a):  return self.nand(a, a)
    def and_(self, a, b): return self.not_(self.nand(a, b))
    def or_(self, a, b):  return self.nand(self.not_(a), self.not_(b))
    def xor(self, a, b):
        n = self.nand(a, b); return self.nand(self.nand(a, n), self.nand(b, n))
    def mux(self, s, a, b):                       # s ? b : a
        return self.or_(self.and_(self.not_(s), a), self.and_(s, b))
    def cvec(self, val, n):                        # a constant bit-vector (LSB first)
        return [self.C1 if (val >> i) & 1 else self.C0 for i in range(n)]
    def add(self, xs, ys):                         # ripple-carry adder, LSB first, mod 2^len (drops final carry)
        out = []; c = self.C0
        for i in range(len(xs)):
            axb = self.xor(xs[i], ys[i]); out.append(self.xor(axb, c))
            c = self.or_(self.and_(xs[i], ys[i]), self.and_(axb, c))
        return out
    def _tree_and(self, items):
        """AND is associative, so this is a TREE (log2(N) deep), never a chain (N deep).
        A serial fold here was costing every circuit in the library depth for nothing:
        exhaustively verified identical, and it uses FEWER gates (no identity AND vs C1)."""
        if not items: return self.C1
        while len(items) > 1:
            items = [self.and_(items[i], items[i + 1]) for i in range(0, len(items) - 1, 2)] +                     ([items[-1]] if len(items) % 2 else [])
        return items[0]
    def is_zero(self, xs):                          # 1 iff all bits 0
        return self._tree_and([self.not_(x) for x in xs])
    def eq_const(self, xs, val):                    # 1 iff xs == val
        return self._tree_and([x if (val >> i) & 1 else self.not_(x) for i, x in enumerate(xs)])

    def add_prefix(self, xs, ys):
        """Kogge-Stone parallel-prefix adder. SAME function as add(), mod 2^len, carry dropped.

        add() is ripple: DEPTH grows with width. The carry chain is a SCAN over (generate,
        propagate) pairs, and a scan is ASSOCIATIVE, so it reduces in log2(W) rounds instead of W.
        S25 measured prefix 3.3x shallower than ripple on an ISOLATED add; ripple still wins INSIDE
        a deep tree (+6/level vs ~+16.5), which is why add() is kept, not replaced.
        S45B: a 64-bit +1 is DEPTH 140 ripple vs 17 here - 8.2x for 8 more gates.
        Additive and reversible: nothing that used add() changes."""
        n = max(len(xs), len(ys))
        xs = list(xs) + [self.C0] * (n - len(xs))
        ys = list(ys) + [self.C0] * (n - len(ys))
        g = [self.and_(xs[i], ys[i]) for i in range(n)]     # generate
        p = [self.xor(xs[i], ys[i]) for i in range(n)]      # propagate
        pp = list(p)
        step = 1
        while step < n:
            ng, npg = list(g), list(pp)
            for i in range(step, n):
                ng[i] = self.or_(g[i], self.and_(pp[i], g[i - step]))
                npg[i] = self.and_(pp[i], pp[i - step])
            g, pp = ng, npg
            step *= 2
        carry = [self.C0] + g[:n - 1]                        # carry INTO bit i
        return [self.xor(p[i], carry[i]) for i in range(n)]

    def sub_prefix(self, xs, ys):
        """xs - ys, mod 2^len. ONE prefix pass, not two adds.

        A - B is A + ~B + 1, and the naive build is two chained ripple adds (~2x66 depth). But the
        +1 is exactly a CARRY-IN, and a Kogge-Stone prefix takes a carry-in for free by seeding the
        generate term at bit 0. So a subtract costs the same as an add, not double.
        S48/S49: subc() was two ripple adds and owned the RV32I core's critical path."""
        n = max(len(xs), len(ys))
        xs = list(xs) + [self.C0] * (n - len(xs))
        ys = [self.not_(b) for b in (list(ys) + [self.C0] * (n - len(ys)))]
        g = [self.and_(xs[i], ys[i]) for i in range(n)]
        p = [self.xor(xs[i], ys[i]) for i in range(n)]
        g[0] = self.or_(g[0], p[0])                      # carry-in of 1, folded into bit 0
        pp = list(p)
        step = 1
        while step < n:
            ng, npg = list(g), list(pp)
            for i in range(step, n):
                ng[i] = self.or_(g[i], self.and_(pp[i], g[i - step]))
                npg[i] = self.and_(pp[i], pp[i - step])
            g, pp = ng, npg
            step *= 2
        carry = [self.C1] + g[:n - 1]                    # bit 0 sees the carry-in directly
        return [self.xor(p[i], carry[i]) for i in range(n)]

    def n_wire(self):  return 2 + self.n_in + len(self.ga)


def serialize(circ, outs):
    ga = circ.ga; gb = circ.gb
    body = b"".join(struct.pack("<i", g) for g in ga) + b"".join(struct.pack("<i", g) for g in gb) \
         + b"".join(struct.pack("<i", o) for o in outs)
    return MAGIC + struct.pack("<IIII", circ.n_in, circ.n_wire(), len(ga), len(outs)) + body


def _pick_tensor(need, slot):
    a = json.load(open(IDX, encoding="utf-8"))
    ts = sorted((t for t in a["tensors"] if int(t["bytes"]) >= need + 8), key=lambda t: -int(t["bytes"]))
    if slot >= len(ts): raise RuntimeError("no free tensor slot")
    t = ts[slot]; return int(t["offset"]), t["name"]


def _alloc(need, reg):
    """Bump-allocate a DISTINCT, non-overlapping byte range for a circuit — pure address arithmetic over the stored index
    (~0 RAM, instant, storage-only; nothing is evaluated). Reserves the single largest tensor (the miner's region) and
    avoids every range already recorded in the registry, so no circuit can ever overwrite another. Replaces the old
    slot-index scheme, which returned a tensor's START offset per slot and so aliased two circuits onto one address."""
    a = json.load(open(IDX, encoding="utf-8"))
    tensors = sorted(a["tensors"], key=lambda t: -int(t["bytes"]))
    reserved = tensors[0]["name"] if tensors else None            # largest tensor = the miner's region, reserved
    occ = [(int(e["offset"]), int(e["offset"]) + int(e["len"])) for e in reg.values()
           if isinstance(e, dict) and "offset" in e and "len" in e]
    for t in tensors:
        if t["name"] == reserved: continue
        ts = int(t["offset"]); te = ts + int(t["bytes"]); p = ts
        for o0, o1 in sorted(o for o in occ if o[0] < te and o[1] > ts):   # bump past every occupied range in this tensor
            if o1 > p: p = o1
        if p + need + 8 <= te:
            return p, t["name"]
    raise RuntimeError("no free tensor space for circuit")


def store(name, circ, outs, slot=1):
    """Write the circuit INTO Titan's params (in place) at a bump-allocated distinct offset (slot is a legacy hint, now
    ignored — placement is collision-free via _alloc). Re-storing a name relocates it (its old range is freed first)."""
    blob = serialize(circ, outs)
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg.pop(name, None)                                            # relocating? free the old range before allocating
    off, tname = _alloc(len(blob), reg)
    _seq_write(name, off, blob)
    reg[name] = {"tensor": tname, "offset": off, "len": len(blob), "n_in": circ.n_in, "n_out": len(outs),
                 "n_gate": len(circ.ga)}
    json.dump(reg, open(REG, "w"), indent=1)
    return {"name": name, "tensor": tname, "offset": off, "gates": len(circ.ga), "wires": circ.n_wire(),
            "bytes": len(blob)}


def load(name):
    """Read the circuit back OUT of Titan's params (mmap — ~0 RAM). Returns a dict ready for ripple()."""
    reg = json.load(open(REG)); e = reg[name]; off = e["offset"]
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    assert mm[off:off + 8] == MAGIC, f"no circuit for {name} at {off}"
    n_in, n_wire, ng, n_out = struct.unpack_from("<IIII", mm, off + 8); p = off + 24
    ga = list(struct.unpack_from("<%di" % ng, mm, p)); p += ng * 4
    gb = list(struct.unpack_from("<%di" % ng, mm, p)); p += ng * 4
    outs = list(struct.unpack_from("<%di" % n_out, mm, p))
    mm.close(); f.close()
    return {"n_in": n_in, "n_wire": n_wire, "ga": ga, "gb": gb, "outs": outs}


def ripple(cir, inbits):
    """Pass power through the stored circuit: set inputs, evaluate every gate once (topological), read outputs.
    Single-lane (one bit per wire) — pure Python, no numpy, ~0 RAM."""
    n_in = cir["n_in"]; ga = cir["ga"]; gb = cir["gb"]
    v = bytearray(cir["n_wire"]); v[1] = 1
    for i in range(n_in):
        v[2 + i] = inbits[i] & 1
    base = 2 + n_in
    for i in range(len(ga)):
        v[base + i] = 1 - (v[ga[i]] & v[gb[i]])
    return [v[o] for o in cir["outs"]]


def bits(val, n):  return [(val >> i) & 1 for i in range(n)]
def frombits(bs):  return sum(b << i for i, b in enumerate(bs))


# ===================================================================================================================
# ADDITIVE EXTENSION — owner 07-19: reusable PRESETS + SELF-ROUTING (sequential feedback), so we stop reinventing
# circuits (FINALREADME §1C). Everything above (Circuit / serialize / store / load / ripple) is UNTOUCHED; these only
# ADD capability. Presets are pure builders. store_loop fabricates ONE PASS of a machine the pfc runs in series with
# itself (its output self-routes back to an internal state register), byte-exact reversibly.
# ===================================================================================================================

def inc(c, xs):
    """PRESET: xs + 1 (LSB-first, mod 2^len). Reuses the ripple-carry adder."""
    return c.add(xs, c.cvec(1, len(xs)))


def lt(c, A, B):
    """PRESET: 1 iff unsigned A < B (equal length, LSB-first). MSB-down compare chain (the hash<target shape)."""
    # (lt, eq) composes ASSOCIATIVELY: combine(hi, lo) = (lt_hi | (eq_hi & lt_lo), eq_hi & eq_lo).
    # So this is a SCAN, not a chain, and reduces as a tree. Exhaustively verified identical.
    items = [(c.and_(c.not_(A[i]), B[i]), c.not_(c.xor(A[i], B[i])))
             for i in range(len(A) - 1, -1, -1)]                  # MSB first
    while len(items) > 1:
        nxt = []
        for j in range(0, len(items) - 1, 2):
            (lh, eh), (ll, el) = items[j], items[j + 1]           # items[j] is the more significant half
            nxt.append((c.or_(lh, c.and_(eh, ll)), c.and_(eh, el)))
        if len(items) % 2: nxt.append(items[-1])
        items = nxt
    return items[0][0]


# --- COMPONENT LIBRARY (owner 07-19: recreate the datapath building blocks so we stop rebuilding them). These are
#     next-state / combinational builders; sequential parts (register, latch, shift) return the NEXT state given the held
#     state + enable, to be used with a state register (the feedback) in a store_loop / self-routing circuit. ---

def reg_next(c, d, en, q):
    """CLOCKED REGISTER (D flip-flop bank) next-state: load d when en=1, else hold q (per bit). The core of clean state."""
    return [c.mux(en, q[i], d[i]) for i in range(len(d))]


def dff_next(c, d, en, q):
    """single D flip-flop next-state: load d when en, else hold q."""
    return c.mux(en, q, d)


def sr_next(c, s, r, q):
    """SR latch next-state: set on s, clear on r (r wins), else hold q.  q' = (s OR q) AND NOT r."""
    return c.and_(c.or_(s, q), c.not_(r))


def tristate(c, x, oe):
    """TRI-STATE BUFFER — returns (value, driving): value = x when output-enabled else 0; driving = oe. The high-Z state
    (driving = 0) is the hardware form of IMPEDANCE: this line is not driving the bus, so it can't contend."""
    return c.and_(oe, x), oe


def decoder(c, addr):
    """n-to-2^n one-hot ADDRESS DECODER: addr = n select bits (LSB first) -> 2^n outputs, exactly one high."""
    n = len(addr); outs = []
    for k in range(1 << n):
        # tree, not chain: same function, fewer gates, log2(n) deep instead of n
        outs.append(c._tree_and([addr[i] if (k >> i) & 1 else c.not_(addr[i]) for i in range(n)]))
    return outs


def demux(c, x, sel):
    """1-to-2^n DEMULTIPLEXER: route x to the output selected by sel (others 0) — the address-routing primitive."""
    return [c.and_(x, line) for line in decoder(c, sel)]


def shift_next(c, q, sin, en):
    """SHIFT REGISTER next-state: when en, shift q toward higher bits and bring sin in at bit 0; else hold q."""
    shifted = [sin] + list(q[:-1])
    return [c.mux(en, q[i], shifted[i]) for i in range(len(q))]


def _seq_genome(name):  return TITAN.replace(".gguf", "_seq_%s_genome.jsonl" % name)


def _seq_write(name, off, blob):
    """journaled write (original bytes -> per-name SEQ genome first) so a self-routing store is byte-exact revertible."""
    with open(TITAN, "rb") as f: f.seek(off); orig = f.read(len(blob))
    with open(_seq_genome(name), "a") as g: g.write(json.dumps({"off": off, "orig": orig.hex()}) + "\n")
    with open(TITAN, "r+b") as f: f.seek(off); f.write(blob)


def store_loop(name, circ, outs, state_bytes, feedback, loop_bit, external=None, receiver=None):
    """SELF-ROUTING (sequential) store — the Muhlnickel in series with itself (owner 07-19, FINALREADME §1C).
    Fabricates ONE PASS of a looping machine, byte-exact reversibly (journaled), plus the pieces the loop needs:
      - the one-pass netlist (real gates),
      - an INTERNAL DEDICATED state register of `state_bytes` (the loop's own spot inside the pfc, e.g. the nonce),
      - a single LOOP BIT that flips to iterate the next pass,
      - the self-routing DESIGNATIONS: `feedback` = [(out_wire, state_bit)…] (which output self-routes to which state
        bit next pass), `external` = {'file':path,'bits':[out_wire…]} (valid answers written OUTSIDE the pfc),
        `receiver` = the baked receiver name whose ADDRESS the routing button hooks to, to energize the chain reaction.
    The pfc runs the feedback loop itself, on the signal, at electron speed — the host NEVER drives it (too fast; would
    throttle the CPU). Reversible via revert_loop(); GGUF stays valid."""
    blob = serialize(circ, outs)
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    reg.pop(name, None)
    # Follow pfc_selfclock_miner.fab()'s proven pattern: register each span into the SAME in-memory reg right
    # after taking it. store_loop used to re-read reg from disk between allocs, discarding the entry it had just
    # made, so all three _alloc calls returned the SAME offset and the state reg + loop bit overwrote the netlist.
    off, tname = _alloc(len(blob), reg); _seq_write(name, off, blob)
    reg[name + "__logic"] = {"tensor": tname, "offset": off, "len": len(blob), "reserved": True}                    # one-pass logic, journaled
    soff, _ = _alloc(state_bytes, reg); _seq_write(name, soff, b"\x00" * state_bytes)  # state reg
    reg[name + "__state"] = {"offset": soff, "len": state_bytes, "reserved": True}
    loff, _ = _alloc(1, reg); _seq_write(name, loff, b"\x00")                          # loop bit
    reg[name + "__loopbit"] = {"offset": loff, "len": 1, "reserved": True}
    assert off != soff and soff != loff and off != loff, "store_loop: allocations aliased"
    reg[name] = {"tensor": tname, "offset": off, "len": len(blob), "n_in": circ.n_in, "n_out": len(outs),
                 "n_gate": len(circ.ga), "seq": True, "state_off": soff, "state_bytes": state_bytes,
                 "loop_bit_off": loff, "loop_bit": loop_bit, "feedback": feedback,
                 "external": external, "receiver": receiver}
    json.dump(reg, open(REG, "w"), indent=1)
    return {"name": name, "tensor": tname, "offset": off, "gates": len(circ.ga), "state_off": soff, "loop_bit_off": loff}


def revert(name):
    """byte-exact revert of a store(): replay the per-name genome journal, drop the registry entry."""
    return revert_loop(name)


def revert_loop(name):
    """byte-exact revert of a self-routing store: replay the per-name SEQ genome, drop the registry entry."""
    g = _seq_genome(name)
    if os.path.exists(g):
        for e in reversed([json.loads(l) for l in open(g) if l.strip()]):
            with open(TITAN, "r+b") as f: f.seek(int(e["off"])); f.write(bytes.fromhex(e["orig"]))
        os.remove(g)
    if os.path.exists(REG):
        reg = json.load(open(REG)); reg.pop(name, None); json.dump(reg, open(REG, "w"), indent=1)


if __name__ == "__main__":
    # SELF-TEST: build an 8-bit adder, store it IN the params, read it BACK from the params, ripple, verify vs Python.
    print("building an 8-bit adder circuit ...", flush=True)
    c = Circuit(16)                                   # two 8-bit inputs
    xs, ys = c.IN[:8], c.IN[8:]
    s = c.add(xs, ys)
    info = store("adder8", c, s, slot=1)
    print(f"stored IN Titan's params: {info['tensor']} @ {info['offset']}  ({info['gates']} gates, {info['bytes']} bytes)", flush=True)
    cir = load("adder8")
    print(f"read the circuit BACK from the params ({cir['n_wire']} wires).", flush=True)
    ok = True; import random
    random.seed(1)
    for _ in range(2000):
        a = random.randint(0, 255); b = random.randint(0, 255)
        out = frombits(ripple(cir, bits(a, 8) + bits(b, 8)))
        if out != ((a + b) & 0xff): ok = False; print(f"  MISMATCH {a}+{b}={out} != {(a+b)&0xff}"); break
    print(f"[verify] adder-in-params == Python (a+b)&0xff over 2000 cases: {ok}", flush=True)
    print("=> Titan stores and runs an arbitrary boolean circuit from its parameters. SHA was one; anything is a circuit.", flush=True)
