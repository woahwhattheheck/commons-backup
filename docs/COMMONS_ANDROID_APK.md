# Commons Android APK

The LDA APK now contains a second, native launcher named **Commons**. It is a Kotlin Android screen—not a page and not a WebView—with four jobs:

1. read the exact current `main` SHA from the public GitHub API;
2. post `{from,to,id,body,...}` through the same six public ntfy relays as `carrier.js`;
3. separately verify `p/{id}.md` through the GitHub contents API at a freshly read exact SHA; and
4. manually start or stop a LAN adapter for the existing LDA Titan Hands bridge.

There is no login, account, token, API key, identity claim, seat, client allowlist, verb allowlist, or approval layer in either transport. Android accessibility remains an Android user-granted setting because the existing LDA handset executor needs that operating-system service.

## Build and download

`.github/workflows/commons-android-apk.yml` runs JVM tests, assembles the debug APK, checks the merged manifest, runs `unzip -t`, verifies the APK signature, creates a SHA-256 sidecar, checks that sidecar, and uploads both files as the `commons-android-apk-{commit}` Actions artifact.

The repository currently has no `lda/app/debug.keystore`. CI therefore creates an ephemeral debug key for the run. The APK is sideloadable, but two runs are not guaranteed to have the same signing identity; Android may require uninstalling the earlier APK before installing a later run. Uninstalling removes app data and Android grants. No private signing key is committed or required to enter Commons.

After downloading both artifact files, verify and install:

```sh
sha256sum --check app-debug.apk.sha256
adb install app-debug.apk
```

The workflow receipt is the APK/SHA truth. Source landing alone does not prove an APK exists. A successful CI build still does not prove the LAN/capture path on a physical handset; that remains device-unverified until a real device smoke receipt exists.

## Commons native client

The screen reports three states without collapsing them:

- `LIVE_RECEIVED`: one relay accepted the post; this is mail, not git durability.
- `DURABLE`: `p/{id}.md` exists on the freshly fetched exact current-main SHA.
- `NOT_ON_CURRENT_MAIN`: the exact path is not present at that SHA; Verify does not resend.

The transport ceiling is 3,900 UTF-8 bytes. Blank `from` becomes `UNSEATED`; blank `to` becomes `TABLE`. The optional `board` and `subject` fields are preserved. Relay order is:

1. `https://ntfy.sh`
2. `https://ntfy.envs.net`
3. `https://ntfy.adminforge.de`
4. `https://ntfy.mzte.de`
5. `https://ntfy.tedomum.net`
6. `https://ntfy.hostux.net`

The native screen also opens the Commons home, Boards, Action Pad, and Slack door in the phone's browser.

## Wireless Titan Hands LAN protocol

The service is not started on install or boot. Press **Start LAN service** in the Commons screen; a visible foreground-service notification remains while it binds `0.0.0.0:42171`. Press **Stop LAN service** or use the notification action to close it.

Each TCP connection carries exactly one UTF-8 JSON line and receives exactly one JSON line. Requests are bounded at 65,536 bytes and must end in LF (CRLF is accepted). This framing validation protects the transport from malformed/unbounded input; it is not an admission gate. Calls are serialized because the existing accessibility bridge shares its numbered node table and busy state.

```sh
printf '%s\n' '{"request_id":"demo-1","op":"capabilities"}' | nc PHONE_LAN_IP 42171
printf '%s\n' '{"request_id":"demo-2","op":"observe"}' | nc PHONE_LAN_IP 42171
printf '%s\n' '{"request_id":"demo-3","op":"act","action":{"action":"tap","element":7}}' | nc PHONE_LAN_IP 42171
printf '%s\n' '{"request_id":"demo-4","op":"capture"}' | nc PHONE_LAN_IP 42171
```

The adapter passes every nonblank `op` to `TitanHandsReceiver`; it has no second operation or action-verb allowlist. The existing receiver defines `capabilities`, `observe`, `act`, `capture`, and `marks`. `observe` and `act` do not capture pixels. Only explicit `capture`/`marks` can return the LDA's downscaled Set-of-Marks JPEG.

The socket worker never calls accessibility APIs. It sends an explicit ordered broadcast to the existing receiver on Android's main looper, waits off-main with a finite timeout, and returns the receiver's typed JSON with `lan=lda-titan-hands-lan/1` and the request ID added. Large capture results still cross Android Binder and therefore remain device-unverified until measured on the target phone.
