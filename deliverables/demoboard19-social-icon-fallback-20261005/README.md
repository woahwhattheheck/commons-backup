# Keep custom social-link icon fallbacks on the configured table

The social-links proposal uses plain objects for built-in icons and labels. Its truthy indexed lookups can select inherited Object.prototype members for custom type strings such as __proto__, constructor or toString. Those values bypass the generic link fallback; __proto__ selects an ordinary prototype object as the SVG child instead of the generic path element.

This follow-up selects a built-in key only when it is an own property of the existing icons table, otherwise using the existing link key. Both icon and default label consequently use the same selected key. Links are still rendered. Custom labels and explicit icons retain their existing precedence, and URLs, normalization, layout, new-window behavior and the original feature remain unchanged.

## Integration

Apply change.patch to the existing [egoist/demoboard PR234](https://github.com/egoist/demoboard/pull/234), after reconciling its current head. The exact preparation head is `5a4ea66f5007bea2f226901188bb30e424706df6`; original src/SocialLinks.js blob `fdf584840dd782fa8275c3a901865bf43ad76af9`. Complete before/after sources and the unchanged upstream MIT license accompany the patch.

The fixed-bottom-sidebar feature, API documentation and demo remain apples-kksk's existing work. PR44 by kenanchristian is closed and unmerged. Issue19 remains assigned to egoist; maintainer acceptance, the existing contributor's submission and payment rights are preserved. This is an internal source follow-up, not a new upstream PR or IssueHunt claim.

## Source contract

The candidate README documents built-in github/twitter/donate types and the generic custom-link icon. App forwards the mount option to Sidebar, which renders SocialLinks. The component contains matching own keys github, twitter, donate and link in both icon and label tables. Its previous fallback used icons[type] || icons.link and labels[type] || labels.link; inherited truthy values defeated those expressions.

The source correction changes only the selection of the table key. No URL validation or configuration rejection is added. This is not a general schema validator and does not promise support for arbitrary object-valued type, label or icon inputs. The existing own-property call handles string keys without a new dependency or modern Object.hasOwn requirement.

React's [createElement reference](https://react.dev/reference/react/createElement) documents child values as React nodes; arbitrary prototype objects are not icon elements. That is supporting API context, not an executed React16 result. The candidate package requests React and React DOM ^16.8.6.

## Validation state

Static source/contract inspection and exact patch/postimage comparison only. No browser, app, build, compiler, package install, tests, fixtures, workflow or native execution was run. The original PR author's reported browser/build checks remain their own observations. Upstream integration and runtime acceptance, award and payment are unclaimed.
