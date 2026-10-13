# Completion-order consumer repair

RECEIPT-9096 follow-through to PR10065. The existing base reader now requires its single unittest success/failure footer to occur **after** its single reported test count. No helper, producer, workflow, policy, runtime, or archived test source is changed.

## Reproduction and source

The preceding reader `007a846e91e8923be742c1754da0c9bc8777d896` accepted `OK\n\nRan 16 tests in 0.1s\n` as a complete funded-suite result. This was reproduced on a detached copy of existing artifact10036877991 with only `funded-join-tests.log` changed. A newly calculated local fixture digest was supplied, so a provider-digest mismatch could not mask the ordering error. The old reader returned COMPLETE_PASS95 with no problems; the corrected reader returns INCOMPLETE with `funded_join: missing or ambiguous unittest completion`.

The original provider artifact remains unchanged: SHA256 `af9b3fc1de67eaed39c842b6c71d8fcd84e4ae8c0bd31465cb89ed73252cae29`, checkout0144d5c6e2d71ac80cb62abd8d7ca0223bb75f27, run34174806533, attempt1. A detached fixture digest is not a provider receipt.

Corrected reader: 25,590 bytes, Git blob `0cc4b4ab6b3db350b06ec24bd63068b13ae17946`, SHA256 `dbe2481740f0f619096d57f0d258af51003e4f8da4b7a750ba7ce2a99257d2f5`.

New regression source: `test_footer_order.py`, 1,919 bytes, Git blob `00664d4307a10124865faefe21f3ebe510ad03c9`, SHA256 `89ac5e35e93f9f6b564371de95e6a6a860690dfed73d14e7a68ad0f151926c06`.

## Executed results

Three new methods cover reversed funded completion, reversed completion across all three core suites, and correctly ordered output with its optional JSON trailer. On the preceding reader these three methods have four failing assertions/subtests and zero errors; on the corrected reader all three pass. The combined command runs **44 methods**, all passing, with zero failures/errors: unchanged20 base +13 funded +8 v2 +3 ordering.

```sh
cd revenue/kaggriculture/cloud-selected-joint-checks
python -B -m unittest -v test_joint_receipt test_funded_receipt test_combined_receipt test_footer_order
```

The executed helper for this result is unchanged JOINT `f3b0562221cc1ef81ad0e95f3a6145474c44ac8b`, SHA256 `08f5d5c81a580dc961c1fd4d5127a8b7cdef8206228d35026348d7a23a86dda`. Its own completion-order check was already correct and is not duplicated or replaced.

Six existing downloaded ZIPs were consumed with matching retained provider digests and snapshot checkout/run/attempt expectations. Their results remain:

| Artifact | Reported methods | Status |
| --- | ---: | --- |
| 10033736596 | 37 | INCOMPLETE, same three missing-market issues |
| 10033795374 | 51 | COMPLETE_PASS |
| 10034414947 | 79 | COMPLETE_PASS |
| 10036877991 | 95 | COMPLETE_PASS |
| 10037093197 | 117 | COMPLETE_PASS |
| 10037249764 | 119 | INCOMPLETE; capture/score/workflow additions remain unexamined by this helper version |

The last artifact contains159 methods;119 is explicitly the recognized subset before JOINT's separate helper extension, not a new159-method result. Its provider SHA256 is `ddacdc557419258c072e1c2ef62ebe4d101a5f3b79e6967a153a650268a6d42d`, checkout4ab883af10561fa7f685f90a79e98f80f7061fc0, run34175970193, attempt1.

All prior source-bound41-reader/26-independent/22-helper receipts remain attached to their original sources. This result does not relabel the independent26 methods as executed on the corrected reader. No archived test methods, engine transitions, games or seeds were rerun. Only receipt-consumer regression methods executed.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
