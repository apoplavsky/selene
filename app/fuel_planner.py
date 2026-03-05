"""Fuel-constrained reachability and delta-v budgeting."""

from __future__ import annotations

import math

from app import config
from app.models import TelemetryRow


def remaining_delta_v(fuel_pct: float) -> float:
    """Total delta-v (m/s) available from current fuel percentage."""
    propellant_frac = (1.0 - config.DRY_MASS_RATIO) * (fuel_pct / 100.0)
    total_mass = config.DRY_MASS_RATIO + propellant_frac
    if total_mass <= config.DRY_MASS_RATIO:
        return 0.0
    return config.EXHAUST_VELOCITY_MPS * math.log(total_mass / config.DRY_MASS_RATIO)


def braking_delta_v(vertical_speed: float, altitude: float) -> float:
    """Delta-v (m/s) needed to zero vertical speed via constant-thrust braking.

    Includes gravity loss ≈ g * burn_time / 2 (approximate).
    """
    g = config.LUNAR_GRAVITY_MPS2
    if vertical_speed <= 0:
        return 0.0
    # Burn time estimate: t ≈ v / (thrust_accel - g); for simplicity assume
    # thrust_accel ≈ 2*g (typical powered descent), so t ≈ v / g
    burn_time = vertical_speed / g
    gravity_loss = g * burn_time * 0.5
    return vertical_speed + gravity_loss


def lateral_budget(fuel_pct: float, vertical_speed: float, altitude: float) -> float:
    """Delta-v (m/s) available for lateral maneuvering after braking reserve."""
    total = remaining_delta_v(fuel_pct)
    braking = braking_delta_v(vertical_speed, altitude)
    margin = total - braking
    # Reserve 50% of margin for attitude control and contingency
    return max(0.0, margin * 0.5)


def reachable_ellipse_km(telemetry: TelemetryRow) -> dict:
    """Estimate reachable landing area as an ellipse (semi-axes in km).

    Along-track range is larger because we can modulate braking start time.
    Cross-track range depends on lateral delta-v and time to ground.
    """
    lat_dv = lateral_budget(
        telemetry.fuel_pct,
        telemetry.vertical_speed_down_mps,
        telemetry.altitude_m,
    )
    ttg = telemetry.time_to_ground_s or 0.0

    cross_track_m = lat_dv * ttg / 2.0

    # Along-track: braking earlier or later shifts ground-track by ≈ v_lateral * dt
    along_track_m = cross_track_m * 1.5  # empirical factor for along-track advantage

    return {
        "cross_track_km": round(cross_track_m / 1000.0, 2),
        "along_track_km": round(along_track_m / 1000.0, 2),
    }


def fuel_score(telemetry: TelemetryRow) -> float:
    """Score 0-100 based on fuel margin after braking. 100 = plenty of fuel."""
    total_dv = remaining_delta_v(telemetry.fuel_pct)
    needed_dv = braking_delta_v(
        telemetry.vertical_speed_down_mps,
        telemetry.altitude_m,
    )
    if total_dv <= 0:
        return 0.0
    margin_ratio = (total_dv - needed_dv) / total_dv
    return max(0.0, min(100.0, margin_ratio * 100.0))
