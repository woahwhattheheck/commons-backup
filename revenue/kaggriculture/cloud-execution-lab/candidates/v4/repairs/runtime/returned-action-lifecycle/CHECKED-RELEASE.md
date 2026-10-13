# Checked-release parity addendum

This extends the earlier component-only `LIFECYCLE-RESULTS.json`; it does not
relabel those tests as full-game evidence or as current-source-HEAD validation.
One existing V4 lifecycle package, one unchanged source repair.

## Executed result

Verified the checked archive `b567942e4fb4e0571ebf9f8eaaf143d4a9156df3289f09a98db37823ef4d68d9`,
its SOURCE manifest, and all 109 runtime members. Ran the native `main.py::agent`
with its unchanged configuration and the official interpreter/process evaluator.
The candidate differs from the baseline in exactly two members: the repaired
runtime `863a36442bd0f2b475db4c2647a27daf933bba83` and integrated consumer
`53a610f9abaab64690d7a555bf283b87aa282e51`.

Four complete games: baseline and candidate against `official_starter`, seed
9922999, both seats. Each game completed 719 TITAN calls without a reported failure.
Both pairs have identical full action/state trace hashes and final scores.
TITAN scored 190363 and the starter 3550 in each game; this is a parity smoke,
not a win-rate estimate or evidence of improvement against competitive opponents.
The 32 component tests also passed in normal and optimized Python on these
checked-release dependencies. Python was 3.13.5; no Python 3.11 or hosted Kaggle run.

`CHECKED-RELEASE-SUMMARY.json` contains the paired results and all scope limits.
`CHECKED-RELEASE-LOGS.json` contains the lossless full result and execution logs.
The earlier independent cold-start and mutation receipts retain their own scope.

## Reproduce

Existing artifact 10175943272 contains the pinned archive at
`checked-package/exports/titan-current.tar.gz`. The runner refuses a different
archive or manifest and never writes a new release archive or changes defaults.

```sh
python check_release_parity.py \
  --archive /path/to/checked-package/exports/titan-current.tar.gz \
  --output /path/to/NEW-parity-result.json
```

The archive is not interchangeable with current source HEAD: at validation,
its selected_action_sell.py was 7d0f4e68, whereas main source was 68b82183.
This result does not close current-HEAD composition, whole-V4 acceptance,
competitive economics, or deployment gates. Consume both repair outputs in the
single V4 assembly and keep the separate integration checks; do not overwrite a
newer peer runtime or bypass exact input pins.

## Decode and verify the original records

The initial unchunked transport at commit b6f7d8df had transcription corruption.
Commit 912372fd corrected only the log transport; source, tests, summaries and
executed results did not change. The corrected bundle's Git blob is
`6cc47a695b1f93c0f62db6c3c35d8280a467b0a6`, verified against the local originals.

```python
import base64, gzip, hashlib, json
from pathlib import Path
bundle = json.loads(Path('CHECKED-RELEASE-LOGS.json').read_text())
raw = gzip.decompress(base64.b64decode(''.join(bundle['data_chunks']), validate=True))
if hashlib.sha256(raw).hexdigest() != bundle['decoded_json_sha256']:
    raise ValueError('log bundle mismatch')
logs = json.loads(raw)
summary = json.loads(Path('CHECKED-RELEASE-SUMMARY.json').read_text())
full_result = logs['CHECKED-RELEASE-PARITY.json'].encode()
if hashlib.sha256(full_result).hexdigest() != summary['raw_result_sha256']:
    raise ValueError('full result mismatch')
for name, text in logs.items():
    print('\n=== ' + name + ' ===\n' + text)
```

No production source, default, release archive, Actions dispatch or Kaggle
submission was changed by this package or these validations.
