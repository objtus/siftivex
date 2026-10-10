#!/usr/bin/env bash
# One-time / after venv refresh: GPU ONNX for cl_tagger (see docs/setup/gpu-workloads.md)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"
PIP="${ROOT}/.venv/bin/pip"

"${PIP}" uninstall -y onnxruntime 2>/dev/null || true
"${PIP}" install -U 'onnxruntime-gpu>=1.19.0'

echo "Providers:"
"${PY}" -c "
import sys
sys.path.insert(0, '${ROOT}/src')
from siftivex.gpu_env import configure_nvidia_libs
configure_nvidia_libs()
import onnxruntime as ort
print(ort.get_available_providers())
"
