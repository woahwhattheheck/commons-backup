# FusionMeter architecture and authority boundary

```text
Existing AGA-3 point
  upstream P,T ----+
  orifice DP -------+--> existing indicated gas rate ------+
  downstream P* ----+--> permanent pressure loss -> PLR ---+--> domain + health fence
                                                          |
                                                          v
                                             calibrated over-read model
                                                          |
                           +------------------------------+--------------------+
                           |                                                   |
                    IN DOMAIN + HEALTHY                                  HOLD / OUTSIDE
                           |                                                   |
                           v                                                   v
            corrected candidate gas rate                         raw AGA-3 rate preserved
            + certificate SHA + receipt                         + quality/alarm flag
                           |
                           v
                    flow computer / historian
```

`*` downstream observation is a POC engineering item. The exact tap location/manifold/transmitter must be selected and approved for the site; the repository does not prescribe a field modification by itself.

## Authority rules

1. `SYNTHETIC` and `LAB_ANALOG` certificates can exercise software but never yield field authority.
2. Only `REPRESENTATIVE_POC` can produce `FIELD_EVIDENCE` authority.
3. The sample must be inside every certificate domain bound.
4. Sensor health must be true.
5. A certificate is content-hashed; coefficient/domain tampering invalidates it.
6. The result receipt binds sample, output and certificate.
7. The screening uncertainty is explicitly not a GUM-certified uncertainty statement.
8. Submission readiness is a second, separate gate: human contribution, IP, Challenge Agreement, safety/standards and support commitments must exist before release.

## Why no opaque online learner

Measurement/accounting authority should not move because a model silently retrained. FusionMeter certificates are immutable snapshots produced from identified calibration evidence. A new calibration produces a new certificate SHA and requires a new review/deployment decision. That is slower than online learning and intentionally safer for production accounting.
