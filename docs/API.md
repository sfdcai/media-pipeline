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
- GET  /api/workflow/status
- GET  /api/workflow/overview
- POST /api/workflow/sync/{batch_id}
- POST /api/workflow/sort/{batch_id}
- GET  /api/config
- PUT  /api/config
- GET  /api/dashboard
- POST /api/cleanup/run
- GET  /dbui  (sqlite-web separate process; see scripts/run.sh)

## Workflow

### POST /api/workflow/run

Launch the full dedup → batch → sync → sort pipeline as a background task.
Returns `{ "started": true }` when the workflow begins or `{ "started": false }`
if a previous run is still in progress.

### GET /api/workflow/status

Summarises the state of the asynchronous workflow runner, including whether it
is currently processing and the most recent run summary (if available).

### GET /api/workflow/overview

Convenience endpoint consumed by the control center UI. Returns dedup status,
recent batches, file counts by status, the `running` flag, and the most recent
workflow results.

### POST /api/workflow/sync/{batch_name}

Start a Syncthing sync cycle for the batch and poll completion briefly. Returns
step metadata (`status`, `progress`, `synced_at`, etc.). Skips work when the
batch is already syncing or has reached `SYNCED`.

### POST /api/workflow/sort/{batch_name}

Run the sorter for a batch, returning the number of files moved and files
skipped. Responses mirror the structure used by the CLI/control center.

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
