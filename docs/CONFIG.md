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
dedup:
  hash_algorithm: sha256
  threads: 4
  move_duplicates: true
syncthing:
  api_url: http://127.0.0.1:8384/rest
  api_key: ""
  folder_id: ""
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
