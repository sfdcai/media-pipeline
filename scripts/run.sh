#!/bin/bash
set -euo pipefail

APP_DIR="/opt/media-pipeline"
DB_PATH="/var/lib/media-pipeline/db.sqlite"
PY_ENV="$APP_DIR/.venv"
LOG_DIR="$APP_DIR/data/logs"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Application directory $APP_DIR not found. Have you run install.sh?" >&2
  exit 1
fi

if [[ ! -d "$PY_ENV" ]]; then
  echo "Virtual environment missing at $PY_ENV. Run setup.sh to provision dependencies." >&2
  exit 1
fi

mkdir -p "$LOG_DIR"

# shellcheck disable=SC1091
source "$PY_ENV/bin/activate"

export PYTHONPATH="$APP_DIR:${PYTHONPATH:-}"

pushd "$APP_DIR" >/dev/null || exit 1

nohup "$PY_ENV/bin/uvicorn" --app-dir "$APP_DIR" main:app --host 0.0.0.0 --port 8080 >"$LOG_DIR/api.log" 2>&1 &
nohup "$PY_ENV/bin/sqlite_web" "$DB_PATH" --host 0.0.0.0 --port 8081 >"$LOG_DIR/dbui.log" 2>&1 &

popd >/dev/null

echo "API:     http://<host>:8080"
echo "DB-UI:   http://<host>:8081"
