# Sublime electrochemical cement batch qualification dossier

Operation: `SUBLIME-CEMENT-BATCH-DOSSIER-ZHBR5Q8-20260913`.

This package is a deterministic, read-only evidence **dossier assembler** for a bounded cement-manufacturing acceptance fixture. It joins eight source domains:

1. feedstock lot + mineral-assay evidence;
2. electrochemical recipe revision;
3. reagent lot + COA evidence;
4. equipment + calibration evidence;
5. in-process chemistry;
6. fineness + strength test records;
7. evidence labeled for ASTM C1157;
8. COA-to-delivery-lot mapping.

Every source section must explicitly report `source_status` as either `AVAILABLE` or `HOLD`. The assembler never infers a pass state. A batch with one or more `HOLD` source sections emits one explicit exception per held fault class and no complete dossier. A batch whose eight source sections are all explicitly `AVAILABLE` emits `DOSSIER_COMPLETE`, which means only that the required evidence is present in the supplied packet.

`DOSSIER_COMPLETE` is **not** an ASTM conformance decision, material or structural suitability judgment, production release, batch disposition, or shipment approval. The result embeds an authority map with every such action set to `false`.

## Golden acceptance

The focused suite builds 96 deterministic synthetic batches. Exactly 24 are bad: three batches in each of eight fault classes. The required result is exactly:

- 72 complete dossiers;
- 24 batch+reason exception rows;
- three exceptions in each fault class;
- raw source ID + SHA-256 lineage for every included section;
- deterministic decision digest independent of input batch ordering;
- packet digest that still binds exact source list order.

## CLI

```bash
python revenue/sublime_cement_batch_dossier/engine.py packet.json
```

Input is strict UTF-8 JSON (duplicate keys and non-finite numbers are rejected) and is bounded to 2 MB. Invalid evidence exits `2` and emits no READY/pass state. The CLI and library have no provider, process-control, equipment, payment, customer-contact, or accounting side effects.
