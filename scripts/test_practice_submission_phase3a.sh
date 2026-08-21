#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

PYTHONPATH=tests ../.venv/bin/pytest \
  tests/test_practice_submission_phase3a.py \
  tests/test_manual_key_entry_phase2.py \
  tests/test_auditor_api.py::TestEndToEnd \
  -q
