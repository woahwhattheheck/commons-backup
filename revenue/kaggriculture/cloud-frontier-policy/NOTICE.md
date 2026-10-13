# Attribution, license and provenance

All delivered policy/build/measurement code is Apache-2.0; LICENSE contains the full text. Upstream authors retain ownership.

- **Kaito Fukami:** unchanged63,309-byte public v43 SparseShopHybrid agent, notebook version13 / scriptVersionId344404785. SHA-256 `69f06a802b62aa08f28705dab5728eb924bb6a7c23ffe0164f65b104cc3dadf3`. Complete source is preserved in vendor/kaito_v43.py and embedded unchanged in candidate.py/main.py. Its bundled modules, route data, planner and weed transactions are reused logic, not LARK inventions.
- **Igor Zharov:** unchanged148,200-byte public Multi-Route agent, version84 / scriptVersionId343725556. SHA-256 `8ac34abce129cf5c9456776c90edf7d2233b3a280bbdcf7622628825ef3669a0`. Complete source is preserved in vendor/igor_multiroute.py. The selected build embeds only exact observation/inventory/market helper functions and constants named in build_selected.py. No Igor farm routes or replay-counter data are included in the selected artifact. Original source describes its route work as public-replay reconstruction; that attribution remains intact.
- **LARK / Commons, September2026:** sales.py, build_selected.py, entrypoint.py, measure.py, focused tests, experiment changes and documentation, under Apache-2.0. Additions are clearly marked in combined source. The selected derivative calls Kaito's actual parent entrypoint once and conditionally changes only sale orders, preserving original worker actions and capital/feed slots. Persistent production state remains Kaito's.

Both parents were already permitted and pinned by cloud-opponent-bench/UPSTREAM.json and the root coordination thread1788762339.088829. Exact cached files were reused in this cloud workspace; no new notebook downloads were made. Public notebooks:

- https://www.kaggle.com/code/kaitofukami/103-128-fresh-public-v43-sparse-shop-hybrid
- https://www.kaggle.com/code/flexonafft/kaggriculture-multi-route-farming-agent

candidate.py is the frozen validated policy. main.py appends a uniquely named official-loader entrypoint without changing that byte prefix. DISTRIBUTION-NOTICE.txt and LICENSE travel inside the archive. Historical results/*-candidate.py files retain rejected/ablation sources with their own hashes; they are not the selected upload. build.py/overlay.py are the first rejected Igor reconstruction, retained for reproduction only.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
