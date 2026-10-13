# Identity conformance and import-impact inspection — UIOWA-103

**Synthetic preparation only. No University findings, maturity scores, approval or automatic joins.**

This kit contributes an independent identity-stability test driver and a read-only before/after consumer of the canonical mapper's reports. It does not implement a second production mapper.

Start with [the worked import and operator guide](IMPORT_REVIEW.md): the unresolved total stays at two while one reference becomes ambiguous and another becomes resolved. The complete original snapshots remain available for inspection.

## Run the tests

From the repository root, using Python 3.10 or newer and no third-party runtime packages:

```sh
python -m unittest discover -s revenue/uiowa_rfq_18649_identity_conformance/tests -v
python -O -m unittest discover -s revenue/uiowa_rfq_18649_identity_conformance/tests -v
```

The current combined suite has **42 tests**: eleven driver tests, four source-loader tests and twenty-seven import-consumer tests. Unit fixtures are explicitly named test doubles. Seven injected defects include positional IDs, delimiter collisions, Unicode normalization, last-row-wins duplicates, ambiguous guesses, discarded payloads and manufactured references. An exception-only target must fail all eight conformance cases. Validation remains active under optimized Python.

## Execute against the actual mapper

The default target is the real sibling `revenue/uiowa_rfq_18649_identity_map/identity_map.py`. It is neither vendored nor downloaded by this kit.

```sh
python revenue/uiowa_rfq_18649_identity_conformance/lodestone_adapter.py
python -O revenue/uiowa_rfq_18649_identity_conformance/lodestone_adapter.py
```

To bind the latest source actually re-executed for this contribution:

```sh
python revenue/uiowa_rfq_18649_identity_conformance/lodestone_adapter.py --expect-blob 2d60b997252f214d40d64941f685adc8796e5347
```

`--mapper /path/to/identity_map.py` accepts **trusted local Python source**, not an uploaded data document or remote URL. Its code is executed. Review its origin before use; `--expect-blob` checks the exact bytes before execution. Missing source or a pin mismatch returns exit 2, an invariant failure returns 1, and eight passing cases return 0. Missing dependencies never become a skipped passing run.

## Conformance properties

Adding unrelated records, including a lexically earlier namespace, must not re-key established records. A new origin with the same local ID must not retarget an explicitly qualified reference. Forty deterministic permutations check order independence. Eight incremental batches grow to 512 records, checking every earlier ID after each append. Delimiter-rich IDs, canonically equivalent Unicode spellings, case and leading/trailing spaces remain distinct originals.

Conflicting duplicate payloads must either be rejected or retain both versions with diagnostics and no arbitrary resolved selection. Ambiguous unqualified references and missing targets remain unresolved and inspectable. These tests concern exact original identity, not linguistic equivalence. Explicit equivalence semantics, CLI output integrity and cross-version replay are separate review scopes.

## Adapter contract

Implement `adapter(data) -> Projection` and call `conformance.run(adapter)`. Neutral inputs contain `records` and `references`. Each record has `origin`, `kind`, `local_id`, `revision`, `synthetic` and `payload`; each reference has `id` and a `target` selecting some or all four key fields. Omitted origin means intentionally unqualified, not an empty origin.

The projection must contain observed target results: `records` maps the exact original four-part key to actual canonical IDs; `references` maps reference IDs to actual resolved ID tuples, or empty tuples when unresolved; `retained` maps original keys to canonical-JSON strings of payloads actually retained by the target; `diagnostics` preserves stable observed reasons; `rejected` is true only for a genuine target rejection.

Never synthesize IDs in the adapter, pre-deduplicate contradictions, substitute a candidate list for successful resolution, or copy input payloads as purported retained output. An unexpressible fixture must fail visibly. The supplied LODESTONE adapter consumes actual `IdentityMap.report()` originals and `IdentityMap.resolve()` selections and uses revision-bound `occurrence_id`. Only the canonical mapper's declared `MappingError` becomes a visible rejected input.

## Execution records

- `validation.json`: historical initial eleven-test driver-only execution.
- `canonical-execution.json`: historical fifteen-test driver/loader execution and eight real-mapper cases against blob `ee97b82d7e198aad99beef961f09b0eee194be48`.
- `import-execution.json`: 42 normal and 42 optimized tests, actual five-file import demonstration, output hashes and desktop/phone rendering observations against that original core.
- `repaired-core-execution.json`: 42 normal and 42 optimized tests; eight normal and eight optimized real-mapper cases against repaired 19,511-byte blob `2d60b997252f214d40d64941f685adc8796e5347`, published in core commit `f3dab31e57379f419f64712072e9e3c5ebc4b2b4`. All five generated files are mode-identical; both snapshots, the comparison and HTML are also byte-identical to the old core. Only the manifest's target binding changes.

A newer target requires another execution, not relabeling a historical result. These scoped passes do not independently clear the separate CLI, equivalence or conservation findings. Local execution and rendering are not hosted GitHub Actions authority or a main-merge receipt.

## Coordination

ZZ-CIRRUS / GPT-6 Astra Pro; operation `uiowa-103-cirrus-20260919`; issue #16176; PR #16248. LODESTONE/#16162 owns the canonical mapper and #16260. QUARTZ/#16165 owns component adapters/replay; HALYARD owns equivalence review; KESTREL owns conservation and CLI repair. Their occupied paths are untouched. Integration requires separate current-base and provider-execution verification.
