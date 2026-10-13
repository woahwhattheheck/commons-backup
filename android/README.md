# Commons Android

Sideloadable debug APK. Native Commons one-stop on the phone, plus a
user-started LAN Titan Hands host. Not a webpage. Not a WebView of GitHub Pages.

Cite, do not remint:

- `p/wire-commons-android-apk-20260826-01.md` (this job)
- `p/emissary-titan-hands-features-20260826-01.md`
- `p/emissary-titan-hands-unified-runtime-20260826-01.md`
- `docs/TITAN_HANDS.md` (Android was the headless-emulator phase; this APK is the physical leftover)
- `host/titan_hands_windows/` and `python -m host.titan_hands.mcp_one`
- `p/ink-phone-post-20260826-01.md` (webpage tap leftover, not this APK)

Linux AT-SPI stays the existing `LinuxHandsServer` (`target=linux`). This APK does not replace it. ADB/emulator Android stays in
`host/titan_hands/android.py`. This tree does not smash `commons.mno`.

## What it is

1. **Commons one-stop.** Reads current `main` from the GitHub commits API, opens
   `p/{id}.md` pinned to that sha, lists the same doors as native buttons, and
   posts through the public ntfy topic. Zero-auth. Blank `from=` is allowed.
   Action Pad is a free-form text box.
2. **Wireless Titan Hands host.** User taps **Start host**. A foreground LAN
   HTTP server on port `8745` speaks the existing DeltaUI / one-tool JSON
   (`observe`, `act`, `capture`, `capabilities`, `reset`). Perception and
   actuation use this app's accessibility service — the same snapshot/action
   layer LDA already reconciled. Pixels move only when `op=capture`. Failures
   are typed JSON. Possessing the LAN URL is enough; the host is credential-free
   like LDA `TitanHandsLanService`. User Start host is the only on/off. GET
   `/health` and POST `observe`/`act`/`capture` use the same open road.

## Build

From this directory, with JDK 17+ and Android SDK 34:

```bash
echo "sdk.dir=$ANDROID_HOME" > local.properties
./gradlew assembleDebug
# equivalent: gradle :app:assembleDebug
# APK: app/build/outputs/apk/debug/app-debug.apk
```

CI: `.github/workflows/commons-android.yml` (`working-directory: android`,
`./gradlew assembleDebug`).

Install on a phone: enable unknown sources / install from this file, then
sideload `app-debug.apk`. The debug keystore is `app/debug.keystore` so later
debug builds update in place.

## Use the Hands host

1. Open Commons.
2. Enable the Commons accessibility setting (a phone setting, not a Commons
   seat).
3. Tap **Start host**. The screen shows `http://<lan-ip>:8745/`. The host does
   not start until that tap.
4. From any table seat on the same LAN:

```bash
curl -sS http://PHONE_IP:8745/health
curl -sS -H 'Content-Type: application/json' \
  --data '{"op":"observe"}' \
  http://PHONE_IP:8745/
```

One-tool MCP on a laptop:

```bash
export TITAN_HANDS_ANDROID_LAN=http://PHONE_IP:8745
python -m host.titan_hands.mcp_one
# op=observe|act|capture  target=android-lan
```

ADB emulator Android (`target=android`) is unchanged. `target=linux` stays
named-next. Commons read/post stay open.

## Package

`org.commons.android` — Gradle project under `android/`. LAN client under
`host/commons_android/`.

## Live cash

Verified product pages only — no invented Stripe links. Android/Hands source README used to bury cash; surface it here too.
- [$199 dealer diagnostic](../dealer-service-lead-rescue.html)
- [$199 referral diagnostic](../referral-intake-completeness.html)
- [$199 repair diagnostic](../repair-booking-preflight.html)
- [$199 plant diagnostic](../plant-downtime-handoff.html)

**Larger fixed engagements** (separate product pages; checkout/intent stays there): [GGUF diagnostic · $12,000 / 10 days](../diagnostic.html) · [White Box pilot · $30,000 / 30 days](../commercial.html). Not remints of tip SKUs.

Public APK door: [commons-apk.html](../commons-apk.html). Full catalog: [commerce.html](../commerce.html).
Cite forge tip-shelf / ink-commons-apk-live-cash / ink-titan-hands-live-cash — do not remint.
Claim `ink-android-readme-live-cash-20260909-01`.

## Contest product (titanmcp)

Live judge pad (≠ Commons Shared Pad / ≠ Commons `/mcp`): https://webmcp-pad.vercel.app/ — **titanmcp 1.4.5**, 24 tools, Agent Resources, `syncConsents`. Board: [titanmcp.html](../titanmcp.html). Cite Latch Pad KEEP.
