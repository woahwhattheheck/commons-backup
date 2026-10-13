# SpoilerShield — spoiler-bounded context AI for Fire TV

**Competition target:** Amazon Build, Ship, Shape 2026 — Fire TV track.

SpoilerShield is a TV-native co-viewing assistant for three common questions: **Who is that? Why does this matter? Catch me up.** It only uses transcript cues that have fully completed at the viewer's current playhead. A model is never trusted to decide which scenes are safe.

## What is runnable now

The `web/` client is a dependency-free packaged HTML5 app suitable for Amazon Fire TV's Web App Tester. It includes a synthetic six-minute demo timeline and a complete offline provider. `backend/` is an optional AWS Lambda + Bedrock path that independently re-verifies the spoiler boundary.

```bash
./scripts/run-tests.sh
```

That runs the JavaScript hostile suite, Python backend hostile suite, and builds a deterministic `dist/spoilershield-firetv-webapp.zip` for on-device testing.

## Fire TV test path

Amazon documents both hosted and packaged HTML5 Fire TV apps. Build the ZIP, copy it to `/sdcard/amazonwebapps/`, and load it in Web App Tester. See `DEVICE_TEST.md` for the exact evidence gate. The hackathon's final demo must visibly run on an actual Fire TV device or the Fire TV/Vega simulator; source publication is **not** represented as that external proof.

Official references:

- Hackathon rules: https://amazonappdev2026.devpost.com/rules
- Fire TV developer portal: https://developer.amazon.com/apps-and-games/fire-tv
- Fire TV HTML5 Web App Tester: https://developer.amazon.com/docs/fire-tv/webapp-app-tester.html

## Product boundary

`web/core.js` mechanically admits only cues with `endMs <= positionMs`, seals the bounded evidence into a canonical SHA-256 packet, and revalidates it before a provider call. The optional backend repeats those checks and can pin one exact transcript generation. If Bedrock is unavailable, the app falls back to local deterministic answers over the same bounded packet.

See `ARCHITECTURE.md`, `THREAT_MODEL.md`, `SUBMISSION.md`, and `DEVICE_TEST.md`.

## Authority / status

- Source + local hostile tests: intended to be mergeable here.
- Fire TV/Vega device execution: **HOLD until actual device/simulator receipt**.
- AWS deployment/spend: **not performed by this carrier**.
- Hackathon registration/submission/prize/payment/revenue: **not claimed**.
