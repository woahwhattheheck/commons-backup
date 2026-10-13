# XOR Ramsey product API — recovered source

The complete pure-JavaScript implementation is published here with its mathematical derivation. It constructs and navigates implicit triangle-free edge colorings from a finite XOR-difference palette, with exact edge/neighbor rank, selection, paging and triangle witnesses.

**The originally computed dimension-14 dataset is unavailable.** A connected-store loss occurred before publication. The implementation was recovered byte for byte from its full tool transcript and matches the source frozen before execution: Git blob `62aae4f304edd0440c61e1e2a09dfa57ae4a1b2c`, 25,505 UTF-8 bytes. The lost snapshot and full 18-query output packet were not reconstructed or rerun.

| File | Contents |
| --- | --- |
| [xor_ramsey_product.cjs](xor_ramsey_product.cjs) | Complete recovered normalizer, compiler and saved-reader source |
| [RAMSEY_PRODUCT_API.md](RAMSEY_PRODUCT_API.md) | Product proof, exact orderings, contracts, limits and custody boundary |
| [product14_run_custody.json](product14_run_custody.json) | Surviving transcript observations, normalization steps, query inputs and explicit missing-data disposition |

The custody JSON is **not a loadable snapshot**. The originally planned `greenwood_gleason_product14.json` is absent. Its pre-loss 133,904-byte identity is recorded only as unavailable content, without a durable locator.

The one pre-loss execution used the classical Greenwood–Gleason three-color K16 palette and 14 first-difference coordinates. It reported 42 colors on 72,057,594,037,927,936 vertices, represented without enumerating the product's vertices, edges or triangles. Its summary/counters and 18 query inputs survive; the complete certificate rows and query outputs do not.

The base construction retains [Greenwood–Gleason's 1955 attribution](https://doi.org/10.4153/CJM-1955-001-4). The [official August 1, 2026 report, item 9](https://openai.com/index/ten-advances-in-mathematics/), and current formal source report Erdős 183 resolved by a superexponential lower bound; this package records that status without a proof audit. It is not a new Ramsey bound, exact Ramsey number, record or resolution.

The module has no imports, I/O or native dependency. Its generic compiler can produce a complete snapshot for an authorized caller; its saved reader requires that complete snapshot. Documentation does not substitute the custody record for the missing data, and recovery performed no new mathematical execution.
