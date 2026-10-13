# From source text to a defensible quotation

**Executed fictional examples, not University findings.** This guide is an operator-facing readout of the composed UIOWA-032 extractor. It explains what changed, what a reviewer can quote, and what still requires the original document. It complements [SABLE's PDF document-error guide](PDF_DOCUMENT_ERRORS.md), rather than replacing it.

**Publication states are separate:** this document may be on main while the runtime repair is still under review or awaiting provider execution in [canonical PR #16309](https://github.com/woahwhattheheck/commons/pull/16309). The demonstrated runtime is pinned below. Do not assume a main checkout already contains it.

## The six TXT/DOCX examples actually executed

The identical input bytes were passed to the original extractor and the composed candidate. Neither changed any input. Full input bytes, output objects, source digests and logs are retained in the [execution archive](https://github.com/woahwhattheheck/commons/blob/f471b2a043e0c4b3e017eb5d087af96c5edbff5b/revenue/uiowa_rfq_18649_document_extraction/C5_EXECUTION.json.xz); [decoding and replay instructions](https://github.com/woahwhattheheck/commons/blob/f471b2a043e0c4b3e017eb5d087af96c5edbff5b/revenue/uiowa_rfq_18649_document_extraction/C5_EXECUTION.md) require only Python's standard library to read the record.

| Fictional input | Original observed output | Composed observed output | Practical consequence |
| --- | --- | --- | --- |
| A Markdown code fence containing `# This is a code comment` | The comment becomes a heading; following evidence inherits that invented section. | The only heading is `Release practice`; lines 2–6 remain one literal code/text segment. | A reviewer follows the actual section, not a heading invented from example code. |
| A line of evidence with blank lines around it | Text is stripped but its locator remains `lines 2-5`. | Text keeps its two leading and two trailing spaces; locator is `lines 4-4`. | The quoted characters and locator refer to the same source span. |
| Text inside a Word content control | `unreadable`, no segments. | `Fictional wrapped evidence.` at `sdt 1/sdtContent/paragraph 1`; status remains `partial`. | Useful supported text becomes available, while the structural locator and page-number limitation remain explicit. |
| Inline Word compatibility alternatives, one reading `APPROVED`, the other `DECLINED` | `APPROVEDDECLINED`. | An empty, unreadable segment at `paragraph 1`, with `DOCX_ALTERNATE_CONTENT_NOT_EXTRACTED`. | The adapter does not manufacture a statement by concatenating alternative representations. Inspect the original before quoting. |
| Those alternatives inside a heading, after `Prior heading` | Following evidence inherits `APPROVEDDECLINED`. | Following evidence has `heading_path=["(unresolved heading)"]`. | Uncertainty about the section is not hidden behind an invented title or an unrelated previous heading. |
| The Word run `re` + `w:noBreakHyphen` + `sign` | `resign`. | `re‑sign`, retaining U+2011. | A displayed hyphen survives instead of silently changing the word. |

These DOCX cases are minimal OOXML parser fixtures, not polished Word documents or a test of rendered appearance. The result is not a claim of complete Word format support.

## A worked decision: the conflicting approval text

The original extraction emitted a string that appears in neither alternative alone. That string must not enter a finding, a summary or a quotation. The repaired result is deliberately less assertive:

```text
status: unreadable
locator: paragraph 1
text: ""
warning: DOCX_ALTERNATE_CONTENT_NOT_EXTRACTED:paragraph 1;
         entire paragraph withheld; inspect original
```

The useful next action is to inspect that exact source version and paragraph in an appropriate document reader, then retain the verified passage and its provenance. The warning does **not** mean the source paragraph was empty, that approval was absent, or that either alternative was authoritative. Withholding is a disclosure of the adapter's limit.

A similar rule applies to a table: an affected table is withheld rather than making an ambiguous cell look like a genuinely blank value. CAESURA's unchanged tests also cover that case, content-control locators, clean headings after an unresolved heading, and deleted/drawing content that should not erase unrelated current prose.

## Keep the complete evidence reference

Retain the document SHA-256, complete segment locator, extracted text, heading context, document warnings and segment warnings together. A digest ties the output to bytes; it does not authenticate those bytes or establish the truth of their contents. DOCX locators describe OOXML structure, not printed pages. A `partial` result is not a guarantee of completeness, and `unreadable` must not become a finding of no practice.

The extractor opens the source once into a bounded snapshot and uses that same snapshot for parsing, byte count and SHA-256. `--output` exclusively creates a new file; it refuses an existing report or source alias. A failed write may leave an incomplete newly created output, so check the exit code. Shell redirection is outside that protection: never redirect into source evidence or an existing report.

## Reproduce the actual comparison

Use an authorized disposable cloud checkout of [publication f471b2a0](https://github.com/woahwhattheheck/commons/commit/f471b2a043e0c4b3e017eb5d087af96c5edbff5b), not Bryce's computer and not a live evidence directory. From that checkout's repository root:

```sh
scratch=$(mktemp -d)
git show 1b9cdfe426fc83d0da5c65b20e10ec63da8b6da2:revenue/uiowa_rfq_18649_document_extraction/extract.py > "$scratch/original_extract.py"
cd revenue/uiowa_rfq_18649_document_extraction
python -m pip install -r requirements.txt
python replay_fidelity.py --baseline "$scratch/original_extract.py" --output "$scratch/normal"
python -O replay_fidelity.py --baseline "$scratch/original_extract.py" --output "$scratch/optimized"
```

The replay verifies both source identities before compiling the exact checked byte buffers. It creates eight fictional inputs and `rehearsal.json` in a new directory. All **eight explicit comparison checks** passed; normal and optimized runs produced byte-identical nine-file packets. Wrong-source and existing-output trials exited 2 without creating the refused output or changing retained output bytes. The two PDF cases in that packet demonstrate a named page-tree error and an explicit zero-page warning; use the separate PDF guide for their operator interpretation.

The replay is intentionally pinned. A different source generation is refused, not silently treated as the same demonstration. Installing dependencies in the recipe is an operator prerequisite; the recorded run used an isolated, hash-verified pypdf 6.19.0 installation.

## Source and verification record

Original runtime: `d275410fe0842426ad32bf9d15da4f69beaba463` from #16120. Composed runtime: `765d9601b3f1fef8ee6cd2517d71018eaafc593d`, first published at [ec45f79b](https://github.com/woahwhattheheck/commons/commit/ec45f79bfd88a30d8eca1050d8ea6b879d592880) and unchanged in f471b2a0. Replay utility: `71630d5aa83ae76dce26bc347bfbe7b2e47fae4c`.

The composed runtime passed **85/85 distinct unittest methods in each of normal, optimized and ResourceWarning-strict execution**, on CPython 3.13.5/Linux and pypdf 6.19.0, with zero outer-suite skips. Those are 85 methods exercised three ways, not 255 distinct tests. The eight operator checks are reported separately. Native absent-backend subtests deliberately verify explicit skips and the dependency error; those are not a PDF-backend pass. These are actual cloud-container runs, not Commons GitHub Actions.

Attribution: original extractor **ZZ-Sol**; snapshot/locator implementation **CELADON-DX32**; independent DOCX diagnosis, two-defect repair and retained acceptance cases **CAESURA-5812F333**; PDF contribution **SABLE-6D4F-R15**; current fixture/dependency work **MICA-83D9, KESTREL-P8R and Solstice-ZZ**; composition and this executed readout **CELADON-DX32-C5 / GPT-6 Astra Pro**. [Full composition contract and source map](https://github.com/woahwhattheheck/commons/blob/f471b2a043e0c4b3e017eb5d087af96c5edbff5b/revenue/uiowa_rfq_18649_document_extraction/COMPOSED_FIDELITY.md).

No University records, live-system access, pricing or personal-profile material, customer communication, appointment or approval is created by these examples.
