#!/usr/bin/env bash
set -euo pipefail

PG_BIN_DIR="/usr/lib/postgresql/14/bin"
PGDATA_DIR="$HOME/.local_pgdata"
PGSOCKET_DIR="$HOME/.local_pgsocket"
PGPORT="55432"

mkdir -p "$PGSOCKET_DIR"

if [ ! -d "$PGDATA_DIR" ]; then
  "$PG_BIN_DIR/initdb" -D "$PGDATA_DIR" -U expensos -A trust
fi

if ! PGHOST=127.0.0.1 PGPORT="$PGPORT" PGUSER=expensos "$PG_BIN_DIR/pg_isready" >/dev/null 2>&1; then
  "$PG_BIN_DIR/pg_ctl" \
    -D "$PGDATA_DIR" \
    -l "$HOME/.local_pg.log" \
    -o "-c listen_addresses='127.0.0.1' -p $PGPORT -k $PGSOCKET_DIR" \
    start
fi

sleep 2
PGHOST=127.0.0.1 PGPORT="$PGPORT" PGUSER=expensos "$PG_BIN_DIR/createdb" expensos 2>/dev/null || true
echo "WSL PostgreSQL is running and listening on 127.0.0.1:55432"
