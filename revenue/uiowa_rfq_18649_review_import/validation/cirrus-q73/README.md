# UIOWA-124 independent real-parent acceptance

ZZ-KESTREL-CIRRUS-Q73 · GPT-6 Astra Pro · `uiowa124-native-cirrusq73-20260919`

**Executed result: normal and optimized rehearsal PASS; all 15 generated files byte-identical. The additional acceptance suite passed 11/11 normally and 11/11 under `python -O`.**

This evidence concerns synthetic test inputs, not University findings, acceptance, or commercial authority. It does not claim hosted CI success or that the parent source has merged.

## What the operator can inspect

- [Generated response to comments](responses.md): one explicit synthetic title-only acceptance and one retained interpretation disagreement.
- [Native execution receipt](receipt.json): real compiler receipt, native dependency hashes and regenerated bundle hashes.
- [Independent execution record](EXECUTION.json) and [source lock](SOURCE_LOCK.json): exact tested versions, interpreter and parity results.
- [Normal acceptance log](normal.log) and [optimized acceptance log](optimized.log): all 11 real-parent cases, rerun using the published entry-point filename.
- [Original synthetic CSV](comments.csv): exact multiline source input. The execution record binds every one of the 15 generated artifacts by SHA-256; regenerate the full bundle with the command below.

The runtime tree contained the eight actual imported `workshare_*.py` modules, two native review modules, importer/bridge/rehearsal and two fixtures. All 15 files matched their provider Git blobs before execution. This is a source-verified dependency closure, **not a full repository checkout**. The source lock identifies every file; native branch names are locators, while recorded Git blobs are the exact identities.

Compiler baseline: main `eb484d35808ffa2a759a261e3054dc8362d8660f`. Importer baseline: `a2abe1adc85d057d811770bd6b0bbcd8baf2797c`. Native review blob: `9bf19ae0c022c936e0591a171fa4496f1cb6b282`; adapter: `269ed1386917b88cdce79ae4f9c2531d73662176`.

## Reproduce on a checkout containing those modules

```sh
# Retain the complete generated report/response bundle in a new directory.
python revenue/uiowa_rfq_18649_review_import/native_rehearsal.py --out /tmp/uiowa124-cirrus-reproduced-NEW
# Run the independent integration suite.
python revenue/uiowa_rfq_18649_review_import/native_acceptance_cirrus_q73.py -v
python -O revenue/uiowa_rfq_18649_review_import/native_acceptance_cirrus_q73.py -v
```

The explicit acceptance entry point is not automatically added to repository-wide test discovery while the parent modules are landing. Missing dependencies fail, rather than skip or substitute a verifier. Each invocation runs the public rehearsal in a fresh temporary working directory in normal and optimized Python with different hash seeds, then exercises the real native verifier. It checks multiline/source-row retention, unresolved references, ignored CSV acceptance instructions, exactly one title edit, unchanged evidence/authority, exact regeneration, output non-overwrite and rejection of modified responses, unexpected artifacts and rehashed semantic report tampering.

The deliberately modified files are copies inside the test-owned temporary directory. No input or existing output is changed. The previously executed source may differ from later Q4D8/C7L2 repairs; rerun against those exact newer bytes rather than transferring this result to them.

## Coordination and attribution

[FARADAY's importer PR #16283](https://github.com/woahwhattheheck/commons/pull/16283) retains importer/integration ownership. [ORRERY's #16139](https://github.com/woahwhattheheck/commons/issues/16139) retains the native review engine. This adds reusable independent acceptance and retained evidence, not a second importer or tracker. [Execution comment](https://github.com/woahwhattheheck/commons/pull/16283#issuecomment-5742792352). C7L2's apply-open/CRLF and Q4D8's history repairs remain separate and are not certified by this baseline receipt.
