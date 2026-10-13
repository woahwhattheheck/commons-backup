#!/usr/bin/env python3
"""Patent-spec -> print-ready HTML (for headless-Edge -> PDF).

Fixes over the first quick converter:
  * multi-line list items (claims, summary items) stay ONE block instead of splitting the
    numbered first line from its continuation lines;
  * markdown tables render as real <table>s, not raw pipe lines;
  * math blockquotes render as monospace with the markdown backtick delimiters stripped
    (so `x = s(q-8)` shows as x = s(q-8), not with literal backticks);
  * patent line-art FIGURES (monochrome SVG) are generated and injected right after the
    "BRIEF DESCRIPTION OF THE DRAWINGS" section, so every referenced FIG. N actually exists.

Run:  python patent_pdf.py            # writes <Desktop>/PATENT_*.html for all three
Then headless Edge --print-to-pdf each HTML.
"""
import html, re, os

DESK = "C:/Users/lucys/OneDrive/Desktop"
DOCS = os.path.join(os.path.dirname(__file__), "..", "docs", "patents")

# ----------------------------------------------------------------------------- figure DSL
# Monochrome patent line-art. Absolute coords in a 900xH viewBox. Boxes auto-wrap text.
def _wrap(text, w, fs=15):
    cpl = max(6, int(w / (fs * 0.54)))
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 <= cpl:
            line = (line + " " + word).strip()
        else:
            if line:
                out.append(line)
            line = word
    if line:
        out.append(line)
    return out

def box(x, y, w, h, text, fs=15, dashed=False, bold_first=False):
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="white" stroke="black" stroke-width="1.5"{dash}/>']
    lines = _wrap(text, w - 14, fs)
    total = len(lines) * (fs + 3)
    ty = y + (h - total) / 2 + fs
    for i, ln in enumerate(lines):
        wt = "700" if (bold_first and i == 0) else "400"
        s.append(f'<text x="{x + w/2}" y="{ty:.0f}" font-size="{fs}" font-weight="{wt}" text-anchor="middle" font-family="Georgia,serif">{html.escape(ln)}</text>')
        ty += fs + 3
    return "".join(s)

def _arrowdefs():
    return ('<defs><marker id="ah" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" '
            'markerUnits="strokeWidth"><path d="M0,0 L8,3 L0,6 z" fill="black"/></marker></defs>')

def arrow(x1, y1, x2, y2, label="", fs=13, dashed=False):
    dash = ' stroke-dasharray="4 3"' if dashed else ""
    s = [f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="black" stroke-width="1.5" marker-end="url(#ah)"{dash}/>']
    if label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2 - 5
        s.append(f'<rect x="{mx-len(label)*3.6-3}" y="{my-fs}" width="{len(label)*7.2+6}" height="{fs+5}" fill="white" opacity="0.9"/>')
        s.append(f'<text x="{mx}" y="{my}" font-size="{fs}" text-anchor="middle" font-style="italic" font-family="Georgia,serif">{html.escape(label)}</text>')
    return "".join(s)

def txt(x, y, s, fs=14, anchor="middle", style="normal", weight="400"):
    return f'<text x="{x}" y="{y}" font-size="{fs}" text-anchor="{anchor}" font-style="{style}" font-weight="{weight}" font-family="Georgia,serif">{html.escape(s)}</text>'

def _maxy(body):
    """Bottom-most drawn coordinate in the body SVG, so the caption never overlaps the diagram."""
    m = 0.0
    for a, b in re.findall(r'<rect[^>]*?\sy="([\d.]+)"[^>]*?\sheight="([\d.]+)"', body):
        m = max(m, float(a) + float(b))
    for v in re.findall(r'\sy1="([\d.]+)"', body):
        m = max(m, float(v))
    for v in re.findall(r'\sy2="([\d.]+)"', body):
        m = max(m, float(v))
    for v in re.findall(r'<text[^>]*?\sy="([\d.]+)"', body):
        m = max(m, float(v))
    return m

def fig(num, caption, _hint, body):
    # auto-size: caption sits BELOW the lowest diagram element (the _hint arg is ignored)
    dbottom = _maxy(body) + 14
    cap = _wrap(caption, 860, 14)
    height = dbottom + 22 + len(cap) * 18
    sep = f'<line x1="40" y1="{dbottom:.0f}" x2="860" y2="{dbottom:.0f}" stroke="#cccccc" stroke-width="1"/>'
    cy0 = dbottom + 20
    capsvg = "".join(txt(450, cy0 + i * 18, ln, fs=14, weight="400") for i, ln in enumerate(cap))
    return (f'<div class="figwrap"><svg viewBox="0 0 900 {height:.0f}" xmlns="http://www.w3.org/2000/svg" '
            f'class="fig">{_arrowdefs()}'
            f'{txt(450, 26, f"FIG. {num}", fs=18, weight="700")}'
            f'{body}{sep}{capsvg}</svg></div>')

# ----------------------------------------------------------------------------- figures per doc
def figs_whitebox():
    F = []
    # FIG 1 — overall flow
    b = []
    b.append(box(30, 50, 150, 60, "Parameter file (stored bits)", bold_first=False))
    b.append(box(240, 50, 140, 60, "Bit-level reader (no inference)"))
    b.append(box(440, 40, 200, 34, "Anatomy · Precision map · Layer scan"))
    b.append(box(440, 82, 200, 34, "Decompiler · Tensor scope"))
    b.append(box(440, 130, 200, 40, "Search-and-destroy · Alignment (edit)"))
    b.append(box(700, 70, 165, 70, "Genome journal (byte-exact revert)"))
    b.append(arrow(180, 80, 238, 80))
    b.append(arrow(380, 68, 438, 57))
    b.append(arrow(380, 80, 438, 99))
    b.append(arrow(380, 92, 438, 150))
    b.append(arrow(640, 150, 700, 120, "edit"))
    b.append(arrow(700, 90, 640, 57, "revert", dashed=True))
    b.append(arrow(782, 140, 782, 175))
    b.append(arrow(782, 175, 105, 175, "byte-exact restore", dashed=True))
    b.append(arrow(105, 175, 105, 112))
    F.append(fig(1, "The instrument's overall flow: a parameter file is opened by a bit-level reader (no forward pass); "
                    "analysis panels read meaning and structure while edit panels reversibly modify the file; every edit is "
                    "journaled to a byte-exact genome enabling exact revert.", 240, "".join(b)))
    # FIG 2 — decompiler + bit-edit
    b = []
    b.append(box(30, 46, 120, 46, "token “cat”"))
    b.append(box(190, 40, 150, 58, "stored embedding row (dequantized bits)"))
    b.append(box(390, 40, 175, 58, "nearest stored tokens: kitten, feline, gato…"))
    b.append(arrow(150, 69, 188, 69))
    b.append(arrow(340, 69, 388, 69, "cosine"))
    b.append(box(190, 130, 150, 54, "bit-edit: row ← (1−a)·cat + a·dog, re-quantized in place"))
    b.append(box(390, 132, 175, 50, "re-read neighbors: dog, puppy, canine…"))
    b.append(arrow(265, 98, 265, 128, "edit"))
    b.append(arrow(340, 157, 388, 157, "re-decompile"))
    b.append(arrow(478, 132, 478, 100, "before / after", dashed=True))
    F.append(fig(2, "The decompiler reads a token's stored meaning as its nearest stored neighbors, straight from the "
                    "dequantized bits with no inference; a reversible bit-edit interpolates the row toward a target token "
                    "and the changed meaning is re-read immediately (before vs. after).", 230, "".join(b)))
    # FIG 3 — alignment axis
    b = []
    b.append(box(30, 46, 120, 40, "positive concept set P"))
    b.append(box(30, 104, 120, 40, "negative concept set N"))
    b.append(box(200, 66, 150, 58, "axis d̂ = (mean ÊP − mean ÊN) / ‖·‖"))
    b.append(box(400, 40, 175, 44, "vocabulary projected on d̂ (the SIGHT): toward pole / away pole"))
    b.append(box(400, 108, 175, 48, "move token i by β: E′[i]=E[i]+β‖E[i]‖d̂ (journaled)"))
    b.append(box(630, 74, 165, 60, "measure ⟨E[i],d̂⟩ and neighbors, before / after"))
    b.append(arrow(150, 66, 198, 82))
    b.append(arrow(150, 124, 198, 108))
    b.append(arrow(350, 82, 398, 66, "see"))
    b.append(arrow(350, 100, 398, 128, "then move"))
    b.append(arrow(575, 132, 628, 110, "reversible"))
    F.append(fig(3, "Targeted, sighted alignment: an axis is formed from contrasting concept sets; the whole vocabulary is "
                    "projected onto it so the practitioner sees which meanings it moves before touching a parameter; one "
                    "token is then moved along the axis reversibly, with a measured before/after — the opposite of a "
                    "blind global gradient nudge.", 240, "".join(b)))
    # FIG 4 — precision recipe reader
    b = []
    b.append(txt(200, 48, "tensors grouped by role → protected precision", fs=15, weight="700"))
    rows = [("attention Q / K proj", "base (4-bit)"), ("attention V proj", "HIGHER (6-bit)"),
            ("FFN gate / up proj", "base (4-bit)"), ("FFN down proj", "MIXED"), ("output head", "HIGHER (6-bit)")]
    y = 62
    b.append(f'<rect x="30" y="{y}" width="380" height="{len(rows)*30+8}" fill="white" stroke="black" stroke-width="1.5"/>')
    for i, (r, p) in enumerate(rows):
        yy = y + 12 + i * 30
        b.append(txt(45, yy + 12, r, fs=14, anchor="start"))
        b.append(txt(300, yy + 12, p, fs=14, anchor="start", weight="700"))
        b.append(f'<line x1="290" y1="{yy}" x2="290" y2="{yy+28}" stroke="black" stroke-width="0.8"/>')
    # quant-stress histogram
    hx, hy, hh = 470, 70, 120
    b.append(txt(560, 56, "quant-stress: per-block |max|", fs=14, weight="700"))
    bars = [20, 34, 55, 78, 100, 70, 44, 26, 16, 9]
    bw = 34
    for i, v in enumerate(bars):
        bh = v * 1.0
        b.append(f'<rect x="{hx+i*bw}" y="{hy+hh-bh}" width="{bw-6}" height="{bh}" fill="black" opacity="0.78"/>')
    b.append(f'<line x1="{hx-4}" y1="{hy+hh}" x2="{hx+len(bars)*bw}" y2="{hy+hh}" stroke="black" stroke-width="1.2"/>')
    b.append(f'<line x1="{hx-4}" y1="{hy}" x2="{hx-4}" y2="{hy+hh}" stroke="black" stroke-width="1.2"/>')
    b.append(txt(hx+len(bars)*bw-40, hy+hh+16, "p99 outliers →", fs=12, anchor="middle", style="italic"))
    F.append(fig(4, "The precision-recipe reader groups tensors by role and reports the numeric precision each role "
                    "received in a mixed-quantization file (revealing which roles the quantizer protected), together with a "
                    "per-block outlier-magnitude (“quant-stress”) histogram locating where quantization most degrades "
                    "stored values.", 250, "".join(b)))
    # FIG 5 — search-and-destroy + genome
    b = []
    b.append(box(20, 60, 120, 48, "search by name / pattern"))
    b.append(box(175, 44, 150, 80, "select target: whole tensor | one expert slice | token row"))
    b.append(box(360, 54, 145, 60, "record original bytes → GENOME (off, len, bytes)"))
    b.append(box(540, 54, 150, 60, "zero / scale / scrub the bytes in place"))
    b.append(box(725, 54, 150, 60, "revert-last / revert-all → byte-exact (SHA-verified)"))
    b.append(arrow(140, 84, 173, 84))
    b.append(arrow(325, 84, 358, 84))
    b.append(arrow(505, 84, 538, 84, "backup first"))
    b.append(arrow(690, 84, 723, 84, "write"))
    b.append(arrow(800, 114, 800, 150))
    b.append(arrow(800, 150, 435, 150, "restore", dashed=True))
    b.append(arrow(435, 150, 435, 116))
    F.append(fig(5, "Reversible search-and-destroy: a named tensor, a single mixture-of-experts expert slice, or a token "
                    "row is selected; the exact original bytes of only that region are journaled to the genome before the "
                    "zero/scale/scrub write; revert-last or revert-all restores the file byte-exactly, verified by checksum.",
                    215, "".join(b)))
    # FIG 6 — pool scan
    b = []
    b.append(box(30, 50, 120, 70, "model files 1 … N (heterogeneous pool)"))
    b.append(box(200, 50, 150, 70, "stream each tensor; dequantize a bounded fixed-size sample"))
    b.append(box(400, 40, 150, 44, "classify per tensor: DEAD / SPARSE / HEALTHY"))
    b.append(box(400, 100, 150, 44, "per-role: healthiest source model + prune list"))
    b.append(box(600, 66, 170, 58, "retained fallback for anything pruned (source / genome)"))
    b.append(arrow(150, 85, 198, 85, "storage-first"))
    b.append(arrow(350, 78, 398, 62, "std, near-zero frac"))
    b.append(arrow(350, 92, 398, 118))
    b.append(arrow(550, 122, 598, 100))
    F.append(fig(6, "The multi-model pool health scan streams every tensor of every model and dequantizes only a bounded "
                    "sample (so peak memory is independent of file size — a 40-GB file is never loaded whole), classifies "
                    "each tensor as junk or valuable, names the healthiest source per tensor-role, and retains a fallback for "
                    "anything pruned.", 210, "".join(b)))
    # FIG 7 — the circuitry mapper: FFN block as a bank of transistors
    b = []
    busY = 52
    b.append(f'<line x1="40" y1="{busY}" x2="860" y2="{busY}" stroke="black" stroke-width="2"/>')
    b.append(txt(48, busY - 7, "residual bus  (attention = interconnect)", fs=13, anchor="start", style="italic"))
    # transistors: (x, class, fill)
    trans = [(150, "amp", "white"), (300, "inh", "white"), (445, "dead", "#d8d8d8"),
             (590, "amp", "white"), (720, "pass", "white")]
    chY, chW, chH = busY + 34, 28, 56
    for (x, cls, fill) in trans:
        lw = 1 if cls == "dead" else 2
        b.append(f'<line x1="{x}" y1="{busY}" x2="{x}" y2="{chY}" stroke="black" stroke-width="{lw}"/>')                 # drain wire
        b.append(f'<rect x="{x-chW/2}" y="{chY}" width="{chW}" height="{chH}" rx="3" fill="{fill}" stroke="black" stroke-width="1.5"/>')  # channel
        b.append(f'<line x1="{x-chW/2-20}" y1="{chY+chH/2}" x2="{x-chW/2}" y2="{chY+chH/2}" stroke="black" stroke-width="2"/>')  # gate stub
        b.append(f'<circle cx="{x-chW/2-20}" cy="{chY+chH/2}" r="2.6" fill="black"/>')
        b.append(f'<line x1="{x}" y1="{chY+chH}" x2="{x}" y2="{chY+chH+15}" stroke="black" stroke-width="1.5"/>')        # source stub
        b.append(txt(x, chY + chH + 32, cls, fs=13, weight="700"))
    # terminal callouts on the first transistor
    x0 = 150
    b.append(txt(x0 - chW/2 - 24, chY + chH/2 - 4, "gate g", fs=12, anchor="end"))
    b.append(txt(x0 - chW/2 - 24, chY + chH/2 + 11, "(switch)", fs=10.5, anchor="end", style="italic"))
    b.append(txt(x0 + chW/2 + 8, chY + 12, "drain d", fs=12, anchor="start"))
    b.append(txt(x0 + chW/2 + 8, chY + chH + 4, "source u", fs=12, anchor="start"))
    # the transistor equation
    b.append(txt(450, chY + chH + 62, "each SwiGLU hidden unit j :   yⱼ = SiLU(gⱼ·x) · (uⱼ·x)   →   residual += yⱼ·dⱼ", fs=14))
    # legend
    ly = chY + chH + 86
    for i, (lab, fl) in enumerate([("amplifier (ρ>0)", "white"), ("inhibitor (ρ<0)", "white"), ("dead (‖g‖·‖d‖≈0)", "#d8d8d8")]):
        lx = 150 + i * 230
        b.append(f'<rect x="{lx}" y="{ly-11}" width="16" height="14" fill="{fl}" stroke="black" stroke-width="1.2"/>')
        b.append(txt(lx + 22, ly, lab, fs=12, anchor="start"))
    F.append(fig(7, "The circuitry mapper reads a gated feed-forward block from the stored bits and renders it as a bank of "
                    "transistors on the residual bus: each hidden unit j is a transistor whose gate row gⱼ is the switch "
                    "(SiLU(gⱼ·x)), up row uⱼ the source, and down column dⱼ the drain; per-transistor gate gain, drain drive, "
                    "and gate–source alignment ρ classify it as an amplifier, inhibitor, or dead — all from the weights, no "
                    "inference.", 240, "".join(b)))
    return F

def figs_sdc():
    F = []
    b = []
    chain = [("user goal / prompt", 30), ("input translation", 175), ("THE PROCESS (per-tick model build + operators)", 320), ("material: param pool + operators + codecs + caches", 505), ("output translation", 700)]
    for t, x in chain:
        w = 150 if "material" in t or "PROCESS" in t else 130
        b.append(box(x, 55, w, 66, t))
    b.append(arrow(160, 88, 173, 88)); b.append(arrow(305, 88, 318, 88))
    b.append(arrow(470, 88, 503, 88)); b.append(arrow(655, 88, 698, 88))
    b.append(box(700, 150, 130, 40, "rendered artifact"))
    b.append(arrow(765, 121, 765, 148))
    b.append(f'<rect x="30" y="205" width="800" height="30" fill="white" stroke="black" stroke-dasharray="5 4" stroke-width="1.2"/>')
    b.append(txt(430, 224, "truth / physics floor: output = f(training, prompt) — no external intelligence", fs=13, style="italic"))
    F.append(fig(1, "Block diagram of the Stored Digital Computer stack: a human goal is translated in, processed by a "
                    "per-tick model built from a stored parameter pool under operator control, and translated out to a "
                    "rendered artifact — all above a truth/physics floor.", 285, "".join(b)))
    b = []
    b.append(box(60, 60, 160, 60, "operator σ (formal removable conditioning)"))
    b.append(box(300, 50, 160, 80, "parameter pool (roles, experts, layers)"))
    b.append(box(540, 60, 170, 60, "the model for THIS step (selected subset)"))
    b.append(arrow(220, 90, 298, 90, "selects subset"))
    b.append(arrow(460, 90, 538, 90, "compute one tick"))
    b.append(arrow(625, 122, 625, 150)); b.append(box(555, 150, 140, 34, "discard → rebuild next tick"))
    F.append(fig(2, "The per-tick model-builder: an operator selects a subset of the stored parameter pool to form the model "
                    "for a single computation step; the model is discarded and rebuilt the next step, so one stored pool "
                    "realizes many per-tick machines.", 210, "".join(b)))
    b = []
    steps = [("conditioned output", 30), ("outcome-gated capture", 190), ("residency: σ-ON vs σ-OFF ablation", 350), ("bounded reversible edit", 540), ("keep if residency rose / else exact revert", 710)]
    for t, x in steps:
        b.append(box(x, 55, 150 if x in (350, 710) else 140, 70, t))
    b.append(arrow(170, 90, 188, 90)); b.append(arrow(330, 90, 348, 90))
    b.append(arrow(500, 90, 538, 90)); b.append(arrow(680, 90, 708, 90))
    b.append(box(300, 165, 200, 34, "graduation: behavior resident → drop σ (zero prompt tokens)"))
    b.append(arrow(430, 125, 430, 163))
    F.append(fig(3, "The gradient-free baking loop: conditioned output is captured on outcome, residency is measured by "
                    "σ-ON/σ-OFF ablation, a bounded reversible edit is applied and kept only if residency rose (else "
                    "byte-exact revert), and a fully resident behavior graduates — the operator is dropped.", 220, "".join(b)))
    b = []
    b.append(box(30, 55, 140, 60, "parameters stored on flash (memory-mapped)"))
    b.append(box(210, 55, 140, 60, "stream only the read fraction α per token"))
    b.append(box(390, 55, 140, 60, "resident working set (bounded)"))
    b.append(arrow(170, 85, 208, 85)); b.append(arrow(350, 85, 388, 85))
    # alpha-throughput curve
    cx, cy, cw, ch = 590, 55, 250, 130
    b.append(f'<line x1="{cx}" y1="{cy+ch}" x2="{cx+cw}" y2="{cy+ch}" stroke="black" stroke-width="1.2"/>')
    b.append(f'<line x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy+ch}" stroke="black" stroke-width="1.2"/>')
    b.append(f'<path d="M{cx+8},{cy+10} Q{cx+90},{cy+40} {cx+cw-10},{cy+ch-8}" fill="none" stroke="black" stroke-width="1.8"/>')
    b.append(txt(cx+cw/2, cy+ch+18, "α = fraction read/token", fs=12))
    b.append(txt(cx-6, cy+ch/2, "t", fs=13, anchor="end"))
    b.append(txt(cx+cw/2, cy-2, "read-energy / speed knob", fs=12, weight="700"))
    F.append(fig(4, "Storage-first execution: parameters live on storage and are memory-mapped; only the operator-selected "
                    "fraction α is read per token, so model size is bounded by storage while the resident set is bounded by "
                    "RAM — α is the speed/energy knob.", 220, "".join(b)))
    b = []
    b.append(box(60, 55, 150, 66, "routing folder: roles · experts · operator library"))
    b.append(box(300, 45, 150, 40, "per-entry fallback (keep-if-better)"))
    b.append(box(300, 100, 150, 40, "the router selects across entries"))
    b.append(box(560, 55, 150, 66, "composed model for the step"))
    b.append(arrow(210, 78, 298, 65)); b.append(arrow(210, 96, 298, 120))
    b.append(arrow(450, 90, 558, 90, "elect"))
    F.append(fig(5, "The routing folder holds roles, experts, and the operator library, each with a retained fallback; the "
                    "router (itself an operator layer) selects across them to compose the model for a step.", 190, "".join(b)))
    b = []
    b.append(box(60, 70, 150, 56, "TRAIN = compile (world → stored bits)"))
    b.append(box(300, 40, 150, 44, "INFER = decompile (bits → meaning)"))
    b.append(box(300, 110, 150, 44, "BAKE = re-compile (edit stored bits)"))
    b.append(box(560, 70, 150, 56, "read-side + write-side instruments (the White Box)"))
    b.append(arrow(210, 84, 298, 62)); b.append(arrow(210, 110, 298, 132))
    b.append(arrow(450, 62, 558, 88)); b.append(arrow(450, 132, 558, 108))
    F.append(fig(6, "Decompiling meaning from bits: training compiles the world into stored parameters, inference "
                    "decompiles them into meaning, and baking re-compiles by editing the stored bits — read-side and "
                    "write-side instruments operate directly on the file.", 200, "".join(b)))
    return F

def figs_agent():
    F = []
    b = []
    b.append(box(330, 46, 240, 50, "on-device language model (the DRIVER — makes every decision)", bold_first=True))
    b.append(box(60, 150, 220, 56, "perception translator: screen → structured perception"))
    b.append(box(620, 150, 220, 56, "actuation translator: chosen action → device action"))
    b.append(box(330, 235, 240, 44, "hard safety gates in the executor"))
    b.append(arrow(280, 165, 428, 92, "reads"))
    b.append(arrow(470, 96, 640, 165, "one action"))
    b.append(arrow(730, 206, 570, 250, "gate", dashed=True))
    F.append(fig(1, "The driver/translation-layer architecture: the on-device model is the driver; a perception translator "
                    "turns the screen into structured perception it reads, and an actuation translator turns its chosen action "
                    "into a device action — with hard safety gates enforced in the executor, not the model.", 300, "".join(b)))
    b = []
    loop = ["safety gate", "resource / stuck caps", "capture perception", "screen-unchanged skip", "reflex suggestions", "rolling re-plan", "decide ONE action", "execute"]
    xs = [20, 130, 250, 370, 500, 620, 730, 830]
    for t, x in zip(loop, xs):
        b.append(box(x, 60, 100 if x not in (250,500) else 108, 70, t, fs=13))
    for i in range(len(xs) - 1):
        b.append(arrow(xs[i] + (108 if xs[i] in (250,500) else 100), 95, xs[i+1], 95))
    b.append(arrow(880, 132, 880, 165)); b.append(arrow(880, 165, 70, 165, "loop", dashed=True)); b.append(arrow(70, 165, 70, 132))
    F.append(fig(2, "The perceive→decide→act loop with its guards: a safety gate and resource/stuck caps precede "
                    "perception capture; an unchanged screen is skipped; behavior-triggered reflexes only SUGGEST; a rolling "
                    "re-plan runs on progress; the model decides exactly one action, which is executed.", 220, "".join(b)))
    b = []
    b.append(box(40, 55, 150, 70, "structured element list + set-of-marks badges"))
    b.append(box(220, 55, 150, 70, "labeled grid + navigation scrape"))
    b.append(box(430, 40, 170, 44, "fast text-only decision (confident)"))
    b.append(box(430, 100, 170, 44, "slow vision decision (unsure)"))
    b.append(arrow(190, 90, 218, 90))
    b.append(arrow(370, 78, 428, 62, "conf = high"))
    b.append(arrow(370, 100, 428, 120, "conf = low"))
    F.append(fig(3, "Efficient perception: the screen is rendered as a structured element list, set-of-marks badges, a "
                    "labeled grid, and a navigation scrape; the model's own stated confidence selects a fast text-only "
                    "decision or a slower vision decision (adaptive compute).", 200, "".join(b)))
    b = []
    b.append(box(40, 55, 150, 60, "model elects a reasoning move (operator)"))
    b.append(box(230, 40, 150, 44, "system credits moves that lead to progress"))
    b.append(box(230, 100, 150, 44, "self-authored new moves"))
    b.append(box(440, 55, 150, 60, "only relevant moves shown for the step"))
    b.append(box(640, 55, 160, 60, "plan-time pre-mortem"))
    b.append(arrow(190, 78, 228, 62)); b.append(arrow(190, 92, 228, 120))
    b.append(arrow(380, 85, 438, 85)); b.append(arrow(590, 85, 638, 85))
    F.append(fig(4, "The operator layer: the model elects a reasoning move; the system credits which moves lead to progress "
                    "and lets the model author new ones; only relevant moves are surfaced per step; a plan-time pre-mortem runs "
                    "before acting.", 200, "".join(b)))
    b = []
    b.append(box(40, 55, 160, 66, "self-correcting screen → action → screen map"))
    b.append(box(250, 45, 150, 44, "use-as-training-data capture"))
    b.append(box(250, 100, 150, 44, "proven-after-twice memory"))
    b.append(box(460, 55, 150, 66, "reusable success sequences"))
    b.append(arrow(200, 78, 248, 62)); b.append(arrow(200, 98, 248, 120))
    b.append(arrow(400, 85, 458, 85))
    F.append(fig(5, "On-device learning: a self-correcting map of screen→action→screen transitions, capture of the "
                    "owner's own use as training data, memory that promotes a step after two clean successes, and reusable "
                    "success sequences — all on the device.", 190, "".join(b)))
    b = []
    b.append(box(40, 55, 150, 66, "on-screen text is DATA, never instructions (injection guard)"))
    b.append(box(230, 45, 140, 44, "narrow hard gates in executor"))
    b.append(box(230, 100, 140, 44, "kill switches (stop / caps)"))
    b.append(box(430, 45, 160, 44, "typed give-up + owner remedy"))
    b.append(box(430, 100, 160, 44, "blind ≠ lost (recover)"))
    b.append(arrow(190, 78, 228, 66)); b.append(arrow(190, 98, 228, 120))
    b.append(arrow(370, 66, 428, 66)); b.append(arrow(370, 122, 428, 122))
    F.append(fig(6, "Safety and useful failure: an injection guard treats on-screen text as data; narrow hard gates and "
                    "kill switches live in the executor; a give-up is typed with a plain owner remedy; and being unable to see "
                    "is distinguished from being lost.", 190, "".join(b)))
    b = []
    steps = [("proven reasoning move", 30), ("baseline backup", 220), ("bounded parameter edit", 400), ("keep if improved / else revert", 590), ("journaled, reversible", 760)]
    for t, x in steps:
        b.append(box(x, 60, 150 if x in (590,) else 140, 66, t))
    b.append(arrow(170, 92, 218, 92)); b.append(arrow(360, 92, 398, 92))
    b.append(arrow(540, 92, 588, 92)); b.append(arrow(740, 92, 758, 92))
    F.append(fig(7, "On-device gradient-free consolidation of a proven reasoning move into the model's parameters: a "
                    "baseline is backed up, a bounded edit is applied and kept only if it improves behavior, and every edit is "
                    "journaled for exact reversal.", 190, "".join(b)))
    return F

FIGS = {"PATENT_1_SDC": figs_sdc, "PATENT_2_WHITEBOX": figs_whitebox, "PATENT_3_AGENTIC_HANDSET_OPERATOR": figs_agent}

# ----------------------------------------------------------------------------- markdown -> html
CSS = """<style>@page{margin:1in}
body{font-family:Georgia,'Times New Roman',serif;font-size:11.5pt;line-height:1.5;max-width:7in;margin:0 auto;color:#111}
h1{font-size:15pt;text-align:center;margin:0 0 4pt}
h2{font-size:12.5pt;border-bottom:1px solid #999;padding-bottom:2pt;margin-top:22pt}
h3{font-size:11.5pt;margin-top:15pt}
.mono{font-family:'Cascadia Code',Consolas,monospace;font-size:10pt}
blockquote{margin:7pt 0;padding:5pt 12pt;border-left:3px solid #888;background:#f6f6f4;font-family:'Cascadia Code',Consolas,monospace;font-size:10pt;white-space:pre-wrap;line-height:1.45}
p{margin:6pt 0;text-align:justify}
.li{margin:5pt 0 5pt 22pt;text-align:justify;text-indent:-16pt}
table{border-collapse:collapse;margin:8pt 0;font-size:10.5pt;width:100%}
th,td{border:1px solid #999;padding:3pt 7pt;text-align:left;vertical-align:top}
th{background:#f0f0ee}
hr{border:none;border-top:1px solid #ccc;margin:14pt 0}
.figwrap{margin:14pt 0;page-break-inside:avoid;text-align:center}
svg.fig{width:100%;max-width:6.7in;border:1px solid #ddd;background:white}
.drawings-page{page-break-before:always}
</style>"""

def inline(s):
    s = html.escape(s)
    s = re.sub(r'`([^`]+)`', lambda m: '<span class="mono">' + m.group(1) + '</span>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
    return s

def md_to_html(md, figures=None):
    lines = md.split("\n")
    out, i, para = [], 0, []
    def flush():
        if para:
            out.append("<p>" + " ".join(para) + "</p>")
            para.clear()
    n = len(lines)
    while i < n:
        ln = lines[i]
        st = ln.strip()
        # blockquote (math) -> monospace, strip backtick delimiters
        if st.startswith(">"):
            flush(); bq = []
            while i < n and lines[i].strip().startswith(">"):
                c = re.sub(r'^\s*>\s?', '', lines[i]).replace('`', '')
                bq.append(html.escape(c)); i += 1
            out.append("<blockquote>" + "\n".join(bq) + "</blockquote>"); continue
        # table
        if st.startswith("|") and i + 1 < n and set(lines[i+1].strip()) <= set("|-: "):
            flush(); rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[2:])
            out.append(f"<table><tr>{th}</tr>{body}</table>"); continue
        # heading
        m = re.match(r'^(#{1,4})\s+(.*)', ln)
        if m:
            flush(); lvl = len(m.group(1)); out.append(f"<h{lvl}>{inline(m.group(2).strip())}</h{lvl}>")
            # inject figures right after the drawings heading
            if figures and "BRIEF DESCRIPTION OF THE DRAWINGS" in m.group(2).upper():
                # emit the list items of this section first, then the figures
                j = i + 1; items = []
                while j < n and not re.match(r'^#{1,4}\s', lines[j]):
                    items.append(lines[j]); j += 1
                # render the bullet list normally
                buf, cur = [], []
                for it in items:
                    s2 = it.strip()
                    if re.match(r'^[-*]\s|^\d+\.\s', s2):
                        if cur: buf.append(" ".join(cur)); cur = []
                        cur.append(s2)
                    elif s2 == "":
                        if cur: buf.append(" ".join(cur)); cur = []
                    else:
                        cur.append(s2)
                if cur: buf.append(" ".join(cur))
                for it in buf:
                    out.append(f'<div class="li">{inline(it)}</div>')
                out.append('<div class="drawings-page"></div>')
                out.append("".join(figures))
                i = j; continue
            i += 1; continue
        if st == "---":
            flush(); out.append("<hr>"); i += 1; continue
        # list item (numbered or bulleted) — accumulate continuation lines into ONE block
        if re.match(r'^[-*]\s|^\d+\.\s', st):
            flush(); parts = [st]; i += 1
            while i < n:
                s2 = lines[i].strip()
                if s2 == "" or re.match(r'^[-*]\s|^\d+\.\s', s2) or re.match(r'^#{1,4}\s', lines[i]) or s2 == "---" or s2.startswith(">"):
                    break
                parts.append(s2); i += 1
            out.append(f'<div class="li">{inline(" ".join(parts))}</div>'); continue
        if st == "":
            flush(); i += 1; continue
        para.append(inline(st)); i += 1
    flush()
    return "<!doctype html><meta charset=utf-8>" + CSS + "".join(out)

def build(name):
    md = open(os.path.join(DOCS, name + ".md"), encoding="utf-8").read()
    figs = FIGS[name]() if name in FIGS else None
    htmlout = md_to_html(md, figures=figs)
    p = os.path.join(DESK, name + ".html")
    open(p, "w", encoding="utf-8").write(htmlout)
    print(f"  {name}.html  ({len(htmlout)//1024} KB, {len(figs) if figs else 0} figures)")

if __name__ == "__main__":
    for nm in ("PATENT_1_SDC", "PATENT_2_WHITEBOX", "PATENT_3_AGENTIC_HANDSET_OPERATOR"):
        build(nm)
    print("done")
