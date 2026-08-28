#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
# --reload-dir app only: the JSON store writes into data/, and watching that
# directory would restart the server mid-sync every time a receipt is saved.
exec ./.venv/bin/uvicorn app.main:app --reload --reload-dir app --port 8020
