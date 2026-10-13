# TITAN v3 — L02 terminal-window ablation (SOL-TRIDENT)

The complete L02 development panel at head `67519b5a37e609ea7511f0cb9d6b9032b34fda02`
rejected the broad late-game tranche: 80/96 paired cells lost own cash, with mean
own delta `-315.615`. Control and candidate were identical through step 671; every
cell first diverged at the step-695 checkpoint. At that checkpoint mean own delta
was `-170.000` while rival delta was `-376.948` (margin `+206.948`). By step 718,
own delta fell to `-315.615` and rival delta recovered to `-347.042` (margin only
`+31.427`). The causal hypothesis is therefore temporal: an early denial signal is
being overwhelmed by repeated/final liquidation.

This additive lane does not alter canonical TITAN or the original L02 files. It
loads the exact checked-out L02 overlay and screens five isolated arms:

- `once_all`: all L02 components only at step 672;
- `day28_all`: all components during day 28, never day 29;
- `once_carrot`: CARROT only at step 672;
- `once_wheat`: WHEAT only at step 672;
- `once_noncarrot`: non-CARROT FrozenSelected products only at step 672.

`run_arm.py` reuses L02's complete official-engine paired runner while rebinding
candidate identity to the selected entrypoint and recording the full ablation
bundle plus imported L02 overlay hash. `rank_arms.py` requires one immutable grid,
strict JSON, complete reports, finite arithmetic, and ranks by own cash before
margin. It can emit only `NO_ARM_SURVIVES_SCREEN` or `FULL_PANEL_REQUIRED`; it can
never promote a candidate or make a leaderboard claim.
