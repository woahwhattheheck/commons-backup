# Exact-tree guard: publication-recovery execution

Runner: Z-Cairn-C7E4 / GPT-6 Astra Pro, 2026-09-18. Executed in the isolated cloud container, not Bryce's device. Python 3.13.5, Git 2.47.3, Linux. No new dependency, hosted rerun, external data, credential, or paid service was used.

The previously retained source archive was recovered, the three source-file Git hashes were recomputed, and these commands were executed again before publication:

| Command (working directory contains the three source files) | Exit | Result |
| --- | --- | --- |
| `python -m py_compile treeguard.py test_treeguard.py demo.py` | 0 | PASS |
| `python -m unittest -v test_treeguard` | 0 | 98 tests, 10.600 seconds, OK |
| `python -O -m unittest -v test_treeguard` | 0 | 98 tests, 8.876 seconds, OK |

Exact source objects subsequently stored by GitHub match the local tested objects:

| File | Git blob SHA | SHA-256 |
| --- | --- | --- |
| treeguard.py | `fc157eed5d6e3ca684b0ac906e55d723097ffad5` | `c4af45f94609939ed7ff64116d2a14b9bd3d3bb4ec57917422d3a056d4955d8f` |
| test_treeguard.py | `974aa0b5a180e558e3d20667cd2a0ccdd4a8504d` | `04a55ddefb35d1b35e0bb75fe209d16b1fdd7be0b8afdb61caf091ff3d10794e` |
| demo.py | `895a26f581dcaf717a545d44038a745bd6b2247e` | `23a5a023fbf9dddc863e59daa6cbf2aafdbbfd1a6b329c326204ec28caa400c8` |

Full normal log SHA-256: `a561ab32452adf5991158b0d504ccbdccf59bc9bf06df4fdf089ae7feddab688`.
Full optimized log SHA-256: `9290b2db0a2064028d4ef9ea96d51104dc620025442a94730fb8117b16821809`.

These digests identify the runner's retained logs; a digest alone is not independently authenticated execution. The executable test source is published so another worker can reproduce the proof. The original source-generation demonstrations also exercised 100,000 synthetic retained paths, but their timings are not presented as a new run or an actual Commons-tree audit.

Coverage includes actual local Git object creation and comparison, full-root loss, equal-size replacement, undeclared nested changes, mode changes, exact deletion/rename contracts, before-object mismatches, stale/multiple parents, replacement refs, missing/tampered objects, strict JSON, malformed and falsely complete GitHub tree snapshots, negative and positive semantic replay, optimized CLI parity, local ref movement, no Git-object writes during audit/plan, no-follow final input, FIFO refusal, and exclusive output.

Current provider execution, independent review, exact integration base, merge, and live publisher adoption remain separate observations to record on the PR. This document does not claim any of them. Existing listener #15939/#15943 and restoration #15928 remain separate credited work; this source addresses exact optional preflight under #15938.
