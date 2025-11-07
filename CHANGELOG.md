# Changelog

## Unreleased
- fix(api): serialize dataclass responses with `asdict` to support slots-based models across cleanup/sort/sync endpoints
- feat(batch): add file-count selection mode, sequential batch guard, and expose skip reasons in API responses
- fix(config): rebuild the FastAPI service container after `/api/config` updates so every module reads a single config snapshot
- docs: describe batch selection options, sequential guardrails, and centralized configuration in README/API/CONFIG
- test: cover file-count batching and the sequential guard in `tests/test_batch.py`
- fix(sync): refresh syncing batches during overview generation and add `/api/workflow/sync/refresh` for manual progress polls
- feat(ui): surface an active sync panel with manual refresh controls and shareable dashboard/control/db-ui URLs in /control
- fix(config): ignore blank MEDIA_PIPELINE_CONFIG overrides when resolving the effective configuration path
- feat(debug): emit web UI links and Syncthing `/db/completion` probes from scripts/debug.sh for faster troubleshooting
- fix(sync): normalize Syncthing completion payloads, track last errors, and honor optional device ids
- feat(sync): expose `/api/sync/diagnostics` for REST-driven troubleshooting and surface detail fields in status responses
- feat(ui): enrich /control with quick links, config helpers, and Syncthing diagnostics tooling
- fix(scripts): export MEDIA_PIPELINE_CONFIG in run.sh and extend debug.sh with Syncthing status checks
- docs: document new diagnostics flow, config path handling, and control center enhancements
- fix(sync): use folder-aware rescans, trim API keys, and surface actionable Syncthing 401/403 guidance
- feat(dashboard): expose completion metrics and recent batches for richer summaries
- fix(dashboard): serialize dataclass payloads without relying on __dict__
- feat(ui): redesign /dashboard with headline cards, charts, and recent batch table
- feat(syncthing): ship configurator CLI and auto-bind GUI/listeners to 0.0.0.0 during setup/install
- fix(debug): detect virtualenvs provisioned under the install directory
- test: cover syncthing configurator idempotency
- fix(db): migrate legacy `batches` tables to include numeric ids for workflow APIs
- fix(api): expose `/config` JSON snapshot for compatibility with legacy tooling
- test: cover the new configuration snapshot endpoint
- feat(run): add config-aware run/stop/restart helpers with PID tracking
- feat(setup): install and enable syncthing during install/setup provisioning
- feat(workflow): propagate batch ids through orchestrator, API, CLI, and tests
- feat(ui): refresh control center with batch selectors, cards, and guidance
- docs: expand README/API with architecture, lifecycle, and batch id usage
- test: update workflow coverage for id-based orchestration
- chore(config): add repository default config template and load-time fallback
- chore(install): bootstrap config and database using shared helper script
- chore(setup): reuse default template and schema helper during manual installs
- feat(scripts): add CLI to initialize the SQLite database schema
- fix(scripts): harden run.sh environment detection and module import path
- docs: expand README with pipeline operations, module-by-module workflows, and enhancement roadmap
- docs: capture upcoming work in prompts/TASKS.md
- feat(workflow): centralize service wiring, add async workflow manager, and expose overview endpoints
- feat(cli): ship menu-driven scripts/workflow.py helper with config override support
- feat(ui): introduce /control operations console with config editor and module triggers
- docs: document new workflow endpoints and interactive controls in README/API
- test: cover orchestrator pipeline logic and workflow API surface

## v0.1.0 (scaffold)
- Repository structure
- Docs
- Setup & run scripts
- FastAPI skeleton
- SQLite schema init

## v0.2.0
- feat(dedup): implement hashing service and API endpoints
- add SQLite manager, config loader, and hashing utilities
- feat(config): add configuration API with YAML persistence and audit logging
- feat(batch): add batch creation service, API endpoint, and tests
- feat(sync): add Syncthing integration, sync API endpoints, and progress polling
- feat(sort): implement EXIF-aware sorter with API and filesystem moves
- feat(cleanup): remove stale artifacts and expose maintenance endpoint
- feat(dashboard): aggregate metrics and ship HTMX dashboard with auth middleware

## v0.3.0
- chore(install): add cross-platform installer that provisions dependencies and deploys release artifacts
- chore(debug): ship diagnostic script for environment, database, and service inspection
- ci(release): publish GitHub Action to create packaged releases after pull request merges
- docs: refresh README with installation, debugging, and automation guidance
