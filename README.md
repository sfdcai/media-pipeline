# Media Pipeline

Media Pipeline is a FastAPI-based automation service that synchronizes, sorts, and prepares large photo and video collections for downstream workflows. It coordinates batch creation, Syncthing-powered synchronization, EXIF-aware organization, cleanup routines, and an HTMX dashboard backed by SQLite state.

## Features

- **Configuration Management** – RESTful endpoints for inspecting and updating YAML-driven application configuration.
- **Batch Orchestration** – Deduplicates assets, builds transfer-ready batches, and records manifests for downstream systems.
- **Syncthing Integration** – Triggers rescans, monitors completion, and feeds events into the SQLite journal for traceability.
- **EXIF Sorting & Cleanup** – Groups media into date-based folders and removes stale batches or orphaned files.
- **Operational Dashboard** – HTMX interface summarizing throughput, queue depth, and health indicators in near-real time.

## Getting Started

The easiest way to install Media Pipeline on a fresh host is via the automated installer, which prepares system dependencies, downloads the latest GitHub release, and provisions the Python environment.

```bash
curl -fsSL https://raw.githubusercontent.com/sfdcai/media-pipeline/main/scripts/install.sh | bash
```

> **Note:** The installer detects the local package manager (APT, DNF/YUM, or Homebrew) and may prompt for sudo privileges while installing dependencies.

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

## Configuration

Default configuration values are stored at `/etc/media-pipeline/config.yaml` when installed via the provided scripts. The REST API exposes `GET /api/config` and `PUT /api/config` endpoints for live inspection and updates. Refer to [`docs/CONFIG.md`](docs/CONFIG.md) for the full schema and guidance on overriding paths, deduplication settings, Syncthing credentials, and dashboard options.

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
