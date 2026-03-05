from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

class TelemetryRow(BaseModel):
    frame_id: str
    time_s: float
    altitude_m: float
    altimeter_m: Optional[float] = None
    vertical_speed_down_mps: float
    lateral_speed_mps: float
    flow_proxy_0to1: float
    throttle_proxy_0to1: float
    fuel_pct: float
    dust_level_0to1: float
    nav_pos_sigma_m: float

    # computed fields filled by telemetry_loader
    time_to_ground_s: Optional[float] = None
    fuel_at_landing_pct: Optional[float] = None
    reachable_radius_km: Optional[float] = None


# ---------------------------------------------------------------------------
# Hazard analysis
# ---------------------------------------------------------------------------

class HazardType(str, Enum):
    CRATER = "crater"
    BOULDER_FIELD = "boulder_field"
    STEEP_SLOPE = "steep_slope"
    RIDGE = "ridge"
    SHADOW_ZONE = "shadow_zone"
    EJECTA = "ejecta"
    TERRAIN_ANOMALY = "terrain_anomaly"


class Hazard(BaseModel):
    hazard_type: HazardType
    severity: int = Field(ge=1, le=5)
    description: str
    frame_region: str = ""  # e.g. "upper-left", "center"


# ---------------------------------------------------------------------------
# Terrain analysis (per-frame VLM output)
# ---------------------------------------------------------------------------

class MissionAdvisory(str, Enum):
    PROCEED = "PROCEED"
    CAUTION = "CAUTION"
    ABORT = "ABORT"


class TerrainAnalysis(BaseModel):
    frame_id: str
    altitude_m: float
    suitability_score: int = Field(ge=1, le=10)
    crater_count: int = 0
    crater_sizes: str = ""
    boulder_fields: bool = False
    slope_assessment: str = ""
    flat_zones: str = ""
    hazards: list[Hazard] = Field(default_factory=list)
    mission_advisory: MissionAdvisory = MissionAdvisory.CAUTION
    advisory_reason: str = ""
    advisory_overridden: bool = False
    reasoning: str = ""
    summary: str = ""


# ---------------------------------------------------------------------------
# Landing site recommendation
# ---------------------------------------------------------------------------

class GoNoGo(str, Enum):
    GO = "GO"
    MARGINAL = "MARGINAL"
    NO_GO = "NO-GO"


class LandingSiteRecommendation(BaseModel):
    rank: int
    frame_id: str
    composite_score: float = Field(ge=0.0, le=100.0)
    surface_safety_score: float
    fuel_cost_score: float
    nav_confidence_score: float
    go_no_go: GoNoGo
    reasoning: str
    fuel_remaining_pct: Optional[float] = None
    reachable: bool = True


# ---------------------------------------------------------------------------
# Full analysis report
# ---------------------------------------------------------------------------

class AnalysisReport(BaseModel):
    mission_id: str = "SELENE-001"
    total_frames: int
    key_frames_analyzed: int
    terrain_analyses: list[TerrainAnalysis] = Field(default_factory=list)
    recommendations: list[LandingSiteRecommendation] = Field(default_factory=list)
    comparison_reasoning: str = ""
    telemetry_summary: dict = Field(default_factory=dict)
