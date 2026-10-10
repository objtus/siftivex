#!/usr/bin/env bash
# C: pixiv tagger → d1 (see docs/plans/tag-stack-migration.md)
# GPU2 tagger, then GPU0 d1. Run from repo root; logs under data/batch/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
LOG="${ROOT}/data/batch"
mkdir -p "$LOG"

echo "=== pixiv tagger (route/pixiv) ==="
echo "Log: ${LOG}/tagger-pixiv.log"
nohup "$PY" scripts/tagger_batch.py --route route/pixiv --commit-every 50 \
  >> "${LOG}/tagger-pixiv.log" 2>&1 &
TAGGER_PID=$!
echo "tagger PID=${TAGGER_PID}"
echo "Wait for tagger to finish, then run d1:"
echo "  ${PY} scripts/d1_batch.py --route route/pixiv --commit-every 10"
echo "Or: tail -f ${LOG}/tagger-pixiv.log"
