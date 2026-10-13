# Committed seed-purchase retry

This runtime component repairs a missed seed purchase before an existing,
unchanged next-turn planting commitment. It appends the missing seed order;
it does not introduce a new planting route, replace market orders, call a
second producer, or change the current package by being present in this folder.

## Integration seam

The tested parent is archive
`820ed99e09ea22b09ab4e412742c654ad7330e266ab25d92fb1997cda91a18be`
(302328 bytes). Its `_seed_selected` method returns immediately when the selected
market has no BUY_SEED, so it cannot recover a previously failed purchase on an
otherwise empty market turn.

`seed_retry.py` supplies the complete implementation. For an exact-source
composition, include this module at the package root and call the following
once immediately after creating the existing `TitanAgent` instance and before
its first `act`:

```python
from seed_retry import install_seed_retry
install_seed_retry(_INSTANCE)
```

The adapter wraps the instance's existing `_seed_selected`; the original seed
reduction runs first and remains intact. It does not initialize the controller,
call its producer, alter deadline handling, or replace the entrypoint. Repeated
installation is idempotent. A canonical integration may instead call
`apply_committed_seed_retry(runtime, obs, cfg, selected)` directly at that same
post-seed-transform seam and retain its diagnostic separately.

Only the new helper and those two entrypoint lines differed in the measured
candidate. Canonical entrypoint, builder, CURRENT pointers and configuration are
not changed by this additive publication. WIDEFIELD/ECON retain runtime
composition; QUICKSTEP's performance integration and the separate callback
consumer remain compatible paths to compose, not files to overwrite.

## Behavior and scope

The transform reads authoritative post-unit own inventory, counts all existing
next-turn per-crop PLANT requests, and purchases a complete deficit only when
those workers exist and their target tiles are exclusive and empty. This
preserves the interpreter's atomic per-crop planting behavior, including its
counting of requested but nonexistent worker slots. An already-selected seed
purchase is never assumed to have failed; its actual outcome must be observed
before considering a retry. Every existing market slot and unit action remains
byte-equivalent as a Python value, and new orders are append-only.

Admission reuses the existing `seed_funding.certify_seed_funding`. It certifies
that the FULL proposed queue fits observed cash without relying on sales.
The certificate is invoked in its documented seed-reduction direction by
comparing that full queue with identical slots whose appended seeds are empty.
Its reduction cash delta is not reported as a gain from buying seeds.

The current adapter also preserves the existing seller's bounded, same-day,
fixed-price cash reservation (up to its eight-turn horizon and before a route
switch). This is not a complete future-route solvency or profitability proof.
Dynamic product purchases in that window retain the original action rather
than reusing a heuristic quote as a guaranteed future price. Day/route switches,
terminal boundaries, nonstandard day lengths, and separate unit-rewriting
features also retain the existing behavior in this first composition. The pure
`propose_seed_retry` function accepts a caller-supplied authoritative committed
unit program and reservation for subsequent coordinated compositions.

## Validation

Run in a cloud environment with the extracted tested package:

```sh
TITAN_TEST_RUNTIME=/private/extracted-current \
  python -B test_seed_retry.py
python -B verify_witness.py --runtime /private/extracted-current \
  --witness /private/NATIVE-WITNESSES.json.gz \
  --output /private/seed-retry-witness-result.json
```

The 29 focused tests pass against the real packaged controller and pinned
official primitives, including native market-to-plant execution in both seats.
`verify_witness.py` consumes the existing private two-turn QUARTZ witness and
checks all three native market checkpoints and all three next-turn successors:
unchanged, timely purchase, and too-late purchase. It runs no old prefix and no
new full game. Never run the assertion-based regression scripts with `-O`.

A separate frozen comparison completed 16 new full games: four development
seeds, candidate/current-parent, both seats, against intact Arlene. All games
completed 719 action rounds with zero failures; 11520 states and 23008 actor
packets were retained and checked. Seven of eight paired full-state histories
are identical. One reached pair first differs at the appended seed purchase,
with identical prior histories. These are dependent development comparisons,
not sixteen independent seeds or a default-promotion decision. Complete cash
changes, original traces, source closure and failures from setup/test attempts
remain in the private project handoff; no original match data are in this folder.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
