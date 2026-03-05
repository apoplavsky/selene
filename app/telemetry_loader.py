"""Load telemetry JSONL and compute derived fields."""

from __future__ import annotations

import json
import math
from pathlib import Path

from app import config
from app.models import TelemetryRow


def load_telemetry(path: Path | None = None) -> list[TelemetryRow]:
    path = path or config.TELEMETRY_PATH
    rows: list[TelemetryRow] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(TelemetryRow.model_validate(json.loads(line)))
    _compute_derived(rows)
    return rows


def _compute_derived(rows: list[TelemetryRow]) -> None:
    for row in rows:
        if row.vertical_speed_down_mps > 0:
            row.time_to_ground_s = row.altitude_m / row.vertical_speed_down_mps
        else:
            row.time_to_ground_s = float("inf")

        row.fuel_at_landing_pct = _estimate_fuel_at_landing(row)
        row.reachable_radius_km = _reachable_radius(row)


def _estimate_fuel_at_landing(row: TelemetryRow) -> float:
    """Rough estimate of remaining fuel at touchdown given current state.

    Uses the Tsiolkovsky equation backwards: how much fuel is needed to kill
    the current vertical speed, then subtract from current fuel percentage.
    """
    if row.vertical_speed_down_mps <= 0:
        return row.fuel_pct

    delta_v_needed = row.vertical_speed_down_mps
    ve = config.EXHAUST_VELOCITY_MPS
    mass_ratio = math.exp(delta_v_needed / ve)

    # fuel fraction consumed = 1 - 1/mass_ratio (of current mass)
    fuel_fraction_consumed = 1.0 - 1.0 / mass_ratio

    # Convert to percentage of total fuel: we assume current fuel_pct maps
    # linearly to propellant mass fraction (1 - DRY_MASS_RATIO)
    propellant_fraction = (1.0 - config.DRY_MASS_RATIO) * (row.fuel_pct / 100.0)
    propellant_used = fuel_fraction_consumed * (propellant_fraction + config.DRY_MASS_RATIO)
    remaining_propellant = propellant_fraction - propellant_used

    fuel_at_landing = max(0.0, remaining_propellant / (1.0 - config.DRY_MASS_RATIO) * 100.0)
    return round(fuel_at_landing, 2)


def _reachable_radius(row: TelemetryRow) -> float:
    """Estimate how far laterally (km) the lander can deviate from current track.

    Simplification: available lateral delta-v ≈ 10% of total remaining delta-v,
    and lateral displacement ≈ dv_lateral * time_to_ground / 2.
    """
    if row.time_to_ground_s is None or row.time_to_ground_s == float("inf"):
        return 0.0

    ve = config.EXHAUST_VELOCITY_MPS
    propellant_fraction = (1.0 - config.DRY_MASS_RATIO) * (row.fuel_pct / 100.0)
    total_mass_ratio = (config.DRY_MASS_RATIO + propellant_fraction) / config.DRY_MASS_RATIO
    total_dv = ve * math.log(max(total_mass_ratio, 1.001))

    # Reserve 90% for vertical braking; 10% for lateral maneuvering
    lateral_dv = total_dv * 0.10
    ttg = row.time_to_ground_s

    radius_m = lateral_dv * ttg / 2.0
    return round(radius_m / 1000.0, 2)


def telemetry_by_frame_id(rows: list[TelemetryRow]) -> dict[str, TelemetryRow]:
    return {r.frame_id: r for r in rows}
