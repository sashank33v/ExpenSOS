#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PGDATA_DIR="$ROOT_DIR/.local_pgdata"

if [ -d "$PGDATA_DIR" ]; then
  /usr/lib/postgresql/14/bin/pg_ctl -D "$PGDATA_DIR" stop
fi
