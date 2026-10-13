# Creator-backed niche app studio — Hive demand 016

This is the customer-facing first version for `bm-hive-20260908-016`: a **$3,000 fixed scoped MVP sprint** for creators whose audience repeatedly asks for one practical tool. The deliverable is a reusable local-first app shell configured by a strict creator brief plus one concrete niche workflow, onboarding, usage limits, support handoff, runnable source, and launch copy.

## First niche: KilnKit Class Planner

The first workflow is grounded in a creator-authored ceramics-class planning problem previously captured in the Hive research feed: a teacher distinguished a **35-person roster from ~28 people who consistently attend** while planning supplies, and many requested tools were reusable/shared. That falsifies the naive "multiply every item by roster" model.

KilnKit therefore models three explicit supply modes:

- `per_attendee_consumable` — scales only with **expected attendance**;
- `per_class_shared` — scales with the number of classes, not students;
- `program_shared` — fixed shared inventory across the program.

A class retains both rostered and expected attendance. Updating expected attendance recomputes only per-attendee consumables while preserving shared-tool requirements.

## Run

```bash
cd revenue/hive_creator_niche_app_studio
python -m unittest -v test_studio.py test_app.py
python -O -m unittest -v test_studio.py test_app.py
python app.py --config example_creator.json --db kilnkit.sqlite3 --port 8765
```

Open `http://127.0.0.1:8765/`.

The browser app is intentionally loopback-only. The same SQLite workspace is safely serialized across threaded browser requests; browser-path tests exercise real form submissions and exports, not just the calculation core. It performs no external network calls, sends no support messages, and processes no payment. JSON/CSV exports are local downloads. Support produces a packet for the user to review and send through the creator-managed route.

## Creator brief contract

`example_creator.json` is the reusable brief. It pins creator/app identity, audience, promise, support route, $3,000 sprint offer, the workflow kind, and bounded usage limits. The SQLite workspace binds to the config digest on first open; swapping creator configuration under existing saved state fails closed.

The shell supplies:

1. creator-branded product header and audience promise;
2. onboarding explaining the exact workflow semantics;
3. plan/usage limits mechanically enforced by the store;
4. local SQLite reopen durability and revisioned records;
5. deterministic planner output and immutable saved-plan IDs;
6. spreadsheet-safe CSV and canonical JSON export;
7. a pricing page describing the configured $3,000 sprint without pretending payment occurred;
8. a support packet with `send_authority=false`.

## Launch assets

**One-line positioning:** "Plan what your class actually needs without buying one of every tool for every rostered student."

**Demo path:** add a 35-rostered / 28-expected class, add clay as per-attendee, banding wheels as per-class shared, and texture rollers as program shared. Reduce expected attendance and show only clay quantity changing. Export the supply plan.

**Creator CTA:** offer the niche tool as the scoped MVP produced during the $3,000 sprint. Any creator distribution, hosted deployment, recurring pricing, payment rail, partnership, revenue share, or external support integration is a separate commercial action.

## Safety/truth boundary

This product is inventory/planning software. It makes no nutrition, medical, education-quality, purchasing, safety, or legal recommendation. Quantities are arithmetic over user/creator inputs. It does not claim the cited creator is a customer, partner, buyer, or willing seller. It does not recognize revenue merely because the configured sprint price exists.
