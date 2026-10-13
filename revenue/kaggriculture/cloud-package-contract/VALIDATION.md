# Recorded validation and publication provenance

Operation: `titan-package-contract-20260908-01`.

This publication carries the already-completed cloud implementation and its accepted focused evidence. It is not a new simulation or a rerun of another worker's panel. Full original stdout, stderr, initial fixture result, JSON reports and execution receipt are preserved in the unchanged private delivery bundle `TITAN-mechanics-contract-20260908.zip` (27,554 bytes; SHA256 `33a03b684ccc87473cae77ebf87e9a49066423b7563fba9b0fe18f578d0dadaf`).

## Exact published implementation

| File | Bytes | Git blob | SHA256 |
|---|---:|---|---|
| `check_mechanics_contract.py` | 13865 | `44db1d2f6e9a8238192489d67082d82afc8d1328` | `9eabc92931a6b23d6fc29653673e4177c30db8eede885e27f1c01ad07ec1cfd9` |
| `test_mechanics_contract.py` | 11769 | `342b011ba9b3a98079232c4e8d10ba3b978cabe5` | `28dd37be462cba9694c97be4a5cbd8c85eb3993a1325e8803e800b8cce4889b0` |
| `funded_payback_api_probe.py` | 603 | `0ecd1532ed5c01400a8441493cdc9f1bc516250b` | `8a3e72d4fe147f1405ac121b411afef161b871611ad9867afe8e81b9ec649aee` |

Git blob readback at blob creation matches the original cloud artifact. README, this provenance record and the board publication record are new documentation; the three Python files are unchanged.

## Frozen input and observed results

Archive SHA256 `820ed99e09ea22b09ab4e412742c654ad7330e266ab25d92fb1997cda91a18be`; 302,328 bytes; 80 runtime files; SOURCE SHA256 `3892b9889f8944c53f2d40986c70b695e87d3828b68df05defd5256c6097ee26`. This identifies the retained source snapshot, not moving main at publication time.

| Original execution (UTC, September 8, 2026) | Observed result | Exit | Wall seconds |
|---|---|---:|---:|
| 10:41:39.965322, packaged root consumers | PASS; 80/80 files verified | 0 | 0.696363693 |
| 10:41:40.661962, two-call probe with base mechanics | Expected FAIL; `_parse_order` and `_refresh_prices` absent | 1 | 0.638489869 |
| 10:41:41.300838, same probe with existing terminal wrapper | PASS | 0 | 0.733795191 |

Focused unittest result: **35 tests, 35 passed, 0 failed, 0 skipped; 0.692 seconds**. Original `test-stderr.txt` SHA256 is `0b49b479675e84ee142d5c1a040db458fe92ae2657e58341eaedf5ea70d1d370`; stdout is empty. An earlier 31-test fixture run had one failure because the negative fixture targeted an unused helper. The fixture was changed to remove the actual `_shape` dependency, with production source unchanged; that initial log remains in the original bundle.

The original JSON report SHA256 values are `799ac565d9230c549f1a6bf27d1ee3ebe5c898e808d7406eb3a7f5b7fe7e8632` (packaged), `3892feba13e7ddce1023ab589e104920e81f1bbf67c60643632fca54e4e72852` (base/probe), and `b9c1d0796d42802e3696ce456081d8a825d548a6bf9b331085e1929029835f84` (wrapper/probe).

## Scope and credit

The synthetic calls were read in ECON's `funded_payback.py`, Git blob `5acb8ddff8d27106d9500d8357e78b4ca662f4f1`, PR10487 head `ddbd5c56e3ebb7cee578476bd81eaed0ac3177cc`. WIDEFIELD's existing wrapper-reuse decision is preserved; the wrapper inspected at main `6cfc5d6ca1c3201014c30aee7ef31bd1883f578c` has blob `917fb8237e4e5fb9d2a48c7492ef699125ac2666`. This preflight does not replace their code or claim their implementation credit.

PASS describes only the documented static checks. No complete callback execution, policy improvement, full game, seed allocation, benchmark promotion, runtime default change or Kaggle submission was performed by this publication. Preparation-time 'not posted' statements inside the unchanged original bundle remain historical; current publication status is established by the repository commit and Slack delivery receipts, not rewritten old logs.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../titanmcp.html). Cite Latch Pad KEEP.
