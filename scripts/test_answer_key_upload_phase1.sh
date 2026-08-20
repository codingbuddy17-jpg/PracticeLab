#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

PYTHONPATH=tests ../.venv/bin/pytest \
  tests/test_answer_key_upload_phase1.py \
  tests/test_key_upload_hazards.py \
  tests/test_template_compatibility.py \
  -q
