# Media Pipeline

Media Pipeline is a FastAPI-based automation service that synchronizes, sorts, and prepares large photo and video collections for downstream workflows. It coordinates batch creation, Syncthing-powered synchronization, EXIF-aware organization, cleanup routines, and an HTMX dashboard backed by SQLite state.

## Features

- **Configuration Management** – RESTful endpoints for inspecting and updating YAML-driven application configuration.
- **Batch Orchestration** – Deduplicates assets, builds transfer-ready batches, and records manifests for downstream systems.
- **Syncthing Integration** – Triggers rescans, monitors completion, and feeds events into the SQLite journal for traceability.
- **EXIF Sorting & Cleanup** – Groups media into date-based folders and removes stale batches or orphaned files.
- **Operational Dashboard & Control Center** – HTMX dashboard plus a lightweight control UI for editing config, launching runs, and reviewing workflow history.

## Getting Started

### Automated Provisioning (recommended)

Fresh machines can be bootstrapped end-to-end with the bundled shell scripts. Run the following commands in order:

```bash
# 1. Install system dependencies, download the release bundle, and create /opt/media-pipeline
curl -fsSL https://raw.githubusercontent.com/sfdcai/media-pipeline/main/scripts/install.sh | bash

# 2. Ensure configuration, database schema, and service scaffolding are in place
sudo /opt/media-pipeline/scripts/setup.sh

# 3. Launch the API and SQLite web UI (backgrounded; logs land in /opt/media-pipeline/data/logs)
sudo /opt/media-pipeline/scripts/run.sh
```

The installer detects the host package manager (APT, DNF/YUM, Homebrew) and may prompt for elevated privileges while installing prerequisites. The setup script copies `config/default_config.yaml` into `/etc/media-pipeline/config.yaml` when no user file exists, initializes `/var/lib/media-pipeline/db.sqlite`, and ensures `/var/log/media-pipeline` plus `/opt/media-pipeline/data/*` directories are present. The run script now validates that `/opt/media-pipeline` and the virtual environment exist, exports the correct `PYTHONPATH`, and tails FastAPI/sqlite-web output into `/opt/media-pipeline/data/logs/api.log` and `/opt/media-pipeline/data/logs/dbui.log` for troubleshooting.

To start the stack after a reboot, rerun `run.sh` (steps 1–2 are only needed when upgrading or reinstalling). Services started manually can be stopped with `pkill -f uvicorn` and `pkill -f sqlite_web` or by terminating the PIDs printed in the respective log files.

### Manual Installation

1. Ensure system prerequisites are available:
   - Python 3.10+
   - `python3-venv`, `pip`, `git`, `curl`, `sqlite3`, `unzip`
2. Clone the repository and enter the project directory:
   ```bash
   git clone https://github.com/sfdcai/media-pipeline.git
   cd media-pipeline
   ```
3. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
4. Launch the API locally:
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8080
   ```

### Starting Processes Individually

If you prefer to manage components yourself, activate the virtual environment created by the installer and start each service explicitly:

```bash
source /opt/media-pipeline/.venv/bin/activate

# API server (logs to stdout)
uvicorn main:app --host 0.0.0.0 --port 8080

# SQLite web UI (DB browser)
sqlite_web /var/lib/media-pipeline/db.sqlite --host 0.0.0.0 --port 8081
```

Backgrounded processes started via `run.sh` emit logs to `/opt/media-pipeline/data/logs/api.log` and `/opt/media-pipeline/data/logs/dbui.log`.

### Interactive Control Center

Navigate to `http://<host>:8080/control` to open the new operations console. The page allows you to:

- Inspect and edit `config.yaml` in-place with validation feedback.
- Trigger the full workflow or individual modules (dedup, batch, sync, sort, cleanup).
- Monitor dedup status, recent batches, aggregated file counts, and the results of the most recent workflow run.

The page refreshes status snapshots automatically every five seconds and surfaces warnings inline when API calls fail.

### Menu-driven Workflow CLI

Operators who prefer the terminal can launch the interactive helper:

```bash
./scripts/workflow.py            # Uses /etc/media-pipeline/config.yaml by default
./scripts/workflow.py --config /path/to/custom.yaml
```

The menu mirrors the control center functionality—run the full pipeline, trigger individual modules, or view an overview without issuing raw HTTP requests. Results are printed step-by-step with structured JSON payloads.

## Operating the Pipeline

Once the services are online, the API lives at `http://<host>:8080` and the sqlite-web console at `http://<host>:8081`.

### End-to-end workflow (API)

To start a background workflow run via HTTP, call:

```bash
curl -X POST http://<host>:8080/api/workflow/run
```

The endpoint responds with `{ "started": true }` when a pipeline begins or `{ "started": false }` if another run is still in-flight. Poll `GET /api/workflow/status` for the latest result snapshot and `GET /api/workflow/overview` for live metrics.

### Triggering modules one at a time (API)

Each subsystem can also be invoked independently—handy for incremental processing or debugging specific steps. All examples below assume the API is running and authentication is disabled (the default). Add the header `-H "x-api-key: <token>"` when auth is enabled.

```bash
# 1. Deduplicate the ingestion source
curl -X POST http://<host>:8080/api/dedup/start
curl http://<host>:8080/api/dedup/status

# 2. Build a batch of unique files (adjust max_size_gb in config.yaml for throughput)
curl -X POST http://<host>:8080/api/batch/create

# 3. Kick off Syncthing sync for a batch (replace BATCH_NAME)
curl -X POST http://<host>:8080/api/workflow/sync/BATCH_NAME
curl http://<host>:8080/api/sync/status/BATCH_NAME

# 4. Sort synced files into the archival tree
curl -X POST http://<host>:8080/api/workflow/sort/BATCH_NAME
curl http://<host>:8080/api/sort/status/BATCH_NAME

# 5. Periodic maintenance (log rotation, stale artifacts, temp pruning)
curl -X POST http://<host>:8080/api/cleanup/run
```

Tip: while developing locally you can call these endpoints with the provided `./scripts/debug.sh` to confirm the database schema, log locations, and HTTP health probe responses.

## Configuration

Default configuration values are stored at `/etc/media-pipeline/config.yaml` when installed via the provided scripts. The REST API exposes `GET /api/config` and `PUT /api/config` endpoints for live inspection and updates. Refer to [`docs/CONFIG.md`](docs/CONFIG.md) for the full schema and guidance on overriding paths, deduplication settings, Syncthing credentials, and dashboard options.

## Enhancement Opportunities

We are actively tracking the next improvements for the pipeline:

- **Systemd hardening:** ship dedicated unit files for the API and sqlite-web processes (socket activation, restart policies, log forwarding).
- **Observability:** emit Prometheus metrics and structured traces so that sync throughput and error rates can be graphed over time.
- **Live log streaming:** surface tail-follow views in the control center to monitor API and worker output in real time.

See [`prompts/TASKS.md`](prompts/TASKS.md) for the detailed task breakdown and status.

## Debugging

Use the bundled debug helper to collect environment diagnostics when investigating issues:

```bash
./scripts/debug.sh
```

The script prints platform details, verifies Python and dependency versions, checks the SQLite schema, inspects recent log files, and exercises health endpoints. Its output can be attached to support requests or issue reports.

## Release Automation

A GitHub Actions workflow automatically packages and publishes a release every time a pull request merges into `main`. Each release includes a compressed snapshot of the repository, which the installer consumes when provisioning new machines. Manual downloads are also available on the [Releases](https://github.com/sfdcai/media-pipeline/releases) page.

## Contributing

1. Fork the repository and create a feature branch.
2. Install development dependencies (`pip install -r requirements.txt`).
3. Run the test suite (`pytest`) before submitting changes.
4. Open a pull request describing the enhancement or fix.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
