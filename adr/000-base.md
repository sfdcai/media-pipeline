# ADR 000: Baseline Decisions

- FastAPI for API (no Docker)
- SQLite + sqlite-web for DB + UI
- YAML config at /etc/media-pipeline/config.yaml
- Modular services: dedup, batch, sync, sort, cleanup
