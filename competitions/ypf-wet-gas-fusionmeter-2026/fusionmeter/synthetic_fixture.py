"""Deterministic public-safe synthetic wet-gas rows used only to exercise software."""
from __future__ import annotations

import math
from typing import Any


def build_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    pressures = [60.0, 65.0, 72.5, 80.0, 85.0]
    temperatures = [30.0, 40.0, 50.0, 60.0]
    betas = [0.50, 0.60, 0.68]
    idx = 0
    for pressure in pressures:
        for temperature in temperatures:
            for beta in betas:
                idx += 1
                primary_dp = 70.0 + 3.0 * (idx % 7)
                dry_plr = 0.18 + 0.015 * (beta - 0.5) / 0.18
                plr_excess = 0.018 + 0.012 * ((idx * 7) % 9)
                permanent_loss = primary_dp * (dry_plr + plr_excess)
                density_ratio = 0.035 + 0.00032 * (pressure - 60) + 0.00008 * (temperature - 30)
                gas_froude = 0.85 + 0.15 * ((idx * 5) % 12)
                reference = 35.0 + 1.15 * (idx % 17) + 0.04 * (pressure - 60)
                # Hidden fixture process. These coefficients are invented solely to
                # create a reproducible software test; they are not a wet-gas correlation.
                log_overread = (
                    0.15 * math.sqrt(plr_excess)
                    + 0.42 * plr_excess
                    - 0.012 * math.log(density_ratio)
                    + 0.018 * math.log(gas_froude)
                    + 0.035 * (beta - 0.58)
                    + 0.035 * math.sqrt(plr_excess) * math.log(density_ratio)
                )
                noise = ((idx * 37) % 13 - 6) * 0.00045
                indicated = reference * math.exp(max(0.0, log_overread + noise))
                sample = {
                    "indicated_gas_rate": round(indicated, 12),
                    "primary_dp_kpa": primary_dp,
                    "permanent_loss_kpa": round(permanent_loss, 12),
                    "dry_plr_reference": round(dry_plr, 12),
                    "density_ratio": round(density_ratio, 12),
                    "gas_froude": round(gas_froude, 12),
                    "beta": beta,
                    "pressure_kgf_cm2": pressure,
                    "temperature_c": temperature,
                    "indication_uncertainty_pct": 1.0,
                    "sensor_health": True,
                }
                rows.append({"sample": sample, "reference_gas_rate": round(reference, 12)})
    validation = [row for i, row in enumerate(rows) if i % 4 == 0]
    training = [row for i, row in enumerate(rows) if i % 4 != 0]
    return training, validation
