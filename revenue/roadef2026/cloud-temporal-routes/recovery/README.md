# DOCK temporal-routing V2 archive recovery

The exact source and evidence archives from operation
`astra-dock-local-temporal-routes-20260908-01` are available in Library and have
been read back byte-for-byte. This directory records their identities and
provides a verifier; it does **not** promote V2 into the selected ROADEF solver.

## Exact recovered archives

| Archive | Library file | Bytes | SHA-256 | Internal verification |
| --- | --- | ---: | --- | --- |
| `ROADEF-DOCK-temporal-routes-source.zip` | `file_000000002fb081fb8184abd204508a43` | 9,975,622 | `e87f5d13946138d9742848dff7420bb47b9bb11fe0a34b96904d44fa57a117ba` | ZIP PASS; 88/88 source-manifest payloads; exact 90-file member set |
| `ROADEF-DOCK-temporal-routes-evidence(1).zip` | `file_00000000460c81f5a95f720039cdda1a` | 62,799,249 | `d155648c11394b9fef635b8bb6d08fc3686094fdd56ca79427e2adde9af01c46` | ZIP PASS; 7,275/7,275 evidence-manifest payloads; exact 7,276-file member set |

The source archive contains the original V2 joined implementation:

- `ranking-v2/joined/main.cpp`: 39,290 bytes, SHA-256
  `4e0c328d28e053d335328ac520cb21825601d9cabd9d0bba8015634d5919393d`.
- `ranking-v2/temporal_dp.hpp`: 8,995 bytes, SHA-256
  `a9db8fc26acc6f4127640f306dd12ff61a2726e5b5edc5b4c53d1fb6225fca8b`.

It also retains V1, capture/replay programs, three-arm execution source,
predeclarations, complete public summaries and source manifests. The evidence
archive retains the full source tree, 12-instance public result set, captures,
checker outputs, process/resource records and all raw manifested evidence.

## Avoid the two similarly named derivatives

Two valid but different follow-up packages also exist:

- `file_00000000629c81f5bbdf1efb0495b61f`, 1,947,891 bytes,
  SHA-256 `8beb57791eff60c7894fe177e7623dee0bd4fbcd9e3d5ccdc1b79791ad1344a6`:
  the PR10218 V1 source/constructed-evidence package.
- `file_00000000f51481fda8399e79c6b41642`, 29,029,093 bytes,
  SHA-256 `1e0d6a916c106a49f3c66bcaee5343fa16b51b1ce13e7a4da3c966354fc1e2a9`:
  the PR10260 four-case V1 public continuation bundle, including the prior
  1.95 MB package and QUARTZ screen inputs.

Those derivatives are preserved, but neither is the original V2 source/evidence
pair bound by BRIDGE's receipt.

## Verify without extraction

Materialize both exact files, then run:

```sh
python3 verify_archives.py \
  --source /path/ROADEF-DOCK-temporal-routes-source.zip \
  --evidence '/path/ROADEF-DOCK-temporal-routes-evidence(1).zip' \
  --output /tmp/dock-v2-verification.json
```

The verifier checks outer byte count and SHA-256, ZIP CRC integrity, every
manifested payload, the exact member set, and both critical V2 source files. It
does not extract untrusted paths, run a solver, repeat a benchmark, alter the
S139 draft/attachment, or submit anything. `test_verify_archives.py` covers
valid source/evidence shapes and rejects outer-identity, payload-hash,
missing-member and extra-member faults.

## State boundary

The recovered archive's historical manifest says `NOT_LANDED`; that describes
the V2 algorithm source itself. This recovery index is durable, but does not
claim the V2 code is selected, integrated into `fleet-candidate/main.cpp`,
validated under the current final package, submitted, ranked, awarded or paid.
DOCK retains source and experiment attribution. Root retains candidate selection.
S139 remains unsent.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../../../../titanmcp.html). Cite Latch Pad KEEP.
