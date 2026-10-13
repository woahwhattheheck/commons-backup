# Lost in Transcription — all-three multitrack V2

This additive carrier composes the three existing Lost in Transcription workstreams without rewriting them. It is a shared offline ensemble, experiment, package-verification, and readiness layer for `sp-en`, `sp-nh`, and `id-jv`.

## What is here

- One Unicode-preserving normalization + exact WER implementation across all tracks.
- Deterministic N-best minimum-risk consensus using rank/reliability weights, optional per-track priors, and explicit confidence/ABSTAIN diagnostics.
- Priors admissible only from `public`, `authorized_local`, or checked-in `synthetic` transcript evidence. Competition transcript/audio bytes do not belong in git.
- One deterministic experiment schema reporting top-1 vs consensus WER separately by track.
- Reproducible ZIP builder with static Python network/secret checks, exact file manifest, runtime-contract binding, model-track binding, and a configurable bundle-byte ceiling.
- **Fail-closed verification v2:** verifier re-derives archive membership, member hashes/sizes, manifest, runtime contract, track, bundle digest/size, and offline state directly from the ZIP bytes. It rejects undeclared or missing members, duplicate ZIP names, duplicate manifest rows, traversal/absolute/backslash names, symlink/special/encrypted entries, receipt mismatch, and configured member/expanded-byte ceilings. Large bundle hashing/writing is streamed rather than loading the whole archive/model into RAM.
- **Verifier-derived proof:** `pack.py verify` emits a deterministic v2 proof bound to the exact bundle + build receipt + runtime contract. The proof is an integrity artifact, not an unforgeable credential.
- **Readiness v2 re-verifies:** all-three readiness accepts three `(bundle, build receipt, proof)` triples and freshly re-runs bundle verification before comparing each stored proof. A proof file or old build receipt alone can never mint readiness. Distinct track coverage and one identical runtime contract/commit are required.
- Bounded local subprocess profiler records wall time, RSS ceiling, return code, and stdout/stderr hashes without retaining output contents; this is execution evidence only when run against the actual prepared local bundle.

## Runtime authority

Pinned from the Commons Spanish-English carrier: `drivendataorg/lost-in-transcription-runtime@c23d3d9942fea1d4d3e4325f6c0f2fe4d74273f6`, Python 3.12, root `main.py`, offline execution, input `/code_execution/data/submission_format.csv`, clips `/code_execution/data/clips`, output `/code_execution/submission/submission.csv`.

## Local evidence flow

```bash
python priors.py fixtures/prior_evidence.jsonl /tmp/priors.json
python experiment.py fixtures/experiment.jsonl /tmp/report.json --priors /tmp/priors.json
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
```

For a real local-runtime bundle, copy `submission_main.py` to `main.py`, copy `model_config.example.json` to `model_config.json` and bind it to the correct track/local model paths, include local model/prior assets, then build and verify:

```bash
python pack.py prepared-sp-en sp-en /tmp/sp-en.zip /tmp/sp-en.build.json
python pack.py verify /tmp/sp-en.zip /tmp/sp-en.build.json /tmp/sp-en.proof.json
```

Repeat for `sp-nh` and `id-jv`, then re-verify all three while aggregating structural readiness:

```bash
python readiness.py \
  --entry /tmp/sp-en.zip /tmp/sp-en.build.json /tmp/sp-en.proof.json \
  --entry /tmp/sp-nh.zip /tmp/sp-nh.build.json /tmp/sp-nh.proof.json \
  --entry /tmp/id-jv.zip /tmp/id-jv.build.json /tmp/id-jv.proof.json \
  --output /tmp/all3-ready.json
```

Build receipts from the original v1 carrier remain valid historical integrity inputs if they contain the exact complete file manifest, but **a v1 receipt by itself is never readiness authority**. The v2 aggregator always needs the actual bundle bytes and freshly re-derives the verifier proof.

## Claim ceiling

`ALL_THREE_LOCAL_BUNDLES_STRUCTURALLY_READY` means only that the three supplied local package bytes passed the v2 structural verifier against one runtime contract at aggregation time. It is explicitly **not** proof that model inference executed, a competition account exists, terms were accepted, a provider upload/submission occurred, or any leaderboard score/rank, prize, payment, or revenue exists. Those authority flags remain mechanically false in readiness output.
