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
sorter:
  folder_pattern: "{year}/{month:02d}/{day:02d}"
  exif_fallback: true
auth:
  api_key: ""
  header_name: x-api-key
system:
  db_path: /var/lib/media-pipeline/db.sqlite
  log_dir: /var/log/media-pipeline
  port_api: 8080
  port_dbui: 8081
  cleanup_empty_batches: true
```

- `batch.selection_mode` controls whether batches are capped by total size
  (`size`, default) or the number of files selected (`files`).
- `batch.max_size_gb` and `batch.max_files` set the respective limits for the
  chosen selection mode. Set unused limits to `0` to disable the guard.
- `batch.allow_parallel` defaults to `false` so a new batch is only created once
  the previous one has reached `SORTED`. Flip to `true` when your deployment can
  safely process multiple batches concurrently.
- `syncthing.device_id` is optional but recommended when multiple downstream
  devices share a folder. Populate it with the Syncthing device identifier so
  completion polling and diagnostics target the expected peer.
