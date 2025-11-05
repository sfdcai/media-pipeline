#!/bin/bash
APP_DIR="/opt/media-pipeline"
DB_PATH="/var/lib/media-pipeline/db.sqlite"
PY_ENV="$APP_DIR/.venv"

mkdir -p "$APP_DIR/data/logs"

source "$PY_ENV/bin/activate"

nohup uvicorn main:app --host 0.0.0.0 --port 8080 >"$APP_DIR/data/logs/api.log" 2>&1 &
nohup sqlite_web "$DB_PATH" --host 0.0.0.0 --port 8081 >"$APP_DIR/data/logs/dbui.log" 2>&1 &

echo "API:     http://<host>:8080"
echo "DB-UI:   http://<host>:8081"
