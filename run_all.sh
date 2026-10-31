#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
export LOKY_MAX_CPU_COUNT=1
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MPLCONFIGDIR="$PWD/.mplconfig"
"$PYTHON" src/run_pipeline.py
