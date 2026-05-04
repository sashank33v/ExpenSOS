#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PG_BIN_DIR="/usr/lib/postgresql/14/bin"
PGDATA_DIR="$ROOT_DIR/.local_pgdata"
PGSOCKET_DIR="$ROOT_DIR/.local_pgsocket"
PGLOG_FILE="$ROOT_DIR/.local_pg.log"
PGPORT="${PGPORT:-55432}"

mkdir -p "$PGSOCKET_DIR"

if [ ! -d "$PGDATA_DIR" ]; then
  "$PG_BIN_DIR/initdb" -D "$PGDATA_DIR" -U expensos -A trust
fi

if ! PGHOST="$PGSOCKET_DIR" PGPORT="$PGPORT" PGUSER=expensos "$PG_BIN_DIR/pg_isready" >/dev/null 2>&1; then
  "$PG_BIN_DIR/pg_ctl" \
    -D "$PGDATA_DIR" \
    -l "$PGLOG_FILE" \
    -o "-c listen_addresses='' -p $PGPORT -k $PGSOCKET_DIR" \
    start
fi

PGHOST="$PGSOCKET_DIR" PGPORT="$PGPORT" PGUSER=expensos "$PG_BIN_DIR/createdb" expensos 2>/dev/null || true

DATABASE_URL="postgresql://expensos@/expensos?host=$PGSOCKET_DIR&port=$PGPORT" \
  "$ROOT_DIR/venv/bin/python" -c "from backend.database import init_db; init_db(); print('Local database ready.')"
