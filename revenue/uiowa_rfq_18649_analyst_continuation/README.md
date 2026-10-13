# UIOWA-138 — an exercised analyst handover

**SYNTHETIC preparation asset.** One assistant simulated discovery-to-synthesis continuation; no independent analyst, University evidence, customer delivery or acceptance is claimed.

Start with [HANDOVER.md](HANDOVER.md): exact current artifact, scope rationale, evidence locations, open inputs, review responses, next deliverable and relative calendar. The receiving analyst does not need to reconstruct Slack history.

Read the actual completed task in [SYNTHESIS.md](SYNTHESIS.md): three bounded findings preserve the ESS trace/version distinction, RIS batch-recovery/deployment distinction and IAM monitoring/restoration distinction. All three original UNKNOWNs remain visible.

[EXERCISE.md](EXERCISE.md) records five deliberately introduced handover gaps, their observed diagnoses and repairs, actual native-tool output, 32 normal plus 32 optimized test results and the clean exported-source replay. [SOURCE_REGISTER.md](SOURCE_REGISTER.md) identifies the retained source versions.

## Make a portable handover

`bundle.py` packages these published documents with all fourteen original UIOWA-091 files. It checks the source-register Git blob identities, runs the unchanged native collection validator, and creates an offline browser index with local source-line links. The three UNKNOWNs are read directly from the original fact ledger; no finding or fact is rescored.

Requires Python 3.10 or later and no third-party packages. From the repository root:

```sh
python revenue/uiowa_rfq_18649_analyst_continuation/bundle.py assemble \
  --collection revenue/uiowa_rfq_18649_synthetic_collection \
  --out /tmp/uiowa138-handover
python /tmp/uiowa138-handover/bundle.py verify /tmp/uiowa138-handover
```

Open `/tmp/uiowa138-handover/index.html` in a browser. The output includes all five Markdown documents, unchanged raw sources, line-addressable browser views, the packager and `bundle-manifest.json`. Copy the whole output directory to continue without the repository, Slack or a network connection. [analyst-handover.zip](analyst-handover.zip) is a ready-to-extract copy from the registered snapshot; open its `index.html`, or run `python bundle.py verify .` from the extracted directory.

The collection directory must contain the exact registered snapshot. If current source bytes differ, obtain the selected revision from an existing Git checkout without changing its working tree:

```sh
mkdir /tmp/uiowa138-selected
git archive bcf765be4d537a513bf1d7ac54a210b25b053d07 \
  revenue/uiowa_rfq_18649_synthetic_collection | tar -x -C /tmp/uiowa138-selected
python revenue/uiowa_rfq_18649_analyst_continuation/bundle.py assemble \
  --collection /tmp/uiowa138-selected/revenue/uiowa_rfq_18649_synthetic_collection \
  --out /tmp/uiowa138-selected-handover
```

Use fresh output directories. A failed source check leaves the destination absent; an existing destination is preserved. If a filesystem write fails after publication starts, an incomplete new directory may remain and the command exits nonzero. Preserve it or choose a different output directory before retrying.

`verify` checks the manifest's retained file hashes, enforces the fourteen original source pins and runs their original validator. Extra files are ignored. Hashes establish byte continuity, not source authenticity or narrative truth. The manifest is not a signature. The copied native validator executes locally; use this published source snapshot as ordinary repository code.

The separately described historical `continuation.py`, handover JSON and tests are not part of the published document branch. `bundle.py` is a new packaging adapter over the existing completed synthesis, not a reconstruction of that companion or a rerun of its historical results. The four original handover, synthesis, source-register and exercise documents remain byte-for-byte unchanged.

## Integration

- Original corpus: UIOWA-091 / ZZ-Sol / merged PR #16172. Consumed unchanged.
- Work record: https://github.com/woahwhattheheck/commons/issues/16186
- Operation: `uiowa-138-boreal138q-20260919`; seat ZZ-BOREAL-138Q, GPT-6 Astra Pro.
- Additive lane only; no changes to the compiler, workbench, catalog, ID reconciliation or operator-handoff components.
- The human handover and completed exercise are usable as documents and as the portable bundle above. Historical executable-companion publication and provider-check state are distinct from this adapter; its local runtime validation does not claim hosted CI results.

This kit is an internal preparation/evidence surface, not a customer storefront. It introduces no meeting, staffing commitment, procurement action, additional acceptance condition or payment trigger.
