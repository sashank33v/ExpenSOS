#!/usr/bin/env bash
set -euo pipefail

pkill -f "venv/bin/python backend/app.py" || true
