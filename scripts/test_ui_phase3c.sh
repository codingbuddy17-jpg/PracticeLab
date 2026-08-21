#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

cd "$ROOT_DIR/frontend"
npm run build

cd "$ROOT_DIR/backend"
"$PYTHON_BIN" -m pytest tests/test_frontend_action_contracts_phase3c.py -q
