# Changelog

## Unreleased
- chore(config): add repository default config template and load-time fallback
- chore(install): bootstrap config and database using shared helper script
- chore(setup): reuse default template and schema helper during manual installs
- feat(scripts): add CLI to initialize the SQLite database schema
- fix(scripts): harden run.sh environment detection and module import path
- docs: expand README with pipeline operations, module-by-module workflows, and enhancement roadmap
- docs: capture upcoming work in prompts/TASKS.md

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
