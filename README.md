# SELENE: Surface Evaluation for Landing and Navigation Engine

An autonomous, air-gapped advisory system for lunar landers powered by
**NVIDIA Cosmos Reason 2 8B**.

Built for the [NVIDIA Cosmos Cookoff 2026](https://github.com/orgs/nvidia-cosmos/discussions/4).

![Python 3.11](https://img.shields.io/badge/python-3.11-blue)
![Docker](https://img.shields.io/badge/docker-compose-blue)
![Cosmos Reason 2](https://img.shields.io/badge/NVIDIA-Cosmos_Reason_2-green)

---

## The Problem

Future crewed lunar missions (Artemis, CLPS, and commercial landers) face a
critical gap during powered descent: **real-time landing site assessment with no
Earth-based assistance.** Communication latency to the Moon is 1.3 seconds each
way, far too slow for the final minutes of descent where terrain hazards must be
identified and avoided in real time.

Existing hazard detection relies on pre-mapped terrain databases and classical
computer vision (edge detection, texture analysis). These approaches cannot
**reason** about novel terrain features or combine visual evidence with vehicle
state to produce actionable crew advisories.

## The Solution

SELENE is an **independent decision-support system** designed to run entirely
onboard (no internet required). It processes descent-camera video frames and
flight telemetry through NVIDIA Cosmos Reason 2 to produce frame-by-frame
terrain assessments with mission advisories (PROCEED / CAUTION / ABORT).

**This is not an autopilot.** SELENE advises; the crew decides.

### How Cosmos Reason 2 Is Used

Cosmos Reason 2 is the core reasoning engine. For each descent camera frame,
the model:

1. **Analyzes terrain morphology** by counting craters, classifying sizes,
   detecting boulder fields, assessing slopes from shadow geometry, and
   locating flat landing zones
2. **Issues a mission advisory** (PROCEED / CAUTION / ABORT) based on both
   the visual terrain assessment and telemetry data (fuel level, navigation
   uncertainty, speed)
3. **Explains its reasoning** via chain-of-thought traces, providing
   human-readable justification critical for crew trust

Classical CV can detect a crater rim. Cosmos Reason 2 can tell you that the
sharp rim and radial ejecta streaks mean a recent impact with loose, unstable
regolith underneath, making it unsuitable despite appearing flat from a distance.

### Two-Layer Advisory Architecture

SELENE implements a dual-layer safety design:

- **Layer 1 (VLM):** Cosmos Reason 2 makes the primary advisory call, combining
  what it sees in the image with fuel/nav/speed telemetry
- **Layer 2 (Algorithmic Safety Net):** Hard-coded telemetry thresholds act as a
  backup that can only **escalate** (never downgrade) the VLM's decision.
  If the model says PROCEED but fuel is at 18%, the safety net overrides to ABORT.

This ensures intelligent, nuanced primary judgment with deterministic fail-safe
guarantees.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                Docker Compose Stack                  │
│                                                      │
│  ┌─────────────────────┐   ┌───────────────────────┐ │
│  │   vLLM Service      │   │   App Service         │ │
│  │                     │   │                       │ │
│  │  Cosmos Reason 2 8B │◄──│  FastAPI Backend      | │ 
│  │  OpenAI-compat API  │   │  Streamlit Dashboard  │ │
│  │  port 8000          │──►│  Analysis Pipeline    │ │
│  │                     │   │                       │ │
│  └─────────────────────┘   └───────────────────────┘ │
│         ▲                           ▲                │
│         │                           │                │
└─────────│───────────────────────────│────────────────┘
          │                           │
   Model weights             frames/ + telemetry.jsonl
   (volume mount)             (volume mounts)
```

### Pipeline Stages

1. **Ingest** — Load descent-camera frames and paired telemetry
2. **Key-frame selection** — Pick N evenly spaced frames across the descent
3. **Terrain survey** — Cosmos R2 analyzes each frame: craters, boulders,
   slopes, flat zones, suitability score (1-10)
4. **Mission advisory** — VLM issues PROCEED/CAUTION/ABORT per frame;
   algorithmic safety net validates against telemetry thresholds
5. **Comparative ranking** — Top candidate frames sent for side-by-side
   comparison
6. **Scoring** — Composite score = 50% surface safety + 30% fuel margin +
   20% navigation confidence
7. **Live dashboard** — Real-time Streamlit UI shows progressive frame
   analysis, telemetry readouts, and evaluation log

## Features

- **Real-time progressive analysis**: frames analyzed one-by-one with live
  dashboard updates; no waiting for the full batch
- **Start/Stop control**: begin or halt evaluation at any time
- **Terrain classification**: per-frame labels (SAFE TO LAND, LANDABLE,
  ROUGH SURFACE, UNSUITABLE TERRAIN, HAZARDOUS TERRAIN) with color coding
- **Advisory badges**: colored PROCEED/CAUTION/ABORT indicators with
  algorithmic override warnings when the safety net intervenes
- **Telemetry readouts**: altitude, descent rate, lateral speed, fuel %,
  navigation uncertainty, dust level displayed alongside each frame
- **Evaluation log**: compact scrollable log of all assessed frames
- **Hazard detection**: per-frame hazard inventory with type, severity,
  and location
- **Fuel planning**: delta-v budgets via Tsiolkovsky equation, reachable
  landing ellipse computation
- **Fully containerized**: single `docker compose up` to deploy
- **Air-gapped**: zero network dependencies after model download

## Quick Start

### Prerequisites

- Docker with NVIDIA GPU support ([nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html))
- GPU with >= 32 GB VRAM (A100, L40S, H100, or equivalent)
- ~16 GB disk for model weights

### 1. Download Cosmos Reason 2 8B

```bash
pip install huggingface_hub
huggingface-cli download nvidia/Cosmos-Reason2-8B \
  --local-dir ./Cosmos-Reason2-8B
```

### 2. Launch

```bash
docker compose up --build
```

The vLLM server takes ~2 minutes to load the model. Once healthy:

| Service    | URL                        |
|------------|----------------------------|
| Dashboard  | http://localhost:8501      |
| API docs   | http://localhost:8080/docs |

### 3. Run Analysis

Open the dashboard and click **Start** in the sidebar. The system will
progressively analyze key frames and display results in real time.

Or via API:

```bash
curl -X POST "http://localhost:8080/analyze?num_key_frames=15"
```

### 4. Local Development (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start vLLM separately (needs GPU):
vllm serve ./Cosmos-Reason2-8B \
  --reasoning-parser qwen3 --max-model-len 8192 --port 8000

# API server
uvicorn app.main:app --port 8080 &

# Dashboard
streamlit run ui/dashboard.py --server.port 8501
```

## Project Structure

```
├── docker-compose.yml          # Two services: vllm + app
├── Dockerfile.app              # Python application container
├── entrypoint.sh               # Starts FastAPI + Streamlit
├── requirements.txt            # Python dependencies
├── frames/                     # Chandrayaan-3 descent camera frames
├── telemetry.jsonl             # Synthetic flight telemetry
├── app/
│   ├── config.py               # Environment-based settings
│   ├── models.py               # Pydantic schemas (telemetry, hazards, analysis)
│   ├── cosmos_client.py        # Async OpenAI-compatible client for Cosmos R2
│   ├── prompts.py              # Structured prompt templates (survey, hazard, comparison)
│   ├── terrain_analyzer.py     # Frame analysis + advisory logic + sanitization
│   ├── hazard_detector.py      # Hazard aggregation and scoring
│   ├── fuel_planner.py         # Tsiolkovsky-based delta-v and reachability
│   ├── pipeline.py             # End-to-end orchestration with progress tracking
│   ├── telemetry_loader.py     # JSONL parser with derived fields
│   └── main.py                 # FastAPI endpoints (analyze, stop, status, results)
└── ui/
    ├── dashboard.py            # Streamlit main application
    └── components.py           # Reusable UI components (cards, badges, telemetry)
```

## Input Data

### Descent Camera Frames

140 PNG frames extracted from the **Chandrayaan-3** Lander Imager Camera 1
footage, captured during the lunar descent on August 17, 2023. The imagery
shows the lunar surface with craters, ridges, ejecta patterns, and maria at
varying scales during approach.

**Source:** Indian Space Research Organisation (ISRO),
[Chandrayaan-3 Mission: The moon, as seen by Lander Imager Camera 1](https://www.isro.gov.in/Ch3_Moon_VideoBy_Lander_Imager_Camera1.html).
This data is publicly released by ISRO for educational and research purposes.

### Telemetry

Synthetic telemetry simulating a powered descent from ~15,000 m (PDI) to
~5,000 m altitude. Each data point includes:

| Field | Description |
|-------|-------------|
| `altitude_m` | Current altitude above surface |
| `vertical_speed_down_mps` | Descent rate |
| `lateral_speed_mps` | Cross-track velocity |
| `fuel_pct` | Remaining propellant percentage |
| `dust_level_0to1` | Dust obscuration factor |
| `nav_pos_sigma_m` | Navigation position uncertainty |

The pipeline derives additional fields: `time_to_ground_s`,
`fuel_at_landing_pct`, and `reachable_radius_km`.

## Technical Details

### Prompt Engineering

Three structured prompt types extract different aspects of terrain analysis:

- **TERRAIN_SURVEY**: Comprehensive per-frame analysis with terrain
  classification, hazard inventory, and mission advisory. The model receives
  full telemetry context and applies defined thresholds for advisory decisions.
- **HAZARD_ASSESSMENT**: Focused hazard identification with severity ratings
  (1-5) and frame-region locations, plus avoidance feasibility.
- **LANDING_SITE_COMPARISON**: Multi-image comparative ranking of top
  candidate sites.

All prompts use `<think>` reasoning traces for structured chain-of-thought,
enabling both machine-parseable JSON output and human-readable explanations.

### Scoring Model

Each candidate site receives a composite score (0-100):

```
composite = 0.50 x surface_safety + 0.30 x fuel_margin + 0.20 x nav_confidence
```

- **Surface safety** (0-100): VLM suitability score scaled, minus hazard penalties
- **Fuel margin** (0-100): Ratio of available delta-v to required braking delta-v
- **Nav confidence** (0-100): Inverse of navigation position uncertainty

### Advisory Thresholds

| Advisory | VLM Criteria | Safety Net Override |
|----------|-------------|---------------------|
| PROCEED  | Terrain has landing options, fuel > 30% | (no override) |
| CAUTION  | Poor terrain (suitability <= 3), fuel 20-30%, or nav sigma > 200m | Fuel < 30%, nav > 200m, or lateral speed > 25 m/s |
| ABORT    | Fuel < 20%, or fuel < 25% with nav sigma > 150m | Fuel < 20%, or fuel < 25% + nav > 150m |

The safety net can only escalate, never downgrade the VLM's decision.

## Acknowledgments

- **NVIDIA** for [Cosmos Reason 2](https://github.com/nvidia-cosmos/cosmos-reason2)
  and the [Cosmos Cookbook](https://nvidia-cosmos.github.io/cosmos-cookbook/)
- **ISRO** for the publicly released
  [Chandrayaan-3 Lander Imager Camera 1 footage](https://www.isro.gov.in/Ch3_Moon_VideoBy_Lander_Imager_Camera1.html)
  used as input data
- **vLLM** project for the high-performance inference engine

## License

MIT License. See [LICENSE](LICENSE) for details.
