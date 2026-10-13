# Optional bounded asset codecs — LARK KAG-PACK continuation

This adds a streaming asset format, deployable decoder bundles and a measured
comparison of Commons MUHC/RINGDELTA against ordinary archives. PR9770 and its
accepted nine tests/eight parity games are preserved; neither batch was rerun.
Root remains the Claude UI driver and owns E4B model decisions.

**Use ordinary archives for the four measured inputs.** All 40 final codec/input
combinations restored exact bytes, but none beat the best ordinary archive once
decoder source, manifests and licenses were included. RDV1 beat gzip on the
synthetic correlated records; ordinary xz was smaller still. These are small
asset measurements, not model-weight results or a model-to-100-MB claim.

## Implemented tools

- `asset_codec.py`: streaming encode/decode, plus bounded seek/read sampling.
- `assets.py build`: an actual `asset-bundle.tar.gz`, containing framed bytes,
  a callable `restore.py`, exact decoder source, asset notices and licenses.
  It extracts that archive and measures a fresh-process restoration.
- `assets.py bench`: compares gzip/bzip2/xz ordinary archives with ten framed
  options: raw, zlib, bz2, xz, RDV1, RDV1+zlib, MUHC raw/stack/fold/evolve.
- `assets.py compose-profile`: adds the bundle to an existing PR9770 export
  profile without rewriting main.py. The selected agent explicitly invokes its
  restore function when it needs the asset.
- `inputs.py`: regenerates the bounded comparison inputs, preserving hashes.

Inner codecs are the unchanged Commons Python byte APIs at
`fed09b138bf110aff02a26e6edfacaba03ec21db`; exact source and license references
are in `vendor/manifest.json`. RDV1 uses width25. MUHC uses width200; stack uses
25×1 tiles, fold uses four adjacent folds, evolve uses XOR_ROW plus zlib.
No exploratory search or substrate actuation is performed by this integration.

## Memory and framing

New KAC1 framing: a 56-byte file header containing codec, frame size, original
size and SHA-256; each frame has a 40-byte length/hash header followed by the
unchanged inner container. Each frame is independently decoded and checked.
The final frame retains every tail byte; zero-length files require no frames.
MUHC/RINGDELTA headers are counted separately from the outer framing.

Every transform receives **at most 16,384 bytes**. Encoding and restoration
stream from disk and publish the completed result without replacing an existing
file. MUHC dimensions are checked against the bounded frame before decoding.
The default input/output budget is 256 KiB; callers can explicitly choose a
different total budget while the per-frame limit stays fixed. The comparison
driver limits its whole input batch to 1 MiB. Child encoding/decoding processes
use 512 MiB address-space, 30-second CPU and 40-second wall limits.

The 3.66-GB model was not opened, downloaded, hashed or expanded in this run.
To measure a real model sample in root's existing cloud VM:

```sh
python -B revenue/kaggriculture/cloud-pack/asset-codecs/asset_codec.py sample \
  /existing/cloud/model.gguf /tmp/model-sample.bin --offset 1048576 --length 65536
```

Choose offsets from the actual file/tensor layout. The command reads only the
requested 1..65,536-byte span and records its offset, hash and source file size;
it explicitly does not compute a whole-model hash. Preserve the model's actual
license/notice with the sample. Sampling alone does not establish a whole-file
ratio, model quality, peak inference memory or hosted runtime compatibility.

## Use a codec bundle

From the repository root, choose an actual asset and its original license:

```sh
python -B revenue/kaggriculture/cloud-pack/asset-codecs/assets.py build \
  --input /tmp/model-sample.bin --asset-license /existing/cloud/MODEL-LICENSE \
  --notice 'Original model author, version, source and sample offset' \
  --codec rdv1 --output /tmp/asset-rdv1
```

The result contains `payload/`, the deployable tar.gz and a complete receipt.
After extracting the bundle, `python -B restore.py /tmp/restored.bin` restores
the asset. For a selected agent's submission profile:

```sh
python -B revenue/kaggriculture/cloud-pack/asset-codecs/assets.py compose-profile \
  --profile /existing/selected-profile.json --bundle /tmp/asset-rdv1 \
  --prefix titan_assets --output /tmp/selected-with-assets.json
python -B revenue/kaggriculture/cloud-pack/pack.py build \
  --spec /tmp/selected-with-assets.json --output /tmp/selected-export
```

The candidate can call `from titan_assets.restore import restore`, then
`restore('/tmp/restored.bin')` once before using that file. The decoder is loaded
from its own bundle by path, so multiple codec bundles can coexist in a process.
Restoration is explicit: simply adding assets does not alter the policy.
Charge restoration, model import and inference to the applicable runtime budget.

## Final measured archive sizes

Numbers include notices, licenses and manifests. Optional codecs additionally
include the actual decoder/bootstrap and required vendor sources. All optional
distributions use tar.gz externally. Ordinary archives store the original asset
directly and need no Python decoder. No ratio below excludes delivery overhead.

| Input | Source bytes | Ordinary gzip | Ordinary xz | RDV1 bundle | MUHC raw bundle | MUHC stack bundle | MUHC evolve bundle |
|---|---:|---:|---:|---:|---:|---:|---:|
| lean20 main.py | 15,645 | 6,383 | 6,080 | 25,754 | 29,430 | 39,149 | 35,598 |
| Already packed lean20 archive | 12,594 | 14,026 | 13,896 | 26,691 | 36,582 | 36,636 | 36,591 |
| Synthetic correlated width25 records | 250,013 | 89,139 | 61,824 | 81,163 | 113,268 | 210,288 | 103,969 |
| Synthetic noise | 65,537 | 67,093 | 67,660 | 80,671 | 90,572 | 90,718 | 90,633 |

For the correlated fixture, RDV1's total distribution is 7,976 bytes smaller
than gzip, but 19,339 bytes larger than xz. This input was deliberately generated
with 25-byte rows and four changed positions per row; it is not representative
evidence about quantized model weights. The noise and precompressed controls
also preserve negative results. All optional codecs remain explicitly usable.

Measured cold RDV1 restore plus extraction for the 250,013-byte fixture was
0.0756s. MUHC raw/stack/fold/evolve took about 0.555/0.795/1.097/0.713s respectively.
These include a fresh Python process, imports, decode, hashing and file writes;
ordinary extraction timings are measured in the already-running driver and are
labeled separately. Child-reported peak RSS reached 29,140 KiB across this
bounded run, including process startup. These cloud measurements do not impose
Kaggle's CPU quota or certify hosted behavior. A costly asset decode may consume
the first-action budget before model inference begins.

`measurements/comparison.json` contains every row, framing/decoder byte count,
source and archive hashes, encode/decode CPU, wall time, RSS and limits.
`profile-integration.json` records two differently packaged assets restored in
one process and a real 38,320-byte PR9770 export with unchanged main.py.
`sample-receipt.json` records a 65,536-byte seek/read from the synthetic fixture.
These are new asset measurements; zero game runs and zero old-suite reruns.

## Reproduce only when another measurement is needed

```sh
python -B revenue/kaggriculture/cloud-pack/asset-codecs/inputs.py /tmp/codec-inputs
python -B revenue/kaggriculture/cloud-pack/asset-codecs/assets.py bench \
  --input /tmp/codec-inputs/main.py --input /tmp/codec-inputs/submission.tar.gz \
  --input /tmp/codec-inputs/synthetic-correlated-25.bin \
  --input /tmp/codec-inputs/synthetic-noise.bin \
  --asset-license revenue/kaggriculture/cloud-pack/LICENSE-MIT.txt \
  --notice 'TokenJunkieLabs owner-authored inputs, MIT option. main.py and submission.tar.gz are existing lean20 artifacts; synthetic-correlated-25.bin and synthetic-noise.bin are labeled fixtures, not model weights.' \
  --output /tmp/codec-comparison
```

Use new output directories. For a targeted comparison supply repeated `--codec`
arguments. The initial prototype comparison was superseded after the generated
bootstrap was isolated from other asset modules; final table/report values refer
to the delivered loader. Do not repeat PR9770's completed game/test batches.

## Delivery and licensing

`examples/structured-rdv1.tar.gz` and `examples/lean20-muhc-stack.tar.gz` are actual
decoder bundles with their matching receipts. `examples/lean20-with-asset.tar.gz`
is the integrated submission-shaped demonstration; it does not activate or
promote a new policy. Root selects any use in its model lane.

New integration source: MIT OR CC-BY-4.0; full texts included. Decoder bundles
select the MIT option to avoid redundant license payload. Vendored codec source
and its Apache-2.0 license remain unchanged, and each input's supplied notices
and license are included. No model assets are relicensed or redistributed here.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
