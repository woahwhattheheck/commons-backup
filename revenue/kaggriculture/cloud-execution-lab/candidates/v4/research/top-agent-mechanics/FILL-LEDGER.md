# FILLPROOF: executed market fills

Offline analysis component in the existing `main:candidates/v4/research/top-agent-mechanics`
package. SOL/HARVESTMAP retain their intent/actor miner; Riot retains the three policy
lanes. No production imports, feature keys, defaults, archives, workflows or Kaggle
submissions change. This is one canonical V4 workspace, not a successor controller.

## Findings and limits

The checked published native archive b567942e fills **281/281 HIREs per game** on
seeds 17 and 6607 versus the pinned official starter, in both seats. Hiring costs
5,539 and 5,484 respectively. Within-day timing is concentrated: hour 0/1/3 counts
are 214/66/1 and 215/65/1; all other hours have zero. Thus the proposed peer count
of 259-294 HIRE rows does not establish an absent hiring mechanism, but cadence
and marginal productive labor remain valid questions. The peer top-team counts
were not independently verified here.

Native WHEAT buys fill 143/146 units from 150 requested in 52 rows: 85 early and
58/61 middle, no late buys (phase boundaries 240 and 480). Seed 17 sells 340 WHEAT
and 322 FERTILIZER, and buys 73 FERTILIZER. BUY+SELL presence **does not establish
merchant arbitrage or lot provenance**: purchases may feed animals while sales
come from crops. Retain the merchant policy's marginal-profit question.

Native seed-17 missed/partial purchases at steps 206, 224, 241, 242 and 244 are
cash constrained, not shed-capacity constrained. Step 206 BUY WHEAT 3 fills zero:
money 8, quote 31, occupancy 17/100. Step 241 BUY FERTILIZER 3 fills one: subsequent
money 13 versus quote 88, occupancy 49/100. Both seeds return SELL FERTILIZER 23
at step 697 with zero stock and zero fills. These are diagnostics, not proof of
a competitive loss or profitable repair.

Constructed official-engine witnesses prove that four HIRE requests with money 2
fill only two; an hour-23 HIRE can genuinely fill and cost 1 before day-end clears
all hands; SELL FERTILIZER 9 with stock 3 at the floor fills/earns 3 while market
inventory stays unchanged; BUY WHEAT 1000 with cash 26 fills only one. Gross sales
and buys can cancel in net stock. Invalid raw slots are not compacted into the
cap. Town, unit DROP and end-of-day transfers must not be labeled market fills.

## API and validation

`market_fill_ledger.py` observes the original pinned official parser, unit commits,
atomic hires/land, town and end-of-day functions. It records raw slot/seat/cap,
parsed/requested and filled units, actual cash, shed/seeds/market deltas, quotes,
and failed-attempt resource states. Row mutations must reconcile to the actual
market phase. Original functions are restored even when the interpreter raises.

`audit_transition(engine, state, env)` uses independent deep copies to run observed
and pristine interpreters on identical complete raw actions. All state and env
fields must match; caller inputs remain unchanged. This requires both players'
private state and is **offline only**, not hidden information for a live agent.
Hooks are process-local, not thread-safe. Action-only CSVs cannot supply missing
historical private stock. No top-team corpus or fresh-loss replay arrived here.

Executed: **27/27 tests normal and 27/27 optimized**, no errors/failures/skips;
256 randomized two-seat full-engine worlds per mode plus focused witnesses.
Nine deliberately corrupted observer-output variants are assertion-rejected in
each mode after green controls; errors/skips do not earn kill credit. These are
observer-output faults, not engine or gameplay mutants.

Eight complete native games (two seeds x two seats x normal/optimized): **5,752
actual main.py::agent calls**, all completed, zero fallback; **5,752 full-state/env
pristine twins equal**; 11,512 interpreter calls including initialization/twins.
All market-row cash reconciles exactly to terminal rewards. Normal/optimized
outputs match except measured timing. All 109 runtime members, archive, manifest,
engine sources and loader authenticate. This is checked published-archive
accounting, **not composed-V4, hosted-deadline, competitive-strength or promotion
validation**. No policy was changed.

## Reproduce

Recover existing GitHub artifact 10175943272 from woahwhattheheck/commons.
ZIP SHA256: 3a3b74936d238bf884f89a1b279f42676cda35c590f131a6a3548de52d61b4e8.
Extract its checked-package/exports/titan-current.tar.gz into a clean native dir.
From this source directory:

```sh
export TITAN_NATIVE=/absolute/path/to/extracted-native
export CHECKED=/absolute/path/to/artifact/checked-package
python -B -m unittest -v test_market_fill_ledger
python -O -B -m unittest -v test_market_fill_ledger
python -B check_market_fill_mutants.py
python -O -B check_market_fill_mutants.py
for mode in normal optimized; do
  flags='-B'; [ "$mode" = optimized ] && flags='-O -B'
  for seed in 17 6607; do for seat in 0 1; do
    python $flags run_market_fill_native.py --native "$TITAN_NATIVE" \
      --manifest "$CHECKED/runtime/integrated-selected/CURRENT-SOURCE.json" \
      --archive "$CHECKED/exports/titan-current.tar.gz" \
      --seed "$seed" --seat "$seat" --output "native-$mode-$seed-$seat.json"
  done; done
done
```

All reference inputs fail closed before import; no network or Actions dispatch.
FILL-VALIDATION.json binds exact source hashes, results and limits. Three
FILL-EVIDENCE.part-*.b64 files retain the eight full census outputs, two test logs
and two negative-control outputs. Decode and authenticate:

```python
import base64, gzip, hashlib, json
from pathlib import Path
r = json.loads(Path('FILL-VALIDATION.json').read_text())
encoded = ''.join(Path(p['path']).read_text().strip() for p in r['evidence']['parts'])
raw = gzip.decompress(base64.b64decode(encoded))
if hashlib.sha256(raw).hexdigest() != r['evidence']['decoded_json_sha256']:
    raise ValueError('evidence digest mismatch')
evidence = json.loads(raw)
# evidence['files']: original census outputs/logs, not complete game traces.
# Census outputs retain whole-stream hashes plus every selected nonfull witness.
```

Consume the existing code and diagnostics; do not commission another fill
estimator or activate a policy from counts alone.
