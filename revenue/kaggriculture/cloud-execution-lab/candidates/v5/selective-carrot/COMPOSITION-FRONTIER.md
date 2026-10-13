# TITAN V5 composition frontier

This is the intake and ordering contract for the single V5 candidate line. The
immutable base is production-v3 archive SHA256
`20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`.
Every candidate remains held from CURRENT, release, and Kaggle until the
separate promotion gate is satisfied.

## Current evidence map

| Candidate | Exact production-v3 carrier | Current evidence | Composer disposition |
| --- | --- | --- | --- |
| Future own supply | Yes: `components/future-own-supply-v1/COMPONENT.json` | Standalone: five development cells positive, mean +19. After WF1+C02: three of six worlds regress, mean only +5.33 and worst -10 | Retain as a standalone research arm; exclude from the held local leader |
| C02 deferred replacement | Yes: `components/c02-deferred-replacement-v1/COMPONENT.json` | Standalone: six engaged matched cells positive and six inert, mean +75.5. Incremental after WF1: six engaged positive and six inert, mean +67.33, no negatives; timers disabled | Retain after WF1 in the held local leader; run the posted native Apex/Arlene and union gates |
| P05 weed queue PASS catch-up | Yes: deterministic component materializer | Source and contract tests only; native engagement and economics are unmeasured | Eligible for a standalone screen; owns `r04_full_router.py` |
| P02 goose capacity economy | Yes: deterministic exact-archive builder | Source and contract tests only; natural placement, EGG realization, and economics are unmeasured | Eligible for a standalone screen; owns `main.py` |
| WF1 wheat/fertilize | Yes: `components/wf1-production20f-v1/COMPONENT.json` replaces the standard `main.py` return seam and adds the pinned modules | Exact-current local screen: 12/12 matched cells positive over six mirrored-seat worlds, mean margin +385.5, median +353, worst +314, zero failures; responsive Arlene with timers disabled | Admitted to held intake; run native Apex/Arlene and top-30-union gates before promotion |
| H3/S420 microstack | Current-ABI source transform only | Historical V3.1 receipt was 16/16 positive at about +441 mean; no exact-current economics | High-priority current V5 screen, then export only a measured winner |
| Fertilizer hand | Current-ABI theorem only | Historical V3.1 receipt reports +261.6 cash/game across 1,920 games; no exact-current economics | High-priority current V5 screen; likely a `main.py` integration owner |
| P04 route rows R05-R08 | Exact native experiments | All four blanket rows have negative mean margin versus C00 and the receipt marks them discovery-only | Exclude from composition; conditional-route research may continue separately |
| Other animal, midnight, overflow, unit-market, and bulk-feeder ideas | Default-off research carriers | No exact-current matched economics | Do not enter the composer until engagement and paired economics exist |

The future-own-supply figures come from `FUTURE-SUPPLY-RESULTS.json`. WF1,
H3/S420, fertilizer-hand, P02, and P05 explicitly label their retained or
missing evidence in their local README files. P04 status and deltas come from
`route-matrix-native/BLOCK-B/SUMMARY.json`. These are experiment results and
proposals. Future-own-supply, C02, and WF1 have checked-in component instances.
WF1's exact-current development receipt is
`../wf1-current-native/LOCAL-SCREEN.json`; its 94-member candidate has SHA256
`7c9126d961915acbe1c69930d7cebc4938641233fe50323f2fb043c08334ac3d`.
Composing the checked-in future-supply component followed by this WF1 component
also succeeds without overlap and yields a 95-member held archive SHA256
`db605e8db69d1a8392c9bc448d50abed165d024096b749d75aa91b921df3353f`.
That two-component result is structural; its interaction economics are still
unmeasured.

## One writer per boundary

The composer consumes components in one explicit order. A lane hands the
composer an authenticated archive and result receipt, not a source patch. The
exporter converts its exact winning bytes into `COMPONENT.json` plus
deterministically named, hash-authenticated payloads.

The member set defines the collision domain:

| Domain | Members | Rule |
| --- | --- | --- |
| Seller | `frozen_selected.py`, `selected_sell_core.py` | Future-supply, H3/S420, or another seller experiment must first be tested alone. If more than one survives, build and measure one combined seller postimage; do not text-merge manifests. |
| Route | `r04_full_router.py` | P05 and every route successor are mutually exclusive direct writers. Select one measured route postimage or measure an intentionally combined route postimage. |
| Runtime wrapper | `main.py` | P02, WF1, fertilizer-hand, and other postprocessors must converge into one ordered wrapper implementation before export. Helpers belong to that same component. |
| Addition-only helper | Candidate-specific module names | An addition composes only while the member is absent. A later edit must name the immediately preceding writer through `overlap_after`. |

The normal fan-in order is seller, route, then runtime wrapper. This minimizes
overlap because the current exact seller component does not touch the route or
runtime wrapper. It does not imply that every surviving component should be
enabled: each cumulative step must be measured against the immediately prior
boundary so an interaction regression is visible.

## Lane intake

For each lane:

1. Materialize one deterministic candidate from the exact production-v3
   archive. Record the archive SHA256, engine SHA256, opponent identity, seed,
   seat, terminal own/rival/margin, engagement counters, failures, and timing.
2. Screen the candidate against production-v3 on matched cells. A zero-trigger
   run is non-engagement. Mirrored seats are retained but are not independent
   replicates.
3. Export only a candidate that improves the paired economics contract. For a
   direct production-v3 delta, use `export_staging_component.py --baseline ...
   --candidate ...`. For a later boundary, also provide the exact current
   archive and its composer receipt; the exporter reconstructs writer custody.
4. Send the component directory, result receipt, candidate archive SHA256, and
   touched-member list to the single composer owner. The composer performs no
   source merge and rejects undeclared overlaps, deletions, stale preimages,
   duplicate IDs, and dependency-order drift.
5. Compose the accepted component after the current receipt, then run the
   cumulative candidate against that immediately prior boundary. If it loses,
   remove that component from the chain without rewriting the earlier winner.

No lane should edit another lane's component manifest or the active chain. A
collision is resolved by a new combined candidate archive whose behavior is
measured as its own experiment, then exported with explicit `depends_on` and
`overlap_after` custody.

## Promotion sequence

The first practical sequence is:

1. Run the admitted WF1+C02 local leader through native Apex/Arlene and the
   union top-30 gate. Re-gate H3/S420 separately because its historical receipt
   shows the largest remaining untested upside.
2. Run P05 and P02 engagement screens in parallel because they own independent
   files. Keep only variants with real trigger evidence and positive matched
   economics.
3. Measure the seller winner with the route winner, then build one runtime
   wrapper from the surviving postprocessor set and measure its incremental
   effect on that cumulative boundary.
4. Run the resulting single archive through the union top-30 corpus with both
   seats and fresh holdouts. Require zero game failures, positive median paired
   margin, no unexplained new loss flips, and controlled lower-tail behavior.
   The 3000+ target needs a material win-rate and margin improvement over
   production-v3; a tiny development mean is only a component signal.
5. Feed only the final archive and complete receipt into the existing promotion
   gate. Keep CURRENT, release, and Kaggle unchanged until the owner releases
   the explicit submission hold.

`future-own-supply-v1` is the first concrete intake artifact. Composing it alone
onto production-v3 deterministically reconstructs candidate archive SHA256
`ca8ca6f5d1ffb5ad828db5d924ed27d4d3c2f35b3a54ebd1f4cb311d7cdea9e1`.
That exact reconstruction establishes custody and composability; its five-cell
development result is not sufficient promotion evidence.

`c02-deferred-replacement-v1` is the second concrete intake artifact. It
reconstructs candidate SHA256
`8c294b6dbe296c6b822eaeccab8e3ecb3fbfc7854b50d6f584d9bd6da26e6d61`
and composes with future-own-supply in either order to SHA256
`3bd665c3a88425964b396703f3531a93d68b9e67680b3fbff812a2d2fa9f3778`.
The C02-only local screen is positive but small; its future-supply interaction
archive still has no economics.

`wf1-production20f-v1` is the third concrete intake artifact. Applying WF1 and
then C02 produces the 94-member held local leader SHA256
`8b4b074012fe3bd731c218a4956f85ce8dadd74d5afe81a3e04c2795a2a533ee`.
`WF1-C02-COMPOSER-RECEIPT.json` records exact composition custody. In
`WF1-C02-LOCAL-SCREEN.json`, C02 adds mean paired margin `+67.33` over WF1:
six engaged cells improve, six are exact identity, none regress, and all 12
finish. Relative to production-v3, the six distinct-world deltas are `+754`,
`+505`, `+358`, `+412`, `+348`, and `+340` (mean `+452.83`, median `+385`).
This is the strongest exact-current local candidate so far. Native timing,
opponent diversity, the union gauntlet, and fresh holdouts remain open, so the
archive stays held from CURRENT, release, and Kaggle.

The attempted next addition, `future-own-supply-v1`, produces the 95-member
archive SHA256
`e6cf2ee6495304b0b0ed73782b341402b983954e87e9486f1be293829483ef22`.
`FUTURE-WF1-C02-COMPOSER-RECEIPT.json` records its custody and
`FUTURE-WF1-C02-LOCAL-SCREEN.json` records its incremental result. All six
worlds engage, but the deltas are `+26`, `+6`, `-10`, `-2`, `+15`, and `-3`.
The mean is only `+5.33`, three worlds regress, and the worst is `-10`, so the
triple is excluded from the leader before native or union compute is spent.
