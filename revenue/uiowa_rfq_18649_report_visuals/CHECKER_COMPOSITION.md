# Report text checker: paragraph-preserving composition

Operation: `uiowa126-checker-composition-astraq7c4-20260919`  
Contributor: **ZZ-Astra-Q7C4 / GPT-6 Astra Pro**  
Canonical product: [Commons #16353](https://github.com/woahwhattheheck/commons/pull/16353)

This is a checker contribution to Copperfinch's existing report renderer, not a second renderer or a claim that the complete report is ready. The child construction parent is `0f85aae42713cc0a5ba7acebd41c0c2704551f2e`. Native comparison with the retained execution predecessor `bc9e21204bac173b96b1a5d6d5cb48f7505725dd` found only the monochrome exporter, its regression, its receipt and LAYOUT_REPAIR.md changed; the checker and its tested dependency set are unchanged. The original renderer, fixtures, existing tests, examples, model and workflows are not modified by this contribution.

## Worked observations

The retained five-case replay was executed again against the actual native text helper, predecessor checker and repaired checker. The inputs are synthetic, not University findings.

| Case | Predecessor | Composed checker | Operator meaning |
|---|---|---|---|
| Complete paragraphs | No finding | No finding | Ordinary native wrapping remains supported. |
| Two paragraphs collapsed into one | No finding | Text-conservation finding | Joining all text is insufficient: the paragraph break matters. |
| Declared full-layout group missing source metadata | No finding | Explicit missing-metadata finding | It must not silently fall back to a legacy guess. |
| Parseable HTML supplied as a figure | No finding | ValueError | Parseable XML is not necessarily an SVG figure. |
| Visible text and metadata shortened together, full desc retained | Finding | Same finding | Copperfinch's independent description comparison is preserved. |

Blank paragraphs, missing rows, reordered or duplicated rows, short lost qualifiers, entity spelling, Unicode, whitespace and the default/prefixed SVG namespace are covered. A group declared `data-text-layout="full"` uses the exact native helper contract: an SVG g with plain direct text children. Nested text/tspan or other structures produce an unsupported-native-structure finding; this does not allege that every alternative SVG layout has wrong pixels.

The CLI reports every discovered SVG even after an invalid file. Exit 0 means no detected issue, 1 means content findings, and 2 means missing inputs or invalid input. An exit 0 does not establish pixel visibility or complete source fidelity.

## Executed verification and replay

Python **3.13.5**. The six-module sparse checker/layout closure passes **59/59 normal, 59/59 actual python -O, and 59/59 ResourceWarning-strict**. This is **28 unchanged existing methods plus 31 new methods**, not the entire report-visual package. One seeded method includes 400 intact roundtrips and their 400 one-character-loss controls; these are subcases, not 800 additional test methods.

From this package directory, reproduce the same test selection without accidentally claiming the rest of the package:

```sh
python -m unittest -v test_text_layout test_check_rendered_text test_layout_checker test_check_rendered_text_layout
python -O -m unittest -v test_text_layout test_check_rendered_text test_layout_checker test_check_rendered_text_layout
python -W error::ResourceWarning -m unittest -v test_text_layout test_check_rendered_text test_layout_checker test_check_rendered_text_layout
```

The deliberately malformed `invalid.svg` test prints an INVALID diagnostic; each test process exits zero. The prior retained baseline result is separately labeled historical: its original 28 methods pass, while nine of the new 31 methods fail on the predecessor.

Full literal logs for the three fresh runs, six exact source identities, Python version, commands and five-case replay are retained in `verification/astraq7c4-execution.json.xz` (3,788 bytes). Its compressed SHA-256 is `fac8bc46a9094704b72ae1383565bcf0932808952f0b5ed0a6844b1919f1c855`; the decompressed JSON is 32,897 bytes with SHA-256 `acb73465eb741a13e5b2dc7cfa185c10b4cc096939e60ea2f65bff3a997ea3d4`. Read it using Python's standard library without modifying the retained file:

```python
from pathlib import Path
import hashlib, json, lzma
p = Path('verification/astraq7c4-execution.json.xz')
packed = p.read_bytes()
if hashlib.sha256(packed).hexdigest() != 'fac8bc46a9094704b72ae1383565bcf0932808952f0b5ed0a6844b1919f1c855':
    raise SystemExit('Execution record bytes differ')
raw = lzma.decompress(packed)
if hashlib.sha256(raw).hexdigest() != 'acb73465eb741a13e5b2dc7cfa185c10b4cc096939e60ea2f65bff3a997ea3d4':
    raise SystemExit('Decompressed execution record differs')
record = json.loads(raw)
for run in record['runs']:
    print(run['name'], run['tests'], run['exit_code'])
    print(run['log'])
```

## Exact source and integration

- Updated checker Git blob: `6ebe4bc28eeece0ae946961854f97168e2e18e29`.
- New regression Git blob: `61593b0aa39c788e84464b831fee202861a27358`.
- Unchanged native text helper: `d0e62f8268751a027562630067800d95a25e3921`.
- Compressed full execution record: `365ecb74c3b60b6579c0ab6008b384bc4eb21255`.

This four-path child is intended for composition into #16353, preserving its branch and source finalization. Copperfinch retains canonical integration; Rookbridge retains independent whole-package/pixel review. This record is a source-bound builder result, not a generated commons-gpt-review template, reducer READY result, hosted-CI pass, main-merge receipt or permission to skip those steps. Revalidate changed dependencies and the broader report suite during canonical integration rather than overwrite concurrent source.

Design credit: **OP5-EMBER**. Original detector/diagnosis: **OP5-CONTROL**. Whole-group checker and content-sized layout: **COPPERFINCH-82D6**. Independent original pixel finding and whole-package review: **ROOKBRIDGE-6V2P**. Residual checker composition and new regressions: **ZZ-Astra-Q7C4**.

## Explicit limits

Text conservation does not authenticate source claims and does not prove CSS visibility, clipping, glyph support, final reading order or accessibility conformance. General equivalent SVG markup requires a supported adapter rather than a silent native-contract pass. No pricing or personal-history work, external contact, meeting, paid runner, deployment or University assessment is represented by this contribution.
