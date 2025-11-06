#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_PATH="${MEDIA_PIPELINE_CONFIG:-/etc/media-pipeline/config.yaml}"
DEFAULT_DB="/var/lib/media-pipeline/db.sqlite"
DEFAULT_LOG_DIR="/var/log/media-pipeline"
DB_PATH="${MEDIA_PIPELINE_DB:-$DEFAULT_DB}"
LOG_DIR="${MEDIA_PIPELINE_LOG_DIR:-$DEFAULT_LOG_DIR}"
INSTALL_DIR="${MEDIA_PIPELINE_INSTALL_DIR:-$ROOT_DIR}"
API_URL="${MEDIA_PIPELINE_API_URL:-http://127.0.0.1:8080}"

if [[ -z "${MEDIA_PIPELINE_DB:-}" && -f "$CONFIG_PATH" ]]; then
  conf_db=$(grep -E "^\s*db_path:" "$CONFIG_PATH" | head -n1 | awk -F': ' '{print $2}') || true
  if [[ -n "${conf_db:-}" ]]; then
    DB_PATH="$conf_db"
  fi
fi

if [[ -z "${MEDIA_PIPELINE_LOG_DIR:-}" && -f "$CONFIG_PATH" ]]; then
  conf_log=$(grep -E "^\s*log_dir:" "$CONFIG_PATH" | head -n1 | awk -F': ' '{print $2}') || true
  if [[ -n "${conf_log:-}" ]]; then
    LOG_DIR="$conf_log"
  fi
fi

section() {
  printf '\n========== %s ==========' "$1"
  printf '\n'
}

run_cmd() {
  printf '\n$'
  for arg in "$@"; do
    printf ' %q' "$arg"
  done
  printf '\n'
  "$@"
  local status=$?
  if [[ $status -ne 0 ]]; then
    printf '(command exited with status %s)\n' "$status" >&2
  fi
}

section "Environment"
run_cmd uname -a
if command -v hostnamectl >/dev/null 2>&1; then
  run_cmd hostnamectl
fi
if command -v python3 >/dev/null 2>&1; then
  run_cmd python3 --version
else
  echo "python3 not found on PATH"
fi
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  run_cmd "$ROOT_DIR/.venv/bin/python" --version
fi

section "Filesystem"
printf 'Project root: %s\n' "$ROOT_DIR"
printf 'Install dir:  %s\n' "$INSTALL_DIR"
printf 'Config path:  %s\n' "$CONFIG_PATH"
printf 'DB path:      %s\n' "$DB_PATH"
printf 'Log dir:      %s\n' "$LOG_DIR"

section "Python packages"
if [[ -x "$ROOT_DIR/.venv/bin/pip" ]]; then
  run_cmd "$ROOT_DIR/.venv/bin/pip" list
else
  echo "Virtual environment not detected at $ROOT_DIR/.venv"
fi

section "Configuration snapshot"
if [[ -f "$CONFIG_PATH" ]]; then
  run_cmd sed -n "1,200p" "$CONFIG_PATH"
else
  echo "Config file not found. Override MEDIA_PIPELINE_CONFIG to specify a custom path."
fi

section "Database"
if command -v sqlite3 >/dev/null 2>&1 && [[ -f "$DB_PATH" ]]; then
  run_cmd sqlite3 "$DB_PATH" ".tables"
  run_cmd sqlite3 "$DB_PATH" "SELECT COUNT(*) AS files FROM files;"
  run_cmd sqlite3 "$DB_PATH" "SELECT COUNT(*) AS errors FROM files WHERE error IS NOT NULL AND error != '';"
else
  echo "Database not reachable. Ensure sqlite3 is installed and the DB path is correct."
fi

section "Service status"
if command -v systemctl >/dev/null 2>&1; then
  run_cmd systemctl status media-pipeline
else
  echo "systemctl not available on this host."
fi

section "Recent logs"
if [[ -d "$LOG_DIR" ]]; then
  recent_logs=$(find "$LOG_DIR" -maxdepth 1 -type f -name '*.log' | head -n 5)
  if [[ -n "$recent_logs" ]]; then
    for log_file in $recent_logs; do
      printf '\n--- %s (last 50 lines) ---\n' "$log_file"
      tail -n 50 "$log_file" || true
    done
  else
    echo "No log files found in $LOG_DIR"
  fi
else
  echo "Log directory not found."
fi

section "HTTP health check"
if command -v curl >/dev/null 2>&1; then
  run_cmd curl -fsS "$API_URL/health"
else
  echo "curl not available; skipping API health check."
fi

section "Completed"
printf 'Debug capture finished at %s\n' "$(date --iso-8601=seconds 2>/dev/null || date)"
