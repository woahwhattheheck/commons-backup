# L3 rival-gate fail-closed correctness donor

Canonical V4 custody of the Struct-safe fail-closed L3 repair reviewed in V3.1 PR #12565. This is a theorem/test donor, not a patch to the current V4 router.

Exact reviewed artifacts:
- `repair.patch`: Git blob `84becf2f6135e2d9155863cf6887a340a7852dba` (6,162 B);
- `test_failclosed.py`: Git blob `eeb07459a70a30eae689fc3e706d31b1916a6d97` (8,187 B), 17 focused source contracts in the reviewed staging workflow;
- reviewed staging head: `84d3cfe1616d5e4d6802cf12f43e11ff8cb44400`.

The repair replaces the retired fail-open opening classifier with a fail-closed theorem: only a complete, contiguous, strictly typed 143-step public opening may certify OFF_TAPE and allow L3 to suppress incumbent E184 late-sale reservation. Missing/gapped/malformed/type-poisoned/partial evidence is treated as on-tape and preserves the incumbent behavior; the final decision is frozen until rewind/new game.

Do not `git apply` this patch to current V4 as-is: its hunks target the historical V3 `r04_full_router.py` layout and old sale-policy call site. Do not revive the older fail-open classifier. Any V4 semantic port must re-derive the call site against current source, retain strict type/cardinality/contiguity/frozen-decision contracts, and run the focused donor tests (or an audited equivalent) plus current V4 regression gates before activation.
