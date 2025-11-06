#!/usr/bin/env bash
set -euo pipefail

PROJECT_REPO="sfdcai/media-pipeline"
INSTALL_DIR="/opt/media-pipeline"
PYTHON_BIN="python3"
VENV_DIR="$INSTALL_DIR/.venv"
RELEASE_CHANNEL="latest"
OWNER_USER="${SUDO_USER:-$USER}"
OWNER_GROUP="$(id -gn "$OWNER_USER" 2>/dev/null || id -gn)"

usage() {
  cat <<USAGE
Media Pipeline installer

Usage: install.sh [options]

Options:
  --install-dir DIR     Target directory for the application (default: /opt/media-pipeline)
  --channel NAME        Release channel to install (default: latest)
  --python PATH         Python interpreter to use (default: python3)
  -h, --help            Show this help message
USAGE
}

log() {
  printf "[install] %s\n" "$1"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command '$1' not found" >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-dir)
      INSTALL_DIR="$2"
      shift 2
      ;;
    --channel)
      RELEASE_CHANNEL="$2"
      shift 2
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

ensure_sudo() {
  if [[ $EUID -ne 0 ]]; then
    if command -v sudo >/dev/null 2>&1; then
      echo sudo
    else
      echo "This script requires elevated privileges (sudo)." >&2
      exit 1
    fi
  else
    echo ""
  fi
}

install_packages() {
  local sudo_cmd
  sudo_cmd=$(ensure_sudo)

  if [[ "$(uname -s)" == "Darwin" ]]; then
    log "Detected macOS"
    if ! command -v brew >/dev/null 2>&1; then
      echo "Homebrew is required but not installed. Install Homebrew first from https://brew.sh/." >&2
      exit 1
    fi
    brew update
    brew install python git sqlite curl unzip || true
    return
  fi

  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    case "$ID" in
      ubuntu|debian)
        log "Detected Debian/Ubuntu"
        $sudo_cmd apt-get update -y
        $sudo_cmd apt-get install -y python3 python3-venv python3-pip git curl unzip sqlite3
        return
        ;;
      centos|rhel|fedora)
        log "Detected RHEL/Fedora"
        local pkgmgr="dnf"
        if ! command -v dnf >/dev/null 2>&1; then
          pkgmgr="yum"
        fi
        $sudo_cmd $pkgmgr install -y python3 python3-venv python3-pip git curl unzip sqlite
        return
        ;;
      arch|manjaro)
        log "Detected Arch Linux"
        $sudo_cmd pacman -Sy --noconfirm python python-pip git curl unzip sqlite
        return
        ;;
    esac
  fi

  echo "Unsupported or undetected operating system. Install dependencies manually." >&2
  exit 1
}

fetch_release() {
  local channel="$1"
  local tmp_dir
  tmp_dir=$(mktemp -d)
  local download_url

  if [[ "$channel" == "latest" ]]; then
    download_url="https://api.github.com/repos/${PROJECT_REPO}/tarball"
  else
    download_url="https://api.github.com/repos/${PROJECT_REPO}/tarball/${channel}"
  fi

  log "Downloading release ($channel)"
  need_cmd curl
  curl -fsSL "$download_url" -o "$tmp_dir/release.tar.gz"
  echo "$tmp_dir"
}

unpack_release() {
  local archive_dir="$1"
  local sudo_cmd
  sudo_cmd=$(ensure_sudo)

  log "Extracting release into $INSTALL_DIR"
  $sudo_cmd mkdir -p "$INSTALL_DIR"
  need_cmd tar
  tar -xzf "$archive_dir/release.tar.gz" -C "$archive_dir"
  local extracted_dir
  extracted_dir=$(find "$archive_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)
  if [[ -d "$INSTALL_DIR" && "$INSTALL_DIR" != "/" ]]; then
    $sudo_cmd rm -rf "$INSTALL_DIR"/*
  fi
  $sudo_cmd cp -a "$extracted_dir"/. "$INSTALL_DIR"/
}

setup_virtualenv() {
  log "Creating virtual environment"
  need_cmd "$PYTHON_BIN"
  $PYTHON_BIN -m venv "$VENV_DIR"
  # shellcheck source=/dev/null
  source "$VENV_DIR/bin/activate"
  pip install --upgrade pip wheel
  pip install -r "$INSTALL_DIR/requirements.txt"
}

post_install() {
  log "Writing default configuration"
  local sudo_cmd
  sudo_cmd=$(ensure_sudo)
  $sudo_cmd mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/data/logs" "$INSTALL_DIR/data/manifests" "$INSTALL_DIR/data/temp"
  $sudo_cmd mkdir -p /var/lib/media-pipeline /var/log/media-pipeline
  $sudo_cmd mkdir -p /etc/media-pipeline
  if [[ ! -f /etc/media-pipeline/config.yaml ]]; then
    $sudo_cmd tee /etc/media-pipeline/config.yaml >/dev/null <<'YAML'
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
  poll_interval_sec: 60
  auto_sort_after_sync: true

sorter:
  folder_pattern: "{year}/{month:02d}/{day:02d}"
  exif_fallback: true

system:
  db_path: /var/lib/media-pipeline/db.sqlite
  log_dir: /var/log/media-pipeline
  port_api: 8080
  port_dbui: 8081
  cleanup_empty_batches: true
YAML
  fi

  $sudo_cmd touch /var/log/media-pipeline/app.log
  $sudo_cmd chown -R "$OWNER_USER":"$OWNER_GROUP" "$INSTALL_DIR" /var/lib/media-pipeline /var/log/media-pipeline

  log "Installer complete"
  cat <<'INFO'
Next steps:
  1. Activate the environment: source $INSTALL_DIR/.venv/bin/activate
  2. Start the API:      uvicorn main:app --host 0.0.0.0 --port 8080
  3. Visit the dashboard at http://localhost:8080/dashboard
INFO
}

main() {
  install_packages
  local tmp_dir
  tmp_dir=$(fetch_release "$RELEASE_CHANNEL")
  unpack_release "$tmp_dir"
  setup_virtualenv
  post_install
  rm -rf "$tmp_dir"
}

main "$@"
