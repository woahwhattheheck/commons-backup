# Finite hinted-product resilience

Exact Boolean witnesses and intermediate-deletion navigation for a staged left-matrix / hint-matrix / column-query interface.

The retained instance uses seven saved agreement masks from [Commons #31621](https://github.com/woahwhattheheck/commons/pull/31621), with n=13, t=7 and the declared hint V=M transpose. Its complete index has 128 deletion profiles, 153 positive ordered base entries and 45 weight/loss buckets. Thirty-seven saved reader responses include seven complete conditional families, without recomputing matrix intersections or profiles.

Start with [the API guide](HINTED_PRODUCT_RESILIENCE_API.md). The separate [left preparation](left_preparation.json), [complete phase-2 certificate](nearest_word_resilience_certificate.json), and [reader record](saved_reader_queries.json) retain the stage and input lineage. The dependency-free [CommonJS module](hinted_product_resilience.cjs) supports new bounded inputs and saved navigation.

The general v-hinted formulation and conjecture are attributed to van den Brand, Nanongkai and Saranurak (2019). This exponential finite deletion index and structured transpose input establish no general asymptotic tradeoff or online-matrix result.
