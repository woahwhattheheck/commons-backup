# Accessible visual language for the final report

**UIOWA-090** (the visual language) and **UIOWA-126** (correct treatment of unknown and
inapplicable values). Reusable chart and table templates for the four figures the final report needs —
the twelve-cell assessment matrix, cross-group comparison, evidence coverage, and the phased
roadmap — built so a reader understands each one **without relying on colour**, and so an
**unassessed cell never reads as a low rating**.

Python 3 standard library only. No third-party packages, no plotting library, no network at
runtime. SVG is written out by hand so every mark, hatch, label and ARIA attribute in the output
is something this package put there deliberately and can therefore test.

---

## The two rules the whole package exists to enforce

**1. No meaning lives in colour alone.** Every assessment band carries four independent channels:
a fill colour, a drawn **shape**, a fill **texture**, and a written **label**. Take any one away —
a colour-blind reader, a monochrome printer, a projector that flattens fine hatching, a screen
reader that sees only text — and the remaining channels still name the band.

**2. A state that is not a rating must never look like the bottom of the scale.**
The report is read by people who will act on it, and quietly converting *our* missing evidence
into *their* low score is the single most damaging thing these visuals could do. There are
**four** distinct non-rating states, and each answers a different question:

| State | The question it answers | Why it is not a rating |
|---|---|---|
| **Insufficient evidence** | What did we receive? | We looked; what arrived did not support a rating. |
| **Not assessed** | What was in scope? | Outside the agreed scope for this group. |
| **Not applicable** | How does this group operate? | The practice does not apply to them. **Nothing is missing.** |
| **Sources disagree** | Do the sources agree? | Two readings conflict; both are kept, unreconciled. |

`Not applicable` and `Not assessed` are the pair a careless chart merges into one grey box —
one is a fact about *the group's context*, the other about *our evidence*. `Sources disagree`
is the most informative cell on the page and the easiest to lose: averaging it invents a
confident middle value, dropping it produces silence.

Separately, in any **count**, a measured **zero** is a value and an **omission** is not:

| | Border | Counted as |
|---|---|---|
| **Measured zero** — searched, found none | solid | the value `0` |
| **Not recorded** — no count supplied | dashed | excluded; never summed as `0` |

A zero drawn as an empty bar is indistinguishable from "we have no data", so a real finding
("zero unresolved items") gets filed as a hole. The border language is consistent throughout:
**solid = a value we have, dashed = a value we do not have, double = more than one value, both
kept.**

All non-rating states are:

- pulled off the ordinal scale entirely (`rank is None`, so nothing can sort them to the bottom),
- denied the solid border, which is reserved for values we actually have, and given their own
  shape and texture,
- kept **at least 3:1 away from every rating fill after the colour is stripped out** — measured,
  not asserted,
- placed **below a solid dividing rule** in the comparison chart, under the heading
  *"Off the rating scale — these are statements about the evidence, not lower ratings"*, so a
  reader scanning downward hits a boundary instead of running out of scale,
- excluded from every count of ratings, rather than counted as zero.

---

## What "accessible" is backed by here

Not a claim — a measurement that runs in the test suite.

`contrast.py` implements WCAG 2.1 relative luminance and contrast ratio from the specification.
It is validated against published reference values (white/black = 21.0; `#767676` on white = 4.54,
the documented 4.5:1 boundary). `palette.audit_palette()` runs every colour pair this package
ships:

```
62 checks, 62 pass, 0 fail        # theme 'print'
62 checks, 62 pass, 0 fail        # theme 'screen'
```

Thresholds: **4.5:1** for text of any size (the large-text exemption is deliberately *not* taken —
report figures get resized, printed and projected), **3:1** for borders, marks, hatch strokes and
rules, **3:1** for two fills a reader must tell apart after colour is removed.

The eight measurements that matter most, from `examples/contrast-audit.txt`:

| pair (colour removed) | Strength | Established | Developing | Gap |
|---|---|---|---|---|
| **Not assessed** | 7.83:1 | 5.07:1 | 4.50:1 | **6.38:1** |
| **Insufficient evidence** | 6.32:1 | 4.09:1 | 3.63:1 | 5.15:1 |
| **Not applicable** | 7.08:1 | 4.58:1 | 4.07:1 | 5.77:1 |
| **Sources disagree** | 7.15:1 | 4.63:1 | 4.11:1 | 5.83:1 |

Sixteen pairs, every one above the 3:1 bar, every one asserted in the suite.

A test (`test_audit_actually_detects_a_bad_colour`) deliberately breaks a colour and asserts the
audit goes red, because a checker that cannot fail proves nothing.

### Two things the measurement changed

Both of these were caught by running the numbers, not by looking at the chart:

1. The first `Developing` ochre measured 3.47:1 on white and left Not-assessed-vs-Developing at
   exactly 3.00:1 — on the line, no headroom. Darkened to `#8F6510`; that pair is now 4.50:1.

2. **`Not applicable`'s texture stroke measured 2.99:1** against its own fill — one hundredth
   under the 3:1 bar, which no eye would have caught. The audit went red and the ink was
   darkened to `#7A7A73` (3.39:1). This is the entire argument for measuring rather than
   reviewing.

3. **The three group colours are indistinguishable from each other in grayscale** — measured at
   **1.03:1, 1.11:1 and 1.15:1**. Three mid-tone hues at similar luminance always collapse this
   way; picking nicer hues does not fix it. So group identity does **not** ride on colour at all:
   each group gets a distinct **shape** (square / pentagon / hexagon) and its **code printed next
   to every mark**. The colours stay because they help a sighted reader scan, and
   `palette.GROUP_COLOUR_IS_DECORATIVE = True` records the decision so nobody later promotes them
   back to load-bearing. A test asserts every plotted mark has its group code printed beside it.

   This package therefore does **not** claim to be "colour-blind safe" in the sense of having
   three mutually distinguishable group colours. It claims something stronger and testable:
   group colour is never the carrier of meaning.

---

## Honest limits

- **Fills alone cannot separate all eight states, and this package does not pretend otherwise.**
  Eight fills cannot sit 3:1 apart — the luminance range does not contain that many steps. The
  closest monochrome pairs are `Not applicable` / `Sources disagree` at **1.01:1** and
  `Established` / `Developing` at **1.13:1**. So the rule enforced is the one that actually
  decides something, and it is enforced exactly: **no rating may ever be the closest thing to a
  non-rating state** (`test_no_rating_is_ever_the_closest_thing_to_an_unrated_state`), and **any
  pair closer than 3:1 must differ in texture, shape, glyph and label** — all four
  (`test_every_close_pair_is_separated_by_three_other_channels`). Two states that look alike in
  print are acceptable only when four other channels tell them apart; a rating and a non-rating
  looking alike is never acceptable.
- **Monochrome is proved by conversion, not by assertion.** Every figure also ships as
  `*.mono.svg`, in which every colour has actually been replaced by its luminance-equivalent
  grey. That file is not a simulation of the worst case — it is the worst case, on disk, openable
  and printable. A test asserts the conversion removes all hue, keeps every word, and preserves
  the textures and border styles.
- **Verification here is structural, not visual.** The SVGs are parsed as XML, checked for
  `role="img"`, a real `<title>`/`<desc>`, and that no text or box falls outside the canvas. No
  rasteriser (`rsvg-convert`, `cairosvg`, headless browser) exists in this environment, so
  **nobody has yet looked at these figures rendered as pixels.** They should be opened in a
  browser before use.
- **No testing with actual assistive technology or actual readers has been done.** The ARIA
  structure follows the spec; it has not been driven through a screen reader.
- Long titles are truncated to fit a roadmap card. A title over ~80 characters will clip.

---

## Files

| File | What it is |
|---|---|
| `contrast.py` | WCAG 2.1 luminance / contrast / grayscale, written from the spec |
| `palette.py` | The visual vocabulary + `audit_palette()`; the design contract in comments |
| `svg.py` | Hand-written SVG emitter: marks, hatch patterns, ARIA-labelled documents |
| `model.py` | The assessment data model and the counting rules that keep it honest |
| `figures.py` | The five figure templates, including the states comparison fixture |
| `monochrome.py` | Real colour removal for the `.mono.svg` exports, plus separation reporting |
| `alt_text.py` | Text alternatives + Markdown table templates, generated from the same data |
| `render_report_visuals.py` | CLI: render / `--audit` / `--check-encoding` |
| `fixtures/synthetic_assessment.json` | The fictional example data |
| `examples/` | Rendered output, committed so a reviewer can open it without running anything |
| `test_report_visuals.py` | 90 tests |

## Run it

```bash
cd revenue/uiowa_rfq_18649_report_visuals

python3 render_report_visuals.py                  # render everything into examples/
python3 render_report_visuals.py --audit          # the WCAG contrast report
python3 render_report_visuals.py --check-encoding # verify the redundancy contract
python3 -m unittest test_report_visuals           # 90 tests
```

`--check-encoding` verifies that label, glyph, shape and texture are each unique per band, that
ratings use the solid border and non-ratings the dashed one, that non-ratings carry no rank, and
that every not-a-rating/rating pair clears 3:1 in grayscale. `render` refuses to draw anything if
that contract is broken.

Rendering is **deterministic** — no clock, no randomness, sorted traversal. A second operator
running the same command on the same input gets byte-identical files and a `manifest.json` of
SHA-256 digests, so a diff means the data changed and nothing else. A test renders twice into two
directories and compares bytes.

## Output

Per theme (`print`, `screen`): `matrix`, `cross-group`, `evidence-coverage`, `roadmap` and
`states` as `.svg`, each with a true-monochrome `.mono.svg` twin.

`states.print.svg` is the **compact comparison fixture**: all eleven states on one page with what
each means and how each is counted. It is the artifact a reviewer uses to check that a legend is
honest, because it puts the dangerous confusions side by side instead of three pages apart.
Plus `text-alternatives.md` (the exact text embedded in each SVG's `<desc>`), `matrix-table.md`,
`evidence-coverage-table.md`, `roadmap-table.md`, `contrast-audit.txt`, `manifest.json`.

The table templates carry the same redundancy as the charts — a glyph **and** the written band
name in every cell, never a colour swatch on its own:

| Group | Software delivery | Reliability and operations | Security practices | AI readiness |
|---|---|---|---|---|
| **ESS** Enterprise Shared Services | ● **Established** | ▲ **Strength** | ◆ **Developing** | — **Not assessed** |
| **RIS** Research Infrastructure Services | ◆ **Developing** | ● **Established** | ▼ **Gap** | ◎ **Insufficient evidence** |
| **IAM** Identity and Access Management | ● **Established** | ◎ **Insufficient evidence** | ● **Established** | — **Not assessed** |

### Text alternatives cannot drift

Each SVG's `<desc>` is produced by `alt_text.py` from the same `Matrix` object that drew the
picture, and a test asserts `desc == ALT_BUILDERS[key](matrix)` for every figure. A hand-written
caption is correct on the day it is written and wrong the first time the data changes; this one
cannot be.

---

## What is real and what is draft

**Real and working:** the contrast implementation and its audit; the redundant-encoding contract
and its checker; all four figure templates; the text-alternative and table generators; the data
model's rejection rules; deterministic rendering; the 60-test suite. All of it runs on stdlib
Python 3 and is exercised by the committed example.

**Draft / not yet done:** visual review of the rendered pixels (see *Honest limits*); screen-reader
testing; a dark theme; pagination for a matrix wider than four areas or taller than about six
groups; the exact typeface the report will use (the SVG names a generic sans stack).

**Fiction is labelled fiction.** Everything in `fixtures/synthetic_assessment.json` and everything
under `examples/` is invented to exercise the templates. Every figure, table and text alternative
carries the line *"SYNTHETIC EXAMPLE — fictional groups and fictional evidence. Not a University of
Iowa finding."*, and a test asserts that string is present in every output. The example is built to
exercise **every** state, because a template that has only ever been run against tidy data has not
been tested: a genuine strength (`ESS / Reliability`), a real gap (`RIS / Software delivery`), two
insufficient-evidence cells, one unassessed cell, one not-applicable cell (`IAM / AI readiness` —
a vendor-hosted core, so the questions do not apply), and one contradictory cell (`RIS / Security`
— the written procedure requires two approvals, seven of twelve sampled changes record one; both
readings are kept). The coverage chart carries the zero-versus-missing pair directly: `RIS` never
recorded observed artifacts, `IAM` did the walkthrough and found none. Both totals are `0`; only
one is a measurement, and the chart, the table and the text alternative all say which.

## University inputs that remain UNKNOWN

Nothing below has been supplied, and none of it is guessed at anywhere in this package:

- The real group names, count and structure, and which are in scope. The three fictional groups
  are placeholders; the templates take any number of groups and areas.
- The agreed assessment areas and the agreed band vocabulary. The eight states here are a working
  proposal and are expected to be renamed.
- Which cells are `Not applicable` rather than `Not assessed` — that call needs the groups' own
  description of how they operate, and it is not one this package can infer.
- Which cells are in scope — i.e. which cells are legitimately `UNASSESSED` rather than pending.
- All actual evidence: documents, interviews, system records, observed artifacts, and their counts.
- The real recommendations, their identifiers, and the real roadmap items, efforts and sequence.
- The report's typeface, page size, column width and print process (these set minimum type size
  and hatch stroke weight; the current values assume roughly a 7-inch text column).
- Whether the client needs a specific conformance target (e.g. WCAG 2.1 AA as a contractual
  obligation) — this package measures against AA thresholds but **makes no certification or
  compliance claim**, here or anywhere in its output.
