# Media Pipeline

Media Pipeline is a FastAPI-based automation service that synchronizes, sorts, and prepares large photo and video collections for downstream workflows. It coordinates batch creation, Syncthing-powered synchronization, EXIF-aware organization, cleanup routines, and an HTMX dashboard backed by SQLite state.

## Features

- **Configuration Management** – RESTful endpoints for inspecting and updating YAML-driven application configuration.
- **Batch Orchestration** – Deduplicates assets, builds transfer-ready batches, and records manifests for downstream systems.
- **Syncthing Integration** – Triggers rescans, monitors completion, and feeds events into the SQLite journal for traceability.
- **EXIF Sorting & Cleanup** – Groups media into date-based folders and removes stale batches or orphaned files.
- **Operational Dashboard** – HTMX interface summarizing throughput, queue depth, and health indicators in near-real time.

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

## Operating the Pipeline

Once the services are online, the API lives at `http://<host>:8080` and the sqlite-web console at `http://<host>:8081`.

### End-to-end workflow

The orchestrated workflow wires the dedupe → batch → sync → sort pipeline together:

```bash
curl -X POST http://<host>:8080/api/workflow/run \
  -H "Content-Type: application/json" \
  -d '{"force_rescan": true}'
```

Responses include a job identifier that can be polled via `GET /api/workflow/status/{job_id}` (see [`docs/API.md`](docs/API.md)).

### Triggering modules one at a time

Each subsystem can also be invoked independently—handy for incremental processing or debugging specific steps. All examples below assume the API is running and authentication is disabled (the default). Add the header `-H "x-api-key: <token>"` when auth is enabled.

```bash
# 1. Deduplicate the ingestion source
curl -X POST http://<host>:8080/api/dedup/start
curl http://<host>:8080/api/dedup/status

# 2. Build a batch of unique files (adjust max_size_gb in config.yaml for throughput)
curl -X POST http://<host>:8080/api/batch/create
curl http://<host>:8080/api/batch/list

# 3. Kick off Syncthing sync for a batch
curl -X POST http://<host>:8080/api/sync/start/{batch_id}
curl http://<host>:8080/api/sync/status/{batch_id}

# 4. Sort synced files into the archival tree
curl -X POST http://<host>:8080/api/sort/start/{batch_id}
curl http://<host>:8080/api/sort/status/{batch_id}

# 5. Periodic maintenance (log rotation, stale artifacts, temp pruning)
curl -X POST http://<host>:8080/api/cleanup/run
```

Tip: while developing locally you can call these endpoints with the provided `./scripts/debug.sh` to confirm the database schema, log locations, and HTTP health probe responses.

## Configuration

Default configuration values are stored at `/etc/media-pipeline/config.yaml` when installed via the provided scripts. The REST API exposes `GET /api/config` and `PUT /api/config` endpoints for live inspection and updates. Refer to [`docs/CONFIG.md`](docs/CONFIG.md) for the full schema and guidance on overriding paths, deduplication settings, Syncthing credentials, and dashboard options.

## Enhancement Opportunities

We are actively tracking the next improvements for the pipeline:

- **Systemd hardening:** ship dedicated unit files for the API and sqlite-web processes (socket activation, restart policies, log forwarding).
- **Workflow CLI:** expose a command-line helper that can start, monitor, and summarize workflow runs without writing raw `curl` calls.
- **Observability:** emit Prometheus metrics and structured traces so that sync throughput and error rates can be graphed over time.

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
