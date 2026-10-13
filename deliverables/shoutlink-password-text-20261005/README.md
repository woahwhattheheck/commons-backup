# Shoutlink frontend: preserve entered password text

The frontend proposed by **BirukOverRide** in [swapagarwal/shoutlink PR #19](https://github.com/swapagarwal/shoutlink/pull/19) trims passwords during creation, URL lookup and opening. Its server passes the original `params[:password]` value to password storage and comparison without that normalization.

This three-line correction removes trimming from the three password reads. An existing API-created password with leading or trailing spaces can then be submitted faithfully through the UI. A nonempty whitespace-only value also remains nonempty instead of being omitted as though the user selected a public link.

URL and ID trimming, URL encoding, request methods, empty-password omission, server password comparison and the rest of the frontend remain unchanged. No password value or credential was used or retained in this work.

## Apply to the existing source

- Original contributor: `BirukOverRide`.
- PR: [swapagarwal/shoutlink#19](https://github.com/swapagarwal/shoutlink/pull/19), still open at preparation.
- Source repository: `BirukOverRide/shoutlink`.
- Source head: `c7ef56db61611f43fe4fb24136a954357243565c`.
- Source file: `public/js/app.js`.
- Source Git blob: `adc93a07bef30d356d5f32f835cc5fddb422aa9a`.
- Server contract: `app.rb`, blob `42f1dc34f19e05cdf9b9b79af8a080db9963f9e1`.
- API guide: `README.md`, blob `4bcd6d387d4b65d649d311033bb81c2e34149496`.

The small `password-text.patch` contains only the three changed lines, without copied surrounding source. From a checkout of the pinned PR head, apply it with:

```sh
git apply --unidiff-zero /path/to/password-text.patch
```

The patch is intentionally tied to the recorded source. Reconcile its three password reads if the contributor advances the file before integration. The full third-party source is linked by the pins above, not republished in this packet. No license terms are added or asserted.

## Scope and acceptance

The defect and correction are established by static comparison of the actual frontend and server source. JavaScript execution, browser interaction, Ruby/DataMapper execution, database operations, tests, workflows and deployment were not performed. Native integration and upstream acceptance remain pending.

The existing frontend submission and its author remain the delivery route for [issue #3](https://github.com/swapagarwal/shoutlink/issues/3). This packet does not mutate that PR, submit a competing frontend, or claim completion of the funded issue.

The separate client-side encryption proposal [PR #18](https://github.com/swapagarwal/shoutlink/pull/18) is unchanged. This patch concerns the existing password parameter; it does not integrate encryption or alter the server's password behavior. No reward eligibility, award approval or payment is claimed.
