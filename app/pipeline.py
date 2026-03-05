"""End-to-end analysis pipeline: load data -> analyse frames -> score -> report."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app import config
from app.cosmos_client import CosmosClient
from app.fuel_planner import fuel_score, reachable_ellipse_km
from app.hazard_detector import aggregate_hazards, frame_hazard_score
from app.models import (
    AnalysisReport,
    GoNoGo,
    LandingSiteRecommendation,
    TerrainAnalysis,
    TelemetryRow,
)
from app.prompts import LANDING_SITE_COMPARISON, SYSTEM_PROMPT
from app.telemetry_loader import load_telemetry, telemetry_by_frame_id
from app.terrain_analyzer import analyze_frame, select_key_frames

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared progress state (read by the API layer)
# ---------------------------------------------------------------------------

class PipelineProgress:
    def __init__(self) -> None:
        self.phase: str = "idle"
        self.total_frames: int = 0
        self.completed_frames: int = 0
        self.current_frame_id: str = ""
        self.analyses: list[dict] = []
        self.key_frame_ids: list[str] = []
        self.done: bool = False
        self.error: str | None = None
        self.cancelled: bool = False

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "total_frames": self.total_frames,
            "completed_frames": self.completed_frames,
            "current_frame_id": self.current_frame_id,
            "key_frame_ids": self.key_frame_ids,
            "analyses": self.analyses,
            "done": self.done,
            "error": self.error,
        }

    def reset(self) -> None:
        self.__init__()


progress = PipelineProgress()


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _composite_score(surface_safety: float, fuel: float, nav_confidence: float) -> float:
    return round(surface_safety * 0.50 + fuel * 0.30 + nav_confidence * 0.20, 2)


def _nav_confidence_score(telemetry: TelemetryRow) -> float:
    sigma = telemetry.nav_pos_sigma_m
    return max(0.0, min(100.0, (10.0 - sigma) / 8.0 * 100.0))


def _empty_report(frames_dir: Path) -> AnalysisReport:
    return AnalysisReport(total_frames=0, key_frames_analyzed=0)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

async def run_pipeline(
    frames_dir: Path | None = None,
    telemetry_path: Path | None = None,
    results_dir: Path | None = None,
    num_key_frames: int | None = None,
) -> AnalysisReport:
    global progress
    progress = PipelineProgress()

    frames_dir = frames_dir or config.FRAMES_DIR
    telemetry_path = telemetry_path or config.TELEMETRY_PATH
    results_dir = results_dir or config.RESULTS_DIR
    results_dir.mkdir(parents=True, exist_ok=True)
    n = num_key_frames or config.NUM_KEY_FRAMES

    try:
        progress.phase = "loading"
        log.info("Loading telemetry from %s", telemetry_path)
        telemetry_rows = load_telemetry(telemetry_path)
        telem_map = telemetry_by_frame_id(telemetry_rows)

        log.info("Selecting %d key frames from %s", n, frames_dir)
        key_frames = select_key_frames(frames_dir, n)
        progress.key_frame_ids = [f.stem for f in key_frames]
        progress.total_frames = len(key_frames)
        log.info("Key frames: %s", progress.key_frame_ids)

        client = CosmosClient()

        # -- Phase 1: per-frame terrain analysis --
        progress.phase = "analyzing"
        analyses: list[TerrainAnalysis] = []
        for i, frame_path in enumerate(key_frames):
            if progress.cancelled:
                log.info("Pipeline cancelled")
                progress.phase = "idle"
                return _empty_report(frames_dir)

            telem = telem_map.get(frame_path.stem)
            progress.current_frame_id = frame_path.stem
            log.info("  [%d/%d] Analyzing %s (alt=%.0f m)",
                     i + 1, len(key_frames), frame_path.stem,
                     telem.altitude_m if telem else 0)

            analysis = await analyze_frame(client, frame_path, telem)
            analyses.append(analysis)

            progress.completed_frames = i + 1
            progress.analyses.append(analysis.model_dump())

        if progress.cancelled:
            log.info("Pipeline cancelled")
            progress.phase = "idle"
            return _empty_report(frames_dir)

        # -- Phase 2: comparative ranking --
        progress.phase = "comparing"
        progress.current_frame_id = ""
        log.info("Phase 2: Comparative ranking")
        top_candidates = sorted(analyses, key=lambda a: a.suitability_score, reverse=True)[:4]
        top_paths = [frames_dir / f"{a.frame_id}.png" for a in top_candidates]

        comparison_reasoning = ""
        if len(top_paths) >= 2:
            avg_fuel = sum(r.fuel_pct for r in telemetry_rows) / len(telemetry_rows)
            prompt = LANDING_SITE_COMPARISON.format(n=len(top_paths), fuel=avg_fuel)
            try:
                comp_result = await client.compare_images(top_paths, prompt, system_prompt=SYSTEM_PROMPT)
                comparison_reasoning = comp_result.get("reasoning", "") + "\n" + comp_result.get("answer", "")
            except Exception:
                log.exception("Comparison call failed, proceeding without it")

        # -- Phase 3: scoring and recommendations --
        progress.phase = "scoring"
        log.info("Phase 3: Scoring and recommendations")
        recommendations: list[LandingSiteRecommendation] = []
        for analysis in analyses:
            telem = telem_map.get(analysis.frame_id)
            surface = frame_hazard_score(analysis)
            f_score = fuel_score(telem) if telem else 50.0
            nav = _nav_confidence_score(telem) if telem else 50.0
            composite = _composite_score(surface, f_score, nav)

            if composite >= 70:
                verdict = GoNoGo.GO
            elif composite >= 45:
                verdict = GoNoGo.MARGINAL
            else:
                verdict = GoNoGo.NO_GO

            recommendations.append(
                LandingSiteRecommendation(
                    rank=0,
                    frame_id=analysis.frame_id,
                    composite_score=composite,
                    surface_safety_score=surface,
                    fuel_cost_score=f_score,
                    nav_confidence_score=nav,
                    go_no_go=verdict,
                    reasoning=analysis.summary,
                    fuel_remaining_pct=telem.fuel_at_landing_pct if telem else None,
                    reachable=True,
                )
            )

        recommendations.sort(key=lambda r: r.composite_score, reverse=True)
        for i, rec in enumerate(recommendations, 1):
            rec.rank = i

        # -- Build report --
        hazard_summary = aggregate_hazards(analyses)
        telem_summary = {
            "start_altitude_m": telemetry_rows[0].altitude_m,
            "end_altitude_m": telemetry_rows[-1].altitude_m,
            "avg_vertical_speed_mps": round(
                sum(r.vertical_speed_down_mps for r in telemetry_rows) / len(telemetry_rows), 1
            ),
            "fuel_start_pct": telemetry_rows[0].fuel_pct,
            "fuel_end_pct": telemetry_rows[-1].fuel_pct,
            "hazard_summary": {
                "total": hazard_summary["total_hazards"],
                "critical": len(hazard_summary["critical_hazards"]),
            },
        }
        latest = telemetry_rows[-1]
        telem_summary["reachable_ellipse"] = reachable_ellipse_km(latest)

        report = AnalysisReport(
            total_frames=len(list(frames_dir.iterdir())),
            key_frames_analyzed=len(key_frames),
            terrain_analyses=analyses,
            recommendations=recommendations,
            comparison_reasoning=comparison_reasoning,
            telemetry_summary=telem_summary,
        )

        report_path = results_dir / "report.json"
        report_path.write_text(report.model_dump_json(indent=2))
        log.info("Report saved to %s", report_path)

        progress.phase = "done"
        progress.done = True
        return report

    except Exception as exc:
        progress.phase = "error"
        progress.error = str(exc)
        raise
