# Deck-to-report agreement report

Deck `AIS-READOUT-EXAMPLE-2026` checked against report `AIS-ASSESS-EXAMPLE-2026`.

**Result: PASS** - 0 error(s), 0 warning(s).

No disagreements. Every figure on a slide equals the report's value, every high-priority gap reaches a core slide, and every main-body figure is backed by an appendix slide carrying the same id.

## Rules applied

| Rule | What it enforces |
|---|---|
| R001_SECTION_ORDER | Core sections are all present, once each, in the canonical readout order. |
| R002_DANGLING_CITATION | Every claim cites an id that exists in the report. |
| R003_FIGURE_DISAGREEMENT | A figure stated on a slide equals the report's value and unit. |
| R004_UNKNOWN_FABRICATION | A measure the report leaves UNKNOWN is not asserted as a number on a slide. |
| R005_OMITTED_PRIORITY_FINDING | Every high-priority report gap is cited by at least one core slide. |
| R006_UNVALIDATED_STRENGTH | A slide calls something a validated strength only if the report validated it. |
| R007_PHASE_DISAGREEMENT | A recommendation's phase on a slide equals its phase in the report roadmap. |
| R008_MAIN_CLAIM_WITHOUT_APPENDIX | A core slide stating a figure names an appendix slide that carries the same id. |
| R009_ORPHAN_APPENDIX | Every appendix slide is reachable from at least one core slide. |
| R010_AGENDA_OVERRUN | Core slide minutes fit the declared session length. |
| R011_MISSING_SPEAKER_NOTES | Every core slide carries at least one speaker-note prompt. |
| R012_DETAIL_IN_MAIN_BODY | Core slides stay inside the executive readability budget. |
| R013_UNRESOLVED_MEASURE | A cited measure name exists on the cited report object. |
| R014_DECISION_UNLINKED | A decision resolves to a recommendation whose phase agrees with the decision's. |
| R015_REPORT_MISMATCH | The deck's report_ref is the report it is being checked against. |
| R016_AGENDA_UNDERRUN | Core slide minutes use a reasonable share of the declared session (advisory). |

