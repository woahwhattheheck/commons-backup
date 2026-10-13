# R05–R08 shared native evidence

All32 candidate games completed719 decisions without failures. These four route experiments reuse the canonical [C00 production-v3 controls](../C00/production-v3-report.json) landed in #13489. Both seats are retained individually; mirrored seats are not independent extra samples.

| Route | Mean delta own | Mean delta margin | Blanket adoption |
|---|---:|---:|---|
| R05 | +729.50 | -1597.25 | No |
| R06 | +727.00 | -420.00 | No |
| R07 | +788.75 | -283.25 | No |
| R08 | +775.75 | -308.75 | No |

Every tested route loses margin on seed1209131101 and gains margin on1209131102 against both opponents. The observed first-two-shop profiles are BAKERY/ICE_CREAM_SHOP and ICE_CREAM_SHOP/ICE_CREAM_SHOP respectively. This is an association across two discovery seeds, not a causal rule or a promotion result. Complete the shared13-route matrix and use predeclared fresh holdouts before adopting conditional routing.

| Route | Opponent | Seed | Own | Rival | Margin | Delta own | Delta margin |
|---|---|---:|---:|---:|---:|---:|---:|
| R05 | apex_v7 | 1209131101 | 73637 | 71182 | +2455 | -6254 | -6990 |
| R05 | apex_v7 | 1209131102 | 161596 | 156799 | +4797 | +8258 | +3941 |
| R05 | arlene_v14 | 1209131101 | 77625 | 77518 | +107 | -7433 | -7080 |
| R05 | arlene_v14 | 1209131102 | 161572 | 158262 | +3310 | +8347 | +3740 |
| R06 | apex_v7 | 1209131101 | 72722 | 70870 | +1852 | -7169 | -7593 |
| R06 | apex_v7 | 1209131102 | 162699 | 154818 | +7881 | +9361 | +7025 |
| R06 | arlene_v14 | 1209131101 | 76339 | 77188 | -849 | -8719 | -8036 |
| R06 | arlene_v14 | 1209131102 | 162660 | 156166 | +6494 | +9435 | +6924 |
| R07 | apex_v7 | 1209131101 | 72739 | 70798 | +1941 | -7152 | -7504 |
| R07 | apex_v7 | 1209131102 | 162762 | 154748 | +8014 | +9424 | +7158 |
| R07 | arlene_v14 | 1209131101 | 76444 | 77097 | -653 | -8614 | -7840 |
| R07 | arlene_v14 | 1209131102 | 162722 | 156099 | +6623 | +9497 | +7053 |
| R08 | apex_v7 | 1209131101 | 72726 | 70810 | +1916 | -7165 | -7529 |
| R08 | apex_v7 | 1209131102 | 162750 | 154761 | +7989 | +9412 | +7133 |
| R08 | arlene_v14 | 1209131101 | 76430 | 77110 | -680 | -8628 | -7867 |
| R08 | arlene_v14 | 1209131102 | 162709 | 156111 | +6598 | +9484 | +7028 |

Both seats mirror these terminals. SUMMARY.json contains all32 cells and the exact canonical control digest.

The shared #13475 builder produced each92-member candidate from exact production-v3 `20f201161b14af7755146b08207593f9fa5df641d2f31e680792ea62c0e24239`. Only the router assignment at144 changed; the terminal assignment remains2 at648. All13plans at144 and648 were separately materialized twice (52publications), with deterministic archives/receipts and complete member/AST verification. That source-only receipt is retained in the raw bundle.

| Route | Candidate archive SHA256 |
|---|---|
| R05 | `a0a0a6bce786ea5aec32f17c193829887c800ddea04840b7ee15e21d432a9d49` |
| R06 | `4ec257841ef36f58a73c66bd55aaf997b3a4fcfd73a7b2dd7866f84057302234` |
| R07 | `2afe7486a6258a2a9a1a3481357882cc42326aa883321aee4ce4b8e812cc2197` |
| R08 | `a67c7d4bd7e7026925baa38045ee1119a3cf479d63b25f1cbdcd87f3c5535be9` |

Native execution uses unchanged evaluator SHA256 `e30b3108e0027477ab7ddbc057892a241c41a1f2b38f72caf267477877c4333c`, loader `61093af280494f95d0f3e5137f716c980ebaf7a2bb53fb333b03566810808e6e`, official engine ref28b6d8af3ce73926b3d0fda1410c1ddd8384ab8c, authenticated Apex_v7/Arlene_v14 source/support, RNG20260912 and1.25/10/900 deadlines. Python3.12.14 and those evaluator/engine/loader/RNG/limit fields match canonicalC00. Archive members and534 inputs perrow were checked before and after; all2,136 post-run file checks passed. This is native offline evidence, not hosted Kaggle scoring.

One passive adapter surrounds the existing pack adapter. It retains only current public farms/market/town/player/step before144/648, preserves delegate argument and returned-action identity, and records runtime plan after144/648/718. Its overhead stays inside the native deadline; isolated overhead is not measured. All64 observed bank vectors match evaluator daily-bank records at143/647. Every candidate and rival has719calls. Each plan has runtime144=its index,648=2 and718=2. Private/configuration fields were not serialized. The original recorder and its four normal/four optimized argument/action/private-data contracts are preserved as execution evidence, not installed as a second long-lived runner.

BLOCK-B-p04-rows.jsonl supplies32 validated rows for the existing P04 consumer. For every seed/opponent/seat, allfour plans share identical raw and normalized pre144 snapshots. Projection uses only the frozen shared core public_step144_snapshot/make_row at source3519ff5 and the merged P04 normalize/hash functions. The six-file #13486 bridge, its candidate-custody gates and private-snapshot game wrapper were not executed or claimed green. The projection receipt names that boundary explicitly.

Raw reports are unchanged executor outputs. raw-evidence.tar.gz retains the original execution/source records, projection records and frozen pure source in90members; BUNDLE-MANIFEST.json lists every raw member digest. It includes command/launch/input receipts, all64rawpublicsnapshots, the4candidate manifests, exact passive-adapter bytes, source materialization evidence, and percell projection/mapping receipts. Historical cloud paths and namespacePIDs identify this run. They are not prerequisites for reading the durable raw bytes.

A racing local C00 run completed after the first authority elsewhere. Its raw reports and explicit DUPLICATE_COMPLETED_NON_AUTHORITATIVE reconciliation are retained under duplicate-control/ in the bundle with zero additional sample weight. All comparisons here use canonicalC00#13489.

Bundle SHA256: `8bb7c01fa36b842c4cd1df5533ba6e46f0b612b5cd1134ede5db69f97d2af9e5`. Combined32-row SHA256: `853cc8df7a20d5d78cefb796ed3ddac079c4ad92d9eaac6c338d9f4d398c9093`.

This evidence update changes no policy/default/CURRENT/release or Kaggle submission.
