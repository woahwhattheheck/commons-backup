#!/usr/bin/env python3
"""host/sdc_programs.py — THE RACK: four impressive storage-first SDC programs, all logic as GATES (owner 07-18).

CLAUDE.md is the spine. Every program obeys the same law:
  - LOGIC IS GATES. Each circuit is composed ONLY from titan_circuit's NAND-universal primitives (xor/and_/or_/mux/add).
    No host recompute of the function at runtime — the SDC computes on power (an addressed read of the stored gates).
  - FABRICATION IS ONE-AND-DONE. fab() builds each circuit, verifies it BYTE-EXACT vs a reference, then stores it
    reversibly. The reference (zlib.crc32 / math.isqrt) is imported INSIDE fab() only — the sole allowed host
    computation (rule 6, fab-time verify). Runtime paths cannot reach it.
  - PYTHON ONLY ADDRESSES. run/attest/memoize load stored gates by offset (mmap, ~0 RAM), route the input in, settle the
    gates (the compute), and write the answer to the SAFEZONE. The host reads the safezone; nothing touches the SDC mid-run.
  - REVERSIBLE + ADDITIVE. Every circuit stored via the reversible registry; titan stays GGUF-valid; revert frees the range.
  - NO numpy. NO socket / NO network.

THE FOUR PROGRAMS
  1. prog_crc32   — COMPUTE-AS-COMPRESSION: CRC-32 of a 4-byte input. A ~KB circuit that IS the whole 2^32-entry CRC
                    table (16 GB if stored), generated on an addressed read.
  2. prog_isqrt   — EXACT SIDECAR: floor(sqrt(x)) for a 32-bit x, exact integer math, no floating point. Also a
                    2^32 -> 16-bit table the agent can call for provably-correct results.
  3. prog_attest  — SELF-ATTEST: CRC-32 over a 64-byte region of titan's OWN bytes. The file signs itself; flip one byte
                    and the signature changes -> tamper-evidence from inside the model.
  4. memoize      — COMPUTE-ONCE, FREE-FOREVER: wraps prog_isqrt with a bounded storage cache. First call computes on the
                    SDC (MISS); repeats are pure addressed reads of the cache cell (HIT, zero gates rippled).

  python host/sdc_programs.py fab                 # fabricate all four (one-and-done, byte-exact, reversible)
  python host/sdc_programs.py run crc  0xDEADBEEF # CRC-32 of the 4 bytes -> safezone
  python host/sdc_programs.py run isqrt 4000000000
  python host/sdc_programs.py attest 0 64        # sign 64 bytes of titan at offset 0 (the GGUF magic region) -> safezone
  python host/sdc_programs.py memoize 123456789  # isqrt via the cache (HIT/MISS) -> safezone
  python host/sdc_programs.py report             # headline (registry only)
  python host/sdc_programs.py revert             # remove all four (reversible; titan bytes untouched, GGUF-valid)
"""
import json, mmap, os, struct, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8")
import titan_circuit as TC

TITAN = "C:/llm/models/titan.gguf"; REG = "C:/llm/models/titan_circuits.json"
SANDBOX = "C:/llm/sdc_sandbox"; OUT = "C:/llm/sdc_out"; ANS = OUT + "/programs_result.json"
CRC_POLY = 0xEDB88320                                     # IEEE 802.3 reflected CRC-32 polynomial


# ------------------------------------------------------------------ gate helpers (composed from titan_circuit only)
def _addc(c, xs, ys, cin):
    """ripple-carry add with carry-in; returns (sum_bits, carry_out), LSB first. Pure gates."""
    out = []; carry = cin
    for i in range(len(xs)):
        axb = c.xor(xs[i], ys[i]); out.append(c.xor(axb, carry))
        carry = c.or_(c.and_(xs[i], ys[i]), c.and_(axb, carry))
    return out, carry


def _add32(c, xs, ys):
    out, _ = _addc(c, xs, ys, c.C0); return out


def _sub_ge(c, xs, ys):
    """xs - ys (unsigned, same width). Returns (diff_bits, ge) where ge=1 iff xs >= ys. Pure gates (two's complement)."""
    notys = [c.not_(y) for y in ys]
    diff, cout = _addc(c, xs, notys, c.C1)               # xs + ~ys + 1 ; carry-out == 1 iff xs >= ys
    return diff, cout


# ------------------------------------------------------------------ program circuits (LOGIC = GATES)
def build_crc32(nbytes):
    """CRC-32 (reflected) over a fixed nbytes-byte input, fully unrolled into a fixed XOR/AND network."""
    c = TC.Circuit(nbytes * 8)
    crc = c.cvec(0xFFFFFFFF, 32)                           # init register = all ones (32 wires)
    for k in range(nbytes):
        for j in range(8):                                # crc ^= byte_k  (into the low 8 bits)
            crc[j] = c.xor(crc[j], c.IN[k * 8 + j])
        for _ in range(8):                                # 8 shift-xor rounds per byte
            lsb = crc[0]; shifted = crc[1:] + [c.C0]      # crc >> 1
            crc = [c.xor(shifted[i], lsb) if (CRC_POLY >> i) & 1 else shifted[i] for i in range(32)]
    outs = [c.not_(crc[i]) for i in range(32)]            # final XOR 0xFFFFFFFF (invert)
    return c, outs


def build_isqrt():
    """floor(sqrt(x)) for a 32-bit x, exact, via the bit-by-bit method, unrolled to 16 iterations. Pure gates."""
    c = TC.Circuit(32)
    n = list(c.IN[:32]); res = c.cvec(0, 32)
    for bp in range(30, -1, -2):                          # bit = 1<<30, 1<<28, ... , 1<<0
        bit = c.cvec(1 << bp, 32)
        t = _add32(c, res, bit)                           # res + bit
        diff, ge = _sub_ge(c, n, t)                       # n - t ; ge = (n >= res+bit)
        n = [c.mux(ge, n[i], diff[i]) for i in range(32)] # ge ? (n - t) : n
        res_sh = res[1:] + [c.C0]                         # res >> 1
        res_pl = _add32(c, res_sh, bit)                   # (res >> 1) + bit
        res = [c.mux(ge, res_sh[i], res_pl[i]) for i in range(32)]   # ge ? res_pl : res_sh
    return c, res[:16]                                    # result fits in 16 bits


# ------------------------------------------------------------------ fabrication (ONE-AND-DONE, byte-exact, reversible)
def _verify_crc(nbytes, cd):
    import random, zlib                                   # reference imported INSIDE fab only (fab-time verify, rule 6)
    random.seed(7)
    for _ in range(300):
        data = bytes(random.randrange(256) for _ in range(nbytes))
        inb = [(data[k] >> j) & 1 for k in range(nbytes) for j in range(8)]
        if TC.frombits(TC.ripple(cd, inb)) != (zlib.crc32(data) & 0xFFFFFFFF): return False
    return True


def _verify_isqrt(cd):
    import random, math
    random.seed(9)
    cases = [0, 1, 2, 3, 4, 0xFFFFFFFF, 0x80000000, 65535, 65536] + [random.getrandbits(32) for _ in range(300)]
    for x in cases:
        if TC.frombits(TC.ripple(cd, [(x >> k) & 1 for k in range(32)])) != math.isqrt(x): return False
    return True


def _cd(c, outs):
    return {"n_in": c.n_in, "n_wire": c.n_wire(), "ga": c.ga, "gb": c.gb, "outs": outs}


def fab():
    reg = json.load(open(REG)) if os.path.exists(REG) else {}
    plan = []
    if "prog_crc32" not in reg:
        c, o = build_crc32(4);  plan.append(("prog_crc32", c, o, _verify_crc(4, _cd(c, o)), "CRC-32(4 bytes)"))
    if "prog_isqrt" not in reg:
        c, o = build_isqrt();   plan.append(("prog_isqrt", c, o, _verify_isqrt(_cd(c, o)), "floor(sqrt(x)) 32-bit"))
    if "prog_attest" not in reg:
        c, o = build_crc32(64); plan.append(("prog_attest", c, o, _verify_crc(64, _cd(c, o)), "CRC-32(64-byte region)"))
    if not plan:
        print("all rack programs already fabricated (one-and-done). revert first to re-bake."); return 0
    for name, c, outs, ok, label in plan:
        print(f"  {name:12s} {label:26s} gates={len(c.ga):>7,}  byte-exact vs reference: {ok}", flush=True)
        if not ok:
            print(f"  MISMATCH on {name} — not storing anything (no cheating)."); return 1
    for name, c, outs, ok, label in plan:                # only store AFTER every circuit verified (all-or-nothing)
        info = TC.store(name, c, outs)
        print(f"FABRICATED {name} @ {info['offset']}: {info['gates']:,} gates, {info['bytes']:,} bytes (reversible).", flush=True)
    with open(TITAN, "rb") as f: print(f"titan GGUF-valid: {f.read(4) == b'GGUF'}.  revert: python host/sdc_programs.py revert", flush=True)
    return 0


# ------------------------------------------------------------------ runtime (Python ONLY addresses; SDC computes)
def _power(name, inbits):
    """ADDRESS the SDC: load the stored gates by offset (mmap, ~0 RAM), settle them on the routed input (the addressed
    read = the compute). Returns the output bits. No host recompute, no network."""
    cd = TC.load(name)
    return TC.ripple(cd, inbits)


def _safezone(payload):
    os.makedirs(OUT, exist_ok=True)
    payload["network"] = "NONE"
    json.dump(payload, open(ANS, "w"), indent=1)         # SDC -> SAFEZONE (the host reads THIS, never the SDC)
    return payload


def run(prog, x):
    if prog == "crc":
        t0 = time.time(); out = TC.frombits(_power("prog_crc32", [(x >> k) & 1 for k in range(32)])); dt = time.time() - t0
        p = _safezone({"program": "prog_crc32", "kind": "compute-as-compression", "input_hex": f"0x{x & 0xFFFFFFFF:08X}",
                       "crc32": f"0x{out:08X}", "ms": round(dt * 1000, 2),
                       "note": "the 4-byte->32-bit CRC table is 2^32 entries (16 GB); this circuit generates any cell on read"})
        print(f"POWERED prog_crc32: CRC32(0x{x & 0xFFFFFFFF:08X}) = 0x{out:08X}  ({dt*1000:.1f} ms) -> safezone {ANS}")
    elif prog == "isqrt":
        t0 = time.time(); out = TC.frombits(_power("prog_isqrt", [(x >> k) & 1 for k in range(32)])); dt = time.time() - t0
        p = _safezone({"program": "prog_isqrt", "kind": "exact-sidecar", "input": x & 0xFFFFFFFF, "isqrt": out,
                       "check": f"{out}^2={out*out} <= {x & 0xFFFFFFFF} < {(out+1)}^2={(out+1)*(out+1)}", "ms": round(dt * 1000, 2)})
        print(f"POWERED prog_isqrt: isqrt({x & 0xFFFFFFFF}) = {out}  ({dt*1000:.1f} ms) -> safezone {ANS}")
    else:
        print("run: prog must be 'crc' or 'isqrt'"); return 1
    return 0


def attest(offset, nbytes=64):
    """SELF-ATTEST: read nbytes of titan's OWN bytes at `offset` (addressing, no copy beyond the routed block), route them
    into prog_attest (CRC-32 over 64 bytes), the SDC emits the signature to the safezone. Flip a byte -> signature changes."""
    if nbytes != 64:
        print("attest: prog_attest signs exactly 64 bytes"); return 1
    f = open(TITAN, "rb"); mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    region = mm[offset:offset + 64]                       # address 64 bytes of the model (bounded block routed in)
    mm.close(); f.close()
    inb = [(region[k] >> j) & 1 for k in range(64) for j in range(8)]
    t0 = time.time(); sig = TC.frombits(_power("prog_attest", inb)); dt = time.time() - t0
    _safezone({"program": "prog_attest", "kind": "self-attest", "offset": offset, "nbytes": 64,
               "region_head_hex": region[:8].hex(), "signature": f"0x{sig:08X}", "ms": round(dt * 1000, 2),
               "note": "CRC-32 of the model's own bytes at this offset; any single-byte change flips the signature"})
    print(f"POWERED prog_attest: signature of titan[{offset}:{offset+64}] = 0x{sig:08X}  ({dt*1000:.1f} ms) -> safezone {ANS}")
    return 0


def memoize(x):
    """COMPUTE-ONCE, FREE-FOREVER: a bounded direct-mapped cache in sandbox storage over prog_isqrt.
    HIT  = the answer is at its address -> a pure storage read (zero gates rippled).
    MISS = power the SDC once to compute isqrt(x), then write the cell. Host does ONLY addressing; the compute is gates."""
    os.makedirs(SANDBOX, exist_ok=True)
    cache = f"{SANDBOX}/memoize_isqrt.cache"; SLOTS = 1 << 20; EMPTY = 0xFFFFFFFF   # 2^20 cells x 8 B = 8 MB, bounded
    if not os.path.exists(cache):
        with open(cache, "wb") as fh: fh.write(b"\xff" * (SLOTS * 8))              # all-empty (key sentinel 0xFFFFFFFF)
    slot = (x & 0xFFFFFFFF) % SLOTS; pos = slot * 8
    cf = open(cache, "r+b"); cm = mmap.mmap(cf.fileno(), 0)
    key, val = struct.unpack_from("<II", cm, pos)                                  # read the cell (addressing)
    if key == (x & 0xFFFFFFFF) and key != EMPTY:
        gates = 0; hit = True                                                      # HIT: no ripple, pure storage read
    else:
        val = TC.frombits(_power("prog_isqrt", [(x >> k) & 1 for k in range(32)])) # MISS: power the SDC once
        struct.pack_into("<II", cm, pos, x & 0xFFFFFFFF, val); cm.flush()          # write the cell (addressing)
        gates = TC.load("prog_isqrt"); gates = len(gates["ga"]); hit = False
    cm.close(); cf.close()
    _safezone({"program": "memoize(prog_isqrt)", "kind": "compute-once-free-forever", "input": x & 0xFFFFFFFF,
               "isqrt": val, "result": "HIT" if hit else "MISS", "gates_rippled": gates, "slot": slot,
               "cache_bytes": SLOTS * 8, "note": "HIT is an addressed read of the cache cell — zero gates"})
    print(f"MEMOIZE isqrt({x & 0xFFFFFFFF}) = {val}  [{'HIT (0 gates)' if hit else f'MISS ({gates:,} gates)'}] -> safezone {ANS}")
    return 0


# ------------------------------------------------------------------ report / revert (registry only; reversible)
def report():
    reg = json.load(open(REG))
    rack = {"prog_crc32": (1 << 32, 4, "CRC-32 table"), "prog_isqrt": (1 << 32, 2, "isqrt table"),
            "prog_attest": (None, None, "self-attest"), "prog_mul32": (1 << 64, 8, "multiply table")}
    print("=== THE SDC PROGRAM RACK — headline (registry only, nothing touches the SDC) ===", flush=True)
    for name, (entries, wide, label) in rack.items():
        e = reg.get(name)
        if not e: print(f"  {name:12s} — not fabricated"); continue
        cb = int(e["len"])
        if entries:
            vb = entries * wide
            print(f"  {name:12s} {cb:>8,} B circuit  =  {label}: {entries:,} entries x {wide} B "
                  f"= {vb/1e9:,.0f} GB if stored  ->  {vb/cb:.2e}x compression")
        else:
            print(f"  {name:12s} {cb:>8,} B circuit  =  {label} (signs the model's own bytes)")
    with open(TITAN, "rb") as f: gg = f.read(4) == b"GGUF"
    print(f"  titan GGUF-valid: {gg} · every program: fabricated once, reversible, powered by a signal, answer in the safezone, NO network.")
    return 0


def revert():
    if not os.path.exists(REG): print("no registry."); return 0
    reg = json.load(open(REG)); removed = []
    for name in ("prog_crc32", "prog_isqrt", "prog_attest"):
        if reg.pop(name, None): removed.append(name)
    json.dump(reg, open(REG, "w"), indent=1)
    cache = f"{SANDBOX}/memoize_isqrt.cache"
    if os.path.exists(cache): os.remove(cache); removed.append("memoize cache")
    print(f"removed {removed} (registry ranges freed; titan bytes untouched, GGUF-valid).")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "fab": raise SystemExit(fab())
    if cmd == "report": raise SystemExit(report())
    if cmd == "revert": raise SystemExit(revert())
    if cmd == "run": raise SystemExit(run(sys.argv[2], int(sys.argv[3], 0)))
    if cmd == "attest": raise SystemExit(attest(int(sys.argv[2], 0), int(sys.argv[3], 0) if len(sys.argv) > 3 else 64))
    if cmd == "memoize": raise SystemExit(memoize(int(sys.argv[2], 0)))
    print("usage: fab | run crc|isqrt X | attest OFFSET 64 | memoize X | report | revert")
