# W0 archive-gate evidence

This evidence is deliberately split into identity, negative-control, and
source-shaped positive-control layers. None is a game-strength, promotion, release,
or submission claim.

## Exact current base pin

The production contract is pinned to the canonical archive receipt published on
`main` when this carrier was cut:

- archive SHA-256: `5f6a4153e502713b9467776eafe7464af650584149173ce7507a31a1b2af60f1`
- archive bytes: `428158`
- archive members: `109`
- entrypoint: `main.py::agent`
- source-manifest SHA-256: `3249398b6aa56d1b3464db8d0cce5aa35e8edee397fc4341bd710d1f74dad469`

`contract-current.json` accepts a candidate only when that exact base is supplied.
It requires the config, source manifest, runtime, and spatial producer to change,
allows only the existing weed-continuation test as an additional changed member,
and rejects every added or deleted archive member.

## Real packaged negative control

A previously shared packaged TITAN transport was mounted and evaluated rather than
re-created from loose source:

- archive SHA-256: `6ac897241cb54baa205e4132fab1f83e7a21e4ae957e19e16c6c48a7ecbd8bc1`
- archive bytes: `408621`
- archive members: `105`
- verdict: `HOLD`
- failure code: `config.weed_continuation_missing`
- deterministic receipt hash: `c6e33f31f08b4d4c3efdb71a548a7244eb597ac68aca178314f9e02082068a49`

This is a stale predecessor and is never substituted for the current base. It is
useful only because importing its actual package reproduces the hidden-W behavior:
an all-off construction still creates and installs `SpatialTempo`.

## Source-shaped executable positive control

A local, non-canonical four-member mutation of that stale transport was used only
to test the gate itself. It added the independent W field, five-capability
construction, W-guarded continuation, and stale-W cleanup, then rebuilt the package
manifest without changing any unrelated member.

- archive SHA-256: `d855281f1beeb566bf31b9485f61034f7fdac2adef23aa00b02a27cf5209c7bb`
- archive bytes: `408998`
- archive members: `105`
- verdict: `PASS`
- deterministic receipt hash: `c69cdad31a735dc20c97df83538edf470e4d4db82e3fc27019547d71bd808e70`
- executable matrix: `32/32` P/T/I/C/W masks
- direct reachability controls: `8/8` P/T/W worlds
- stale-W0 reconstruction: weed plans/events/patches/seed demand removed while
  idle-fertilizer state remained

These bytes are not a proposed runtime and are not committed. They establish that
the gate can pass a production-shaped closure while the real predecessor fails.

## Mutation strength

The unit suite kills the specific regression classes the gate is intended to stop:

- construction coupled only to P/T;
- hidden `_continue_weed` execution under W0;
- retained W1 state during W0 reconstruction;
- a `Features` default of true;
- unconditional all-off installation;
- missing, true, integer, string, or null packaged W0;
- unbound source hashes, undeclared deltas, duplicate members, links, and extraction
  path collisions.
