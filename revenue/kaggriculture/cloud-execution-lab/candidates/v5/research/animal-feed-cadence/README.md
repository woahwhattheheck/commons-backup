# TITAN V5 animal basic-needs cadence

This directory is a pinned-engine research artifact, not a production policy or a new controller.

## Source-real finding

The official pinned engine removes an animal only after **two consecutive** day refreshes without feed. A single unfed day increments `consecutive_unfed` to one; a mechanically successful FEED on the next day resets it to zero.

Base animal production is independent of `fed_today`: when a production refresh is due, the engine adds the base unit even on the one permitted unfed day. Therefore an alternating feed cadence can preserve animal survival and base production while consuming less WHEAT.

That theorem has an important exclusion. CARE bonuses are not feed-independent. CARE only creates `pending_care_bonus` when the animal was also fed that day, and an existing pending bonus is consumed on a production refresh only when `fed_today` is true. A blind every-other-day transform can therefore destroy CARE value even while preserving base output.

## What the verifier proves

`verify_animal_feed_cadence.py` pins both the official engine and the current Arlene producer by Git blob. It checks all three animal species and establishes:

- one unfed refresh followed by a successful feed is survivable and resets the starvation counter;
- two consecutive unfed refreshes eject the animal;
- alternating feeding with no CARE obligation preserves base held yield over the bounded witness and saves WHEAT;
- the first production refresh exposes the CARE-bonus loss when feed is skipped;
- the exact current Arlene route tapes can be censused for FEED, CARE, WHEAT PICKUP, and adjacent same-actor feed-day density without mutating those routes.

## Admission boundary for any future V5 policy

A production transform must fail closed unless it can prove all of the following from the current public/private own state and the exact authored route:

1. skipping the candidate FEED cannot create two consecutive unfed refreshes;
2. the skipped day has no CARE whose bonus depends on feeding;
3. no pending care bonus is lost on a production refresh;
4. the next required FEED will actually execute (position, animal, WHEAT, and action), rather than merely appearing in a route tape;
5. all other actors and every market row remain exactly unchanged.

The artifact intentionally does **not** enable sparse feeding, change defaults, edit the runtime, or activate anything on Kaggle. Its purpose is to turn a metagame observation into a source-pinned theorem plus a measurable current-route opportunity surface before V5 admits a policy.
