# 🚀 Pixel 1 OG & Linux Media Lifecycle Pipeline
> **Automated iPhone ↔ iCloud ↔ NAS ↔ Google Photos Unlimited Original Quality Backup & Storage Optimization Architecture**

![Version](https://img.shields.io/badge/Version-v2.2.0-00f0ff?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-00ff88?style=for-the-badge)
![Platform](https://img.shields.io/badge/Platform-Android%20%7C%20Linux%20%7C%20FastAPI%20%7C%20Kotlin-0082ff?style=for-the-badge)

---

## 💡 The Vision & The Problem

High-resolution 4K iPhone videos and photos consume huge amounts of iCloud storage, quickly forcing upgrades to expensive paid cloud plans ($9.99+/month). 

The **Pixel 1 OG (marlin)** features a permanent, lifetime perk granted by Google: **unlimited, full-resolution, original-quality Google Photos backups for life** for any photo or video uploaded directly from the device.

This project connects an iPhone, Linux Home Server, NAS Vault, and rooted Pixel 1 XL into a **self-healing, zero-cost, 24/7 automated media lifecycle pipeline**.

```
                           +-------------------------------------+
                           |            iPhone 15/16             |
                           |   (Heavy 4K Videos & Live Photos)   |
                           +------------------+------------------+
                                              |
                                              v
                           +-------------------------------------+
                           |              iCloud                 |
                           +------------------+------------------+
                                              |
                                              v (1. icloudpd Automated Pull)
+---------------------------------------------------------------------------------------------------+
|                                 LINUX MEDIA ORCHESTRATOR (THE BRAIN)                              |
|                                     FastAPI Web UI :8000 Dashboard                                |
|                                                                                                   |
|  - EXIF Date Organizer   - Metadata Preservation Engine (.meta.json)   - Tiered Compression       |
|  - 3-Gate Deletion Check - Pixel Watchdog & Dynamic ADB Discovery       - Telemetrics & Savings    |
+-----------------------------------+---------------------------------------------------------------+
                                    |                                       |
          (2. Save Originals)       |                                       | (3. Push 100-File Chunks)
                                    v                                       v
        +---------------------------------------+       +---------------------------------------+
        |            NAS STORAGE VAULT          |       |           PIXEL 1 OG (MARLIN)         |
        |         (Sorted/YYYY/MM/DD)           |       |      PixelBackupManager Android App    |
        |        *Permanent Untouched*          |       |          Ktor REST Server :8080       |
        +---------------------------------------+       +-------------------+-------------------+
                                                                            |
                                                                            | (4. Hard Link & Scan)
                                                                            v
                                                        +---------------------------------------+
                                                        |           GOOGLE PHOTOS CLOUD         |
                                                        |    *Free Unlimited Original Backup*   |
                                                        +---------------------------------------+
```

---

## 🛠️ Hard-Won Engineering Lessons & Battle Scars

Building this pipeline required overcoming severe Android kernel, filesystem, and Google Photos constraints:

### 1. The Mount Namespace Trap (`nsenter -t 1 -m --`)
* **Problem:** Mounts executed via standard ADB shell executed inside a private mount namespace. Shell `ls` showed the files, but Google Photos and `sdcardfs` showed 0 files.
* **Solution:** All mounts in `MountHelper.kt` run in the global `init` (PID 1) mount namespace via `nsenter -t 1 -m -- toybox mount -t sdcardfs ... /mnt/runtime/write/emulated/0/DCIM/Camera`.

### 2. The EXIF Timestamp Corruption Trap (Hard Links vs Copies)
* **Problem:** Standard `cp -rp` through Android's `sdcardfs` silently drops filesystem `mtime`. For large 4K files where Google Photos' EXIF parser timed out, Photos fell back to file `mtime` (now "today"), corrupting photo timelines.
* **Solution:** Instantaneous hard links (`os.link()`) on the ext4 partition. Hard links preserve exact timestamps, cost 0ms, and cause zero NAND wear on internal storage.

### 3. Per-File MediaScanner Broadcasts
* **Problem:** Broadcasting directory-level media scans was silently ignored by Android's MediaStore.
* **Solution:** Loop individual file scan broadcasts: `am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file:///storage/emulated/0/DCIM/Camera/filename"`.

### 4. Google Photos `has_upload_permanently_failed` DB Reset
* **Problem:** When an upload failed once, Google Photos set `has_upload_permanently_failed = 1` in `gphotos0.db`, permanently ignoring the file on future runs.
* **Solution:** Reset the flag before starting each chunk: `UPDATE local_media SET has_upload_permanently_failed = 0`.

### 5. Hardware Safety: Ugreen USB-C Dock, VBUS Bypass & Battery Saver
* **Problem:** Lithium-ion battery swelling ("spicy pillow") from continuous 24/7 charging.
* **Solution:** `BatteryLimiter.kt` toggles `/sys/class/power_supply/battery/charging_enabled` to cap charging at 80%. When connected to a Ugreen USB-C Power Delivery Dock, wall power continues powering the SoC, USB HDD, and Gigabit Ethernet via VBUS passthrough without stressing the battery.

---

## 💎 Key System Features

### 1. Metadata Preservation Engine & Sidecar JSON
Preserves both **in-file** (EXIF, GPS, Apple MakerNotes, ICC color profiles) and **out-of-file** (iCloud faces, albums, favorites, descriptions) metadata:
* `metadata.py` exports iCloud DB fields into `.meta.json` sidecar files.
* Uses `exiftool -TagsFromFile` to copy all tags to compressed files.
* Enforces a mandatory **Metadata Verification Gate** comparing original vs. compressed tags before allowing any upload.

### 2. Tiered Quality Compression Matrix (NAS as Vault)
* **NAS = The Vault:** Stores untouched 4K originals permanently.
* **iCloud = Access Copy:** Gradually scaled down as media ages:
  * **0 – 6 Months:** Original (untouched).
  * **6 – 12 Months:** High (1080p HEVC / 3024px photo).
  * **1 – 2 Years:** Medium (720p HEVC / 2048px photo).
  * **2+ Years:** Compact (480p HEVC / 1440px photo).
* Re-compression **always reads from the NAS original** to eliminate compounding generational quality loss. Reclaims 50-75% iCloud space ($84+/year saved).

### 3. 3-Gate Deletion Safety & 7-Day Quarantine
No iCloud original is released until:
1. ✅ **Gate 1:** NAS original SHA-256 hash verified.
2. ✅ **Gate 2:** Google Photos upload verified via Pixel Ktor DB check.
3. ✅ **Gate 3:** Compressed version uploaded to iCloud.
4. ⏳ **Quarantine:** 7-day safety window expires.

### 4. Android App (`PixelBackupManager` v1.2)
* **Ktor REST Server (Port 8080)**: Offers `/api/health`, `/api/stage`, `/api/verify`, `/api/photos/restart`, `/api/mount`, `/api/unmount`.
* **Hardware Safety**: Battery limit (70-80%), battery bypass, CPU thermal pause (>45°C), screen-off wake lock (`keyevent 223`).
- **UI**: Modern Jetpack Compose dark UI with live network, HDD mount, and system health badges.

### 5. Linux Media Orchestrator Web UI (`v2.2`)
* **Dashboard (`http://localhost:8000`)**: Live Pixel health metrics, telemetrics & annual $ savings calculator, interactive settings form, 2FA prompt, single-file iCloud test downloader, and metadata diff comparison sandbox.
* **24/7 Resilience**: `systemd` unit (`media-orchestrator.service`) with auto ADB port forwarding and dynamic Pixel IP auto-discovery.

---

## 📂 Repository Structure

```
pixel-backup-gang/
├── android-app/                   # PixelBackupManager Kotlin Android Studio Project
│   ├── app/src/main/java/com/backupgang/manager/
│   │   ├── MainActivity.kt        # Jetpack Compose UI & Web Connector Card
│   │   ├── service/BackupService.kt # Ktor REST Server & Pipeline Executor
│   │   └── util/                  # BatteryLimiter, MountHelper, BackupState
│   └── build.gradle
├── linux-orchestrator/            # FastAPI Linux Backend & Web UI Command Center
│   ├── main.py                    # FastAPI entrypoint & REST endpoints
│   ├── pipeline.py                # Inbox organizer, chunk pusher & tier scheduler
│   ├── metadata.py                # Exiftool handler & metadata verification gate
│   ├── compression.py             # Tiered ffmpeg/libvips compression engine
│   ├── pixel_client.py            # HTTP client to Pixel Ktor API with ADB fallback
│   ├── icloud_sync.py             # icloudpd download & pyicloud integration
│   ├── database.py                # SQLite schema & settings management
│   ├── media-orchestrator.service # Systemd unit file for 24/7 background operation
│   └── static/index.html          # Obsidian glassmorphism Web UI dashboard
└── apk/
    └── PixelBackupManager-v1.2.apk # Pre-compiled ready-to-flash Android APK
```

---

## 🚀 Quick Start & Installation

### 1. Install Android App on Pixel 1 OG
Connect Pixel via USB / ADB:
```bash
adb install -r apk/PixelBackupManager-v1.2.apk
adb shell am start -n com.backupgang.manager/.MainActivity
```

### 2. Setup Linux Orchestrator
Install dependencies:
```bash
sudo apt-get update && sudo apt-get install -y libimage-exiftool-perl ffmpeg libvips-tools
pip install --break-system-packages fastapi uvicorn requests pyicloud icloudpd pillow pyexiftool
```

Run Orchestrator:
```bash
cd linux-orchestrator
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```
Open **`http://localhost:8000`** in your browser.

### 3. Install 24/7 Systemd Service
```bash
sudo cp linux-orchestrator/media-orchestrator.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now media-orchestrator
```

---

## 📜 License
MIT License © 2026. Built with passion for hardware longevity, data preservation, and cloud cost optimization.
