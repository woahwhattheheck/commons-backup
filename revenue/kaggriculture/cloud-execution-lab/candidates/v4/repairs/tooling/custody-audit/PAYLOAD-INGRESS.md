# Payload ingress verifier

`verify_payload_packet.py` closes one narrow custody gap that `audit_v4_custody.py` deliberately does not cover: verifying an already-materialized raw-byte handoff *before* those bytes are published into Git.

It is a custody tool, not a source-recovery mechanism. It never fetches Slack/GitHub, decodes prose, reconstructs missing donors, executes/imports packet members, writes packet bytes, creates Git objects, composes V4, or approves activation/economics.

## Packet contract

The manifest is strict UTF-8 JSON with exactly these top-level keys:

```json
{
  "schema": "titan-v4-payload-packet/v1",
  "packet": "defensive-guard",
  "members": [
    {
      "path": "r04_defensive_guards.py",
      "size": 7624,
      "git_blob": "<40 lowercase hex chars>",
      "sha256": "<64 lowercase hex chars>"
    }
  ]
}
```

Every member must have exactly `path`, `size`, `git_blob`, and `sha256`. Paths are canonical relative POSIX paths: no absolute paths, `.`/`..`, backslashes, control characters, non-NFC spelling, duplicate names, or case-folding collisions. The packet directory must contain exactly the declared regular files. Symlinks, FIFOs/devices/sockets, missing files, and undeclared extra files fail closed.

The verifier independently recomputes byte count, Git blob SHA-1 (`sha1("blob <len>\0" + bytes)`), and SHA-256 for every member. A mismatch exits 1; structurally unsafe/invalid evidence exits 2. Success exits 0 and emits a deterministic `titan-v4-payload-verification/v1` JSON receipt.

## Run

```bash
python revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/tooling/custody-audit/verify_payload_packet.py packet-manifest.json unpacked-packet/
python -O revenue/kaggriculture/cloud-execution-lab/candidates/v4/repairs/tooling/custody-audit/verify_payload_packet.py packet-manifest.json unpacked-packet/
```

The manifest should live outside `unpacked-packet/` unless it is itself intentionally declared as a packet member; undeclared extras are rejected.

## Boundary

A GREEN receipt proves exact local byte custody for the declared packet only. It does **not** prove semantic correctness, donor provenance beyond the declared digests, Git publication, compatibility with current `main:candidates/v4`, test execution, composition safety, economics, promotion, or default/production activation. The existing canonical custody census and each lane's component/engine/economic gates remain separate requirements.
