# NUMIH AI SAD retained-byte admission-readiness compiler

Offline, stdlib-only packet preparation for NUMIH / GIP MiPih AI SAD
`2025-0154-00-00-MPF`.

This tool does **not** accept packet metadata as evidence authority. A packet row marked
`EVIDENCED` contributes nothing until a separate evidence bundle supplies exact retained
bytes whose identity, party, kind, locator, generation, byte length, and SHA-256 all match.
The compiler decodes and hashes those bytes itself, seals a deterministic bundle root, and
includes that root in the result receipt.

That proves artifact retention only. It does not prove a document's issuer, legal effect,
truth, currentness, sponsor score, eligibility, admission, award, payment, or revenue.
Every external authority bit remains false and PLACE DCE currentness always remains
`CURRENTNESS_UNVERIFIED`.

## Run

```bash
python -m revenue.numih_ai_sad_admission_readiness.cli \
  revenue/numih_ai_sad_admission_readiness/examples/fictional_partner_packet.json \
  --evidence-bundle revenue/numih_ai_sad_admission_readiness/examples/fictional_evidence_bundle.json \
  --json-out /tmp/numih-result.json \
  --markdown-out /tmp/numih-result.md
```

Both input files are acquired through one retained `O_NOFOLLOW` descriptor generation,
validated with `fstat`, bounded, read twice from the same inode, and UTF-8 decoded only
after the retained read. Platforms without safe no-follow acquisition fail closed.

## Authority model

- Packet `source.locator`, `source.generation`, and `source.sha256` are caller claims.
- A separate bundle contains exact base64 artifact bytes and a manifest binding each
  artifact to an evidence ID, party, kind, locator, generation, length, and digest.
- The compiler recomputes byte length and SHA-256, normalizes the manifest, and seals a
  deterministic bundle root.
- Only exact packet↔bundle matches receive the result label `RETAINED_SOURCE_BYTES`.
- Missing/mismatched bundle entries go to `evidence_authority_queue` and cannot contribute
  partner capacity, category fit, weighted coverage, or `PACKET_REVIEW_READY`.
- `ORIGINAL_FR` requires `language=fr`; `WORKING_TRANSLATION` and `UNTRANSLATED` remain
  queued even when a caller labels the language French.
- Partner evidence is composable only after a same-party retained-byte commitment binds.
- The fixture is explicitly fictional and synthetic.

## Tests

```bash
python -m unittest discover -s revenue/numih_ai_sad_admission_readiness/tests -v
python -O -m unittest discover -s revenue/numih_ai_sad_admission_readiness/tests -v
python -m py_compile \
  revenue/numih_ai_sad_admission_readiness/compiler.py \
  revenue/numih_ai_sad_admission_readiness/cli.py
```

Hostiles cover forged locator/hash/generation metadata, missing and mismatched retained
artifacts, bundle content/length forgery, partner commitment composition, contradictory
translation states, packet/bundle tampering, strict JSON, symlink refusal, and deterministic
path swaps to symlink or oversized foreign generations after descriptor acquisition.
