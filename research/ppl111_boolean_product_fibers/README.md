# Boolean products and inverse fibers

Compile a bounded fixed Boolean matrix into block-product tables and complete output/weight layers. Saved readers return sequential products and exact count/rank/select answers for the vectors producing a requested output.

The actual 12×13 matrix consumes saved flags from [#31614](https://github.com/woahwhattheheck/commons/pull/31614). It has 55 outputs across 8,192 inputs. Output 3455 has 1,056 preimages; its minimum support size is four, attained by masks 616 and 120 in the declared block-choice order.

- [API, derivation and source boundaries](BOOLEAN_PRODUCT_FIBERS_API.md)
- [CommonJS module](boolean_product_fibers.cjs)
- [Complete matrix and compiled layers](local_flag_matrix_certificate.json)
- [35 saved outputs and all 547 conditional memo cells](saved_reader_queries.json)

The primary OMv formulation is credited to [Henzinger, Krinninger, Nanongkai and Saranurak](https://arxiv.org/abs/1511.06773). Preprocessing can be exponential and the finite sequential interface does not claim a subcubic algorithm or a resolution of that conjecture.
