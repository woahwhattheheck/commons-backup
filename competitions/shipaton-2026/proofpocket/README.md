# ProofPocket — RevenueCat Shipaton 2026 carrier

ProofPocket is a new Android-first, offline work-evidence app: create a project, state a bounded completion claim, attach local files, hash them on-device, and export a deterministic content-addressed receipt. Anyone with the JSON receipt can import it and detect changed claims/evidence without trusting a ProofPocket server.

## Product boundary

- **Local-first:** evidence bytes stay on the device. ProofPocket stores only local project metadata and SHA-256 digests.
- **Free:** up to 3 local projects, JSON receipt creation/export/import verification.
- **Pro:** an observed active RevenueCat `pro` entitlement unlocks unlimited local projects and platform-native PDF proof packs.
- **Fail closed:** no RevenueCat public SDK key means Pro stays locked. SDK errors never create entitlement truth.
- **No source-local competition READY:** this repository can validate source state and preserve self-asserted observation history, but cannot authenticate RevenueCat/store/Devpost facts or emit an authoritative competition-ready state.

## Android build

Current pinned build inputs were checked against vendor docs on 2026-09-13:

- AGP `9.4.0`, `compileSdk/targetSdk 37`, minSdk 26.
- RevenueCat Android SDK `10.15.1`.

The project does not currently include a Gradle wrapper. Install a Gradle distribution compatible with the pinned Android Gradle Plugin and Android SDK platform 37 plus its required build tools. Run from this directory with the SDK location configured. Supply the **public** RevenueCat SDK key only at build time (never a secret API key):

```bash
gradle :app:assembleDebug -PPROOFPOCKET_REVENUECAT_PUBLIC_SDK_KEY=goog_xxx
```

This repository intentionally does not contain the key, RevenueCat products/offerings, store credentials, signing keys, or a claim that purchases have been tested.

## Document workflow

Saved projects populate the selector on launch. Evidence hashing, receipt import, and JSON/PDF export run on one document worker, not the UI thread. The evidence digest and byte count come from the same stream, including empty files; provider size metadata is not substituted for bytes read.

The project ID and receipt snapshot are retained while the document picker is open. During a configuration change, the replacement Activity attaches to the existing worker rather than starting a second write or saving an old Activity's project list. Process death is different: an interrupted operation is reported and must be retried; exports are not automatically replayed. A failed export can leave an incomplete selected document. Success is shown only after the stream opens, writes, and closes successfully.

## Local proof-engine tests

The receipt engine, bounded strict JSON preflight, entitlement policy, and competition gate have dependency-light tests:

```bash
kotlinc \
  app/src/main/java/com/tokenjunkielabs/proofpocket/core/UnicodeIntegrity.kt \
  app/src/main/java/com/tokenjunkielabs/proofpocket/core/ReceiptEngine.kt \
  app/src/main/java/com/tokenjunkielabs/proofpocket/core/EntitlementPolicy.kt \
  core-tests/CoreTests.kt -include-runtime -d /tmp/proofpocket-core-tests.jar
java -jar /tmp/proofpocket-core-tests.jar

kotlinc \
  app/src/main/java/com/tokenjunkielabs/proofpocket/core/UnicodeIntegrity.kt \
  app/src/main/java/com/tokenjunkielabs/proofpocket/core/ReceiptImportLimits.kt \
  app/src/main/java/com/tokenjunkielabs/proofpocket/core/StrictJsonKeys.kt \
  core-tests/StrictJsonTests.kt -include-runtime -d /tmp/proofpocket-strict-json.jar
java -Xss256k -jar /tmp/proofpocket-strict-json.jar

python3 -m unittest discover -s tests -v
python3 shipaton/readiness.py shipaton/manifest.json --json  # expected HOLD_EXTERNAL_AUTHORITY
```

The current environment used for this carrier has Java/Kotlin/Python but no Android SDK/Gradle executable, so these receipts are **not** an APK/AAB compile claim.

## Receipt semantics

`receiptId = SHA256(canonical_payload_json)`. Evidence is sorted by stable evidence ID before hashing, so input order does not change identity. Evidence IDs derive from content SHA-256. Duplicate IDs, malformed digests/timestamps, negative sizes, and unsupported schemas are rejected.

Import is stricter than ordinary `JSONObject` parsing: duplicate object keys are refused before parsing (including escaped aliases such as `id` and `\u0069d`), and receipt root/payload/evidence objects must contain exactly the supported fields. This prevents unbound side claims from riding beside an otherwise valid receipt.

Untrusted portable receipts are also availability-bounded **before** JSON decoding: the Android import path streams at most 256 KiB, requires strict UTF-8, and the structural preflight refuses nesting deeper than 64 levels. These are ordinary rejection states, not competition/security claims; the selected receipt contains metadata/digests only, never evidence bytes.

Receipt strings must also be well-formed UTF-16. Lone high/low surrogates are rejected both by strict JSON preflight and by the direct receipt/canonicalization domain path; valid surrogate pairs remain supported. This prevents Java's default UTF-8 replacement behavior from collapsing a malformed logical string onto the same canonical bytes as a literal `?`.

This is **tamper evidence**, not a claim of signer identity or a digital signature. A PDF proof pack contains the same receipt ID and digest excerpts; it does not claim cryptographic signing.

## Competition truth / trust boundary

`shipaton/readiness.py` has **no READY branch**. An optional `--witness` file is treated as `SELF_ASSERTED` integrity/history only; even a fully populated file claiming all provider gates remains `HOLD_EXTERNAL_AUTHORITY` with `ready_authorized=false`.

Crossing the actual competition gate requires a separate host/provider integration that reacquires and authenticates exact RevenueCat account/app/product/offering/entitlement state, eligible store developer/publication state for the exact package/version, retained demo/screenshot evidence digests, Devpost submission identity/time, and a host-owned current-time/deadline evaluation. None of those authorities can be created by this source tree. See `shipaton/OWNER_ACTIONS.md`.
