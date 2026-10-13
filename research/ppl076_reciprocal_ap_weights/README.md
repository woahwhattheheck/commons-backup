# Reciprocal-weight AP-free family index

Exact rational optimization over the saved complete three-term-AP-free families on intervals through 25.

The unique maximizer on [1,25] is {1,2,4,5,10,11,14,22,25}, with reciprocal sum **17693/7700**. The 10,630-node accepted ZDD comes from [Commons #31465](https://github.com/woahwhattheheck/commons/pull/31465); this package adds a new weighted objective without rebuilding AP constraints or old cardinality polynomials.

- [API, recurrence, source attribution and limits](RECIPROCAL_AP_WEIGHTS_API.md)
- [CommonJS module](reciprocal_ap_weights.cjs)
- [Complete weighted certificate](weighted_ap_certificate.json)
- [All 36 saved-reader outputs and condition manifests](saved_reader_queries.json)
- Five condition shards named in that manifest retain every new conditional cell.

The source-qualified three-term reciprocal-divergence implication is already proved by Bloom–Sisask. The finite optimizer does not settle the separate arbitrary-length Erdős conjecture or claim a new asymptotic theorem. Required/forbidden queries perform explicitly counted new work; reopening their saved records performs navigation only.
