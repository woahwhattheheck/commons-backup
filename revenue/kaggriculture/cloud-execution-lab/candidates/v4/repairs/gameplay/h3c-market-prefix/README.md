# H3c raw-market executable-prefix repair

This package preserves the reviewed post-baseline H3c correction in the canonical `candidates/v4` workspace.

The baseline donor `donor/overlay/h3c_goose_eod_cap_rescue.py` (`2044d6cf1e0c51f95027229863f910aa43ac7008`) scans every authored market row even though the pinned engine executes only `q[:max_orders]`. H3c already requires standard `maxOrders == 10`, so inert rows at raw index 10+ must not veto an otherwise-valid goose EOD capacity rescue.

Final released source blob: `79c3fd029054a2db5931609db06f6b9aa4d4be3c`. Focused regression blob: `c24bd784a43267f84071d2c293c10fe57f30a1da`. The release receipt reports 38/38 normal and 38/38 optimized tests passing, including a 25-case executable-prefix equivalence matrix; the baseline donor fails 24 subcases of the added suite.

This is source/semantic-port custody only. It does not enable H3c, move legacy V4 refs, change defaults, or authorize production promotion/economics.