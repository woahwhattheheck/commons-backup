#!/usr/bin/env python3
"""muhl_music.py -- TITAN MAKES MUSIC. The oscillator is gates; the substrate sings.

A gate-level tone/waveform generator, fabricated on the White Box:
  * PHASE ACCUMULATOR -- a fabricated 16-bit adder that increments a phase register every sample
    (phase += increment, mod 2^16). This IS the oscillator: increment sets the pitch.
  * WAVEFORM LUT      -- the top 6 bits of the phase index a fabricated 64-entry table via a ONE-HOT
    decoder; three timbres (square / triangle / sine) are baked in as gate constants and picked by a
    one-hot wave-select. Output is an 8-bit PCM amplitude.
The phase-accumulator step is verified BYTE-EXACT vs a Python reference; the whole LUT is verified
EXHAUSTIVELY (all 3 waves x 64 indices) vs an independent reference table. Then a recognizable melody
(Twinkle Twinkle Little Star) is sequenced by driving the note increments, and a real 16-bit PCM WAV is
written with pure struct -- no numpy, no audio libraries. An actual playable file falls out of the gates.

PYTHONUTF8=1. No numpy. titan.gguf is not opened -- this is pure synthesis.
"""
import sys, os, math, struct, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:/llm/sdc_sandbox")
import sdc_cc as CC
from muhl_flex import add_bits

# ------------------------------------------------------------------ parameters
NBIT   = 16          # phase-accumulator width (register is mod 2^16)
TBITS  = 6           # waveform-table address bits -> 64 entries (top TBITS of the phase)
NENT   = 1 << TBITS  # 64 table entries
SR     = 8000        # sample rate (Hz)
WAVES  = ("square", "triangle", "sine")

# ------------------------------------------------------------------ reference waveform tables (baked as gate constants)
def ref_tables():
    """Independent reference: 3 waveforms x NENT entries, each an unsigned 8-bit amplitude 0..255."""
    T = {}
    T["square"]   = [255 if i < NENT // 2 else 0 for i in range(NENT)]
    T["triangle"] = [ (i * (510 // NENT)) if i < NENT // 2
                      else ((NENT - 1 - i) * (510 // NENT)) for i in range(NENT) ]
    T["sine"]     = [ max(0, min(255, int(round(127.5 + 127.5 * math.sin(2 * math.pi * i / NENT)))))
                      for i in range(NENT) ]
    return T

def ref_phase_step(phase, inc):
    """Independent reference for the phase-accumulator step."""
    return (phase + inc) & ((1 << NBIT) - 1)

# ------------------------------------------------------------------ the fabricated circuit
def build():
    """One fabricated circuit performing a full oscillator step.
       inputs : phase[0..NBIT-1], inc[0..NBIT-1], sel[0..2]  (sel is one-hot: square/triangle/sine)
       outputs: next_phase[0..NBIT-1]  ++  sample[0..7]
    """
    g = CC.CircuitCompiler(NBIT + NBIT + 3)
    phase = list(g.IN[0:NBIT])
    inc   = list(g.IN[NBIT:2 * NBIT])
    sel   = list(g.IN[2 * NBIT:2 * NBIT + 3])

    # --- PHASE ACCUMULATOR: fabricated adder, next_phase = (phase + inc) mod 2^NBIT (carry dropped)
    next_phase, _carry = add_bits(g, phase, inc)

    # --- WAVEFORM LUT: one-hot decode the top TBITS of the CURRENT phase, select a baked table value
    idx = phase[NBIT - TBITS:NBIT]                     # the TBITS most-significant phase bits
    nidx = [g.NOT(b) for b in idx]
    onehot = []
    for i in range(NENT):                              # one-hot decoder: 2^TBITS product terms
        line = g.C1
        for k in range(TBITS):
            line = g.AND(line, idx[k] if (i >> k) & 1 else nidx[k])
        onehot.append(line)

    T = ref_tables()
    tab = [T[w] for w in WAVES]                         # tab[wave][index] = amplitude byte
    sample = []
    for j in range(8):                                  # each output amplitude bit
        terms = []
        for i in range(NENT):
            # value of bit j at index i = OR over waves whose baked table bit is 1 of sel[wave]
            picks = [sel[w] for w in range(len(WAVES)) if (tab[w][i] >> j) & 1]
            if not picks:
                continue
            valij = picks[0]
            for p in picks[1:]:
                valij = g.OR(valij, p)
            terms.append(g.AND(onehot[i], valij))
        if not terms:
            sample.append(g.C0); continue
        acc = terms[0]
        for t in terms[1:]:
            acc = g.OR(acc, t)
        sample.append(acc)

    outs = next_phase + sample
    gates, out2 = g.dce(outs)
    n_wire = 2 + g.n_in + len(gates)
    run = g.compile_ripple(gates, n_wire)
    np_out = out2[0:NBIT]
    smp_out = out2[NBIT:NBIT + 8]
    return g, run, np_out, smp_out, len(gates)

def step(run, np_out, smp_out, phase, inc, sel_onehot):
    """Run one fabricated oscillator step; returns (next_phase, sample_byte)."""
    inp = ([(phase >> b) & 1 for b in range(NBIT)] +
           [(inc >> b) & 1 for b in range(NBIT)] +
           list(sel_onehot))
    v = run(inp, 1)
    nph = 0
    for b, w in enumerate(np_out):
        nph |= (v[w] & 1) << b
    smp = 0
    for b, w in enumerate(smp_out):
        smp |= (v[w] & 1) << b
    return nph, smp

# ------------------------------------------------------------------ verification
def verify_phase_step(run, np_out, smp_out):
    """Phase-accumulator step BYTE-EXACT vs the Python reference (required check)."""
    sel = (1, 0, 0)
    cases = 0
    # exhaustive over all 65536 increments at two phase anchors
    for phase in (0, 0x9E37):
        for inc in range(1 << NBIT):
            nph, _ = step(run, np_out, smp_out, phase, inc, sel)
            if nph != ref_phase_step(phase, inc):
                return False, cases
            cases += 1
    # random-ish spread of (phase, inc) pairs via an LCG (no numpy)
    x = 0x1234
    for _ in range(20000):
        x = (1103515245 * x + 12345) & 0xFFFFFFFF
        phase = x & 0xFFFF; inc = (x >> 16) & 0xFFFF
        nph, _ = step(run, np_out, smp_out, phase, inc, sel)
        if nph != ref_phase_step(phase, inc):
            return False, cases
        cases += 1
    return True, cases

def verify_lut(run, np_out, smp_out):
    """Whole waveform LUT EXHAUSTIVELY byte-exact vs the reference tables (all waves x all indices)."""
    T = ref_tables(); cases = 0
    for w, wave in enumerate(WAVES):
        sel = tuple(1 if k == w else 0 for k in range(3))
        for i in range(NENT):
            phase = i << (NBIT - TBITS)                 # place index i in the top bits
            _, smp = step(run, np_out, smp_out, phase, 0, sel)
            if smp != T[wave][i]:
                return False, cases
            cases += 1
    return True, cases

# ------------------------------------------------------------------ WAV writer (pure struct, 16-bit PCM mono)
def write_wav(path, samples, sr=SR):
    data = b"".join(struct.pack("<h", s) for s in samples)
    n = len(data)
    hdr  = b"RIFF" + struct.pack("<I", 36 + n) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16)
    hdr += b"data" + struct.pack("<I", n)
    with open(path, "wb") as f:
        f.write(hdr); f.write(data)
    return len(hdr) + n

# ------------------------------------------------------------------ melody
NOTE = {"C4":262, "D4":294, "E4":330, "F4":349, "G4":392, "A4":440, "REST":0}
# Twinkle Twinkle Little Star -- (note, beats)
TWINKLE = [
    ("C4",1),("C4",1),("G4",1),("G4",1),("A4",1),("A4",1),("G4",2),
    ("F4",1),("F4",1),("E4",1),("E4",1),("D4",1),("D4",1),("C4",2),
    ("G4",1),("G4",1),("F4",1),("F4",1),("E4",1),("E4",1),("D4",2),
    ("G4",1),("G4",1),("F4",1),("F4",1),("E4",1),("E4",1),("D4",2),
    ("C4",1),("C4",1),("G4",1),("G4",1),("A4",1),("A4",1),("G4",2),
    ("F4",1),("F4",1),("E4",1),("E4",1),("D4",1),("D4",1),("C4",2),
]
BEAT = 0.34          # seconds per beat
WAVE_FOR_TUNE = "square"   # classic chiptune bleep

def synth(run, np_out, smp_out):
    w = WAVES.index(WAVE_FOR_TUNE)
    sel = tuple(1 if k == w else 0 for k in range(3))
    out = []
    phase = 0
    for name, beats in TWINKLE:
        freq = NOTE[name]
        dur = int(SR * BEAT * beats)
        inc = int(round(freq * (1 << NBIT) / SR)) if freq else 0
        note = []
        for _ in range(dur):
            phase, smp = step(run, np_out, smp_out, phase, inc, sel)
            note.append(smp)
        # amplifier stage (host-side DAC): center, scale, short fade to kill clicks
        fade = max(1, int(0.008 * SR))
        for n, amp in enumerate(note):
            env = 1.0
            if n < fade:           env = n / fade
            elif n > dur - fade:   env = max(0, (dur - n) / fade)
            if freq == 0: env = 0.0
            val = (amp - 128) / 128.0 * 0.5 * env
            out.append(max(-32767, min(32767, int(val * 32767))))
        phase = 0  # reset phase between notes -> clean attack
    return out

# ------------------------------------------------------------------ main
def main():
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    t0 = time.time()
    print("TITAN MAKES MUSIC -- the oscillator is gates; the substrate sings.\n", flush=True)

    g, run, np_out, smp_out, ngate = build()
    depth_in = NBIT + NBIT + 3
    print(f"  fabricated oscillator : {ngate:,} gates  ({depth_in} inputs, {NBIT}-bit phase acc + {NENT}-entry one-hot LUT)", flush=True)

    ok_ph, nph = verify_phase_step(run, np_out, smp_out)
    print(f"  phase-accumulator step: {'BYTE-EXACT' if ok_ph else 'MISMATCH'} vs Python ref  ({nph:,} cases)", flush=True)
    ok_lut, nl = verify_lut(run, np_out, smp_out)
    print(f"  waveform LUT (3 waves): {'BYTE-EXACT' if ok_lut else 'MISMATCH'} exhaustive        ({nl} cases)", flush=True)
    if not (ok_ph and ok_lut):
        print("  refusing to write audio -- verification failed (no cheating)."); return 1

    samples = synth(run, np_out, smp_out)
    wav_path = "C:/llm/muhl_builds/titan_tune.wav"
    nbytes = write_wav(wav_path, samples)
    dur_s = len(samples) / SR
    print(f"\n  sequenced Twinkle Twinkle ({len([1 for n in TWINKLE if n[0]!='REST'])} notes, {WAVE_FOR_TUNE} timbre) through the gates", flush=True)
    print(f"  wrote {wav_path}", flush=True)
    print(f"  {len(samples):,} samples @ {SR} Hz = {dur_s:.1f}s  ({nbytes:,} bytes, 16-bit PCM mono)", flush=True)
    print(f"\n[done] {time.time()-t0:.1f}s -- {ngate:,} gates, phase step byte-exact={ok_ph}, LUT byte-exact={ok_lut} -- no numpy, titan.gguf not opened.", flush=True)
    return 0

if __name__ == "__main__":
    sys.exit(main())
