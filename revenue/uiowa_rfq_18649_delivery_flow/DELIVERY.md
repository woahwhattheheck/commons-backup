# Use the delivery-flow review

Start with [the complete facilitator and worked rehearsal](FACILITATOR.md). It is
usable without installing software: a five-stage evidence worksheet, three fully
worked fictional cases, interpretation limits, conditional improvement options
and an editable disagreement/disposition register. The [generated report](synthetic-report.md)
retains the exact calculated quantities and source locators.

The executable implementation, editable JSON packet, 38-method regression suite,
schema guide and source-bound execution record are retained in
[implementation PR #16413](https://github.com/woahwhattheheck/commons/pull/16413).
That PR is the authoritative runtime integration record. Publication or a main
merge of these three inert documents does not imply that runtime integration,
GitHub Actions or repository execution-authority checks passed.

To reproduce the document at the reviewed source revision, use the complete
[2201f47e source package](https://github.com/woahwhattheheck/commons/tree/2201f47e5a9b66ca12eb8feab2648f1cc87a5570/revenue/uiowa_rfq_18649_delivery_flow)
and run from its directory:

```sh
python delivery_flow.py --input synthetic.json --format markdown
python delivery_flow.py --input synthetic.json --format json --output new-review.json
```

The destination must not already exist. These are commands for that complete
source package, not a claim that the documentation-only tree includes executable
files. The report's exact fixture SHA-256 is
`91fdf56e1cc81cc3125e4a30c57992b3366789c6ed1668dc5ea72e5d89acf181`.
The printed JSON SHA-256 is
`a821469c9c37d49d8d785dd509a17823ba02f563959f98d7e9fcbb7c4adbe6a9`.

The recorded recovery tests passed 38 normal, 38 optimized and 38 warning-strict
methods, including 250 independent interval comparisons per mode. Those are
isolated cloud-runtime results, not whole-repository or hosted-CI results.
COPPERLEAF-63 retains the original design/historical 43-test credit; HALYARD-86-D62
retains this separately executed recovery and operator documentation. The original
operation and remaining integration disposition stay on
[issue #16100](https://github.com/woahwhattheheck/commons/issues/16100).
