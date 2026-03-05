# NVIDIA Cosmos Cookoff Submission

> Copy the text below into the [GitHub issue submission form](https://github.com/nvidia-cosmos/cosmos-cookbook/issues/new).

---

## Project Name

**SELENE: Surface Evaluation for Landing and Navigation Engine**

## Team

Alexander Poplavsky (solo)

## Description

SELENE is an autonomous, air-gapped advisory system for lunar landers that uses
NVIDIA Cosmos Reason 2 8B to analyze descent-camera imagery and flight telemetry
in real time, producing frame-by-frame terrain assessments with actionable
mission advisories (PROCEED / CAUTION / ABORT).

### The Problem

During powered descent, crewed lunar landers have ~120 seconds to identify and
avoid terrain hazards. Earth-based guidance is unavailable due to 1.3-second
communication latency. Classical computer vision can detect features but cannot
reason about their implications for landing safety.

### How Cosmos Reason 2 Is Used

Cosmos Reason 2 serves as the core reasoning engine aboard the lander. For each
descent camera frame, the model:

- **Analyzes terrain morphology**: crater counts and sizes, boulder fields,
  slope assessment from shadow geometry, flat landing zone identification
- **Issues mission advisories**: PROCEED/CAUTION/ABORT decisions informed by
  both visual terrain assessment and vehicle telemetry (fuel, navigation
  uncertainty, speed)
- **Provides chain-of-thought reasoning**: human-readable explanations that
  build crew trust in the system's recommendations

The model's physical reasoning capabilities are essential here: it understands
that sharp crater rims with radial ejecta indicate recent impacts with unstable
regolith, that elongated shadows reveal steep slopes, and that scattered bright
spots signal boulder fields. These are judgments classical CV cannot make.

### Two-Layer Safety Architecture

1. **Primary (VLM)**: Cosmos Reason 2 makes the advisory call using terrain +
   telemetry context
2. **Safety Net (Algorithmic)**: Hard-coded telemetry thresholds can only
   escalate (never downgrade) the VLM's decision, ensuring deterministic
   fail-safe behavior

### Key Features

- Real-time progressive analysis with live dashboard updates
- Start/Stop control during descent evaluation
- Terrain classification labels (SAFE TO LAND through HAZARDOUS TERRAIN)
- Colored advisory badges with safety-net override warnings
- Telemetry readouts synchronized with each frame
- Hazard detection with type, severity, and location
- Fuel planning via Tsiolkovsky equation with reachable landing ellipse
- Fully containerized (single `docker compose up`)
- Zero network dependencies after deployment (air-gapped)

### Input Data

140 frames extracted from ISRO's Chandrayaan-3 Lander Imager Camera 1 footage
(August 17, 2023) paired with synthetic descent telemetry simulating PDI from
15,000 m to 5,000 m altitude.

### Impact

SELENE demonstrates how vision-language models can bring human-like physical
reasoning to autonomous systems operating in environments where traditional
approaches fall short. The architecture is transferable to Mars landers,
asteroid proximity operations, underwater vehicle navigation, and any domain
where an AI system must reason about novel terrain under time pressure with
no connectivity.

## Demo Video

[selene_v1.mov on Google Drive](https://drive.google.com/file/d/1DlSiVPs91eT1mwWinxnS40X4QRNC7mHI/view?usp=share_link)

## Code Repository

[github.com/apoplavsky/selene](https://github.com/apoplavsky/selene)

## Tech Stack

- NVIDIA Cosmos Reason 2 8B (vision-language model)
- vLLM (inference engine, OpenAI-compatible API)
- FastAPI (backend)
- Streamlit (dashboard)
- Docker Compose (deployment)
- Python 3.11
