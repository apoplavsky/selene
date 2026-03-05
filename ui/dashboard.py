"""SELENE Lunar Landing Advisory Dashboard (Streamlit)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.components import (
    analysis_card,
    analysis_card_compact,
    frame_with_telemetry,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="SELENE Lunar Landing Advisor",
    page_icon="🌑",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .block-container { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
API_BASE = "http://localhost:8080"


def api_get(path: str):
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def api_post(path: str, **params):
    try:
        r = requests.post(f"{API_BASE}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Resolve frames dir
# ---------------------------------------------------------------------------
def _find_frames_dir() -> Path:
    for candidate in [
        Path("/data/frames"),
        Path(__file__).resolve().parent.parent / "frames",
    ]:
        if candidate.exists():
            return candidate
    return Path("frames")


frames_dir = _find_frames_dir()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("# SELENE")
    st.markdown("**Surface Evaluation for Landing & Navigation Engine**")

    st.markdown("#### Landing Site Evaluation")
    n_frames = st.slider("Key frames", 3, 30, 15)

    _pre_progress = api_get("/analyze/progress")
    _is_active = (
        _pre_progress is not None
        and _pre_progress.get("phase") not in (None, "idle", "error", "done")
    )

    if _is_active:
        if st.button("Stop", type="secondary", use_container_width=True):
            api_post("/analyze/stop")
            st.rerun()
    else:
        if st.button("Start", type="primary", use_container_width=True):
            api_post("/analyze", num_key_frames=n_frames)

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
telemetry: list[dict] = api_get("/telemetry") or []
telem_by_id: dict[str, dict] = {r["frame_id"]: r for r in telemetry}

frame_exts = {".png", ".jpg", ".jpeg", ".webp"}
all_frame_files = sorted(
    [p for p in frames_dir.iterdir() if p.suffix.lower() in frame_exts],
    key=lambda p: p.stem,
) if frames_dir.exists() else []
all_frame_ids = [p.stem for p in all_frame_files]

report: dict | None = api_get("/results")

live_progress = api_get("/analyze/progress")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("# SELENE Lunar Landing Advisory System")
st.caption("Autonomous terrain analysis & landing site recommendation, NVIDIA Cosmos Reason 2")

# ---------------------------------------------------------------------------
# Derived data
# ---------------------------------------------------------------------------
analyses_data = report.get("terrain_analyses", []) if report else []
analysis_by_id: dict[str, dict] = {a["frame_id"]: a for a in analyses_data}

is_running = (
    live_progress is not None
    and live_progress.get("phase") not in (None, "idle", "error")
)


# =====================================================================
# Main view
# =====================================================================
if is_running:
    # ----- ANALYSIS IN PROGRESS -----
    phase = live_progress.get("phase", "?")
    total = live_progress.get("total_frames", 0)
    done_count = live_progress.get("completed_frames", 0)
    current_fid = live_progress.get("current_frame_id", "")
    partial_analyses = live_progress.get("analyses", [])

    phase_labels = {
        "loading": "Loading telemetry",
        "analyzing": "Scanning terrain",
        "comparing": "Comparing sites",
        "scoring": "Computing advisories",
        "done": "Complete",
    }
    st.markdown(f"### Landing site evaluation: **{phase_labels.get(phase, phase)}**")

    if total > 0:
        st.progress(done_count / total, text=f"Frame {done_count} / {total}")
    else:
        st.progress(0, text="Preparing…")

    preview_fid = current_fid or (partial_analyses[-1]["frame_id"] if partial_analyses else "")
    if preview_fid:
        frame_with_telemetry(frames_dir, preview_fid, telem_by_id.get(preview_fid))

    if partial_analyses:
        st.markdown("### Evaluation log")
        for a in reversed(partial_analyses):
            analysis_card_compact(a["frame_id"], a)

    time.sleep(3)
    st.rerun()

elif live_progress and live_progress.get("phase") == "error":
    st.error(f"Analysis failed: {live_progress.get('error', 'unknown')}")

else:
    # ----- IDLE / BROWSE MODE -----
    if not all_frame_ids:
        st.warning("No frames available. Mount frames in `./frames`.")
    else:
        frame_idx = st.slider(
            "Frame",
            0, len(all_frame_ids) - 1, 0,
            format=f"Frame %d / {len(all_frame_ids) - 1}",
            key="browse_slider",
        )

        fid = all_frame_ids[frame_idx]
        trow = telem_by_id.get(fid)
        a = analysis_by_id.get(fid)

        frame_with_telemetry(frames_dir, fid, trow)

        if a:
            st.markdown("#### Terrain assessment")
            analysis_card(a)
            if a.get("reasoning"):
                with st.expander("Model reasoning"):
                    st.markdown(a["reasoning"])
