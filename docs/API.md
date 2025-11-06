# API

Base URL: `http://<host>:8080`

## Endpoints
- POST /api/dedup/start
- GET  /api/dedup/status
- POST /api/batch/create
- GET  /api/batch/list
- POST /api/sync/start/{batch_id}
- GET  /api/sync/status/{batch_id}
- POST /api/sort/start/{batch_id}
- GET  /api/sort/status/{batch_id}
- POST /api/workflow/run
- GET  /api/config
- PUT  /api/config
- GET  /api/dashboard
- POST /api/cleanup/run
- GET  /dbui  (sqlite-web separate process; see scripts/run.sh)

## Sync

### POST /api/sync/start/{batch_name}

Trigger a Syncthing rescan for the batch directory. Marks the batch status as
`SYNCING` and leaves file entries untouched until the remote completion reaches
100%.

### GET /api/sync/status/{batch_name}

Returns the latest progress percentage retrieved from Syncthing. When the
completion reaches 100% the batch status is updated to `SYNCED` and all related
files are marked `SYNCED`.

## Sort

### POST /api/sort/start/{batch_name}

Moves all synced files for a batch into the configured `sorted_dir` organised by
the folder pattern (default `YYYY/MM/DD`). EXIF capture times are preferred and
the file modification timestamp is used as a fallback when configured.

### GET /api/sort/status/{batch_name}

Reports how many files have been sorted for the batch and exposes the current
batch status (`SORTING` / `SORTED`).

## Cleanup

### POST /api/cleanup/run

Deletes empty batch directories, removes temporary files older than the
configured retention window, and rotates oversized log files. The response lists
paths affected by each action.

## Dashboard

### GET /api/dashboard

Aggregates file totals, per-status breakdowns, batch counts, and directory size
estimates for use by the `/dashboard` HTMX front-end.
