# Cal-Maine pancake-line batch evidence gate

This package is a dependency-free, **read-only evidence compiler** for the bounded non-production pilot offered to Cal-Maine Foods. It turns one supplied synthetic/de-identified batch packet plus an owner-approved evidence policy into a deterministic `COMPLETE_FOR_OWNER_REVIEW` or `HOLD_FOR_OWNER_REVIEW` artifact.

It deliberately does **not** decide food safety, approve formula/allergen/label content, control a production line, change a recipe, disposition a lot, or authorize product release. The strongest state is owner review of supplied evidence.

## Evidence families

The compiler checks six declared defect families and binds every HOLD to the exact field and evidence SHA-256 that produced it:

1. `FORMULA_OR_ALLERGEN` — formula revision plus egg/wheat declarations.
2. `LABEL_OR_FILM` — label and packaging-film revision.
3. `LINE_OR_CALIBRATION` — line identity and calibration status.
4. `COOK_PROCESS` — bounded cook time, temperature, and finished weight.
5. `METAL_DETECTOR` — supplied detector-check evidence.
6. `LOT_LINEAGE` — supplied finished-lot ingredient/film lineage.

Snapshot generation, policy revision, complete-export assertion, evidence freshness, strict JSON shape, per-field evidence digests, and canonical UTC are separately fail-closed custody fences.

## Acceptance target

Run:

```bash
python -m revenue.cal_maine_pancake_batch_evidence.gate acceptance
python -m unittest -v revenue.cal_maine_pancake_batch_evidence.test_gate
python -O -m unittest -v revenue.cal_maine_pancake_batch_evidence.test_gate
```

The frozen acceptance generator produces exactly **256 synthetic packets**:

- 128 clean packets that must all compile COMPLETE;
- 96 packets with exactly one seeded defect each — **16 per defect family** — that must all be recalled as HOLD;
- 32 valid robustness packets at the exact freshness boundary with reordered evidence fields.

The acceptance gate requires recall `96/96`, false-complete `0`, all 128 clean COMPLETE, every seeded HOLD carrying source SHA-256 + field, zero network/source writes by the package, and three independent corpus compilations producing byte-identical manifests.

## Production CLI

`compile` intentionally has **no `--as-of` option**. It samples process UTC so a caller cannot backdate evidence into freshness.

```bash
python -m revenue.cal_maine_pancake_batch_evidence.gate compile packet.json policy.json receipt
python -m revenue.cal_maine_pancake_batch_evidence.gate verify receipt.json
```

Input JSON must be a bounded ordinary non-symlink file. Output publication is create-exclusive and refuses existing paths/final-component symlinks. JSON parsing rejects duplicate keys, unknown fields, floating/non-finite numbers, bool-as-int aliases, malformed canonical timestamps, and digest drift.

## Replay semantics

`compile_corpus()` collapses byte-equivalent replay of one `batch_id`; the same batch ID with changed bytes fails closed as a changed-payload replay. Corpus order does not affect canonical decision ordering or receipts.

## Data boundary

Checked-in fixtures are synthetic. Do not commit buyer/customer/product records or credentials. No function in this package performs network access or source-system writes.
