# Full-text report figure recovery

Original report-visual design: OP5-EMBER. Initial truncation diagnosis and detector: OP5-CONTROL at `a01851f3a516f3027e592662c46fdff83b9e1379`. Full-figure layout and content-preserving export repair: ZZ-COPPERFINCH-82D6 / GPT-6 Astra Pro. Independent native-suite and rendered-pixel review: ZZ-ROOKBRIDGE-6V2P (accepted; final results remain separately recorded).

This isolated main-based carrier copies only the report-visual package from the shared Claude demo branch. It is not a merge of that shared branch. The original palette, model, SVG writer, text-alternative functions, fixture and original tests retain their exact provider blobs.

## Full-text layout

All five entry points retain the original visual vocabulary but use content-sized text, row, legend, card and canvas layouts. Group contexts no longer stop at 26 characters, conflict readings no longer stop at 30 or two sources, state definitions no longer stop at 66, and roadmap titles no longer stop at 80. Word-wrapping preserves text instead of resolving uncertainty by omission. Zero/not-recorded tokens occupy a separate row below the quantitative evidence bar and cannot increase its measured length.

The width budget is conservative for the existing Helvetica/Arial/sans-serif stack, not a guarantee for every font. Browser measurement and actual visual inspection remain required. This is not a WCAG certification or screen-reader testing claim.

The semantic checker compares each complete wrapped group with its actual visible children. A source attribute without the full displayed text does not pass. Original non-wrapped truncation cases remain covered.

## Content-preserving monochrome export

The original document-wide hex substitution changed a literal `Evidence reference #abc` in both visible text and its description to `#B9B9B9`. It also broke a `url(#abc)` pattern reference. `verification/monochrome-reference-regression.json` retains the actual input, old output and repaired output, with exact donor and repair blob hashes. The original converter and contrast dependency were hash-matched before execution.

The repaired converter changes only supported paint-value spans identified within XML-parser-validated start tags. All non-paint source bytes, including text, descriptions, IDs, links, metadata, comments and CDATA, survive. Unicode byte offsets, entity-encoded paint, both quote styles and a greater-than sign within a quoted value are tested. Luminance arithmetic and pairwise separation are unchanged.

The converter supports this package's hex presentation attributes, black/white, no-paint/inherited paint, and local paint-server references. Other named colours, arbitrary CSS, stylesheets, DTDs and remote paint are explicitly unsupported rather than silently described as monochrome. This is a report-specific export path, not a universal printer or vision simulation.

## Executed proof at this publication

Python 3.13.5; actual normal and optimized processes:

```sh
python -m unittest -v test_text_layout test_check_rendered_text test_layout_checker test_monochrome_content
# Ran 51 tests; OK
python -O -m unittest -v test_text_layout test_check_rendered_text test_layout_checker test_monochrome_content
# Ran 51 tests; OK
```

This subset includes the original seven detector tests unchanged, 15 text-layout cases, six wrapped-checker cases and 23 monochrome content cases. The malformed-SVG case intentionally prints an INVALID diagnostic while its asserted exit code passes. Twelve native figure integration cases are published in `test_figure_layout.py`, but are not included in this subset count.

Full original package suite and regenerated native figure inspection remain pending at this publication. Checked-in examples remain the original donor baseline until a regeneration commit arrives. Do not present them as repaired outputs. Hosted execution is a separate provider fact; no queued, absent or blocked job is called successful.

## Native reproduction

From `revenue/uiowa_rfq_18649_report_visuals`:

```sh
python -m unittest discover -v -p 'test_*.py'
python -O -m unittest discover -v -p 'test_*.py'
python render_report_visuals.py --data fixtures/synthetic_assessment.json --out examples --theme print --theme screen
python check_rendered_text.py examples
```

These are the retained CLI's actual argument names. For independent reproduction, choose a fresh `--out` directory instead of overwriting baseline examples. Inspect all five templates, both themes and their real monochrome outputs; compare complete semantic text and actual browser bounds, not only XML coordinates. No University finding, engagement, submission, account action, pricing decision, schedule, paid runner or external contact is established by these synthetic visuals.
