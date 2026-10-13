# Fire TV device / simulator validation gate

This is the external gate required before a competition submission can truthfully say the app runs on Fire TV.

## Fire OS / actual Fire TV path

Amazon documents HTML5 testing with **Web App Tester**.

1. Run `scripts/run-tests.sh` and retain the printed package SHA-256.
2. Copy `dist/spoilershield-firetv-webapp.zip` to `/sdcard/amazonwebapps/` on the Fire TV (or host the ZIP over HTTPS).
3. Open Amazon Web App Tester → Packaged Apps → Sync List → select SpoilerShield → Test App.
4. Record the device model / Fire OS version and package SHA-256.
5. With only the remote, prove focus/Enter across seek + WHO/WHY/CATCH-UP controls.
6. At **5:10 or earlier**, ask CATCH-UP and show that the later probe-seven storm-front reveal is absent.
7. Move to **5:35**, ask WHY, and show that the completed 5:20–5:30 reveal can now appear.
8. Disconnect network (offline mode) and repeat one query.
9. If testing the AWS path, reconnect, configure the HTTPS endpoint, show the mode badge switches to AWS BEDROCK, and repeat the same spoiler-boundary case.
10. Capture a <3 minute demo video that visibly includes the Fire TV device or Fire TV/Vega simulator, as required by the hackathon rules.

## Evidence receipt template

- Date/time UTC:
- Device / simulator:
- OS version:
- Package SHA-256:
- Remote-only navigation: PASS / FAIL
- Pre-boundary future reveal absent: PASS / FAIL
- Post-boundary reveal admitted: PASS / FAIL
- Offline fallback: PASS / FAIL
- AWS path (optional): PASS / FAIL / NOT RUN
- Video URL:

Until this receipt is filled from an actual Fire TV device or accepted simulator, `DEVICE_DEMO_STATUS = HOLD_NOT_RUN`.
