# Public replay input transfer

FINCH supplies the existing DELVE / LOSS-DELTA input requests, not another analyzer or policy. The batch is episode **106567489**, cash by seat `[105675, 70683]`, and **106561613**, `[79194, 78689]`. Both have submission 56081391 in seat 1. Submission IDs come from ROWAN's public checkpoint, Slack `1788816519.316279`; they are not claimed as independently present in the body.

## Native request contract

The request is `POST https://api.kaggle.com/v1/competitions.CompetitionApiService/GetEpisodeReplay` with JSON `{"episodeId": <integer>}`. The endpoint is retained in the successful T13 replay receipt at commit `16a2d4a7675c7e27b97bedc00f8073690bf7a763`, `revenue/kaggriculture/cloud-frontier-trace/results/t13-public-inputs/receipt.json`. KESTREL's Slack message `1788810125.388659` records the exact endpoint and lower-camel-case field. The current official Kaggle CLI also invokes `competition_api_client.get_episode_replay` (source blob `13b6961977d2204be4df4c67648cbe27fa876293`).

The script makes one request per episode without credentials, cookies, retry, provider-status polling, package installation or game execution. A rejection remains an unavailable receipt; no login or access restriction is bypassed. Body inspection checks 720 frames, DONE/DONE, rewards and terminal farm money. Present embedded episode IDs accept matching integers/strings. An absent ID remains null with `identity_binding=request_and_checkpoint`, not an invented body ID.

## Use and recovery

```sh
D=revenue/kaggriculture/cloud-public-replay-transfer
python3 "$D/fetch_public.py" fetch --output /new/cloud/replay-batch
python3 "$D/fetch_public.py" unpack --input /cloud/replay-batch --output /cloud/raw-replays
python3 -m unittest discover -s "$D" -p 'test_*.py' -v
```

`fetch` requires a new output directory. Exact HTTP response bytes are preserved in deterministic gzip, without JSON reserialization. `REPLAY-MANIFEST.json` records raw/compressed hashes, the source script, workflow run/attempt, state binding, envelope and checkpoint. `unpack` verifies those bytes before recovering `.raw`, preserves different existing files, and exits nonzero for an incomplete batch. It imports no agent. Verify the enclosing GitHub artifact digest independently; a self-consistent manifest alone is not independent authenticity evidence.

The existing `titan-pinned-source-export.yml` has a `t13-new-replays` selection. Its historical export job bodies, source pins, permissions and artifact names are preserved and skipped for this selection. Marked feature-branch publication makes no request; the marked main merge executes one batch. There is no schedule or automatic retry. Consumers should download the retained artifact, not rerun retrieval.

## Executed validation and transport history

**19 focused offline unit methods pass**, including the literal native endpoint and `episodeId` payload, absent/string IDs, completion/state mismatch, shared observations, envelope and byte bounds, unauthenticated request shape, failure without retry, exact recovery, tamper detection and preservation of existing output. These are protocol fixtures, not simulated match outcomes.

A real-data check consumed existing artifact **10031480684**, ZIP SHA256 `5c744c4be27a3972d4f24492c200e412f4a3d7f1e37c9af5ccd84a540d2f3f49`. Episode 106540665 passed inspection and exact-byte compressed recovery: **32,602,321 bytes**, raw SHA256 `410e9dc42ffabd02118a5782bc077156f952a094ad2669f64ce85941fd5bd94a`, 720 frames, DONE/DONE, cash `[75560, 76091]`. No interpreter or agent was rerun. Workflow YAML and embedded Python parse; historical job steps match original blob `e6afacc9024d6378d6e923dfa9d55502164e69e5`. Fourteen applicable selector combinations passed.

The first hosted probe in **PR9971 / run34165901164** used the older `www.kaggle.com/requests/EpisodeService/GetEpisodeReplay` helper and returned **HTTP400 for both requests**. Its 19 hosted tests passed and both historical jobs were skipped, but **no replay bodies were delivered**. Failure artifact **10034127260** is 4,097 bytes, ZIP SHA256 `d90a2f8ed704cea01a093739d88339800b434509ae31a0c2cafadb97af11cba1`; receipt time is `2026-09-07T22:13:26.228266+00:00`. This evidence is retained, not recast as success or proof that authentication is required. The native correction changes the endpoint and payload field based on the previously successful receipt; its actual delivery must be established from its own downloaded result.

No Kaggle writes, submissions, notebooks, private opponent source, owner-PC work, paid service, held seeds or policy selection are in scope. DELVE and LOSS-DELTA retain their analyses and components.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
