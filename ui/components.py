"""Reusable Streamlit UI components for SELENE dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import plotly.graph_objects as go
import streamlit as st


COLORS = {
    "GO": "#22c55e",
    "MARGINAL": "#f59e0b",
    "NO-GO": "#ef4444",
    "primary": "#6366f1",
    "text": "#e2e8f0",
    "muted": "#94a3b8",
    "bg_card": "#0f172a",
}

_HAZARD_LABELS: dict[str, str] = {
    "crater": "Crater",
    "boulder_field": "Boulder Field",
    "steep_slope": "Steep Slope",
    "ridge": "Ridge / Scarp",
    "shadow_zone": "Shadow Zone",
    "ejecta": "Ejecta / Debris",
    "terrain_anomaly": "Terrain Anomaly",
}


def _hazard_label(raw: str) -> str:
    return _HAZARD_LABELS.get(raw, raw.replace("_", " ").title())


# ---------------------------------------------------------------------------
# Frame + telemetry (image left, telemetry numbers right)
# ---------------------------------------------------------------------------
def frame_with_telemetry(
    frames_dir: Path,
    frame_id: str,
    telemetry_row: Optional[dict],
) -> None:
    """Frame image on the left, telemetry readouts on the right."""
    frame_path = _resolve_frame(frames_dir, frame_id)

    col_img, col_telem = st.columns([3, 2])

    with col_img:
        if frame_path and frame_path.exists():
            st.image(str(frame_path), use_container_width=True)
        else:
            st.warning(f"Frame not found: {frame_id}")

    with col_telem:
        st.markdown(f"#### `{frame_id}`")
        if telemetry_row:
            fuel = telemetry_row.get('fuel_pct', 0)
            fuel_color = "#22c55e" if fuel > 40 else "#f59e0b" if fuel > 20 else "#ef4444"
            dust = telemetry_row.get('dust_level_0to1', 0)
            dust_warn = " ⚠" if dust > 0.5 else ""
            st.markdown(
                f"**Altitude:** {telemetry_row.get('altitude_m', 0):,.0f} m  \n"
                f"**V-speed:** {telemetry_row.get('vertical_speed_down_mps', 0):.1f} m/s  \n"
                f"**Lat-speed:** {telemetry_row.get('lateral_speed_mps', 0):.2f} m/s  \n"
                f"**Fuel:** <span style='color:{fuel_color}'>{fuel:.1f}%</span>  \n"
                f"**Throttle:** {telemetry_row.get('throttle_proxy_0to1', 0):.0%}  \n"
                f"**Nav σ:** {telemetry_row.get('nav_pos_sigma_m', 0):.1f} m  \n"
                f"**Dust:** {dust:.2f}{dust_warn}",
                unsafe_allow_html=True,
            )
        else:
            st.caption("No telemetry for this frame")


# ---------------------------------------------------------------------------
# Analysis result card (displayed below the frame)
# ---------------------------------------------------------------------------
_ADVISORY_COLORS = {
    "PROCEED": "#22c55e",
    "CAUTION": "#f59e0b",
    "ABORT": "#ef4444",
}


def _terrain_class(score: int) -> tuple[str, str]:
    """Map suitability score to a human-readable terrain classification + color."""
    if score >= 8:
        return "SAFE TO LAND", COLORS["GO"]
    if score >= 7:
        return "LANDABLE", COLORS["GO"]
    if score >= 5:
        return "ROUGH SURFACE", COLORS["MARGINAL"]
    if score >= 3:
        return "UNSUITABLE TERRAIN", COLORS["NO-GO"]
    return "HAZARDOUS TERRAIN", COLORS["NO-GO"]


def analysis_card(analysis: dict) -> None:
    """Show terrain analysis results as a compact block."""
    score = analysis.get("suitability_score", 5)
    if not isinstance(score, (int, float)):
        score = 5
    label, color = _terrain_class(int(score))

    advisory = analysis.get("mission_advisory", "")
    adv_color = _ADVISORY_COLORS.get(advisory, COLORS["muted"])
    adv_badge = (
        f" &nbsp;<span style='background:{adv_color};color:#000;padding:2px 10px;"
        f"border-radius:4px;font-weight:bold;font-size:0.85em'>{advisory}</span>"
    ) if advisory else ""

    st.markdown(
        f"<span style='color:{color};font-size:1.3em;"
        f"font-weight:bold'>{label}</span>"
        f"{adv_badge}"
        f" &nbsp; Craters: {analysis.get('crater_count', 0)}"
        f" ({analysis.get('crater_sizes', '—')})"
        f" &nbsp; Boulders: {'Yes' if analysis.get('boulder_fields') else 'No'}",
        unsafe_allow_html=True,
    )

    if analysis.get("advisory_overridden") and analysis.get("advisory_reason"):
        st.markdown(
            f"<span style='color:{adv_color}'>&#9888; {analysis['advisory_reason']}</span>",
            unsafe_allow_html=True,
        )

    slope = analysis.get("slope_assessment", "")
    flat = analysis.get("flat_zones", "")
    if slope:
        st.markdown(f"**Slope:** {slope}")
    if flat:
        st.markdown(f"**Flat zones:** {flat}")

    summary = analysis.get("summary", "")
    if summary:
        st.markdown(f"*{summary}*")

    hazards = analysis.get("hazards", [])
    if hazards:
        st.markdown("**Hazards:**")
        for h in hazards:
            sev = h.get("severity", 0)
            label = _hazard_label(h.get("hazard_type", "terrain_anomaly"))
            st.markdown(
                f"- **{label}** (severity {sev}/5) — "
                f"*{h.get('description', '')}*"
            )


# ---------------------------------------------------------------------------
# Compact analysis entry (text only, for results log during live analysis)
# ---------------------------------------------------------------------------
def analysis_card_compact(frame_id: str, analysis: dict) -> None:
    """Single compact block per frame — no image, used in the running results log."""
    score = analysis.get("suitability_score", 5)
    if not isinstance(score, (int, float)):
        score = 5
    label, color = _terrain_class(int(score))

    hazard_count = len(analysis.get("hazards", []))
    summary = analysis.get("summary", "")
    advisory = analysis.get("mission_advisory", "")
    adv_color = _ADVISORY_COLORS.get(advisory, COLORS["muted"])
    adv_html = f" <span style='color:{adv_color};font-weight:bold'>{advisory}</span>" if advisory else ""

    adv_badge = (
        f" &nbsp;<span style='background:{adv_color};color:#000;padding:1px 8px;"
        f"border-radius:3px;font-weight:bold;font-size:0.85em'>{advisory}</span>"
    ) if advisory else ""

    reason_line = ""
    if analysis.get("advisory_overridden") and analysis.get("advisory_reason"):
        reason_line = (
            f"  \n<span style='color:{adv_color};font-size:0.9em'>"
            f"&#9888; {analysis['advisory_reason']}</span>"
        )

    st.markdown(
        f"**`{frame_id}`** "
        f"<span style='color:{color};font-weight:bold'>{label}</span>"
        f"{adv_badge} &nbsp; "
        f"Craters: {analysis.get('crater_count', 0)} | "
        f"Hazards: {hazard_count}"
        f"{reason_line}"
        f"  \n*{summary}*" if summary else "",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Hazard summary
# ---------------------------------------------------------------------------
def hazard_summary_panel(analyses: list[dict]) -> None:
    all_hazards: list[dict] = []
    for a in analyses:
        for h in a.get("hazards", []):
            all_hazards.append({**h, "frame_id": a["frame_id"]})

    if not all_hazards:
        st.info("No hazards detected across analyzed frames.")
        return

    critical = [h for h in all_hazards if h.get("severity", 0) >= 4]
    st.markdown(f"**Total hazards:** {len(all_hazards)}  |  "
                f"**Critical (sev 4-5):** {len(critical)}")

    type_counts: dict[str, int] = {}
    for h in all_hazards:
        t = _hazard_label(h.get("hazard_type", "terrain_anomaly"))
        type_counts[t] = type_counts.get(t, 0) + 1

    fig = go.Figure(data=[go.Bar(
        x=list(type_counts.keys()),
        y=list(type_counts.values()),
        marker_color=COLORS["primary"],
    )])
    fig.update_layout(
        title="Hazards by Type", template="plotly_dark", height=250,
        margin=dict(l=50, r=20, t=40, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    if critical:
        st.markdown("#### Critical Hazards")
        for h in critical:
            label = _hazard_label(h.get("hazard_type", "terrain_anomaly"))
            st.markdown(
                f"- **{label}** (severity {h.get('severity')}/5) "
                f"in `{h.get('frame_id', '?')}` — {h.get('description', '')}"
            )


# ---------------------------------------------------------------------------
# Landing recommendations
# ---------------------------------------------------------------------------
def recommendations_panel(recommendations: list[dict], frames_dir: Path) -> None:
    if not recommendations:
        st.info("No recommendations available yet.")
        return

    for rec in recommendations[:5]:
        verdict = rec.get("go_no_go", "?")
        color = COLORS.get(verdict, COLORS["muted"])
        score = rec.get("composite_score", 0)

        st.markdown(f"""
<div style='border-left: 4px solid {color}; padding: 0.75rem 1rem; margin-bottom: 0.5rem;
     background: {COLORS["bg_card"]}; border-radius: 0 8px 8px 0;'>
<strong style='font-size:1.1em'>#{rec.get('rank', '?')} — {rec.get('frame_id', '?')}</strong>
<span style='float:right;color:{color};font-weight:bold;font-size:1.2em'>{verdict}</span>
<br/>
<span style='color:{COLORS["muted"]}'>
  Composite: <b>{score:.1f}</b> &nbsp;|&nbsp;
  Safety: {rec.get('surface_safety_score', 0):.0f} &nbsp;|&nbsp;
  Fuel: {rec.get('fuel_cost_score', 0):.0f} &nbsp;|&nbsp;
  Nav: {rec.get('nav_confidence_score', 0):.0f}
</span>
<br/>
<span style='color:{COLORS["text"]}'>{rec.get('reasoning', '')}</span>
</div>
""", unsafe_allow_html=True)

        frame_path = _resolve_frame(frames_dir, rec.get("frame_id", ""))
        if frame_path and frame_path.exists() and rec.get("rank", 99) <= 3:
            st.image(str(frame_path), width=400, caption=f"Rank #{rec['rank']} — {rec['frame_id']}")


# ---------------------------------------------------------------------------
# Mission metrics
# ---------------------------------------------------------------------------
def mission_metrics(report: dict) -> None:
    telem = report.get("telemetry_summary", {})
    recs = report.get("recommendations", [])
    best = recs[0] if recs else {}

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Frames Analyzed", report.get("key_frames_analyzed", 0))
    c2.metric("Start Altitude", f"{telem.get('start_altitude_m', 0):,.0f} m")
    c3.metric("End Altitude", f"{telem.get('end_altitude_m', 0):,.0f} m")
    c4.metric("Fuel Remaining", f"{telem.get('fuel_end_pct', 0):.1f}%")
    c5.metric("Best Site", best.get("frame_id", "—"), delta=best.get("go_no_go", ""))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_frame(frames_dir: Path, frame_id: str) -> Optional[Path]:
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        p = frames_dir / f"{frame_id}{ext}"
        if p.exists():
            return p
    return None
