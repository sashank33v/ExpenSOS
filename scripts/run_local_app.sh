#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PGPORT="${PGPORT:-55432}"
APP_PORT="${PORT:-6969}"

export DATABASE_URL="postgresql://expensos@/expensos?host=$ROOT_DIR/.local_pgsocket&port=$PGPORT"
export SECRET_KEY="${SECRET_KEY:-local-dev-secret}"
export PORT="$APP_PORT"

cd "$ROOT_DIR"
exec "$ROOT_DIR/venv/bin/python" backend/app.py
