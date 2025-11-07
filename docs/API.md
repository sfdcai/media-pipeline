# API

Base URL: `http://<host>:8080`

## Endpoints
- POST /api/dedup/start
- GET  /api/dedup/status
- POST /api/batch/create
- GET  /api/batch/list
- POST /api/sync/start/{batch_id}
- GET  /api/sync/status/{batch_id}
- GET  /api/sync/diagnostics
- POST /api/sort/start/{batch_id}
- GET  /api/sort/status/{batch_id}
- POST /api/workflow/run
- GET  /api/workflow/status
- GET  /api/workflow/overview
- POST /api/workflow/sync/{batch_id}
- POST /api/workflow/sync/refresh
- POST /api/workflow/sort/{batch_id}
- GET  /api/config
- PUT  /api/config
- GET  /api/dashboard
- POST /api/cleanup/run
- GET  /dbui  (sqlite-web separate process; see scripts/run.sh)

## Batch

### POST /api/batch/create

Creates a new batch by selecting files according to the configured
`batch.selection_mode`. When set to `size`, files are added until the running
total reaches `batch.max_size_gb`. When set to `files`, the service stops after
`batch.max_files` entries. The endpoint returns the manifest metadata alongside
`created`, `batch_name`, `file_count`, and `size_bytes`.

If `batch.allow_parallel` is `false` (the default) and another batch has not yet
reached `SORTED`, the response includes `{ "created": false, "reason": "...", "blocking_batch": "batch_001", "blocking_batch_id": 1, "blocking_status": "SYNCED" }`. This guards
single-folder Syncthing deployments from generating overlapping batches while
surfacing which batch is blocking progress. When the blocker is already
`SYNCED`, the workflow will automatically attempt to sort it and retry batch
creation. All `blocking_*` fields are omitted when a new batch is created
successfully.

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
workflow results. The payload also exposes `syncing_batches`, a list of
currently syncing batches (id, name, status, progress, `synced_at`, and the most
recent Syncthing error detail) so stalled syncs can be spotted without running
additional API calls.

### POST /api/workflow/sync/{batch_id}

Start a Syncthing sync cycle for the batch (identified by its numeric `batch_id`) and poll completion briefly. Returns
step metadata (`status`, `progress`, `synced_at`, etc.). Skips work when the
batch is already syncing or has reached `SYNCED`. Responses include both the id and the human-readable batch name for clarity.

### POST /api/workflow/sync/refresh

Force the orchestrator to poll Syncthing for every batch currently marked as
`SYNCING`. This is handy when a sync finishes after the initial polling window
and the batch remains stuck in `SYNCING`. The endpoint returns a payload of the
form `{ "count": 1, "batches": [ ... ] }` where each batch entry mirrors the
structure returned by `/api/sync/status/{batch_id}` and also includes the
numeric `batch_id`.

### POST /api/workflow/sort/{batch_id}

Run the sorter for a batch, returning the number of files moved and files
skipped. Responses mirror the structure used by the CLI/control center and include both the batch id and name.

## Sync

### POST /api/sync/start/{batch_id}

Trigger a Syncthing rescan for the batch directory. Marks the batch status as
`SYNCING` and leaves file entries untouched until the remote completion reaches
100%. The id maps to the `batches.id` column; the service resolves the matching
batch name internally. When `syncthing.folder_id` is configured the service
asks Syncthing to rescan that folder with the batch directory as a relative
sub-directory; otherwise it falls back to the legacy absolute path scan. A
`401`/`403` response from Syncthing is surfaced as `Syncthing request failed
(403 Forbidden - unauthorized…)` – double-check the configured API key and that
the Media Pipeline host is present in Syncthing's allowed API clients list.

### GET /api/sync/status/{batch_id}

Returns the latest progress percentage retrieved from Syncthing. When the
completion reaches 100% the batch status is updated to `SYNCED` and all related
files are marked `SYNCED`. Responses include the resolved batch name and, when
available, a `detail` field describing the most recent Syncthing error surfaced
to the sync monitor.

### GET /api/sync/diagnostics

Exposes the currently configured batch directory, Syncthing folder/device IDs,
the last error recorded by the sync monitor, and the raw payload returned by
`/rest/system/status`. The control center uses this endpoint to populate the
Syncthing diagnostics panel; operators can call it directly when verifying API
credentials or network reachability.

## Sort

### POST /api/sort/start/{batch_id}

Moves all synced files for a batch into the configured `sorted_dir` organised by
the folder pattern (default `YYYY/MM/DD`). EXIF capture times are preferred and
the file modification timestamp is used as a fallback when configured. The sorter
resolves the batch name from the provided id prior to processing.

### GET /api/sort/status/{batch_id}

Reports how many files have been sorted for the batch and exposes the current
batch status (`SORTING` / `SORTED`). Responses include both the id and batch
name.

## Cleanup

### POST /api/cleanup/run

Deletes empty batch directories, removes temporary files older than the
configured retention window, and rotates oversized log files. The response lists
paths affected by each action.

## Dashboard

### GET /api/dashboard

Aggregates file totals, per-status breakdowns, batch counts, directory size
estimates, and the latest batch metadata for the `/dashboard` HTMX front-end.

Returns a payload shaped as follows:

```json
{
  "generated_at": "2025-11-07T10:15:00.123456+00:00",
  "files": {
    "total": 42,
    "by_status": {"SORTED": 30, "BATCHED": 8, "DUPLICATE": 4},
    "total_size_bytes": 987654321,
    "completion_percent": 71.4
  },
  "batches": {
    "total": 5,
    "by_status": {"SORTED": 3, "SYNCING": 1, "PENDING": 1},
    "synced": 4,
    "sorted": 3,
    "completion_percent": 60.0
  },
  "storage": {
    "batch_dir_bytes": 123456789,
    "sorted_dir_bytes": 456789123
  },
  "recent_batches": [
    {
      "id": 7,
      "name": "batch_007",
      "status": "SORTED",
      "file_count": 12,
      "size_bytes": 3456789,
      "created_at": "2025-11-06T22:10:00Z",
      "synced_at": "2025-11-06T22:20:00Z",
      "sorted_at": "2025-11-06T22:30:00Z"
    }
  ]
}
```
