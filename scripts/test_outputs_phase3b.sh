#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

PYTHONPATH=tests ../.venv/bin/pytest \
  tests/test_outputs_phase3b.py \
  tests/test_practice_submission_phase3a.py \
  -q
