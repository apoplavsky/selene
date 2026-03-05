"""Orchestrates frame analysis via Cosmos Reason 2."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from app import config
from app.cosmos_client import CosmosClient
from app.models import Hazard, HazardType, TerrainAnalysis, TelemetryRow
from app.prompts import HAZARD_ASSESSMENT, SYSTEM_PROMPT, TERRAIN_SURVEY

log = logging.getLogger(__name__)

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_BARE_JSON = re.compile(r"(\{[^{}]*\"suitability_score\"[^{}]*\})", re.DOTALL)
_DIGITS = re.compile(r"\d+")


def _safe_int(val, default: int = 0, lo: int | None = None, hi: int | None = None) -> int:
    """Coerce a value to int, extracting digits from strings if needed."""
    if isinstance(val, (int, float)):
        n = int(val)
    elif isinstance(val, str):
        m = _DIGITS.search(val)
        n = int(m.group()) if m else default
    else:
        n = default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def _extract_json(text: str) -> Optional[dict]:
    """Try to pull a JSON object out of model output."""
    m = _JSON_BLOCK.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = _BARE_JSON.search(text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def select_key_frames(
    frame_dir: Path,
    n: int = config.NUM_KEY_FRAMES,
) -> list[Path]:
    """Pick n evenly spaced frames from the directory."""
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    all_frames = sorted(
        [p for p in frame_dir.iterdir() if p.suffix.lower() in exts],
        key=lambda p: p.stem,
    )
    if len(all_frames) <= n:
        return all_frames

    step = (len(all_frames) - 1) / (n - 1)
    indices = [round(i * step) for i in range(n)]
    return [all_frames[i] for i in indices]


_HAZARD_KEYWORDS: dict[str, HazardType] = {
    "crater": HazardType.CRATER,
    "boulder": HazardType.BOULDER_FIELD,
    "rock": HazardType.BOULDER_FIELD,
    "slope": HazardType.STEEP_SLOPE,
    "steep": HazardType.STEEP_SLOPE,
    "ridge": HazardType.RIDGE,
    "scarp": HazardType.RIDGE,
    "shadow": HazardType.SHADOW_ZONE,
    "ejecta": HazardType.EJECTA,
    "debris": HazardType.EJECTA,
}


def _infer_hazard_type(raw_type: str, description: str) -> HazardType:
    """Try exact enum match first, then keyword matching on type+description."""
    try:
        return HazardType(raw_type.lower().strip())
    except ValueError:
        pass
    combined = f"{raw_type} {description}".lower()
    for keyword, ht in _HAZARD_KEYWORDS.items():
        if keyword in combined:
            return ht
    return HazardType.TERRAIN_ANOMALY


def _parse_hazard(h: dict) -> Hazard:
    raw_type = str(h.get("type", ""))
    desc = str(h.get("description", ""))
    ht = _infer_hazard_type(raw_type, desc)
    return Hazard(
        hazard_type=ht,
        severity=_safe_int(h.get("severity", 3), 3, 1, 5),
        description=desc,
        frame_region=str(h.get("region", "")),
    )


_ADVISORY_RANK = {"PROCEED": 0, "CAUTION": 1, "ABORT": 2}


def _enforce_advisory(
    telemetry: Optional[TelemetryRow],
    suitability: int,
    model_advisory: str,
    model_reason: str,
) -> tuple[str, str, bool]:
    """Algorithmic safety net: can only ESCALATE the VLM's advisory, never downgrade.

    Returns (advisory, reason, overridden) where overridden=True means the
    algorithm escalated beyond the VLM's call.
    """
    if model_advisory not in _ADVISORY_RANK:
        model_advisory = "PROCEED"

    if telemetry is None:
        return model_advisory, model_reason, False

    fuel = telemetry.fuel_pct
    nav = telemetry.nav_pos_sigma_m
    lat = telemetry.lateral_speed_mps

    algo_advisory = "PROCEED"
    algo_reason = ""

    caution_reasons = []
    if fuel < 30:
        caution_reasons.append(f"fuel at {fuel:.1f}%")
    if nav > 200:
        caution_reasons.append(f"nav uncertainty {nav:.0f} m")
    if lat > 25:
        caution_reasons.append(f"lateral speed {lat:.1f} m/s")

    if caution_reasons:
        algo_advisory = "CAUTION"
        algo_reason = "Telemetry: " + ", ".join(caution_reasons)

    if fuel < 20:
        algo_advisory = "ABORT"
        algo_reason = f"Fuel critically low at {fuel:.1f}%"
    elif fuel < 25 and nav > 150:
        algo_advisory = "ABORT"
        algo_reason = f"Fuel low ({fuel:.1f}%) with high nav uncertainty ({nav:.0f} m)"

    if _ADVISORY_RANK.get(algo_advisory, 0) > _ADVISORY_RANK.get(model_advisory, 0):
        return algo_advisory, algo_reason, True

    return model_advisory, model_reason, False


def _sanitize_summary(text: str, advisory: str = "", advisory_reason: str = "") -> str:
    """Clean up model summaries: remove leaked reasoning and junk."""
    if not text:
        return ""

    lower = text.lower().strip()

    # Detect leaked JSON or code blocks
    if any(marker in lower for marker in ("```", '{"', '"crater_count"', '"hazards"')):
        return ""

    # Detect leaked chain-of-thought / meta-reasoning
    junk_markers = (
        "okay", "let's", "the user", "i need", "looking at", "sure",
        "alright", "now,", "first,", "step ", "here's", "to analyze",
        "the key points", "i'll ", "we need", "given the", "based on",
        "the terrain is", "the lander",
    )
    if any(lower.startswith(m) for m in junk_markers):
        return ""

    # Strip sentences that reference advisory/fuel decisions (terrain only)
    contradictions = (
        "proceed", "safe to", "not critical", "nominal",
        "no immediate", "safely", "can maneuver", "sufficient fuel",
        "healthy status", "allows for a safe", "abort",
    )
    if any(c in lower for c in contradictions):
        return ""

    # Truncate at sentence boundary if cut off mid-word
    if len(text) > 20 and not text.rstrip().endswith((".", "!", "?")):
        last_period = text.rfind(".")
        if last_period > 20:
            return text[: last_period + 1]

    return text


async def analyze_frame(
    client: CosmosClient,
    frame_path: Path,
    telemetry: Optional[TelemetryRow] = None,
) -> TerrainAnalysis:
    """Run terrain survey on a single frame, return structured result."""
    alt = telemetry.altitude_m if telemetry else 100_000.0
    frame_id = frame_path.stem

    prompt = TERRAIN_SURVEY.format(
        altitude_m=alt,
        vspeed=telemetry.vertical_speed_down_mps if telemetry else 0.0,
        lspeed=telemetry.lateral_speed_mps if telemetry else 0.0,
        fuel=telemetry.fuel_pct if telemetry else 100.0,
        nav_sigma=telemetry.nav_pos_sigma_m if telemetry else 0.0,
        dust=telemetry.dust_level_0to1 if telemetry else 0.0,
    )
    result = await client.analyze_image(frame_path, prompt, system_prompt=SYSTEM_PROMPT)

    answer_text = result["answer"]
    reasoning = result["reasoning"]

    parsed = _extract_json(answer_text)
    if parsed is None:
        parsed = _extract_json(result["raw"])

    if parsed:
        hazards = [_parse_hazard(h) for h in parsed.get("hazards", [])]
        score = _safe_int(parsed.get("suitability_score", 5), 5, 1, 10)
        model_advisory = str(parsed.get("mission_advisory", "")).upper().strip()
        model_reason = str(parsed.get("advisory_reason", ""))

        advisory, reason, overridden = _enforce_advisory(
            telemetry, score, model_advisory, model_reason,
        )

        raw_summary = str(parsed.get("summary", ""))
        summary = _sanitize_summary(raw_summary, advisory, reason)

        return TerrainAnalysis(
            frame_id=frame_id,
            altitude_m=alt,
            suitability_score=score,
            crater_count=_safe_int(parsed.get("crater_count", 0), 0),
            crater_sizes=str(parsed.get("crater_sizes", "")),
            boulder_fields=bool(parsed.get("boulder_fields", False)),
            slope_assessment=str(parsed.get("slope_assessment", "")),
            flat_zones=str(parsed.get("flat_zones", "")),
            hazards=hazards,
            mission_advisory=advisory,
            advisory_reason=reason,
            advisory_overridden=overridden,
            reasoning=reasoning,
            summary=summary,
        )

    log.warning("Failed to parse JSON from model output for %s, using defaults", frame_id)
    advisory, reason, overridden = _enforce_advisory(telemetry, 5, "CAUTION", "")
    return TerrainAnalysis(
        frame_id=frame_id,
        altitude_m=alt,
        suitability_score=5,
        mission_advisory=advisory,
        advisory_reason=reason,
        advisory_overridden=overridden,
        reasoning=reasoning,
        summary=_sanitize_summary(answer_text[:200], advisory, reason),
    )


async def assess_hazards(
    client: CosmosClient,
    frame_path: Path,
    telemetry: TelemetryRow,
) -> list[Hazard]:
    """Dedicated hazard-focused analysis for a frame."""
    prompt = HAZARD_ASSESSMENT.format(
        altitude_m=telemetry.altitude_m,
        vspeed=telemetry.vertical_speed_down_mps,
        lspeed=telemetry.lateral_speed_mps,
        fuel=telemetry.fuel_pct,
    )
    result = await client.analyze_image(frame_path, prompt, system_prompt=SYSTEM_PROMPT)
    parsed = _extract_json(result["answer"]) or _extract_json(result["raw"])
    if parsed:
        return [_parse_hazard(h) for h in parsed.get("hazards", [])]
    return []
