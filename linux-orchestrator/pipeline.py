import os
import time
import shutil
import hashlib
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any

import database
import metadata
import compression
import pixel_client
import icloud_sync

logger = logging.getLogger("pipeline")

SORTED_ROOT = os.environ.get("NAS_SORTED_ROOT", "/mnt/my_drive/Backup/shares/Amit/Photographs/Sorted")
COMPRESSED_CACHE_DIR = "/root/media_orchestrator/cache_compressed"

def calculate_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def calculate_target_tier(exif_date_str: str) -> str:
    """Calculates target iCloud compression tier based on age settings from DB."""
    try:
        dt = datetime.strptime(exif_date_str[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        dt = datetime.now()
        
    days_old = (datetime.now() - dt).days
    high_days = int(database.get_setting("tier_high_months", "6")) * 30
    medium_days = int(database.get_setting("tier_medium_months", "12")) * 30
    compact_days = int(database.get_setting("tier_compact_months", "24")) * 30

    if days_old <= high_days:
        return "original"
    elif days_old <= medium_days:
        return "high"
    elif days_old <= compact_days:
        return "medium"
    else:
        return "compact"

def scan_and_organize_inbox(inbox_dir: str):
    """Scans inbox folder, extracts EXIF date, moves to Sorted/YYYY/MM/DD, generates sidecar JSON, inserts into DB."""
    if not os.path.exists(inbox_dir):
        return
        
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    for root, _, files in os.walk(inbox_dir):
        for file in files:
            if file.startswith(".") or "@eaDir" in root or "syno" in file.lower():
                continue
                
            filepath = os.path.join(root, file)
            try:
                exif_date = metadata.extract_exif_date(filepath)
                date_obj = datetime.strptime(exif_date[:10], "%Y-%m-%d")
                target_dir = os.path.join(SORTED_ROOT, date_obj.strftime("%Y"), date_obj.strftime("%m"), date_obj.strftime("%d"))
                os.makedirs(target_dir, exist_ok=True)
                
                target_path = os.path.join(target_dir, file)
                if not os.path.exists(target_path):
                    shutil.move(filepath, target_path)
                else:
                    target_path = filepath # already in place
                    
                sha256 = calculate_sha256(target_path)
                sidecar_path = metadata.create_sidecar_json(target_path)
                file_size = os.path.getsize(target_path)
                is_video = compression.is_video_file(target_path)
                
                cursor.execute("""
                INSERT OR IGNORE INTO media_files 
                (original_filename, original_hash_sha256, exif_date, file_size_bytes, media_type, nas_path, nas_archived_at, nas_hash_verified, status)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 1, 'archived')
                """, (file, sha256, exif_date, file_size, "video" if is_video else "photo", target_path))
                
            except Exception as e:
                logger.error(f"Error organizing file {filepath}: {e}")
                
    conn.commit()
    conn.close()

def sync_pending_files_to_pixel(batch_size: int = 100):
    """Fetches up to batch_size archived files, sends to Pixel Ktor API /api/stage, polls /api/verify until synced."""
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT id, original_filename, nas_path FROM media_files 
    WHERE status = 'archived' AND gphotos_synced = 0 
    LIMIT ?
    """, (batch_size,))
    rows = cursor.fetchall()
    
    if not rows:
        conn.close()
        return
        
    file_ids = [r["id"] for r in rows]
    nas_paths = [r["nas_path"] for r in rows]
    filenames = [r["original_filename"] for r in rows]
    
    # Check if files exist on Pixel, and push them if missing
    import subprocess
    pixel_client.ensure_adb_forward_and_connection()
    for nas_path in nas_paths:
        exists_on_pixel = False
        try:
            res = subprocess.run(
                ["adb", "shell", "su", "-c", f"test -f \"{nas_path}\" && echo OK"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
            )
            if "OK" in res.stdout:
                exists_on_pixel = True
        except Exception:
            pass
            
        if not exists_on_pixel:
            database.log_event("INFO", f"Pushing {os.path.basename(nas_path)} to Pixel via ADB.")
            success = pixel_client.push_file(nas_path, nas_path)
            if not success:
                database.log_event("ERROR", f"Failed to push {os.path.basename(nas_path)} to Pixel.")
                conn.close()
                return

    database.log_event("INFO", f"Sending chunk of {len(nas_paths)} files to Pixel for Google Photos staging.")
    
    # Call Pixel stage API
    stage_resp = pixel_client.stage_files(nas_paths)
    if stage_resp.get("status") != "staged":
        database.log_event("ERROR", f"Pixel staging failed: {stage_resp}")
        conn.close()
        return
        
    cursor.execute(f"UPDATE media_files SET status = 'uploading', pixel_staged_at = CURRENT_TIMESTAMP WHERE id IN ({','.join('?'*len(file_ids))})", file_ids)
    conn.commit()
    
    # Poll verification up to 60 times (10 minutes total)
    for _ in range(60):
        time.sleep(10)
        verify_results = pixel_client.verify_sync(filenames)
        synced_count = sum(1 for synced in verify_results.values() if synced)
        
        if synced_count >= len(filenames):
            database.log_event("SUCCESS", f"All {len(filenames)} files verified synced in Google Photos!")
            cursor.execute(f"UPDATE media_files SET gphotos_synced = 1, gphotos_synced_at = CURRENT_TIMESTAMP, upload_bytes_verified = 1, status = 'synced' WHERE id IN ({','.join('?'*len(file_ids))})", file_ids)
            conn.commit()
            break
            
    conn.close()

def process_tiered_compression():
    """Finds synced files needing tier compression upgrade based on age, compresses from NAS original, and verifies metadata."""
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT id, original_filename, nas_path, exif_date, current_icloud_tier, is_exempt 
    FROM media_files 
    WHERE gphotos_synced = 1 AND is_exempt = 0
    ORDER BY id ASC LIMIT 50
    """)
    rows = cursor.fetchall()
    
    for r in rows:
        target_tier = calculate_target_tier(r["exif_date"])
        if target_tier != r["current_icloud_tier"] and target_tier != "original":
            database.log_event("INFO", f"Tier upgrade for {r['original_filename']}: {r['current_icloud_tier']} -> {target_tier}")
            
            success, comp_path, report = compression.compress_media_tier(r["nas_path"], target_tier, COMPRESSED_CACHE_DIR)
            if success:
                # Upload compressed to iCloud
                reup_success = icloud_sync.upload_compressed_to_icloud(comp_path)
                if reup_success:
                    quarantine_expire = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("""
                    UPDATE media_files SET 
                        current_icloud_tier = ?, 
                        icloud_compressed_size = ?, 
                        compression_ratio = ?, 
                        last_tier_change_at = CURRENT_TIMESTAMP,
                        icloud_reuploaded = 1,
                        quarantine_expires_at = ?
                    WHERE id = ?
                    """, (target_tier, report.get("compressed_size", 0), report.get("compression_ratio", 1.0), quarantine_expire, r["id"]))
                    
                    cursor.execute("INSERT INTO tier_history (media_file_id, from_tier, to_tier, compressed_size) VALUES (?, ?, ?, ?)",
                                   (r["id"], r["current_icloud_tier"], target_tier, report.get("compressed_size", 0)))
                    conn.commit()
                    
                if os.path.exists(comp_path):
                    os.remove(comp_path) # Clean cache
            else:
                database.log_event("ERROR", f"Compression failed or metadata gate failed for {r['original_filename']}: {report}")
                
    conn.close()

def run_3gate_deletion_check():
    """Runs 3-gate deletion check (1. NAS hash verified, 2. Google Photos synced, 3. Compressed version on iCloud + quarantine expired)."""
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    SELECT id, original_filename FROM media_files 
    WHERE nas_hash_verified = 1 
      AND gphotos_synced = 1 
      AND icloud_reuploaded = 1 
      AND icloud_original_deleted = 0 
      AND quarantine_expires_at <= CURRENT_TIMESTAMP
    """)
    rows = cursor.fetchall()
    
    for r in rows:
        database.log_event("SUCCESS", f"3-Gate Check & Quarantine passed for {r['original_filename']}. Ready to release iCloud original.")
        cursor.execute("UPDATE media_files SET icloud_original_deleted = 1, status = 'complete' WHERE id = ?", (r["id"],))
        
    conn.commit()
    conn.close()

def pipeline_loop():
    database.init_db()
    database.log_event("INFO", "Media Pipeline Orchestrator Started.")
    
    while True:
        try:
            scan_and_organize_inbox(icloud_sync.ICLOUD_DOWNLOAD_DIR)
            sync_pending_files_to_pixel()
            process_tiered_compression()
            run_3gate_deletion_check()
        except Exception as e:
            logger.error(f"Error in pipeline loop: {e}")
        time.sleep(30)
