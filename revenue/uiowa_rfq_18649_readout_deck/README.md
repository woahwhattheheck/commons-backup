# Optional final-readout deck architecture (UIOWA-088)

Recovery note: runtime, original JSON and editable template recovered from
`4056207a59953944fd8f8ca9ec2d4576e988088e`. The historical test suite described
below is not part of this recovery. Run the product's `check` and `render`
commands. An editable PowerPoint exporter and corrected presentation-input copy
are available in [the adjacent export directory](../uiowa_rfq_18649_readout_pptx/README.md).

A reusable structure for the optional leadership / group readout, plus the thing that makes
the structure worth anything: **a checker that proves the deck agrees with its report.**

The order's completion test is *"the deck agrees with its example report."* That is a
checkable property, so it is checked. The report is the single source of truth. The deck is a
set of machine-readable **claims** about it — every figure a presenter says out loud cites a
report id and carries the value being asserted. `deck_architecture.py` resolves each claim
against the report and fails closed on disagreement.

Why it is built this way: a readout deck is the artifact that outlives the engagement. It gets
forwarded, re-presented, and quoted by people who were not in the assessment. A deck that has
quietly drifted from its report — a stale percentage, a citation to a renumbered finding, a
priority gap dropped to save four minutes, an UNKNOWN rounded into a number so the slide looks
finished — is worse than no deck at all. Those four failures are rules R003, R002, R005 and
R004 below, and each has a test.

## Run it

```bash
cd revenue/uiowa_rfq_18649_readout_deck

# check the worked example against its report (exit 0 = agrees, 1 = drifted)
python3 deck_architecture.py check  --report data/example-report.json \
                                    --deck   data/example-readout-deck.json

# regenerate every view from the data
python3 deck_architecture.py render --report data/example-report.json \
                                    --deck   data/example-readout-deck.json \
                                    --outdir examples

# the rule table, self-documenting
python3 deck_architecture.py rules

# tests
python3 -m unittest -v test_deck_architecture
```

Python 3 standard library only. No installs, no network, no clock, no RNG — two operators get
byte-identical output, and a test asserts it.

## What is in here

| Path | What it is |
|---|---|
| `deck_architecture.py` | The engine: loader, report index, 16-rule agreement checker, four renderers, CLI. |
| `data/example-report.json` | The synthetic example report. **Source of truth** for the worked story. |
| `data/example-readout-deck.json` | The worked readout deck: 7 core slides + 7 appendix slides, speaker notes on every core slide. |
| `templates/readout-deck-template.json` | The blank editable template — the reusable structure with the rules written into it. |
| `examples/readout-deck.md` | Rendered deck, with each slide's claims shown beside the report's values. |
| `examples/readout-deck-ascii.txt` | ASCII slide frames + track map + open inputs. 78 columns, no color. |
| `examples/readout-planning-table.csv` | The underlying planning table: one row per claim, deck value beside report value. |
| `examples/deck-report-agreement.md` | The agreement report for the current deck. |
| `test_deck_architecture.py` | 56 tests, `unittest`. |

Everything in `examples/` is generated. Change the deck or the report and re-run `render`.

## The deck structure

Seven core sections, fixed and in this order, because the order is the argument:

`purpose` → `evidence` → `strengths` → `priority_findings` → `roadmap` → `resources` → `decisions`

Detail lives in the appendix, and that is enforced in both directions. A core slide over the
executive readability budget is an error (`R012`) — that material is detail and belongs behind
the main body. An appendix slide no core slide reaches is a warning (`R009`). So "keep the
support in an appendix" cannot quietly degrade into "delete the support."

**Two audiences, one deck.** The executive path is the core slides and must fit the declared
session length. The practitioner path is the same slides plus their drill-downs; the ASCII
track map prints which appendix slide answers which main slide, so the presenter can jump
without hunting.

## The rules

| Rule | What it enforces |
|---|---|
| R001_SECTION_ORDER | Core sections all present, once each, in the canonical order. |
| R002_DANGLING_CITATION | Every claim cites an id that exists in the report. |
| R003_FIGURE_DISAGREEMENT | A figure on a slide equals the report's value **and** unit. |
| R004_UNKNOWN_FABRICATION | A measure the report leaves UNKNOWN is not asserted as a number. |
| R005_OMITTED_PRIORITY_FINDING | Every high-priority report gap reaches a core slide. |
| R006_UNVALIDATED_STRENGTH | "Validated strength" only where the report validated it. |
| R007_PHASE_DISAGREEMENT | A recommendation's phase on a slide equals its roadmap phase. |
| R008_MAIN_CLAIM_WITHOUT_APPENDIX | A main-body figure names an appendix slide carrying the same id. |
| R009_ORPHAN_APPENDIX | Every appendix slide is reachable from a core slide. *(warning)* |
| R010_AGENDA_OVERRUN | Core minutes fit the declared session length. |
| R011_MISSING_SPEAKER_NOTES | Every core slide carries a speaker-note prompt. |
| R012_DETAIL_IN_MAIN_BODY | Core slides stay inside the executive readability budget. |
| R013_UNRESOLVED_MEASURE | A cited measure name exists on the cited report object. |
| R014_DECISION_UNLINKED | A decision resolves to a recommendation whose phase agrees. |
| R015_REPORT_MISMATCH | The deck's `report_ref` is the report being checked against. |
| R016_AGENDA_UNDERRUN | Core minutes use a reasonable share of the session. *(warning)* |

A failed check also stamps the rendered Markdown deck: **"Deck-to-report agreement: FAILED —
do not present it until the disagreements below are resolved."** A drifted deck cannot render
as a clean handout.

### The checker found a real hole in the worked example

On its first run against the example deck, `R008` failed:

```
| error | R008_MAIN_CLAIM_WITHOUT_APPENDIX | S-04 |
  S-04 claim 3 states a figure for F-004 with no appendix slide carrying that id |
```

The executive slide said "two of nine ESS services have no recorded alert routing owner" and
nothing in the appendix carried F-004. Challenged on that number in the room, the presenter
would have had nothing to turn to. The deck was fixed (appendix slide S-A7 added), not the
rule. That is the rule earning its place.

## Readable without color

The ASCII view carries agreement state in **marks, not color**:

```
|   CLAIMS AGAINST THE REPORT                                                |
|    [ok] F-002.single_approval_rate_pct  deck=58  report=58  percent        |
|    [??] F-003.demonstrated_recovery_time_hours  deck=UNKNOWN (not          |
|         assessed)  report=UNKNOWN (not assessed)  hours                    |
```

`[ok]` deck figure equals report · `[??]` UNKNOWN in the report and shown as UNKNOWN ·
`[XX]` disagrees · `[->]` link only, no figure. A photocopy, a screen reader and a projector
with the color balance wrong all lose nothing. Every line is exactly 78 characters and pure
ASCII; a test asserts both, and asserts there are no terminal color escapes.

## UNKNOWN is a first-class value

Where the report has no evidence, the measure's value is the literal string `"UNKNOWN"` with a
`basis` saying why. The deck is **required** to carry it as UNKNOWN:

- asserting a number where the report says UNKNOWN is `R004_UNKNOWN_FABRICATION` — an error;
- showing UNKNOWN where the report has a number is `R003_FIGURE_DISAGREEMENT` — also an error;
- `0` is not an accepted stand-in, and a test asserts that `0` and `"UNKNOWN"` produce
  different outcomes.

Nothing here converts an absent input into a zero, a pass, or a maturity score. The renderers
print every UNKNOWN measure under **OPEN INPUTS** with the reason it is open, so the gap is on
the slide rather than hidden behind one.

## What is real and what is draft

**Real and working now:** the checker, all 16 rules, the four renderers, the planning table,
the CLI, the determinism guarantee, and the 56 tests. Run them; the output is the evidence.

**Draft:** the deck structure itself — section list, minute budget (45), readability budget
(6 bullets / 180 characters per core slide). These are sensible defaults for a leadership
readout, not a validated standard, and they are constants at the top of the module for exactly
that reason.

**Fiction, and labeled fiction:** the entire worked story. Northgate State University does not
exist. Every finding, figure, record and locator in `data/` is invented to exercise the engine.
The example shows both a real strength (ESS records a test result on every sampled change) and
real gaps (IAM deployments recording one approval where the procedure requires two; RIS backups
completing with no restoration ever exercised). **None of it is a University of Iowa finding,
and nothing in this lane should ever be presented as one.**

## University inputs that stay UNKNOWN

This lane has had no contact with the University and holds no University data. These remain
open and are not guessed at anywhere in the code or the fixtures:

- The real assessment report — its findings, its figures, its evidence register, and its
  finding/recommendation id scheme. The engine is agnostic to the ids; it only requires that
  the deck cites ids the report actually carries.
- The real roadmap phase assignments (UIOWA-085's lane). This lane consumes
  `roadmap.items[].phase` as an input contract and does not compute phases itself.
- The actual readout audience, session length, and whether leadership and practitioners are in
  one session or two. `session_minutes` is a declared input; 45 is a placeholder.
- Which strengths the assessment team is prepared to call *validated*, and which stay
  candidates. The engine enforces the distinction; only the team can make the call.
- Real one-time and recurring resource estimates. `RES-002` is deliberately left UNKNOWN in
  the example to demonstrate that an uncosted recommendation reaches the slide as UNKNOWN
  rather than being dropped or guessed.

## Scope limits

No certification, compliance, or peer-percentile claim is made or computed. No maturity score:
the roadmap describes each phase by the evidence it is expected to produce, and the example
report says so in `roadmap.progression_note`. No individual performance scoring — findings
address the record a process leaves, never a person, and the worked example says that on the
slide.
