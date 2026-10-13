# Evidence-led portfolio interview

Start with a bounded service, release revision, assessment date and consequential business behavior. Record the source for each answer. An absent answer remains unknown.

| Topic | Ask | Capture in the packet |
|---|---|---|
| Business behavior | What exact user or service outcome matters? What adjacent claims does it not establish? | Behavior statement; assertion statement; passing establishes and does not establish |
| Scope | Which assertions are required for this change? Why is an assertion outside scope? | Required flag and explicit scope reason |
| Inventory | Is this the complete check inventory for this assertion, or only a sample? | Inventory completeness; check IDs and source locators |
| Layer | What boundary does each check exercise? Which failure mechanisms are independent? | Unit/integration/contract/end-to-end/user-acceptance level; boundary |
| Current evidence | Which exact run, revision, date and artifact support the assertion? | Run/check/assertion/behavior IDs, revision, observed date and artifact locators |
| Apparent duplication | Do these checks establish the same assertion at the same layer and boundary? Would they fail independently? | Equivalence key only where asserted; rationale before consolidation |
| Missing behavior | Is no check known to exist, or is the inventory uncertain? | Complete inventory without checks versus incomplete inventory |
| Regression scope | Which components changed, and which behaviors depend on them? Is impact mapping reliable? | Components, changed components and impact-known flag |
| Effort | What execution and maintenance work is included in each estimate? Which estimates remain unknown? | Nonnegative minutes or null, and the rationale |
| Improvement | What assertion gains useful evidence? Is there a cheaper alternative for exactly that scope? | Explicit assertion set, qualitative gain, effort and source |

For a first failure, preserve the original observation and artifact before rerunning. Ask whether it reflects product behavior, setup/data, environment, or an undetermined cause. A nominal-path pass may be useful evidence for its own assertion while leaving a retry-path failure unresolved. Capture any eventual disposition with a dated source; do not overwrite the failing record or use a later green count as its resolution.

Before discussing a release, explain each untested or uncertain required assertion, every unresolved failure, the source limits and the cost assumptions. This kit supplies evidence descriptions and selection proposals. It does not determine an institutional release policy or issue release authorization.
