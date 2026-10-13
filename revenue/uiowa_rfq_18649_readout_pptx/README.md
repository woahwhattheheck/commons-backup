# Editable readout PowerPoint export

Exports the existing UIOWA-088 report/deck JSON contract to native editable
PowerPoint text. The report remains the source of truth and the original
`deck_architecture.py` performs agreement checks before export.

The ready-to-open `readout-example.pptx` contains the original seven core and
seven appendix slides. Every slide carries a visible synthetic label. Exact
claim IDs, values, units and UNKNOWN states stay editable. Speaker prompts and
complete claim records are in native notes. Supporting-detail links jump to the
appropriate appendix slide, with return links to its core slide.

## Build

Requires Python 3.10+, Node.js and a provisioned `@oai/artifact-tool` 2.8.74
package resolvable by `build.mjs`. The repository does not vendor that dependency.
No provider or model calls occur during export.

From this directory:

```bash
python3 export_pptx.py \
  --report ../uiowa_rfq_18649_readout_deck/data/example-report.json \
  --deck data/example-readout-deck.json \
  --out /tmp/readout-example.pptx --font 'Bitstream Charter'
```

`--node` selects the Node executable. `--font` selects the installed font to
encode; use the same font when rendering. The supplied deck uses Bitstream
Charter. An application without it may substitute a font and change wrapping.
`--parent-engine` supports partial checkouts while retaining the real checker.
The checked output was rendered and inspected on all fourteen slides with the
bundled presentation renderer. Native PowerPoint execution is not claimed.

The exporter returns one for deck/report disagreement and two for input or
output errors. It retains existing files and requires a new output path.
The current layout supports at most three body paragraphs and four claim rows
per slide. Keep longer discussion in notes or add an appendix; inspect rendered
slides after changing text because character count does not prove visual fit.
PPTX package metadata and generated shape identifiers may vary between builds;
the intended reproducible contract is slide content, notes and navigation.

## Source and explicit editorial changes

Architecture, fictional report, original deck data, template and Python checker
come from Driftwood's commit `4056207a59953944fd8f8ca9ec2d4576e988088e`, restored
under `../uiowa_rfq_18649_readout_deck/`. The original engine and JSON inputs are
unchanged. This exporter complements that work instead of replacing its engine.

`data/example-readout-deck.json` is an explicit presentation-input copy with the
three previously identified prose corrections:

- S-01 introduces three decisions, matching D-001 through D-003.
- S-04 says no restoration exercise was *recorded*, preserving the evidence limit.
- S-A1 labels its two citations as selected locators rather than the complete register.

Every claim object, speaker prompt, source slide ID and support relationship is
preserved. The generic exporter does not silently rewrite supplied deck copy.
The original fourteen-slide scope remains intact. All example institutions,
findings and figures are fictional preparation material, with no University
finding, outreach, appointment or spending authorization.
