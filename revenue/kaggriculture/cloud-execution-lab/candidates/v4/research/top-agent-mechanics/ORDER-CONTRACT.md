# Replay ordering repair and native mechanics overlap

ASTRA-HARVESTMAP extends the existing TOP-AGENT-MECHANICS miner. This is the
same canonical `main:candidates/v4/research/top-agent-mechanics` package, not
a new miner, controller, V4 tree, or gameplay/default activation.

## Defect and contract

The original miner (`0aa78703f26ee647bd5af5c0fbfd207ea3dd15f8`) concatenated
all unit rows by `(source, player)`. Separate farmers at the same step could
therefore become an invented sequential mechanic. CSV order is not a proof
of actor identity or market execution order. Self-play also merged the two
seats' count/first-occurrence/coincidence evidence.

The existing CLI now uses one `sequence_contract.py`:

* `seq2` / `seq3` mean recorded same-player/source chronology. They do NOT
  mean the same actor, causality, filled orders, or consecutive callbacks.
  Simultaneous unit rows break this chronology; they are not skipped over.
* `actor_seq2` / `actor_seq3` additionally require a known unit actor. A
  duplicate actor at a step breaks that actor stream; an unknown actor row
  breaks all actor streams at that step. Other known workers do not erase a
  valid same-actor sequence.
* Same-step market order is used only with explicit, unique, nonnegative
  raw slots. Without that evidence, multiple rows are an ambiguity barrier.
  The CSV ordinal remains a witness locator, never an ordering substitute.
* Missing seats cannot produce sequences or same-step coincidences. Known
  self-play seats are analyzed separately; unique-team support and unique
  team/match counts are retained.

CSV inputs optionally accept `actor`, `actor_id`, `farmer_id`, `hand_id`,
`unit_id`, or `worker_id`, and `raw_slot`, `market_index`, `order_index`, or
`order_slot`. Never map the player/seat column to actor identity. The real
vijaikm corpus schema/bytes were not available in this session: these aliases
are an explicit input contract, not a claim about that corpus. Existing
nine tests remain byte-identical. Report schema is `/v2` and states these
semantics. `collect_witnesses` preserves exact match/team/seat/step/source,
row ordinal, actor and raw slot for the downstream replay check.

## Executed native evidence, not leaderboard evidence

`native_mechanics_audit.py` authenticated all **109 runtime members** of the
existing b567 archive, then decoded the four **720-row authored route tapes**
without executing a runtime or the engine. It preserves every authored unit
row, including surplus hands, all market slots and empty rows. This is raw
intent, not proof that a worker existed or an order filled.

Across these four conditional routes, the original algorithm emits
**13,504–13,590 sequence occurrences per route** containing a same-step unit
edge. **2,474–2,551 old unique sequence features per route** are absent under
the corrected player-chronology contract. The added explicit actor family
retains **1,091–1,146 same-actor authored motifs per route**. These four
routes share prefixes and are NOT four independent teams or games.

Exact common opening witness: at step 2, actor 0 performs WEST and actor 1
requests PICKUP COW. The original miner invents `WEST>PICKUP:COW` as a
sequence. Correct extraction retains the coincidence, not that sequence.
The MAIN tape also contains genuinely same-actor authored PICKUP WHEAT at
48 -> FEED at 49 (actor 0), and PICKUP FERTILIZER at 440 -> FERTILIZE at 441
(actor 11). These are already-present TITAN motifs, not novel rival ideas.

No top-5 ranking, real-corpus enrichment, successful-fill inference, whole
native game, current composed-V4 strength or Kaggle improvement is claimed.
Riot's fert_liquidate / wheat_merchant / hire_cadence gameplay lanes stay
with their existing builders. This repair prevents misleading evidence
from being used to commission further lanes.

## Reproduce offline

From this package directory, use an existing copy of artifact 10175943272:

```sh
ARCHIVE=/path/to/checked-package/exports/titan-current.tar.gz
# Obtain the exact historical miner from the same repository, not a rewrite:
git show 5b43dc4acee1c1b4d840069f40a9e0b3cdb765fa:revenue/kaggriculture/cloud-execution-lab/candidates/v4/research/top-agent-mechanics/mine_top_mechanics.py > /tmp/titan-miner-donor.py
python -m unittest -v test_sequence_contract test_top_mechanics
python -O -m unittest -v test_sequence_contract test_top_mechanics
python check_sequence_mutants.py --output mutations.json
python check_native_mechanics.py --archive "$ARCHIVE" --donor /tmp/titan-miner-donor.py
python -O check_native_mechanics.py --archive "$ARCHIVE" --donor /tmp/titan-miner-donor.py
python native_mechanics_audit.py --archive "$ARCHIVE" --output native.json
python -O native_mechanics_audit.py --archive "$ARCHIVE" --output native-optimized.json
cmp native.json native-optimized.json
```

Executed on Python 3.13.5: **29/29 existing+new tests and 7/7 native data
controls in EACH normal/optimized mode**. Seven source mutants fail
behavioral assertions in EACH mode, with all 29 tests executed and no
error-only credit. The six-row permutation test enumerates all 720 orders.
Native controls compare against the actual donor miner and actual native
route decoder, preserve all non-sequence features, check every raw row,
shuffle complete native data, and round-trip actor/slot CSVs. Native reports
are byte-identical across modes. No hosted CI-green claim is implied.

`ORDER-EVIDENCE.json` contains exact source SHA256/Git blob identities,
normal/optimized test results and log digests, mutation assertion counts,
and native route-level counts plus an original row witness. The executable
audit regenerates the full native report. No external packages or network
are needed. Old source pins fail closed rather than silently accepting a
newer archive.
