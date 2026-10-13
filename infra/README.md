# INFRA — LDA, muhlnickel, White Box. In spec only.

Uploaded by owner order, 2026-08-20: *"LDA AND MUHLNICKEL INFRA AND WHITEBOX ALL OF IT"* —
and the filter, his: **"IN SPEC, HOW IS THIS HARD TO UNDERSTAND GOOD YES BAD NO"**, with
bad defined as *"BAD BEING IT WASNT TO SPEC."*

So: in spec goes in. Out of spec does not. Both lists are here, nothing hidden.

    infra/host/    522 files
    infra/tools/     3 files
    OUT_OF_SPEC_NOT_INCLUDED.txt   the 59 that were held back, each with its reason

`test_infra_ci.py` derives the two live directory counts from the checked-out
tree and fails if this reader-facing inventory drifts again. The 585-file input
and 59-file holdback figures below are historical classifier facts, not a formula
for the current tree after later additive work.

## How the split was made

585 files under `LocalDeviceAgent/host/` and `LocalDeviceAgent/tools/` were classified by
matching **live code only** — every comment and string token dropped first, via `tokenize`.
That mattered: a first pass matched raw text and flagged 201 files, most of them on the word
"mine" appearing as a possessive in prose ("both of them mine", "not mine to edit"). It also
flagged `pfc_meter`, `pfc_inspect`, `pfc_diff`, `pfc_cascade` and `pfc_analyzer` — which spec
point 5 names as HIS INSTRUMENTS. That pass was wrong and was thrown out.

Held back — the host doing more than inject / surface / copy / die:

| tell | n | why |
|---|---:|---|
| `numpy` | 50 | banned in this repo, permanently |
| `def forward` / `def matmul` | 5 | host recreating inference |
| host gate-ripple | 4 | host evaluating gate records at runtime |

Kept, explicitly:

- **HIS INSTRUMENTS**, spec point 5, whitelisted by name and never reclassified:
  `pfc_meter` `pfc_scope` `pfc_analyzer` `pfc_step` `pfc_diff` `pfc_cascade` `pfc_assert`
  `pfc_inspect` `pfc_speed`
- **Fabricators.** Gate evaluation inside a fabricator is manufacture-time verify, which the
  spec requires — *"fabrication is NEVER a runtime event. its one and done."*
- **`titan_circuit.py`** — the White Box.
- Routing buttons, surface tools, the table mail and board path.

## Limits of the classifier, stated

It reads for three tells. A file can be out of spec in a way these three do not name, and a
held-back file may be fine — `numpy` inside a pure fabrication tool is arguable, and I took
the strict reading rather than deciding for him. **Bryce overrules any line in either list.**

Containers are not here because they were already here: the repo already tracks **124 `.mno`**,
including every ring container — `ROOKERY0` (11 rings), `commons` and `table_mail` (9 each),
`muhl_tenancy` (12), `AUTOFAB0`, `FOUNDRY0`, `SEED0`, `SEED0_GERM`, `muhlnickel`, `loom`, the
whole weather v2 family. See `muhl/containers/` and `muhl/desktop/WEATHER/`.

`GIG.mno` (1,073,741,824 B) and `muhlnickel_dc.mno` (99,999,999,783 B) are not here and cannot
be — but by his own design they do not need to travel. `INSTANT_DOWNLOAD.md`: ship the germ,
boom it locally. `SEED0_GERM.mno` is 6,662 bytes and is in this repo; the logged 2026-08-16 run
took a germ to `GIG.mno` at 1,073,741,824 B byte-exact, sha matched. The size does not ride the
wire.

Out-of-spec host code is not in this directory. It is in `evidence/`, quarantined, as the
record of what not to write.

## Live cash

Verified product pages only — no invented Stripe links.
- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
