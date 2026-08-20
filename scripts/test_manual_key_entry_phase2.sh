#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"

PYTHONPATH=tests ../.venv/bin/pytest \
  tests/test_manual_key_entry_phase2.py \
  tests/test_answer_key_edit_roundtrip.py \
  tests/test_em_key_visibility.py \
  -q
