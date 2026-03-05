"""Aggregate and score hazards across frames."""

from __future__ import annotations

from collections import Counter

from app.models import Hazard, HazardType, TerrainAnalysis


def aggregate_hazards(analyses: list[TerrainAnalysis]) -> dict:
    """Summarise hazards across all analysed frames."""
    all_hazards: list[Hazard] = []
    for a in analyses:
        all_hazards.extend(a.hazards)

    type_counts: Counter[HazardType] = Counter()
    max_severity: dict[HazardType, int] = {}
    for h in all_hazards:
        type_counts[h.hazard_type] += 1
        prev = max_severity.get(h.hazard_type, 0)
        max_severity[h.hazard_type] = max(prev, h.severity)

    return {
        "total_hazards": len(all_hazards),
        "by_type": {
            ht.value: {"count": type_counts[ht], "max_severity": max_severity.get(ht, 0)}
            for ht in HazardType
            if type_counts[ht] > 0
        },
        "critical_hazards": [h for h in all_hazards if h.severity >= 4],
    }


def frame_hazard_score(analysis: TerrainAnalysis) -> float:
    """Return a 0-100 safety score (100 = safest) for a single frame.

    Combines suitability_score (from the VLM) with penalty from hazards.
    """
    base = analysis.suitability_score * 10.0  # 10-100

    penalty = 0.0
    for h in analysis.hazards:
        penalty += h.severity * 3.0  # each severity point costs 3

    return max(0.0, min(100.0, base - penalty))
