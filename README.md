# Media Pipeline

Media Pipeline is a FastAPI-based automation service that synchronizes, sorts, and prepares large photo and video collections for downstream workflows. It coordinates batch creation, Syncthing-powered synchronization, EXIF-aware organization, cleanup routines, and an HTMX dashboard backed by SQLite state.

## Features

- **Configuration Management** – RESTful endpoints for inspecting and updating YAML-driven application configuration.
- **Batch Orchestration** – Deduplicates assets, builds transfer-ready batches, and records manifests for downstream systems.
- **Centralized Configuration** – A single config snapshot powers the API, CLI, and UI; updates through `/api/config` hot-reload the service container without restarts.
- **Syncthing Integration** – Triggers rescans, monitors completion, and feeds events into the SQLite journal for traceability.
- **EXIF Sorting & Cleanup** – Groups media into date-based folders and removes stale batches or orphaned files.
- **Operational Dashboard & Control Center** – HTMX dashboard plus a lightweight control UI for editing config, launching runs, reviewing workflow history, and visualizing live progress with charts, progress bars, and headline metrics.

## Architecture Overview

The service is composed of modular building blocks that share a common service container:

- **`utils/service_container.py`** wires together the SQLite database manager, Syncthing client, and the core modules using the active configuration (from `/etc/media-pipeline/config.yaml` by default).
- **Dedup module (`modules/dedup.py`)** scans the ingestion directory, hashes files, and labels duplicates so they can be excluded from batching.
- **Batch module (`modules/batch.py`)** selects unique files according to either a size budget or a file-count limit, moves them into `batch_dir`, and records both a manifest and the `batch_id`/`batch_name` pair used throughout the pipeline. By default the service blocks new batches until the prior one has been synced and sorted, matching a single Syncthing folder deployment.
- **Sync monitor (`modules/sync_monitor.py`)** coordinates with Syncthing to rescan the batch folder, polls completion, and marks database records as synced.
- **Sorter (`modules/exif_sorter.py`)** reads EXIF data (with filesystem timestamps as a fallback) and files them into the archival tree.
- **Cleanup (`modules/cleanup.py`)** prunes empty batch directories, old temp files, and rotates log files as needed.
- **Workflow orchestrator (`modules/workflow.py`)** stitches the modules together, exposing both a REST API (`/api/workflow/*`) and a menu-driven CLI (`scripts/workflow.py`).
- **UI templates (`templates/dashboard.html` & `templates/control.html`)** provide a quick operational overview and a control center for day-to-day tasks.

Each component is independently testable and can be invoked either from the API, the CLI helper, or the control center UI.

## Getting Started

### Automated Provisioning (recommended)

Fresh machines can be bootstrapped end-to-end with the bundled shell scripts. Run the following commands in order:

```bash
# 1. Install system dependencies, download the release bundle, and create /opt/media-pipeline
curl -fsSL https://raw.githubusercontent.com/sfdcai/media-pipeline/main/scripts/install.sh | bash

# 2. Ensure configuration, database schema, and service scaffolding are in place
sudo /opt/media-pipeline/scripts/setup.sh

# 3. Launch the API and SQLite web UI (backgrounded via run.sh)
sudo /opt/media-pipeline/scripts/run.sh
```

The installer detects the host package manager (APT, DNF/YUM, Homebrew) and may prompt for elevated privileges while installing prerequisites. Both `install.sh` and `setup.sh` now provision Syncthing alongside Python tooling, copy `config/default_config.yaml` into `/etc/media-pipeline/config.yaml` when needed, initialize `/var/lib/media-pipeline/db.sqlite`, and build an isolated virtual environment at `/opt/media-pipeline/.venv`. During setup we also create `/opt/media-pipeline/run` for PID tracking, ensure log and manifest directories exist, and enable the `syncthing@<user>` systemd service when `systemctl` is available. A dedicated `configure_syncthing.py` helper runs automatically so the Syncthing GUI/API bind to `0.0.0.0:8384` and the sync listeners open on `0.0.0.0:22000`, addressing the localhost-only behaviour highlighted in recent debug captures.

The refreshed `run.sh` script reads port and log settings directly from `config.yaml`, kills any previously launched uvicorn/sqlite-web processes via PID files, and relaunches them with logs written to the configured `system.log_dir` (falling back to `/opt/media-pipeline/data/logs`). Companion helpers `stop.sh` and `restart.sh` live alongside `run.sh` for quick lifecycle management:

```bash
sudo /opt/media-pipeline/scripts/stop.sh     # Gracefully stop background services
sudo /opt/media-pipeline/scripts/run.sh      # Start services (respects MEDIA_PIPELINE_CONFIG)
sudo /opt/media-pipeline/scripts/restart.sh  # Stop + start in one step
```

Use `restart.sh` (or `sudo systemctl restart media-pipeline` when using the generated unit file) after deploying new code so the API picks up the latest changes.

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

# API server (respect configured port; add --reload for hot reloading)
uvicorn main:app --host 0.0.0.0 --port 8080

# SQLite web UI (DB browser)
sqlite_web /var/lib/media-pipeline/db.sqlite --host 0.0.0.0 --port 8081
```

The helper scripts default to the ports defined under `system.port_api` and `system.port_dbui` in `config.yaml`. Backgrounded processes started via `run.sh` emit logs to the configured `system.log_dir` (for example `/var/log/media-pipeline/api.log` and `dbui.log`). Set `UVICORN_RELOAD=1` before calling `run.sh` when you want code changes to auto-reload during development.

### Interactive Control Center

Navigate to `http://<host>:8080/control` to open the new operations console. The page allows you to:

- Inspect and edit `config.yaml` in-place with validation feedback.
- Trigger the full workflow or individual modules (dedup, batch, sync, sort, cleanup).
- Select the target batch by ID for sync/sort actions and review the last five batches at a glance.
- Track the *Active Sync Progress* panel to see every batch still marked as `SYNCING`, complete with progress bars and the most recent Syncthing detail message.
- Fire the **Refresh Sync Progress** button to poll Syncthing on-demand whenever batches appear stuck.
- Monitor dedup status, aggregated file counts, and the results of the most recent workflow run without refreshing.
- Jump straight to the `/dashboard` view for sparkline charts, progress bars, storage usage, and recent batch summaries.
- Launch quick links to the dashboard, sqlite-web DB UI, API docs, or copy the effective config path for terminal work.
- Copy fully-qualified URLs for `/dashboard`, `/control`, and the sqlite-web DB UI—handy when operating across subnets.
- Run one-click Syncthing diagnostics (including REST status checks) and open the Syncthing UI directly from the control page.

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

# 3. Kick off Syncthing sync for a batch (replace BATCH_ID)
curl -X POST http://<host>:8080/api/workflow/sync/BATCH_ID
curl http://<host>:8080/api/sync/status/BATCH_ID

# 4. Sort synced files into the archival tree
curl -X POST http://<host>:8080/api/workflow/sort/BATCH_ID
curl http://<host>:8080/api/sort/status/BATCH_ID

# 5. Periodic maintenance (log rotation, stale artifacts, temp pruning)
curl -X POST http://<host>:8080/api/cleanup/run
```

> **Troubleshooting Syncthing:** The sync endpoints forward requests to the
> Syncthing REST API using the `syncthing.api_url`, `syncthing.api_key`,
> `syncthing.folder_id`, and optional `syncthing.device_id` values from the
> active configuration. If the service logs `Syncthing request failed (403
> Forbidden - unauthorized…)` ensure the API key matches the value shown in the
> Syncthing GUI and that the Media Pipeline host appears under **Settings →
> Advanced → GUI → API Key / Allowed Networks**. When a folder id is supplied the
> rescan call targets `/rest/db/scan` with the batch directory as a relative
> sub-directory; without it the workflow falls back to the legacy absolute path
> scan. Setting `syncthing.device_id` ensures completion polling focuses on the
> intended downstream peer.
>
> For deeper debugging, run `./scripts/debug.sh` to capture the active config
> path, direct control/dashboard/sqlite-web URLs, Syncthing REST/UI addresses,
> API key metadata, and live `/system/status` **and** `/db/completion` payloads.
> The control center's **Syncthing Diagnostics** panel and the
> `/api/sync/diagnostics` endpoint expose the same information over HTTP,
> including the last error seen by the sync monitor. Both surfaces help confirm
> that the API key is in use, the folder ID/device ID are correct, and that the
> Syncthing instance is reachable from the pipeline host.

Tip: while developing locally you can call these endpoints with the provided `./scripts/debug.sh` to confirm the database schema, log locations, and HTTP health probe responses.

### Syncthing accessibility tweaks

If you need to reapply the Syncthing listener changes (for example after a manual edit of `config.xml`) run:

```bash
/opt/media-pipeline/.venv/bin/python /opt/media-pipeline/scripts/configure_syncthing.py
```

Use `--config` to point at a custom `config.xml`. The tool reports the effective GUI address and all listener sockets; the setup
and install scripts call it automatically and restart `syncthing@<user>` so new bindings take effect immediately.

## Configuration

Default configuration values are stored at `/etc/media-pipeline/config.yaml` when installed via the provided scripts. The REST API exposes `GET /api/config` and `PUT /api/config` endpoints for live inspection and updates. Whenever `/api/config` persists changes, the server rebuilds its service container so every module immediately reads the updated settings—there is only a single authoritative configuration snapshot in memory.

Key batch-related settings:

- `batch.selection_mode` – Choose `size` (default) to limit batches by gigabytes or `files` to cap by file count.
- `batch.max_size_gb` / `batch.max_files` – Respectively control the size threshold and the maximum files selected when the corresponding mode is active.
- `batch.allow_parallel` – When `false` (default), `BatchService` refuses to start a new batch while another remains `PENDING`, `SYNCING`, `SYNCED`, `SORTING`, or `ERROR`. Set to `true` only when Syncthing watches multiple destinations and concurrent batches are acceptable.

Refer to [`docs/CONFIG.md`](docs/CONFIG.md) for the full schema and guidance on overriding paths, deduplication settings, Syncthing credentials, and dashboard options.

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

The script prints platform details, verifies Python and dependency versions, checks the SQLite schema, inspects recent log files, lists shareable Web UI URLs, and exercises health endpoints alongside Syncthing status/completion checks. Its output can be attached to support requests or issue reports.

## Release Automation

A GitHub Actions workflow automatically packages and publishes a release every time a pull request merges into `main`. Each release includes a compressed snapshot of the repository, which the installer consumes when provisioning new machines. Manual downloads are also available on the [Releases](https://github.com/sfdcai/media-pipeline/releases) page.

## Contributing

1. Fork the repository and create a feature branch.
2. Install development dependencies (`pip install -r requirements.txt`).
3. Run the test suite (`pytest`) before submitting changes.
4. Open a pull request describing the enhancement or fix.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
