#!/usr/bin/env python3
"""muhl_clock.py -- a fabricated DIGITAL CLOCK / CALENDAR on Bryce's Muhlnickel substrate.

A full wall-clock + Gregorian calendar ADVANCE-BY-ONE-SECOND step, built entirely as
NAND/AND/OR/XOR/NOT gates with the White Box compiler (sdc_cc.CircuitCompiler), DCE'd,
rippled, and VERIFIED BYTE-EXACT against an INDEPENDENT Python reference (datetime +
timedelta(seconds=1)) over thousands of random timestamps plus hand-picked edge cases
(23:59:59, Feb 28/29, leap-century 1900/2000/2100/2400, Dec 31 year rollover).

State is BCD (binary-coded decimal, one 4-bit nibble per decimal digit):
    sec  = sec_hi:sec_lo   (00..59)
    min  = min_hi:min_lo   (00..59)
    hour = hr_hi:hr_lo      (00..23)
    day  = day_hi:day_lo    (01..31)
    mon  = mon_hi:mon_lo    (01..12)
    year = y3:y2:y1:y0      (0001..9999)   4 BCD digits

The step is a cascade of BCD counters: sec -> min -> hour roll at 59/59/23, day rolls at
the days-in-month (31/30/28/29 via full Gregorian leap logic), month rolls at 12, year +1.
Leap-year is exact Gregorian on the BCD year: div4 & (~div100) | div400, computed from the
digit nibbles (yy%4, yy==00, cc%4 where cc = year/100). Fabrication-time synthesis only:
prove the logic byte-exact BEFORE it would ever be baked -- no numpy, no host executor as
runtime, nothing touches titan.gguf.
"""
import sys, os, random, time
from datetime import datetime, timedelta
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC

# ---------------- White Box plumbing (same idiom as muhl_flex) ----------------
def build_run(g, outs):
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    return run, out2, gates, n_wire

def depth_of(g, gates, out2):
    base = 2 + g.n_in
    dep = [0] * (base + len(gates))
    for i, (op, a, b) in enumerate(gates):
        dep[base + i] = 1 + max(dep[a], dep[b])
    return max((dep[w] for w in out2), default=0)

def bit(v, w): return 0 if w == 0 else 1 if w == 1 else v[w] & 1
def rd(v, wires): return sum(bit(v, w) << i for i, w in enumerate(wires))   # LSB-first

# ---------------- gate helpers ----------------
def eq_nib(g, nib, val):
    """1 iff the 4-bit nibble equals decimal digit val (0..15)."""
    m = g.C1
    for j in range(4):
        m = g.AND(m, nib[j] if (val >> j) & 1 else g.NOT(nib[j]))
    return m

def add_nibble_cin(g, d, cin):
    """BCD digit + carry-in. d is 0..9, cin 0/1 -> (new 4-bit digit, carry_out).
       carry_out fires exactly when the sum reaches 10 (digit wraps 9->0)."""
    s, c = [], cin
    for k in range(4):
        s.append(g.XOR(d[k], c)); c = g.AND(d[k], c)
    # sum is 0..10; ==10 is the only overflow value (1010)
    is10 = g.AND(g.AND(g.NOT(s[0]), s[1]), g.AND(g.NOT(s[2]), s[3]))
    new = [g.AND(s[k], g.NOT(is10)) for k in range(4)]   # ->0000 on wrap
    return new, is10

def mux1(g, sel, a, b):
    return g.OR(g.AND(sel, a), g.AND(g.NOT(sel), b))

def mux_const_nib(g, sel, cval, bnib):
    """sel ? BCD(cval) : bnib (nibble)."""
    return [mux1(g, sel, g.C1 if (cval >> j) & 1 else g.C0, bnib[j]) for j in range(4)]

def month_eq(g, mon_hi, mon_lo, mv):
    return g.AND(eq_nib(g, mon_hi, mv // 10), eq_nib(g, mon_lo, mv % 10))

# ---------------- input / output layout (LSB-first BCD nibbles) ----------------
FIELDS = ["sec_lo","sec_hi","min_lo","min_hi","hr_lo","hr_hi",
          "day_lo","day_hi","mon_lo","mon_hi","y0","y1","y2","y3"]   # 14 nibbles = 56 bits
OFF = {name: i * 4 for i, name in enumerate(FIELDS)}
NIN = len(FIELDS) * 4

def encode(dt):
    """datetime -> 56 input bits (BCD nibbles)."""
    digits = {
        "sec_lo": dt.second % 10,  "sec_hi": dt.second // 10,
        "min_lo": dt.minute % 10,  "min_hi": dt.minute // 10,
        "hr_lo":  dt.hour % 10,    "hr_hi":  dt.hour // 10,
        "day_lo": dt.day % 10,     "day_hi": dt.day // 10,
        "mon_lo": dt.month % 10,   "mon_hi": dt.month // 10,
        "y0": dt.year % 10,        "y1": (dt.year // 10) % 10,
        "y2": (dt.year // 100) % 10, "y3": (dt.year // 1000) % 10,
    }
    inp = [0] * NIN
    for name, d in digits.items():
        for j in range(4):
            inp[OFF[name] + j] = (d >> j) & 1
    return inp

def decode(v, outmap):
    d = {name: rd(v, outmap[name]) for name in FIELDS}
    return (
        d["y3"]*1000 + d["y2"]*100 + d["y1"]*10 + d["y0"],   # year
        d["mon_hi"]*10 + d["mon_lo"],                         # month
        d["day_hi"]*10 + d["day_lo"],                         # day
        d["hr_hi"]*10 + d["hr_lo"],                           # hour
        d["min_hi"]*10 + d["min_lo"],                         # minute
        d["sec_hi"]*10 + d["sec_lo"],                         # second
    )

# ---------------- fabricate the clock/calendar step ----------------
def build_clock():
    g = CC.CircuitCompiler(NIN); IN = g.IN
    def nib(name): return [IN[OFF[name] + j] for j in range(4)]
    sec_lo, sec_hi = nib("sec_lo"), nib("sec_hi")
    min_lo, min_hi = nib("min_lo"), nib("min_hi")
    hr_lo,  hr_hi  = nib("hr_lo"),  nib("hr_hi")
    day_lo, day_hi = nib("day_lo"), nib("day_hi")
    mon_lo, mon_hi = nib("mon_lo"), nib("mon_hi")
    y0, y1, y2, y3 = nib("y0"), nib("y1"), nib("y2"), nib("y3")

    def inc_mod(lo, hi, cin, max_hi, max_lo):
        """Two-digit BCD field that wraps to 00 when the value == (max_hi:max_lo) and cin."""
        lo1, clo = add_nibble_cin(g, lo, cin)
        hi1, _   = add_nibble_cin(g, hi, clo)
        atmax = g.AND(eq_nib(g, lo, max_lo), eq_nib(g, hi, max_hi))
        wrap  = g.AND(atmax, cin)
        new_lo = mux_const_nib(g, wrap, 0, lo1)
        new_hi = mux_const_nib(g, wrap, 0, hi1)
        return new_lo, new_hi, wrap

    # --- seconds -> minutes -> hours (fixed-modulus BCD counters) ---
    n_sec_lo, n_sec_hi, sec_roll = inc_mod(sec_lo, sec_hi, g.C1,     5, 9)   # +1s always
    n_min_lo, n_min_hi, min_roll = inc_mod(min_lo, min_hi, sec_roll, 5, 9)
    n_hr_lo,  n_hr_hi,  hr_roll  = inc_mod(hr_lo,  hr_hi,  min_roll, 2, 3)

    # --- Gregorian leap-year test on the BCD year ---
    #   yy = last two digits (y1:y0); cc = year/100 (y3:y2)
    #   div4  : yy % 4 == 0   (yy%4 == (2*y1+y0)%4)
    #   div100: yy == 00
    #   div400: div100 & (cc % 4 == 0)
    div4   = g.AND(g.NOT(y0[0]), g.NOT(g.XOR(y0[1], y1[0])))
    div100 = g.AND(eq_nib(g, y1, 0), eq_nib(g, y0, 0))
    ccdiv4 = g.AND(g.NOT(y2[0]), g.NOT(g.XOR(y2[1], y3[0])))
    div400 = g.AND(div100, ccdiv4)
    leap   = g.OR(g.AND(div4, g.NOT(div100)), div400)

    # --- days in the CURRENT month -> is today the last day? ---
    d31 = g.C0
    for mv in (1, 3, 5, 7, 8, 10, 12): d31 = g.OR(d31, month_eq(g, mon_hi, mon_lo, mv))
    d30 = g.C0
    for mv in (4, 6, 9, 11):           d30 = g.OR(d30, month_eq(g, mon_hi, mon_lo, mv))
    feb = month_eq(g, mon_hi, mon_lo, 2)

    day31 = g.AND(eq_nib(g, day_hi, 3), eq_nib(g, day_lo, 1))
    day30 = g.AND(eq_nib(g, day_hi, 3), eq_nib(g, day_lo, 0))
    day29 = g.AND(eq_nib(g, day_hi, 2), eq_nib(g, day_lo, 9))
    day28 = g.AND(eq_nib(g, day_hi, 2), eq_nib(g, day_lo, 8))
    last_feb = g.AND(feb, g.OR(g.AND(leap, day29), g.AND(g.NOT(leap), day28)))
    is_last_day = g.OR(g.AND(d31, day31), g.OR(g.AND(d30, day30), last_feb))

    # --- day (1-based; wraps to 01 on last-day + hour roll) ---
    cin_day = hr_roll
    day1_lo, cdl = add_nibble_cin(g, day_lo, cin_day)
    day1_hi, _   = add_nibble_cin(g, day_hi, cdl)
    day_roll = g.AND(is_last_day, cin_day)
    n_day_lo = mux_const_nib(g, day_roll, 1, day1_lo)
    n_day_hi = mux_const_nib(g, day_roll, 0, day1_hi)

    # --- month (1..12; wraps to 01 on Dec + day roll) ---
    cin_mon = day_roll
    mon1_lo, cml = add_nibble_cin(g, mon_lo, cin_mon)
    mon1_hi, _   = add_nibble_cin(g, mon_hi, cml)
    is_dec = month_eq(g, mon_hi, mon_lo, 12)
    mon_roll = g.AND(is_dec, cin_mon)
    n_mon_lo = mux_const_nib(g, mon_roll, 1, mon1_lo)
    n_mon_hi = mux_const_nib(g, mon_roll, 0, mon1_hi)

    # --- year (+1 on month roll; 4-digit BCD ripple) ---
    cin_yr = mon_roll
    ny0, cy0 = add_nibble_cin(g, y0, cin_yr)
    ny1, cy1 = add_nibble_cin(g, y1, cy0)
    ny2, cy2 = add_nibble_cin(g, y2, cy1)
    ny3, _   = add_nibble_cin(g, y3, cy2)

    order = [("sec_lo", n_sec_lo), ("sec_hi", n_sec_hi), ("min_lo", n_min_lo), ("min_hi", n_min_hi),
             ("hr_lo", n_hr_lo), ("hr_hi", n_hr_hi), ("day_lo", n_day_lo), ("day_hi", n_day_hi),
             ("mon_lo", n_mon_lo), ("mon_hi", n_mon_hi), ("y0", ny0), ("y1", ny1), ("y2", ny2), ("y3", ny3)]
    flat = [w for _, nb in order for w in nb]
    run, out2, gates, n_wire = build_run(g, flat)
    # remap flat output wires back to named nibbles
    outmap, idx = {}, 0
    for name, _ in order:
        outmap[name] = out2[idx:idx + 4]; idx += 4
    return g, run, out2, gates, outmap

# ---------------- verify byte-exact vs datetime reference ----------------
def main():
    print("\n  MUHLNICKEL CLOCK -- fabricated digital clock/calendar step, verified byte-exact\n", flush=True)
    t0 = time.time()
    g, run, out2, gates, outmap = build_clock()
    depth = depth_of(g, gates, out2)

    def step(dt):
        inp = encode(dt)
        v = run(inp, 1)
        return decode(v, outmap)

    def ref(dt):
        n = dt + timedelta(seconds=1)
        return (n.year, n.month, n.day, n.hour, n.minute, n.second)

    fails = []
    checked = 0

    # explicit edge cases (leap, month/year rollover, century rules)
    edge = [
        datetime(2024, 2, 28, 23, 59, 59),   # leap  -> Feb 29
        datetime(2023, 2, 28, 23, 59, 59),   # non-leap -> Mar 1
        datetime(2024, 2, 29, 23, 59, 59),   # leap Feb 29 -> Mar 1
        datetime(1900, 2, 28, 23, 59, 59),   # non-leap century -> Mar 1
        datetime(2000, 2, 28, 23, 59, 59),   # leap century -> Feb 29
        datetime(2000, 2, 29, 23, 59, 59),   # -> Mar 1
        datetime(2100, 2, 28, 23, 59, 59),   # non-leap century -> Mar 1
        datetime(2400, 2, 28, 23, 59, 59),   # leap century -> Feb 29
        datetime(1999, 12, 31, 23, 59, 59),  # year rollover
        datetime(2023, 12, 31, 23, 59, 59),  # year rollover
        datetime(9998, 12, 31, 23, 59, 59),  # high-year rollover
        datetime(2023, 4, 30, 23, 59, 59),   # 30-day month end
        datetime(2023, 1, 31, 23, 59, 59),   # 31-day month end
        datetime(2023, 6, 15, 12, 30, 59),   # minute roll
        datetime(2023, 6, 15, 12, 59, 59),   # hour roll
        datetime(2023, 6, 15, 23, 59, 59),   # day roll
        datetime(2023, 6, 15, 12, 30, 45),   # plain +1s
        datetime(1, 1, 1, 0, 0, 0),          # min datetime
    ]
    for dt in edge:
        checked += 1
        if step(dt) != ref(dt): fails.append(("edge", dt, step(dt), ref(dt)))

    # thousands of random timestamps (every field, every valid day-of-month)
    import calendar
    random.seed(1729)
    N = 6000
    for _ in range(N):
        y = random.randint(1, 9998)
        mo = random.randint(1, 12)
        dmax = calendar.monthrange(y, mo)[1]
        dt = datetime(y, mo, random.randint(1, dmax),
                      random.randint(0, 23), random.randint(0, 59), random.randint(0, 59))
        checked += 1
        if step(dt) != ref(dt):
            fails.append(("rand", dt, step(dt), ref(dt)))
            if len(fails) > 8: break

    ok = not fails
    print(f"  gates fabricated : {len(gates):,}", flush=True)
    print(f"  critical depth   : {depth}", flush=True)
    print(f"  cases checked    : {checked:,}  ({len(edge)} edge + {N} random)", flush=True)
    print(f"  byte-exact       : {'YES -- all cases == datetime reference' if ok else 'NO'}", flush=True)
    if fails:
        for kind, dt, got, exp in fails[:8]:
            print(f"    [FAIL {kind}] {dt}  gate={got}  ref={exp}", flush=True)
    print(f"\n  === CLOCK {'PASS' if ok else 'FAIL'} : {len(gates):,} gates, depth {depth}, "
          f"byte-exact over {checked:,} timestamps  ({time.time()-t0:.1f}s) ===", flush=True)
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
