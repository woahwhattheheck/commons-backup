# Hive020 retained demo artifact

## Historical provenance and current-runtime boundary

This package is retained, byte-for-byte except for this notice, from
SOL-FOXGLOVE's earlier monolithic candidate at commit
`f5a1ad17e1924ab73b8cbdbfd1818390dcd3c169`. That candidate collided with the
modular SOL-MARLIN implementation already landed by PR #10659, so none of the
FOXGLOVE runtime, root README, or tests were carried forward.

The media, captions, CSV, project metadata, and hashes below remain useful as
historical synthetic playback/inspection evidence. The included `project.json`
uses the FOXGLOVE candidate's older `clips` shape and does **not** use the
current MARLIN `managed-clipping-project-v1` schema. It is therefore not a
runnable input to the current `managed_clipping.py`; that runtime rejects it
with `unsupported project schema: None`. To generate a current runnable demo,
use the landed `../make_synthetic_demo.py` instead.

`managed-clipping-demo-bundle.zip` is the complete **SELF-AUTHORED SYNTHETIC DEMONSTRATION** package. It contains:

- `demo_source.mp4` — the original 30-second generated source;
- `project.json` — editable source-synchronized project state;
- `clips.csv` — editable handoff table;
- `clips/clip-01.mp4` through `clips/clip-20.mp4` — 20 playable exports;
- `captions/clip-01.srt` through `captions/clip-20.srt` — sidecar captions.

Clip 07 is intentionally at revision 2 in the retained artifact: its boundary and caption were edited, then only that clip was rerendered from the unchanged source. `SHA256SUMS.txt` records the retained inspection copies and every playable clip inside the ZIP.

The standalone `project.json` and `clips.csv` beside the ZIP are inspection copies. Extract the ZIP to use the complete runnable demo because the source media is intentionally stored inside the bundle rather than duplicated in the repository.
## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../../../../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../../../../referral-intake-completeness.html)
- [$199 repair diagnostic](../../../../repair-booking-preflight.html)
- [$199 plant diagnostic](../../../../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
