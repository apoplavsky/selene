"""FastAPI backend for SELENE Lunar Landing Advisory System."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app import config
from app.cosmos_client import CosmosClient
from app.models import AnalysisReport
from app.pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(
    title="SELENE",
    description="Surface Evaluation for Landing and Navigation Engine",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_running_task: Optional[asyncio.Task] = None
_latest_report: Optional[AnalysisReport] = None


@app.on_event("startup")
async def _clear_previous_results():
    """Remove stale results from prior runs so the dashboard starts clean."""
    _reset_state()


def _reset_state():
    """Cancel any running analysis, clear in-memory report, delete report file."""
    global _running_task, _latest_report
    from app.pipeline import progress

    if _running_task and not _running_task.done():
        progress.cancelled = True
        _running_task.cancel()
        log.info("Cancelled running analysis task")

    _running_task = None
    _latest_report = None
    progress.reset()

    report_path = config.RESULTS_DIR / "report.json"
    if report_path.exists():
        report_path.unlink()
        log.info("Cleared previous report at %s", report_path)


@app.get("/health")
async def health():
    client = CosmosClient()
    vllm_ok = await client.health_check()
    return {
        "status": "ok",
        "vllm_available": vllm_ok,
        "frames_dir": str(config.FRAMES_DIR),
        "has_report": _latest_report is not None,
    }


@app.post("/analyze")
async def start_analysis(num_key_frames: int = 15):
    global _running_task
    _reset_state()

    async def _run():
        global _latest_report
        try:
            _latest_report = await run_pipeline(num_key_frames=num_key_frames)
        except asyncio.CancelledError:
            log.info("Analysis task was cancelled")
        except Exception:
            log.exception("Pipeline failed")

    _running_task = asyncio.create_task(_run())
    return {"status": "started", "key_frames": num_key_frames}


@app.post("/analyze/stop")
async def stop_analysis():
    _reset_state()
    return {"status": "stopped"}


@app.get("/analyze/status")
async def analysis_status():
    if _running_task is None:
        return {"status": "idle"}
    if not _running_task.done():
        return {"status": "running"}
    exc = _running_task.exception() if _running_task.done() else None
    if exc:
        return {"status": "failed", "error": str(exc)}
    return {"status": "completed"}


@app.get("/analyze/progress")
async def analysis_progress():
    from app.pipeline import progress
    return progress.to_dict()


@app.get("/results")
async def get_results():
    if _latest_report is not None:
        return _latest_report.model_dump()

    report_path = config.RESULTS_DIR / "report.json"
    if report_path.exists():
        return json.loads(report_path.read_text())

    raise HTTPException(status_code=404, detail="No analysis results available. POST /analyze first.")


@app.get("/frames")
async def list_frames():
    if not config.FRAMES_DIR.exists():
        return {"count": 0, "frames": []}
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    frames = sorted(
        [p.name for p in config.FRAMES_DIR.iterdir() if p.suffix.lower() in exts]
    )
    return {"count": len(frames), "frames": frames}


@app.get("/frames/{frame_name}")
async def get_frame(frame_name: str):
    path = config.FRAMES_DIR / frame_name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Frame {frame_name} not found")
    return FileResponse(path, media_type="image/png")


@app.get("/telemetry")
async def get_telemetry():
    if not config.TELEMETRY_PATH.is_file():
        return []
    from app.telemetry_loader import load_telemetry
    rows = load_telemetry()
    return [r.model_dump() for r in rows]
