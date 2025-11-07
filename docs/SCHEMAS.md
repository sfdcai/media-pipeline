# Schemas

## Enums
- File: NEW | UNIQUE | DUPLICATE | BATCHED | SYNCED | SORTED | ARCHIVED | ERROR
- Batch: PENDING | IN_PROGRESS | SYNCING | SYNCED | SORTING | SORTED | ERROR

## Tables
- files(path, size, sha256, exif_datetime, ctime, mtime, status, batch_id, target_path, error)
- batches(id, name, size_bytes, file_count, status, created_at, synced_at, sorted_at, manifest_path)
- events(ts, module, level, message, context)
- config_changes(ts, key, old_value, new_value, actor)

## API Types
See endpoints in API.md.
