from __future__ import annotations

import os
from pathlib import Path


VLLM_BASE_URL: str = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
COSMOS_MODEL: str = os.getenv("COSMOS_MODEL", "/models/Cosmos-Reason2-8B")

FRAMES_DIR: Path = Path(os.getenv("FRAMES_DIR", "frames"))
TELEMETRY_PATH: Path = Path(os.getenv("TELEMETRY_PATH", "telemetry.jsonl"))
RESULTS_DIR: Path = Path(os.getenv("RESULTS_DIR", "results"))

NUM_KEY_FRAMES: int = int(os.getenv("NUM_KEY_FRAMES", "15"))
MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4096"))
REQUEST_TIMEOUT: float = float(os.getenv("REQUEST_TIMEOUT", "120"))

LUNAR_GRAVITY_MPS2: float = 1.625
EXHAUST_VELOCITY_MPS: float = 3100.0  # typical bipropellant
DRY_MASS_RATIO: float = 0.45  # dry mass / total mass (Artemis-class lander estimate)
