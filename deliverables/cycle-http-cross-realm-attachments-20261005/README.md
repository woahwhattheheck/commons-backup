# Recognize browser attachments from another window

This follow-up targets landeqiming666's existing [Cycle.js PR1027](https://github.com/cyclejs/cyclejs/pull/1027), which adds direct browser File and wrapped Blob attachments for [issue294](https://github.com/cyclejs/cyclejs/issues/294).

The proposal identifies those values with the current window's `File` and `Blob` constructors. An ordinary File obtained from another same-origin frame has that frame's prototype, so it does not pass the parent's `instanceof File` check. It then reaches the Node-style path branch with no `path`. A wrapped Blob from the other frame misses its corresponding branch for the same reason. This is a source-derived gap, not an observed browser failure.

## Correction

The original same-realm checks remain first. A small fallback borrows the platform's `File.prototype.name` getter or `Blob.prototype.size` getter and calls it on the candidate. The platform getter accepts objects implementing its interface regardless of which frame's JavaScript prototype they carry. Missing getters or rejected receivers return false. The fallback does not inspect a user-defined tag or allocate a replacement Blob.

The existing browser-only guards remain; Node path attachment routing and all `request.attach` arguments stay unchanged. A wrapped `file` property is read once. File names, explicit field names, explicit filenames, attachment order, HTTP options and public TypeScript interfaces are preserved.

The reasoning follows [JavaScript's multiple-realm behavior](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Operators/instanceof#instanceof_and_multiple_realms), the [File API's File and Blob attributes](https://w3c.github.io/FileAPI/), and [Web IDL's attribute getter algorithm](https://webidl.spec.whatwg.org/#dfn-attribute-getter). That algorithm requires the receiver to implement the declared interface and rejects other receivers. This patch is a compatibility fix, not a new security boundary; existing globals and same-realm behavior are retained.

## Exact integration

The source is `http/src/http-driver.ts`, blob `94f4b963e062a5d9b7bc965be965aa2a280f9dd5`, from PR1027 head `ead3138e1ded5682e387ecc6839524e80c9215c2` in `landeqiming666/cyclejs`. Its base is upstream master `5ece2a48c3659538208da3dc8d43a142bc0d91a7`.

Use the included patch with that existing contribution after reconciling its current head. The packet contains the exact original and complete corrected production file, source bindings and unchanged upstream MIT notice. It does not reproduce the rest of PR1027 or replace its author. Historical example PR868 remains separate.

## Acceptance limits

Complete runtime, interface and package source, the issue's four comments, and the empty PR discussion/review-comment collections were read. Validation is static source reasoning only. No browser or iframe, native operation, upload request, compiler, test, fixture, build, dependency install or workflow was executed. Existing author-reported browser/Node checks remain their reports.

A read of the exact Superagent3.8.3 browser-source URL returned an Internal Error; that route was retained as unavailable and was not retried or replaced. This packet does not assert end-to-end library or browser acceptance. The upstream guide's required build/check workflow remains unperformed under the offline executor restriction. No upstream submission, acceptance, award or payout is claimed.
