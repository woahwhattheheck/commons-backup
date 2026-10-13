# IDLE-HANDS donor preservation

Status: **donor/evidence only — not activated in production**.

This directory preserves the completed `r04_idle_hands` source and focused tests exactly as published by the build-demand lane so later V4 work can consume reviewed bytes instead of reconstructing them from chat or session-local storage.

## Exact custody

- helper Git blob: `7a413ba840fae0bf6319b00d9fd4cb55513e88e8`
- focused-test Git blob: `080a50754e09a2b364056806f15e84ff23fe7ec4`
- engine semantics receipt: `3c202c7ee921da239356789e266b694635103fc4`
- canonical V4 baseline: `15b2b5d2025a7c6976557b5ec3e458a3f09f412b`

## Mechanism boundary

The donor only rewrites exact literal `PASS` rows into local work when strict state/resource predicates are satisfied:

- `feed_all`: FEED an unfed local animal using WHEAT already carried by that actor.
- `care_all`: CARE a fed, uncared local animal.
- `care_goose`: same CARE rule, restricted to GOOSE.
- `wheat_fert`: FERTILIZE a WHEAT tile aged 2–4 using FERTILIZER already carried by that actor and only when current-day coverage is absent.
- `idle_all`: donor-local master that enables feed/care/wheat-fertilize layers.

The source is strict two-seat / standard-config, skips duplicate-occupancy sites, does not move actors or emit market rows, preserves the exact parent object on disabled/malformed/no-op paths, and deep-copies only on activation.

## Not yet promoted

Preservation is **not** a strength or safety promotion. The build-demand handoff still requires the focused suite under normal and optimized Python plus the hardened 8-seed × 2-seat runtime panel, with arms measured separately (`feed_all`, `care_all`, `care_goose`, `wheat_fert`; `idle_all` optional). Report engagement and margin per arm; do not conflate them.

No router key, config surface, default, install wiring, production source, archive, workflow, branch, or legacy V4 ref is changed by this preservation pack. The legacy r04 materializer must not be executed against current production; any later semantic port must follow `candidates/v4/CANONICAL.json` and current-main ABI.
