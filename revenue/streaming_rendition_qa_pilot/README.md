# Streaming Rendition QA Pilot

Operation: `STREAMING-RENDITION-QA-PILOT-ZTCJ4M8-20260913`

This is the sellable diagnostic layer for the already-landed metadata engine in `revenue/streaming_rendition_release_gate/`. It does **not** modify that engine.

## Offer

**$2,500 fixed diagnostic:** one sanitized metadata export, up to 250 assets. The packet compiler returns:

- buyer-facing `report.md`;
- canonical machine `report.json`;
- `receipt.json` binding canonical input, engine proof, result projection, and both report hashes.

**$7,500 integration follow-on:** available only after the paid diagnostic proves value and the buyer's adapter scope is known. No free custom adapter is included.

These are deliberate pilot prices for this offer, not claims about market rates.

## Buyer input

Input is a JSON array of the exact rendition metadata packets accepted by the landed release gate. The pilot is metadata-only. Do not supply media bytes, DRM secrets, production credentials, payment credentials, or customer/private content outside the agreed sanitized export.

The CLI also rejects symlinked input, inputs over 8 MiB, empty arrays, and more than 250 assets.

## Compile a synthetic sales sample

From repository root:

```bash
python3 -m revenue.streaming_rendition_qa_pilot.cli \
  --canonical-sample \
  --out-dir /tmp/streaming-rendition-qa-sample
```

The canonical sample consumes the landed 168-packet fixture. Expected proof is 140 `RELEASE_READY`, 28 `HOLD`, with four HOLDs in each of the seven canonical fault classes. The compiler reads the landed engine manifest at runtime and binds its canonical semantic hash into the report and receipt.

## Compile a paid diagnostic

```bash
python3 -m revenue.streaming_rendition_qa_pilot.cli \
  --input sanitized-rendition-export.json \
  --out-dir diagnostic-output
```

The output directory must not already exist. Files are created exclusively; a compiler error cleans up only artifacts created by that invocation.

## Acceptance

A paid diagnostic is accepted when:

1. every supplied asset is represented exactly once;
2. identical input produces byte-identical report/receipt artifacts under the same engine manifest;
3. every HOLD uses a stable engine reason code and lists the affected asset IDs;
4. the receipt binds canonical input SHA-256, current engine-manifest semantic SHA-256, result projection SHA-256, JSON report SHA-256, and Markdown report SHA-256;
5. external-effect authority remains all false.

`RELEASE_READY` is **not media release authority**. It means only that the supplied metadata contract is internally consistent. Media operations retain rights, content, DRM-secret, release, transcoding, CDN, publishing, production, payment, and customer authority.

## Commercial boundary

Sell the fixed diagnostic first. Do not build a buyer-specific adapter for free. Do not request production/media/DRM access to qualify the pilot. Integration is a separate paid scope after the diagnostic exposes a concrete mapping need.

No prospect contact, contract, acceptance, payment, or revenue is created by this repository artifact.
