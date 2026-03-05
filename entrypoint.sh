#!/bin/sh
set -e

uvicorn app.main:app --host 0.0.0.0 --port 8080 &

streamlit run ui/dashboard.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.headless true \
  --browser.gatherUsageStats false

wait
