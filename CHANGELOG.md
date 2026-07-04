# Changelog

All notable changes to the Pixel Backup Gang media orchestrator and Android manager.

## [2.2.0] - 2026-07-04

### Added
- **Dynamic Mounting Support**: Integrated Ktor REST API endpoints (`/api/mount`, `/api/unmount`) to dynamically mount and unmount the external USB drive (`/dev/block/sdg1` or similar ext4 partitions) on the Pixel 1.
- **Offline Sync Verification**: Created `/api/verify` endpoint in the Android app to query the local Google Photos SQLite database (`gphotos0.db`) directly. The orchestrator now performs fast, offline verification of backup completeness.
- **ADB File Pushing**: Added ADB-based staging file transfer from the server to the Pixel. The script pushes files to `/data/local/tmp` first, then moves them to the target directory via `su` to bypass application UID permission limitations on external mounts.
- **Exiftool Metadata Gate**: Added comprehensive EXIF metadata preservation verification (`exiftool`) to compare tags (`DateTimeOriginal`, `Make`, `Model`) between original and compressed copies.

### Changed
- **Staging Directory Alignment**: Changed the Pixel Ktor API `/api/stage` output directory from `/mnt/my_drive/_stage` to `/mnt/my_drive/the_binding` to align with the directory bind-mounted to the system Camera roll. This ensures the Android MediaStore immediately index new files.
- **Asynchronous Pipeline Loop**: Moved the uvicorn pipeline engine loop to a dedicated background OS thread (`threading.Thread`) to prevent uvicorn web requests from freezing during synchronous network operations.
- **Native iCloud Uploads**: Updated the iCloud sync upload code to use native `api.photos.upload()` library calls instead of command-line modules, avoiding module execution environment issues.

### Fixed
- **Google Photos Sync Block**: Configured the `/api/stage` handler to clear the `has_upload_permanently_failed = 0` flag in the local Google Photos database and force-restart the app. This unblocks stuck synchronization queue scenarios.
