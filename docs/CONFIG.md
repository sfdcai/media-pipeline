# Config

All values in YAML at `/etc/media-pipeline/config.yaml`.

```yaml
paths:
  source_dir: /mnt/nas/photos_raw
  duplicates_dir: /mnt/nas/duplicates
  batch_dir: /mnt/nas/syncthing/upload
  sorted_dir: /mnt/nas/photos_sorted
  temp_dir: /opt/media-pipeline/data/temp
batch:
  max_size_gb: 15
  naming_pattern: batch_{index:03d}
  selection_mode: size
  max_files: 0
  allow_parallel: false
  transfer_mode: move
dedup:
  hash_algorithm: sha256
  threads: 4
  move_duplicates: true
syncthing:
  api_url: http://127.0.0.1:8384/rest
  api_key: ""
  folder_id: ""
  device_id: ""
  poll_interval_sec: 60
  auto_sort_after_sync: true
  rescan_delay_sec: 3
sorter:
  folder_pattern: "{year}/{month:02d}/{day:02d}"
  exif_fallback: true
  transfer_mode: move
auth:
  api_key: ""
  header_name: x-api-key
system:
  db_path: /var/lib/media-pipeline/db.sqlite
  log_dir: /var/log/media-pipeline
  port_api: 8080
  port_dbui: 8081
  cleanup_empty_batches: true
workflow:
  debug:
    enabled: false
    auto_advance: false
    step_timeout_sec: 0
  delays:
    syncthing_settle_sec: 5
    post_sync_sec: 10
  trace:
    syncthing_samples: 25
```

- `batch.selection_mode` controls whether batches are capped by total size
  (`size`, default) or the number of files selected (`files`).
- `batch.max_size_gb` and `batch.max_files` set the respective limits for the
  chosen selection mode. Set unused limits to `0` to disable the guard.
- `batch.allow_parallel` defaults to `false` so a new batch is only created once
  the previous one has reached `SORTED`. Flip to `true` when your deployment can
  safely process multiple batches concurrently.
- `batch.transfer_mode` defaults to `move`. Switch to `copy` to keep the
  originals in the source directory while still staging copies for syncing and
  sorting.
- `syncthing.device_id` is optional but recommended when multiple downstream
  devices share a folder. Populate it with the Syncthing device identifier so
  completion polling and diagnostics target the expected peer.
- `syncthing.rescan_delay_sec` waits before calling the Syncthing rescan API so
  the watcher sees files that were just copied into the folder.
- `sorter.transfer_mode` mirrors the batch option. Choose `copy` if you want to
  retain the synced batch files after they are promoted into the sorted
  structure.
- `workflow.debug.enabled` pauses after every module so operators can inspect
  payloads via the control center before continuing. `auto_advance` resumes
  automatically when paired with `step_timeout_sec`.
- `workflow.delays.syncthing_settle_sec` waits before the first Syncthing rescan
  so the watcher can discover the new batch on disk. `workflow.delays.post_sync_sec`
  adds a configurable idle period after sync completes before sorting begins.
- `workflow.trace.syncthing_samples` caps the number of Syncthing timeline
  snapshots retained per batch. Increase the value to keep a longer history in
  `/api/workflow/status` and the control UI timeline.
