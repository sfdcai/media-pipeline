#!/bin/bash
APP_DIR="/opt/media-pipeline"
DB_PATH="/var/lib/media-pipeline/db.sqlite"
PY_ENV="$APP_DIR/.venv"

mkdir -p "$APP_DIR/data/logs"

source "$PY_ENV/bin/activate"

pushd "$APP_DIR" >/dev/null || exit 1

PYTHONPATH="$APP_DIR" nohup "$PY_ENV/bin/uvicorn" main:app --host 0.0.0.0 --port 8080 >"$APP_DIR/data/logs/api.log" 2>&1 &
nohup "$PY_ENV/bin/sqlite_web" "$DB_PATH" --host 0.0.0.0 --port 8081 >"$APP_DIR/data/logs/dbui.log" 2>&1 &

popd >/dev/null

echo "API:     http://<host>:8080"
echo "DB-UI:   http://<host>:8081"
