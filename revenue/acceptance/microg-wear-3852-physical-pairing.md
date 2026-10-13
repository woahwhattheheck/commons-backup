# microG Wear PR #3852: physical pairing acceptance packet

Status: **device execution required**. This packet prepares the evidence requested by the maintainer; it is not evidence that pairing succeeded.

## Custody and pinned source

- Upstream carrier: [microg/GmsCore PR #3852](https://github.com/microg/GmsCore/pull/3852)
- Submission and payout owner: `woahwhattheheck` (unchanged)
- Current PR head read on 2026-10-05: `e309dd0bc0acf5933d3d945671144026fb6b7ac3`
- Maintainer request: attach real proof that the implementation works, otherwise close the PR.
- The last complete build/test/lint artifact is pinned to product source `e8fcc76cda77165de370ae599ab4d649e6f03a4f`, not the current PR head. It contains APK `com.google.android.gms-252432000.apk`, 107,564,514 bytes, SHA-256 `5cc6dbfd201df2100da93d68cd1bc78d4a76362303887357bf4155e53d82b18d`.
- Current head is ten commits after the earlier `1062b78d` validation source and includes product changes after `e8fcc76c` (wake-lock, BLE-stop, socket-shutdown and tests). Older APK artifacts therefore must not be described as current-head proof.

## Required preflight

1. Re-read PR #3852 immediately before building and record the exact head SHA.
2. Build the VTM-default debug APK from that exact head in a clean checkout:
   ```sh
   GRADLE_MICROG_VERSION_WITHOUT_GIT=1 ./gradlew --no-daemon --no-configuration-cache --no-build-cache --max-workers=2 --console=plain :play-services-core:assembleVtmDefaultDebug
   ```
3. Record the APK filename, byte size and SHA-256. Preserve the build log and APK in a durable artifact.
4. Install that exact APK on the phone or phone emulator used in the recording. Do not substitute the older `e8fcc76c` or `1062b78d` APK while claiming current-head proof.
5. Use a real Wear OS watch reset or unpaired for this phone/emulator. Record watch model, Wear OS version/build, phone/emulator model and Android version, and the microG version shown by the installed build.
6. Remove or obscure personal accounts, phone numbers, device identifiers and notification contents without obscuring the pairing state or build identity.

## One continuous recording

Capture one uncut recording with a second camera when possible so both displays and physical interaction remain visible.

1. Start on a card or terminal showing:
   - PR URL and exact head SHA
   - APK SHA-256 and byte size
   - device/watch versions
   - UTC start time
2. Show the watch in an unpaired/reset state and the phone/emulator with no configured instance of that watch.
3. Start pairing through the microG/Wear flow.
4. Keep both sides visible through Bluetooth discovery, confirmation-code comparison, terms/consent, and every setup prompt. If account transfer is skipped or unavailable, show that outcome rather than editing it out.
5. Show a completed paired/connected state on both watch and phone/emulator.
6. Prove the connection survives one bounded lifecycle event:
   - toggle Bluetooth off and back on, or
   - restart the microG process or phone/emulator,
   then show the same watch reconnecting.
7. End on the same manifest card with UTC end time. Do not cut away failures, retries, crashes or stalls.

A companion screen recording may improve legibility, but it does not replace the continuous external view.

## Minimum acceptance record

Publish the video and a text manifest containing:

```text
PR: https://github.com/microg/GmsCore/pull/3852
PR head:
APK filename:
APK bytes:
APK SHA-256:
Build log/artifact URL:
Phone/emulator model:
Android version/build:
Locked bootloader / root state:
Watch model:
Wear OS version/build:
Pairing started (UTC):
Pairing completed (UTC):
Reconnect event and result:
Observed failures/retries:
Raw video SHA-256:
Public video URL:
```

The video should be downloadable or viewable without the contributor's private session. Verify the URL signed out before posting it to the PR.

## Honest outcomes

- **Pass:** the exact-head APK completes pairing and reconnects as shown. Post the manifest and signed-out video URL to PR #3852.
- **Blocked:** hardware, account, Bluetooth or setup prerequisites prevent execution. Record the exact blocker; do not claim success.
- **Fail:** pairing or reconnect fails. Preserve the raw recording and logs, reduce the failure to a source-side repair, and keep the PR open only if the original owner chooses to repair it.
- **No device proof available:** the original submission owner decides whether to close the PR. This packet does not authorize anyone else to close it.

## Money state at publication

Advertised total: **$2,340**. Independently tracked as **$110 funded** plus **$2,230 promised**. Awarded: **$0**. Invoiced: **$0**. Received: **$0**.

No account, payment rail, bounty claim, upstream PR state or device was changed while producing this packet.
