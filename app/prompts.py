"""Structured prompt templates for Cosmos Reason 2 lunar terrain analysis."""

SYSTEM_PROMPT = (
    "You are SELENE, a lunar terrain analysis system aboard a crewed lander. "
    "You analyze descent-camera imagery and telemetry to assess landing sites. "
    "You output ONLY valid JSON after your reasoning. No commentary, no preamble, "
    "no meta-discussion. Do not describe your own process. Focus on what you see "
    "in the image: craters, boulders, slopes, flat zones. Keep all text fields "
    "concise (one sentence max). The summary field must describe the terrain only, "
    "never reference the advisory, fuel, or your own reasoning process."
)

TERRAIN_SURVEY = """\
Descent camera frame at {altitude_m:.0f} m altitude.
Telemetry: descent {vspeed:.1f} m/s, lateral {lspeed:.2f} m/s, fuel {fuel:.1f}%, nav sigma {nav_sigma:.1f} m, dust {dust:.2f}.

Analyze the terrain AND the telemetry:
1. Count craters, classify sizes (small <100m, medium 100-500m, large >500m)
2. Identify boulder fields
3. Assess slopes from shadows
4. Locate flat landing zones
5. Rate suitability 1-10 (1=extremely hazardous, 10=ideal flat mare)
6. Issue mission_advisory based on terrain AND vehicle state:
   - PROCEED: terrain has landing options and fuel > 30%
   - CAUTION: terrain is poor (suitability <= 3) OR fuel 20-30% OR nav sigma > 200m
   - ABORT: fuel < 20%, or fuel < 25% with nav sigma > 150m

The "advisory_reason" must explain WHY you chose that advisory in one sentence.
The "summary" field must describe the TERRAIN ONLY (what you see in the image).
Do NOT mention fuel, advisory, maneuvering, or "proceed" in the summary.

<think>
Describe what you see in the image, then evaluate the telemetry...
</think>

```json
{{
  "crater_count": <int>,
  "crater_sizes": "<small|medium|large|mixed>",
  "boulder_fields": <true|false>,
  "slope_assessment": "<one sentence>",
  "flat_zones": "<positions of flat areas>",
  "suitability_score": <1-10>,
  "mission_advisory": "<PROCEED|CAUTION|ABORT>",
  "advisory_reason": "<one sentence explaining why>",
  "hazards": [
    {{"type": "<crater|boulder_field|steep_slope|ridge|shadow_zone|ejecta>", "severity": <1-5>, "description": "<brief>", "region": "<position>"}}
  ],
  "summary": "<one sentence about the terrain ONLY>"
}}
```"""

HAZARD_ASSESSMENT = """\
Descent camera frame at {altitude_m:.0f} m. Telemetry: descent {vspeed:.1f} m/s, lateral {lspeed:.1f} m/s, fuel {fuel:.1f}%.

List ALL visible hazards. For each: type, severity (1-5), description, region.

<think>
Describe each hazard you see...
</think>

```json
{{
  "hazards": [
    {{"type": "<crater|boulder_field|steep_slope|ridge|shadow_zone|ejecta>", "severity": <1-5>, "description": "<brief>", "region": "<region>"}}
  ],
  "avoidance_feasible": <true|false>,
  "avoidance_reasoning": "<one sentence>"
}}
```"""

LANDING_SITE_COMPARISON = """\
Compare {n} terrain views for landing. Fuel: {fuel:.1f}%.

Rank by: surface roughness, slope, flat zones, risk level.

<think>
Compare the images...
</think>

```json
{{
  "rankings": [
    {{"image_index": <1-based>, "score": <1-10>, "reasoning": "<why>"}}
  ],
  "best_site_summary": "<one sentence>"
}}
```"""
