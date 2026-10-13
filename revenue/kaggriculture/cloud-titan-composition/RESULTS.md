# T08 results and reproduction

The selected working default is **frozen SELL**, which won all 20 paired
development/held games versus Arlene and Apex. The full cap/carrot/SELL
composition is implementable and preserved, but fails the held comparison with
the stronger frozen control. There is no hosted-rating or submission claim.

| Arm | Development W/T/L | Held W/T/L | Status |
|---|---:|---:|---|
| Intact Arlene | 7/4/1 | 5/2/1 | Independent baseline |
| Carrot | 7/4/1 | — | No score difference on dev |
| Cap harvest | 7/4/1 | — | Small margin gain, no flips |
| Carrot + cap | 7/4/1 | — | Same scores as cap |
| Frozen SELL | 12/0/0 | 8/0/0 | Selected working default |
| Carrot + SELL | 12/0/0 | 8/0/0 | Same scores as SELL; preserved |
| FLORA extra hand | 7/4/1 | — | Separate runnable control |
| Carrot + cap + SELL, immediate reserve | 8/2/2 | — | Weak branch preserved |
| Carrot + cap + SELL, dated reserve | 11/0/1 | — | Improved branch preserved |
| Carrot + cap + SELL, conserved dated reserve | 12/0/0 | 7/0/1 | Held nonpromotion |

120 development games plus 32 held games completed without evaluator failures.
Development: 9780001, 9780019, 9780037. Held: 9780101, 9780119. Each arm uses
both seats against the independent intact Arlene and Apex opponents. Reserved
seeds were checked in Slack and available project sources before scheduling;
no prior use was found. Source was frozen before held; policies were unchanged.

Selected SELL converts 4 ties and 1 loss into wins on development and 2 ties and
1 loss on held, retaining every baseline win. Its held mean own-cash difference
is -168.25, rival-cash difference -201.75, and game-cash-margin difference +33.50
versus baseline. These are observed terminal differences, not an isolated claim
about opponent revenue caused by one sale. W/T/L takes priority over margin.
On development, mean margin falls 139.42 overall despite more wins: the Apex
winning margins shrink while close Arlene outcomes flip.

The four-arm carrot/cap factorial has zero observed margin interaction on these
12 paired states: carrot and baseline scores coincide, as do carrot_cap and cap.
Cap alone improves mean margin by 17.75 overall; FLORA by 45.83, neither with
W/T/L flips. This does not prove their mechanisms have no value on other states.

The integration adapters use one selected production action and the same base
route for inherited expenses/market order positions. Immediate capacity
reservation was replaced by earliest physically possible deposit dates, then
bounded by remaining unbanked units per product to avoid counting a reference
deposit twice. This changes capacity protection, not ASTRA's optimizer. The
last composition matches SELL's 12 development wins and improves mean margin
only 3.83 versus SELL (-30.50 against Arlene, +38.17 against Apex).

Held reveals the limit: on 9780119 versus Arlene, seat 0, composition cash is
58066 versus 58103 (loss by 37); SELL cash is 58178 versus 58141 (win by 37).
Composition's paired margin difference is -74 there and -95.25 on average
across held. It retains the baseline loss rather than converting it. This fails
the predeclared gate, so default routing returns to frozen SELL. No further
source tuning or games followed the held result.

Six focused contract tests pass: frozen vendor hashes, exactly-once action
consumption, one authoritative parent pass, selected units/inherited expense
positions, isolated relocatable archive parity, and deposit-phase/conservation
cases. Existing actual observations are retained in test-observations.json;
they are not live policy inputs. Maximum selected held action time is 0.26704s;
the experimental full composition reaches 0.31152s. These cloud timings include
resource contention and are not hosted-runner latency claims.

## Reproduce

Use the existing `cloud-eval/evaluate.py` and its pinned official engine
28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c. The opponent source and offline adapters
are the existing `cloud-frontier-policy/next-panel` Arlene/Apex fixtures. Engine,
evaluator and every consumed Python source hash are recorded in each raw panel.
The runtime directory must expose the existing `arlene-adapter.py` and
`apex-adapter.py`, including the latter's compiled public Apex dependency.
No downloaded model or paid service is needed.

```sh
python benchmark.py --arm sell --seeds 9780101,9780119 \
  --engine-dir /path/to/pinned-engine --runtime /path/to/opponent-runtime \
  --output /path/to/new-held-sell.json
python analyze.py dev
python analyze.py held
python -m unittest test_composition -v
python build.py --arm sell --output artifacts/titan-selected.tar.gz
python build.py --arm carrot_sell --output artifacts/titan-carrot-sell.tar.gz
python build.py --arm carrot_cap_sell_conserved --output artifacts/titan-composed-research.tar.gz
```

Existing panel files are never overwritten by benchmark.py. `results/` preserves
all ten development arms and all four held arms. SOURCE-FREEZE.json records the
pre-held files and rule; SELECTION.json records the resulting default. The frozen
development default is preserved as development-entrypoint.py. New adapter code
is T08 design; vendor definitions, license notices and code provenance remain
distinct. FLORA's separate overlay is not claimed integrated with cap scheduling.
The requested author generic SELL interface was still unavailable for this
comparison; the T08 adapter is explicitly separate. No new public opponent source
had been admitted through T07 when this bounded panel was scheduled.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
