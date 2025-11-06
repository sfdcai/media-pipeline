#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_TEMPLATE="$PROJECT_ROOT/config/default_config.yaml"
INIT_DB_SCRIPT="$PROJECT_ROOT/scripts/init_db.py"

APP_DIR="/opt/media-pipeline"
PY_ENV="$APP_DIR/.venv"
DB_DIR="/var/lib/media-pipeline"
LOG_DIR="/var/log/media-pipeline"
CONFIG_DIR="/etc/media-pipeline"
DATA_DIR="$APP_DIR/data"

echo "Updating apt and installing dependencies..."
sudo apt update -y
sudo apt install -y python3 python3-venv python3-pip git curl sqlite3 unzip

echo "Creating directories..."
sudo mkdir -p "$APP_DIR" "$DB_DIR" "$LOG_DIR" "$CONFIG_DIR" "$DATA_DIR"/{logs,manifests,temp}
sudo chown -R $USER:$USER "$APP_DIR" "$DB_DIR" "$LOG_DIR" "$CONFIG_DIR" "$DATA_DIR"

if [ ! -f "$APP_DIR/requirements.txt" ]; then
cat > "$APP_DIR/requirements.txt" <<'REQ'
fastapi
uvicorn
pyyaml
sqlite-web
pillow
piexif
aiohttp
rich
black
ruff
REQ
fi

echo "Setting up Python venv..."
python3 -m venv "$PY_ENV"
source "$PY_ENV/bin/activate"
pip install --upgrade pip wheel
pip install -r "$APP_DIR/requirements.txt"

echo "Writing default config (if missing)..."
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
  if [ -f "$CONFIG_TEMPLATE" ]; then
    sudo cp "$CONFIG_TEMPLATE" "$CONFIG_DIR/config.yaml"
  else
    sudo tee "$CONFIG_DIR/config.yaml" >/dev/null <<'YAML'
paths:
  source_dir: /mnt/nas/photos_raw
  duplicates_dir: /mnt/nas/duplicates
  batch_dir: /mnt/nas/syncthing/upload
  sorted_dir: /mnt/nas/photos_sorted
  temp_dir: /opt/media-pipeline/data/temp

batch:
  max_size_gb: 15
  naming_pattern: batch_{index:03d}

dedup:
  hash_algorithm: sha256
  threads: 4
  move_duplicates: true

syncthing:
  api_url: http://127.0.0.1:8384/rest
  api_key: ""
  folder_id: ""
  poll_interval_sec: 60
  auto_sort_after_sync: true

sorter:
  folder_pattern: "{year}/{month:02d}/{day:02d}"
  exif_fallback: true

auth:
  api_key: ""
  header_name: x-api-key

system:
  db_path: /var/lib/media-pipeline/db.sqlite
  log_dir: /var/log/media-pipeline
  port_api: 8080
  port_dbui: 8081
  max_parallel_fs_ops: 4
  cleanup_empty_batches: true
YAML
  fi
fi

echo "Initializing SQLite database..."
DB_FILE="$DB_DIR/db.sqlite"
if [ -x "$PY_ENV/bin/python" ] && [ -f "$INIT_DB_SCRIPT" ]; then
  PYTHONPATH="$PROJECT_ROOT" "$PY_ENV/bin/python" "$INIT_DB_SCRIPT" --config "$CONFIG_DIR/config.yaml"
else
  if [ ! -f "$DB_FILE" ]; then
    sqlite3 "$DB_FILE" <<'SQL'
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE,
    size INTEGER,
    sha256 TEXT,
    exif_datetime TEXT,
    ctime TEXT,
    mtime TEXT,
    status TEXT,
    batch_id INTEGER,
    target_path TEXT,
    error TEXT
);
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    size_bytes INTEGER,
    file_count INTEGER,
    status TEXT,
    created_at TEXT,
    synced_at TEXT,
    sorted_at TEXT,
    manifest_path TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    module TEXT,
    level TEXT,
    message TEXT,
    context TEXT
);
CREATE TABLE IF NOT EXISTS config_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    key TEXT,
    old_value TEXT,
    new_value TEXT,
    actor TEXT
);
SQL
  fi
fi

SERVICE_FILE="/etc/systemd/system/media-pipeline.service"
if [ ! -f "$SERVICE_FILE" ]; then
sudo tee "$SERVICE_FILE" >/dev/null <<EOF
[Unit]
Description=Media Pipeline API Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
ExecStart=$PY_ENV/bin/uvicorn main:app --host 0.0.0.0 --port 8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable media-pipeline
fi

echo "Done. Start with:"
echo "  source $PY_ENV/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8080"
echo "DB UI:"
echo "  sqlite_web /var/lib/media-pipeline/db.sqlite --host 0.0.0.0 --port 8081"
