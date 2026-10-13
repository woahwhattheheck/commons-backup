# Measured service + labor composition

The frozen bounded composition completed all 80 scored games: 40 development
and 40 held, each with 719 executed decisions. The source was frozen at
`50fa6177b802c60f5b46699cfb27a7a60e5ed398` before held play; all four executable
hashes remained unchanged. Ten real-engine/state/file-loader tests passed.
`RESULTS.json` is the game-level receipt, with separate own/rival cash, timing,
engine-trace hashes, explicit inherited controls and factorial interactions.

## Outcomes

Each row covers both seats against intact Arlene and Apex on two seeds: eight
games per arm. The development seeds are 9820001/9820019; held seeds are
9820101/9820119. These are now used seeds, not fresh holdouts for further tuning.

| Arm | Development W/T/L | Held W/T/L | Dev mean own cash | Held mean own cash |
| --- | --- | --- | --- | --- |
| Intact parent | 4/4/0 | 5/2/1 | 90834.750 | 87605.875 |
| T04 service | 8/0/0 | 7/0/1 | 91005.250 | 87688.750 |
| T10 reserve labor | 8/0/0 | 7/0/1 | 90840.000 | 87614.875 |
| Both, bounded forecast | 8/0/0 | 7/0/1 | 91010.500 | 87761.000 |
| Unchanged selected SELL | 8/0/0 | 7/0/1 | 91358.250 | 87890.000 |

Combined mean own-cash gain versus the paired parent is +175.750 development
and +155.125 held. It converts the two held parent ties into wins but retains
the existing loss. On held 9820101 against Arlene in seat 1, combined cash is
75399 versus 75728; selected SELL is 75707 versus 75722. Neither is a win.

The comparison with selected SELL is mixed. Combined mean game margin is
4842.500 versus SELL 4923.000 on development; held is 4478.125 versus 4462.000.
Across both panels, the combined margin is 32.1875 lower on average, with the
same W/T/L as SELL. **The existing frozen SELL remains selected TITAN.** These
small panels do not establish a general win rate, hosted rating or revenue.

## Interaction observed only on held 9820119

Interaction is `both - service - labor + parent`, computed separately for own
cash and own-minus-rival margin. All eight development pairs and the four held
9820101 pairs have zero interaction. Both seats of held 9820119 instead show:

| Opponent | Service own gain | Labor own gain | Combined own gain | Cash interaction | Margin interaction |
| --- | --- | --- | --- | --- | --- |
| Arlene | 90 | 14 | 223 | +119 | +140 |
| Apex | 101 | 12 | 247 | +134 | +134 |

The saved action arrays show the combination choosing CARE-to-HARVEST at
step 445 on hand 8 and step 452 on hand 9 (one-based hand numbering), absent
from service-alone on that held seed. Both also choose the step-592 hand-1
harvest. The full action traces preserve changed dated SELL quantities as well.
This verifies a behavioral interaction, not its complete causal pathway.
No held-driven policy edit or additional tuned held replay was performed.

## Runtime failures, recovery and cost

The final bounded composition has no runtime failures in either panel. Its
maximum measured call is 473.150 ms development and 470.205 ms held under the
unchanged one-second RPC limit. SELL peaks at 82.138 and 75.877 ms respectively.
This considerable extra computation is part of the tradeoff, not hidden.

The initial raw-loader variant recorded 40 failures at decision zero because
the official raw file loader does not define `__file__`. These are not gameplay
losses. The next, state-isolated but recursively nested forecast recorded two
one-second timeouts at decision 148. Its runner was stopped after 13 saved
records; no unfinished slot was converted into a result. Eleven completed,
unchanged non-composed controls from that attempt are explicitly reused in the
40-game development receipt, not counted twice. All 40 held games are fresh
post-freeze executions. The original nested option remains available explicitly
as `forecast_labor=True`, not as the runnable default.

## Durable evidence

`ACTION-TRACES.json.xz.b64` contains all 80 complete own-agent action sequences,
including the loss. It is an indexed dictionary of 1072 unique actions, encoded
as UTF-8 JSON, XZ-compressed and base64-encoded. The packed bytes are 14744 bytes,
SHA256 `f4ad39e2aad885ae563d8119ccf95b499a81b33585b2adaa4dc0e7f424b05ea1`.
The decompressed indexed JSON is 420513 bytes. It contains no executable code.

```sh
python revenue/kaggriculture/cloud-service-labor-composition/decode_traces.py
# Optional new output; the script refuses to overwrite an existing file.
python revenue/kaggriculture/cloud-service-labor-composition/decode_traces.py \
  --output /tmp/service-labor-actions.json
```

The decoder was executed: all 80 reconstructed canonical action hashes match
the original per-game records; a corrupted input is rejected. It does not run
an agent or consume a game seed. `TEST-OUTPUT.txt` preserves the ten-test output.

A separate full session archive was created as a ChatGPT conversation artifact:
`service-labor-session-evidence.json.xz`, 69384 bytes, SHA256
`b064b0f00a2249de5a3ce78c73a3c316e2d04c1ebc256094a4703edb3c2b13c0`.
Its 15368294-byte JSON additionally retains original reports, selected observation
snapshots, prior failed attempts, runtime manifests, source variants and test
output. That full archive is not a GitHub-hosted file; its hash is recorded here
without pretending that a local conversation artifact is a repository URL.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
