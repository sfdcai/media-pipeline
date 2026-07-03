import os
import asyncio
from fastapi import FastAPI, BackgroundTasks, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

import database
import pipeline
import pixel_client
import icloud_sync
import metadata
import compression

app = FastAPI(title="Media Lifecycle Command Center", version="2.2.0")

os.makedirs("/root/media_orchestrator/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="/root/media_orchestrator/static"), name="static")

class SettingsModel(BaseModel):
    pixel_ip: str = "192.168.1.198"
    pixel_port: str = "8080"
    icloud_username: str = ""
    icloud_password: str = ""
    nas_inbox_path: str = "/mnt/my_drive/Backup/shares/Amit/Photographs/Inbox"
    nas_sorted_root: str = "/mnt/my_drive/Backup/shares/Amit/Photographs/Sorted"
    nas_staging_path: str = "/mnt/my_drive/_stage"
    tier_high_months: str = "6"
    tier_medium_months: str = "12"
    tier_compact_months: str = "24"
    quarantine_days: str = "7"
    pixel_upload_enabled: str = "true"
    icloud_sync_enabled: str = "true"
    screen_always_active: str = "false"
    battery_saver_enabled: str = "true"
    disable_charging_completely: str = "false"

class TwoFactorModel(BaseModel):
    code: str

class DownloadSingleFileModel(BaseModel):
    filename: str

class MetadataTestModel(BaseModel):
    filepath: str
    target_tier: Optional[str] = "high"

@app.on_event("startup")
async def startup_event():
    database.init_db()
    asyncio.create_task(pipeline.pipeline_loop())

@app.get("/")
async def read_index():
    return FileResponse("/root/media_orchestrator/static/index.html")

@app.get("/api/dashboard")
async def get_dashboard():
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as count FROM media_files")
    total_files = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM media_files WHERE gphotos_synced = 1")
    synced_gphotos = cursor.fetchone()["count"]
    
    cursor.execute("SELECT COUNT(*) as count FROM media_files WHERE icloud_reuploaded = 1")
    reuploaded_icloud = cursor.fetchone()["count"]

    cursor.execute("SELECT current_icloud_tier, COUNT(*) as count, SUM(file_size_bytes) as original_bytes, SUM(COALESCE(icloud_compressed_size, file_size_bytes)) as current_bytes FROM media_files GROUP BY current_icloud_tier")
    tier_rows = cursor.fetchall()
    tier_breakdown = {r["current_icloud_tier"]: {"count": r["count"], "original_bytes": r["original_bytes"] or 0, "current_bytes": r["current_bytes"] or 0} for r in tier_rows}
    
    cursor.execute("SELECT * FROM pipeline_logs ORDER BY id DESC LIMIT 20")
    logs = [dict(r) for r in cursor.fetchall()]
    
    conn.close()
    
    pixel_health = pixel_client.get_health()
    
    return {
        "summary": {
            "total_files": total_files,
            "synced_gphotos": synced_gphotos,
            "reuploaded_icloud": reuploaded_icloud,
        },
        "tier_breakdown": tier_breakdown,
        "pixel_health": pixel_health,
        "recent_logs": logs
    }

@app.get("/api/telemetry")
async def get_telemetry():
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT SUM(file_size_bytes) as total_orig, SUM(COALESCE(icloud_compressed_size, file_size_bytes)) as total_curr FROM media_files")
    row = cursor.fetchone()
    total_orig = row["total_orig"] or 0
    total_curr = row["total_curr"] or 0
    saved_bytes = total_orig - total_curr
    saved_gb = round(saved_bytes / (1024**3), 2)
    
    # Calculate estimated $ saved ($0.03/GB/mo for iCloud tier difference)
    estimated_monthly_savings_usd = round(saved_gb * 0.03, 2)
    
    conn.close()
    return {
        "total_original_bytes": total_orig,
        "total_current_bytes": total_curr,
        "saved_bytes": saved_bytes,
        "saved_gb": saved_gb,
        "estimated_monthly_savings_usd": estimated_monthly_savings_usd,
        "estimated_annual_savings_usd": round(estimated_monthly_savings_usd * 12, 2)
    }

@app.get("/api/settings")
async def get_settings():
    conn = database.get_db_connection()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}

@app.post("/api/settings")
async def update_settings(settings: SettingsModel):
    for k, v in settings.dict().items():
        database.set_setting(k, str(v))
    database.log_event("INFO", "Pipeline settings updated via WebUI.")
    return {"status": "success", "settings": settings.dict()}

@app.post("/api/icloud/auth")
async def auth_icloud():
    user = database.get_setting("icloud_username")
    pwd = database.get_setting("icloud_password")
    if not user or not pwd:
        return {"status": "error", "message": "Username and password must be set in settings first."}
    
    service = icloud_sync.get_pyicloud_session(user, pwd)
    if service and service.requires_2fa:
        return {"status": "requires_2fa", "message": "2FA Code Required. Please enter the 6-digit code from your Apple device."}
    elif service:
        return {"status": "authenticated", "message": "iCloud Session Active"}
    else:
        return {"status": "error", "message": "Authentication failed"}

@app.post("/api/icloud/2fa")
async def submit_2fa(payload: TwoFactorModel):
    res = icloud_sync.submit_2fa_code(payload.code)
    database.log_event("INFO", f"2FA Submission Result: {res['message']}")
    return res

@app.post("/api/test/download_icloud_file")
async def download_single_file(payload: DownloadSingleFileModel):
    inbox = database.get_setting("nas_inbox_path")
    res = icloud_sync.download_single_file_from_icloud(payload.filename, inbox)
    return res

@app.post("/api/test/metadata_compare")
async def test_metadata_compare(payload: MetadataTestModel):
    if not os.path.exists(payload.filepath):
        return {"status": "error", "message": f"File not found: {payload.filepath}"}
        
    temp_out = "/root/media_orchestrator/cache_compressed"
    success, comp_path, report = compression.compress_media_tier(payload.filepath, payload.target_tier, temp_out)
    
    if not success:
        return {"status": "error", "message": "Compression failed", "report": report}
        
    diff = metadata.compare_metadata_side_by_side(payload.filepath, comp_path)
    
    if os.path.exists(comp_path):
        os.remove(comp_path) # Clean up test file
        
    return {
        "status": "success",
        "verification_gate": report,
        "metadata_diff": diff
    }

@app.get("/api/media")
async def get_media(status: str = None, tier: str = None, page: int = 1, limit: int = 50):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM media_files WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    if tier:
        query += " AND current_icloud_tier = ?"
        params.append(tier)
        
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, (page - 1) * limit])
    
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"page": page, "limit": limit, "items": rows}

@app.post("/api/media/{media_id}/exempt")
async def toggle_exemption(media_id: int, exempt: bool, reason: str = "manual"):
    conn = database.get_db_connection()
    conn.execute("UPDATE media_files SET is_exempt = ?, exempt_reason = ? WHERE id = ?", (1 if exempt else 0, reason, media_id))
    conn.commit()
    conn.close()
    return {"status": "success", "media_id": media_id, "is_exempt": exempt}

@app.post("/api/pipeline/trigger_icloud_download")
async def trigger_icloud_download(background_tasks: BackgroundTasks):
    inbox = database.get_setting("nas_inbox_path")
    background_tasks.add_task(icloud_sync.run_icloud_download, inbox)
    return {"status": "triggered", "message": "iCloud download started in background"}

@app.post("/api/pipeline/trigger_pixel_sync")
async def trigger_pixel_sync(background_tasks: BackgroundTasks):
    background_tasks.add_task(pipeline.sync_pending_files_to_pixel, 100)
    return {"status": "triggered", "message": "Pixel sync chunk started"}

@app.post("/api/pipeline/trigger_tier_review")
async def trigger_tier_review(background_tasks: BackgroundTasks):
    background_tasks.add_task(pipeline.process_tiered_compression)
    return {"status": "triggered", "message": "Tier compression review started"}
