# Mozilla Lost in Transcription — Spanish–English offline carrier

Competition-isolated tooling for the paid North American Spanish–English ASR track. The repository contains no competition media, private transcripts, or model weights.

## What ships

- `core.py` — organizer-compatible text normalization, dependency-free corpus WER, bilingual bigram prior, weighted MBR consensus and uncertainty evidence.
- `build_prior.py` — transforms an offline transcript CSV into raw-text-free aggregate n-gram counts bound to the source SHA-256.
- `submission_main.py` — official-runtime-shaped entrypoint for 2+ **local** `faster-whisper` model directories; no network fallback.
- `pack.py` — deterministic root-level submission ZIP builder with symlink/path, secret, network-code, file-type, and optional size ceilings plus archive/member receipts.
- `experiment.py` — synthetic-only ablation runner.
- `runtime_contract.json` — exact upstream runtime commit and observed interface/dependency contract.
- `tests/` + `fixtures/` — hostile and deterministic regressions.

## Local checks

```bash
python -m unittest discover -s tests -v
python -O -m unittest discover -s tests -v
python experiment.py fixtures/hypotheses.json --output /tmp/spen-report.json
python -m py_compile core.py build_prior.py submission_main.py pack.py experiment.py
```

The synthetic fixture is only a mechanism check. It must never be represented as a competition score.

## Build a real local bundle

Create a private staging directory containing:

- `main.py` copied from `submission_main.py`
- `core.py`
- `model_config.json`
- at least two local model directories named by the config
- optional `prior.json` generated with `build_prior.py`

Then run `python pack.py STAGING submission.zip --receipt receipt.json`. The packer refuses obvious network client code and secret-like credentials because official execution is offline and secrets have no legitimate role in the archive.

See `docs/METHODS.md` for the experiment ladder and truth boundary.
