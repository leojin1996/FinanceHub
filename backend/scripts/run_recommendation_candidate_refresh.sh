#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="${FINANCEHUB_ENV_FILE:-$BACKEND_DIR/.env.local}"

mkdir -p "$BACKEND_DIR/tmp/run-logs"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

export PYTHONPATH="$BACKEND_DIR${PYTHONPATH:+:$PYTHONPATH}"

exec "${PYTHON_BIN:-python3}" "$BACKEND_DIR/scripts/refresh_recommendation_candidate_pool.py" "$@"
